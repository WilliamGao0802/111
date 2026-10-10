"""互动功能区 · 文件区：上传、分类标签、搜索排序、版本管理、下载统计、权限、回收站、分享。"""

from __future__ import annotations

import hashlib
import io
import mimetypes
import secrets
import zipfile
from pathlib import Path

from . import auth, db

ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT / "uploads"
CATEGORIES = ["论文", "数据集", "代码", "课件", "其他"]
VISIBILITIES = {"public": "公开", "login": "仅登录可见", "private": "仅自己可见"}

MAX_FILE_MB = 50          # 单文件大小上限
USER_QUOTA_MB = 500       # 每人总配额
RECYCLE_DAYS = 30         # 回收站保留天数


def _ensure_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def quota_used_mb(uid: int) -> float:
    used = int(db.scalar("SELECT COALESCE(SUM(size),0) FROM files WHERE user_id=? AND deleted=0",
                         (uid,), 0))
    return round(used / 1024 / 1024, 2)


def quota_limit_mb(uid: int) -> int:
    return USER_QUOTA_MB


def guess_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_upload(uid: int, filename: str, data: bytes, category: str = "其他",
                tags: str = "", visibility: str = "public") -> int:
    """保存上传文件。同名文件自动 +1 版本，旧版本标记为非最新。"""
    if not uid:
        raise auth.AuthError("请先登录")
    filename = (Path(filename or "").name).strip()
    if not filename:
        raise auth.AuthError("文件名无效")
    if category not in CATEGORIES:
        category = "其他"
    if visibility not in VISIBILITIES:
        visibility = "public"
    size = len(data or b"")
    if size == 0:
        raise auth.AuthError("文件内容为空")
    if size > MAX_FILE_MB * 1024 * 1024:
        raise auth.AuthError(f"单个文件不能超过 {MAX_FILE_MB} MB（当前 {size/1024/1024:.1f} MB）")
    if quota_used_mb(uid) + size / 1024 / 1024 > USER_QUOTA_MB:
        raise auth.AuthError(f"存储配额已满（上限 {USER_QUOTA_MB} MB，已用 {quota_used_mb(uid)} MB）")

    _ensure_dir()
    ext = Path(filename).suffix
    stored = f"{secrets.token_hex(8)}{ext}"
    (UPLOAD_DIR / stored).write_bytes(data)

    prev = db.query_one(
        "SELECT * FROM files WHERE user_id=? AND filename=? AND is_latest=1 ORDER BY id DESC LIMIT 1",
        (uid, filename),
    )
    version = (int(prev["version"]) + 1) if prev else 1
    root_id = (prev["root_id"] or prev["id"]) if prev else 0
    if prev:
        db.execute("UPDATE files SET is_latest=0 WHERE id=?", (prev["id"],))
    fid = db.execute(
        """INSERT INTO files(user_id,filename,stored_name,category,tags,size,mime,visibility,
                             version,root_id,is_latest,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,1,?)""",
        (uid, filename, stored, category, tags or "", size, guess_mime(filename),
         visibility, version, root_id, db.now_str()),
    )
    if version == 1:
        db.execute("UPDATE files SET root_id=? WHERE id=?", (fid, fid))
    auth.add_points(uid, auth.POINT_RULES["upload"], "上传文件")
    auth.log(uid, "", "upload", f"{filename} v{version} ({size} bytes)")
    return fid


def can_view(f: dict, uid: int) -> bool:
    if not f:
        return False
    if f["visibility"] == "public":
        return True
    if f["visibility"] == "login":
        return bool(uid)
    return f["user_id"] == uid


def list_files(uid: int = 0, category: str = "", keyword: str = "",
               sort: str = "time", only_mine: bool = False,
               include_private: bool = False, limit: int = 100) -> list:
    sql = ("SELECT f.*, u.username, u.nickname, u.avatar FROM files f "
           "LEFT JOIN users u ON u.id=f.user_id WHERE f.deleted=0")
    params: list = []
    if only_mine:
        sql += " AND f.user_id=?"; params.append(uid)
    elif not include_private:
        if uid:
            sql += " AND (f.visibility IN ('public','login') OR f.user_id=?)"; params.append(uid)
        else:
            sql += " AND f.visibility='public'"
    if category:
        sql += " AND f.category=?"; params.append(category)
    if keyword:
        sql += " AND (f.filename LIKE ? OR f.tags LIKE ?)"; params += [f"%{keyword}%"] * 2
    order = {"time": "f.id DESC", "size": "f.size DESC", "downloads": "f.downloads DESC",
             "name": "f.filename ASC"}.get(sort, "f.id DESC")
    sql += f" ORDER BY {order} LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def get_file(fid: int):
    return db.query_one(
        "SELECT f.*, u.username, u.nickname, u.avatar FROM files f "
        "LEFT JOIN users u ON u.id=f.user_id WHERE f.id=?", (fid,))


def file_path(f: dict) -> Path:
    return UPLOAD_DIR / f["stored_name"]


def read_file(fid: int, uid: int = 0) -> bytes:
    f = get_file(fid)
    if not f or f["deleted"]:
        raise auth.AuthError("文件不存在或已删除")
    if not can_view(f, uid):
        raise auth.AuthError("无权访问该文件")
    p = file_path(f)
    if not p.exists():
        raise auth.AuthError("文件已丢失（存储路径不存在）")
    return p.read_bytes()


def register_download(fid: int) -> None:
    db.execute("UPDATE files SET downloads=downloads+1, last_download=? WHERE id=?",
               (db.now_str(), fid))
    auth.log(0, "", "download", f"文件 #{fid}")


def versions(fid: int) -> list:
    f = get_file(fid)
    if not f:
        return []
    root = f["root_id"] or f["id"]
    return db.query(
        "SELECT * FROM files WHERE root_id=? AND user_id=? ORDER BY version DESC", (root, f["user_id"]))


def rollback(fid: int, uid: int) -> None:
    """回滚到指定历史版本：复制该版本内容为新的最新版本。"""
    f = get_file(fid)
    if not f or f["user_id"] != uid:
        raise auth.AuthError("只能回滚自己的文件")
    data = file_path(f).read_bytes()
    save_upload(uid, f["filename"], data, f["category"], f["tags"], f["visibility"])


def delete_file(fid: int, uid: int, is_admin: bool = False) -> None:
    f = get_file(fid)
    if not f:
        return
    if f["user_id"] != uid and not is_admin:
        raise auth.AuthError("只能删除自己的文件")
    db.execute("UPDATE files SET deleted=1, deleted_at=? WHERE id=?", (db.now_str(), fid))


def recycle_bin(uid: int) -> list:
    return db.query("SELECT * FROM files WHERE user_id=? AND deleted=1 ORDER BY deleted_at DESC", (uid,))


def restore_file(fid: int, uid: int) -> None:
    f = get_file(fid)
    if not f or f["user_id"] != uid:
        raise auth.AuthError("只能恢复自己的文件")
    db.execute("UPDATE files SET deleted=0, deleted_at='' WHERE id=?", (fid,))


def purge_expired() -> int:
    """清理回收站中超过 30 天的文件。"""
    cutoff = db.days_ago_str(RECYCLE_DAYS)
    rows = db.query("SELECT * FROM files WHERE deleted=1 AND deleted_at<>'' AND deleted_at < ?", (cutoff,))
    n = 0
    for f in rows:
        p = file_path(f)
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
        db.execute("DELETE FROM files WHERE id=?", (f["id"],))
        n += 1
    return n


def share_link(fid: int) -> str:
    f = get_file(fid)
    if not f:
        raise auth.AuthError("文件不存在")
    token = hashlib.md5(f"{f['id']}-{f['stored_name']}".encode()).hexdigest()[:12]
    return f"?page=files&file={f['id']}&share={token}"


def verify_share(fid: int, token: str) -> bool:
    f = get_file(fid)
    if not f:
        return False
    expect = hashlib.md5(f"{f['id']}-{f['stored_name']}".encode()).hexdigest()[:12]
    return token == expect


def package_zip(fids: list[int], uid: int = 0) -> bytes:
    """批量打包下载。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fid in fids:
            f = get_file(fid)
            if not f or f["deleted"] or not can_view(f, uid):
                continue
            p = file_path(f)
            if p.exists():
                zf.write(p, arcname=f["filename"])
                register_download(fid)
    buf.seek(0)
    return buf.read()


def is_previewable(filename: str) -> str:
    """返回预览类型：image/pdf/markdown/text/code/none。"""
    ext = Path(filename).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in {".md", ".markdown"}:
        return "markdown"
    if ext in {".txt", ".log", ".csv", ".json", ".yaml", ".yml", ".ini", ".cfg"}:
        return "text"
    if ext in {".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".sql",
               ".html", ".css", ".sh", ".r", ".ipynb"}:
        return "code"
    return "none"


def stats() -> dict:
    return {
        "files": int(db.scalar("SELECT COUNT(*) FROM files WHERE deleted=0", (), 0)),
        "size_mb": round(int(db.scalar("SELECT COALESCE(SUM(size),0) FROM files WHERE deleted=0", (), 0)) / 1024 / 1024, 2),
        "downloads": int(db.scalar("SELECT COALESCE(SUM(downloads),0) FROM files WHERE deleted=0", (), 0)),
        "recycled": int(db.scalar("SELECT COUNT(*) FROM files WHERE deleted=1", (), 0)),
    }

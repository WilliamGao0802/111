"""互动功能区 · 文件区：上传、分类标签、搜索排序、在线预览、版本管理、回收站、分享链接。"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import auth, db, files
from ui import common as C


def _upload(uid: int) -> None:
    st.caption(f"单文件上限 {files.MAX_FILE_MB} MB · 每人配额 {files.USER_QUOTA_MB} MB · "
               f"当前已用 {files.quota_used_mb(uid)} MB")
    ups = st.file_uploader("选择文件（可多选）", accept_multiple_files=True, key="up_files")
    c1, c2, c3 = st.columns(3)
    with c1:
        cat = st.selectbox("分类", files.CATEGORIES, key="up_cat")
    with c2:
        tags = st.text_input("标签（逗号分隔）", key="up_tags", placeholder="如：RAG,论文")
    with c3:
        vis = st.selectbox("可见范围", list(files.VISIBILITIES.keys()),
                           format_func=lambda k: files.VISIBILITIES[k], key="up_vis")
    if st.button("开始上传", type="primary", key="up_go"):
        if not ups:
            C.err("请先选择文件")
            return
        okn, errs = 0, []
        for f in ups:
            try:
                files.save_upload(uid, f.name, f.getvalue(), cat, tags, vis)
                okn += 1
            except auth.AuthError as e:
                errs.append(f"{f.name}：{e}")
        if okn:
            C.ok(f"成功上传 {okn} 个文件")
        for e in errs:
            C.err(e)
        if okn:
            st.rerun()


def _preview(fid: int, uid: int) -> None:
    f = files.get_file(fid)
    if not f:
        return
    kind = files.is_previewable(f["filename"])
    if kind == "none":
        st.info("该类型暂不支持在线预览，请下载后查看。")
        return
    try:
        data = files.read_file(fid, uid)
    except auth.AuthError as e:
        C.err(str(e))
        return
    if kind == "image":
        st.image(data, width="stretch")
    elif kind == "markdown":
        st.markdown(data.decode("utf-8", errors="replace"))
    elif kind in ("text", "code"):
        st.code(data.decode("utf-8", errors="replace")[:8000],
                language=Path(f["filename"]).suffix.lstrip(".") or "text")
    elif kind == "pdf":
        try:
            st.pdf(data)
        except Exception:  # noqa: BLE001
            st.info("PDF 预览不可用，请下载查看。")


def _versions_and_actions(f: dict, uid: int) -> None:
    fid = f["id"]
    owner = f["user_id"] == uid
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.download_button("⬇ 下载", files.file_path(f).read_bytes() if files.file_path(f).exists() else b"",
                           file_name=f["filename"], key=f"dl_{fid}", width="stretch")
    with c2:
        if st.button("🔍 预览", key=f"pv_{fid}", width="stretch"):
            st.session_state[f"preview_{fid}"] = not st.session_state.get(f"preview_{fid}", False)
    with c3:
        if C.is_admin() or owner:
            if st.button("🗑 删除", key=f"del_{fid}", width="stretch"):
                files.delete_file(fid, uid, C.is_admin())
                st.rerun()
    with c4:
        if st.button("🔗 分享链接", key=f"sh_{fid}", width="stretch"):
            st.session_state[f"share_{fid}"] = files.share_link(fid)
    if st.session_state.get(f"share_{fid}"):
        st.code(st.session_state[f"share_{fid}"])
    if st.session_state.get(f"preview_{fid}"):
        _preview(fid, uid)

    vs = files.versions(fid) if owner else []
    if len(vs) > 1:
        with st.expander(f"📚 历史版本（{len(vs)} 个）"):
            for v in vs:
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(f"v{v['version']} · {v['size'] / 1024:.1f} KB · "
                                f"{C.rel_time(v['created_at'])}"
                                + ("　**（当前）**" if v["is_latest"] else ""), unsafe_allow_html=True)
                with b:
                    if not v["is_latest"] and st.button("回滚", key=f"rb_{v['id']}", width="stretch"):
                        files.rollback(v["id"], uid)
                        C.ok(f"已回滚到 v{v['version']}（生成新版本）")
                        st.rerun()
    if f["downloads"]:
        st.markdown(f"<div class='bgl-muted'>下载 {f['downloads']} 次 · "
                    f"最近下载 {C.rel_time(f['last_download'])}</div>", unsafe_allow_html=True)


def render() -> None:
    C.hero("FILES", "文件区", "上传与共享学习资料：分类标签、在线预览、版本回滚、回收站、批量下载")
    uid = C.uid()
    stt = files.stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        C.stat("文件总数", stt["files"])
    with c2:
        C.stat("占用空间", f"{stt['size_mb']} MB")
    with c3:
        C.stat("累计下载", stt["downloads"])
    with c4:
        C.stat("回收站", stt["recycled"])

    tabs = st.tabs(["🌐 全部文件", "📂 我的文件", "⬆️ 上传", "♻️ 回收站"])
    with tabs[0]:
        f1, f2, f3 = st.columns([2, 1, 1])
        with f1:
            kw = st.text_input("🔍 搜索文件名或标签", key="fl_kw")
        with f2:
            cat = st.selectbox("分类", ["全部"] + files.CATEGORIES, key="fl_cat")
        with f3:
            sort = st.selectbox("排序", ["最新上传", "文件最大", "下载最多", "文件名"], key="fl_sort")

        rows = files.list_files(uid=uid, category="" if cat == "全部" else cat, keyword=kw,
                                sort={"最新上传": "time", "文件最大": "size",
                                      "下载最多": "downloads", "文件名": "name"}[sort])
        C.section("文件列表", f"共 {len(rows)} 个")
        if not rows:
            C.empty_state("📁", "还没有文件", "切换到「上传」标签分享第一份资料")
        sel = st.multiselect("批量下载（选择文件）", [r["id"] for r in rows],
                             format_func=lambda i: next((r["filename"] for r in rows if r["id"] == i), str(i)),
                             key="fl_zip")
        if sel and st.button("📦 打包下载", key="fl_zip_go"):
            data = files.package_zip(sel, uid)
            st.download_button("⬇ 下载 ZIP", data, file_name="bgl_files.zip",
                               key="fl_zip_dl", width="content")
        for f in rows:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(
                        f"**{C.esc(f['filename'])}** {C.chip(f['category'])}"
                        f"{C.chips(str(f['tags']).split(','), 'gray')}"
                        f"{C.chip(files.VISIBILITIES.get(f['visibility'], ''), 'accent')}"
                        f"{C.chip('v' + str(f['version']), 'gray')}"
                        f"<div class='bgl-muted' style='margin-top:4px'>{f['size'] / 1024:.1f} KB · "
                        f"上传者 {C.esc(f.get('nickname') or f.get('username') or '用户')} · "
                        f"{C.rel_time(f['created_at'])} · 下载 {f['downloads']}</div>",
                        unsafe_allow_html=True)
                with b:
                    st.write("")
                _versions_and_actions(f, uid)

    with tabs[1]:
        if not C.guard(uid, "查看我的文件"):
            return
        rows = files.list_files(uid=uid, only_mine=True, include_private=True, limit=200)
        C.section("我上传的文件", f"共 {len(rows)} 个 · 已用 {files.quota_used_mb(uid)} / "
                                 f"{files.quota_limit_mb(uid)} MB")
        st.progress(min(1.0, files.quota_used_mb(uid) / max(1, files.quota_limit_mb(uid))))
        if not rows:
            C.empty_state("📂", "你还没有上传文件", "去「上传」标签分享你的资料")
        for f in rows:
            with st.container(border=True):
                st.markdown(
                    f"**{C.esc(f['filename'])}** {C.chip(f['category'])}"
                    f"{C.chip(files.VISIBILITIES.get(f['visibility'], ''), 'accent')}"
                    f"{C.chip('v' + str(f['version']), 'gray')}"
                    f"<div class='bgl-muted'>{f['size'] / 1024:.1f} KB · {C.rel_time(f['created_at'])}</div>",
                    unsafe_allow_html=True)
                _versions_and_actions(f, uid)

    with tabs[2]:
        if C.guard(uid, "上传文件"):
            _upload(uid)

    with tabs[3]:
        if not C.guard(uid, "查看回收站"):
            return
        rows = files.recycle_bin(uid)
        C.section("回收站", f"{len(rows)} 个文件 · 删除后 {files.RECYCLE_DAYS} 天内可恢复")
        if not rows:
            C.empty_state("♻️", "回收站是空的", "删除的文件会在这里暂存")
        for f in rows:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(f"**{C.esc(f['filename'])}**"
                                f"<div class='bgl-muted'>删除于 {C.rel_time(f['deleted_at'])}</div>",
                                unsafe_allow_html=True)
                with b:
                    if st.button("恢复", key=f"rs_{f['id']}", width="stretch"):
                        files.restore_file(f["id"], uid)
                        st.rerun()
        if st.button("🧹 清理过期待删除文件", key="purge"):
            n = files.purge_expired()
            C.ok(f"已清理 {n} 个超过 {files.RECYCLE_DAYS} 天的文件")

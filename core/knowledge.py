"""知识点讲解：按模块组织的 AI 知识卡（讲解 + 公式 + 代码 + 难度 + 关联课程）。"""

from __future__ import annotations

from . import db

MODULES = ["大模型基础", "提示词工程", "微调与对齐", "RAG 与向量检索", "AI 应用开发", "评估与安全"]
DIFFICULTIES = ["入门", "进阶", "高阶"]


def list_modules() -> list:
    rows = db.query("SELECT module, COUNT(*) AS n FROM knowledge GROUP BY module")
    stat = {r["module"]: r["n"] for r in rows}
    return [{"name": m, "count": stat.get(m, 0)} for m in MODULES]


def list_knowledge(module: str = "", keyword: str = "", difficulty: str = "", limit: int = 200) -> list:
    sql = "SELECT * FROM knowledge WHERE 1=1"
    params: list = []
    if module:
        sql += " AND module=?"; params.append(module)
    if difficulty:
        sql += " AND difficulty=?"; params.append(difficulty)
    if keyword:
        sql += " AND (title LIKE ? OR summary LIKE ? OR body LIKE ?)"
        params += [f"%{keyword}%"] * 3
    sql += " ORDER BY module, order_no, id LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def get_knowledge(kid: int, count_view: bool = True):
    row = db.query_one("SELECT * FROM knowledge WHERE id=?", (kid,))
    if row and count_view:
        db.execute("UPDATE knowledge SET views=views+1 WHERE id=?", (kid,))
        row["views"] = row["views"] + 1
    return row


def related(kid: int, module: str, limit: int = 5) -> list:
    return db.query("SELECT id,title,difficulty FROM knowledge WHERE id<>? AND module=? "
                    "ORDER BY order_no LIMIT ?", (kid, module, limit))


def add_knowledge(module, title, summary, body, formula="", code="", difficulty="入门") -> int:
    order = int(db.scalar("SELECT COALESCE(MAX(order_no),0)+1 FROM knowledge WHERE module=?",
                          (module,), 1))
    if difficulty not in DIFFICULTIES:
        difficulty = "入门"
    return db.execute(
        """INSERT INTO knowledge(module,title,summary,body,formula,code,difficulty,order_no,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (module, title, summary, body, formula or "", code or "", difficulty, order, db.now_str()),
    )


def progress_of(uid: int) -> dict:
    """按模块统计该用户已阅读比例（用于学习进度提示）。"""
    total = {}
    for r in db.query("SELECT module, COUNT(*) AS n FROM knowledge GROUP BY module"):
        total[r["module"]] = r["n"]
    return total


def counts() -> dict:
    return {
        "total": int(db.scalar("SELECT COUNT(*) FROM knowledge", (), 0)),
        "modules": len(MODULES),
        "views": int(db.scalar("SELECT COALESCE(SUM(views),0) FROM knowledge", (), 0)),
    }

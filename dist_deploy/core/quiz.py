"""练习测评：题库、练习模式、考试模式、自动评分、错题本、成绩记录。"""

from __future__ import annotations

import json
import random
from datetime import datetime

from . import auth, db


def list_questions(module: str = "", qtype: str = "", difficulty: str = "",
                   keyword: str = "", limit: int = 200) -> list:
    sql = "SELECT * FROM questions WHERE 1=1"
    params: list = []
    if module:
        sql += " AND module=?"; params.append(module)
    if qtype:
        sql += " AND qtype=?"; params.append(qtype)
    if difficulty:
        sql += " AND difficulty=?"; params.append(difficulty)
    if keyword:
        sql += " AND stem LIKE ?"; params.append(f"%{keyword}%")
    sql += " ORDER BY module, id LIMIT ?"
    params.append(limit)
    rows = db.query(sql, tuple(params))
    for r in rows:
        r["options"] = _loads(r["options"])
        r["answers"] = split_answer(r["answer"], r["qtype"])
    return rows


def _loads(s):
    try:
        return json.loads(s or "[]")
    except Exception:
        return []


def split_answer(answer: str, qtype: str) -> list:
    if qtype == "multi":
        return [x for x in str(answer or "").replace("，", ",").split(",") if x]
    return [str(answer or "")]


def get_question(qid: int):
    r = db.query_one("SELECT * FROM questions WHERE id=?", (qid,))
    if r:
        r["options"] = _loads(r["options"])
        r["answers"] = split_answer(r["answer"], r["qtype"])
    return r


def modules() -> list:
    return [r["module"] for r in db.query("SELECT DISTINCT module FROM questions ORDER BY module")]


def stats() -> dict:
    return {
        "total": int(db.scalar("SELECT COUNT(*) FROM questions", (), 0)),
        "modules": len(modules()),
        "single": int(db.scalar("SELECT COUNT(*) FROM questions WHERE qtype='single'", (), 0)),
        "multi": int(db.scalar("SELECT COUNT(*) FROM questions WHERE qtype='multi'", (), 0)),
        "judge": int(db.scalar("SELECT COUNT(*) FROM questions WHERE qtype='judge'", (), 0)),
    }


def draw(module: str = "", count: int = 10, difficulty: str = "", qtype: str = "") -> list:
    pool = list_questions(module=module, difficulty=difficulty, qtype=qtype, limit=500)
    if not pool:
        return []
    count = min(count, len(pool))
    return random.sample(pool, count)


def draw_smart(uid: int, module: str = "", count: int = 10, difficulty: str = "") -> list:
    """智能组卷：优先抽错题本中的题（重做巩固），不足再随机补。"""
    wrong_ids = [r["question_id"] for r in db.query(
        """SELECT w.question_id FROM wrong_book w JOIN questions q ON q.id=w.question_id
           WHERE w.user_id=? AND (?='' OR q.module=?) ORDER BY w.times DESC LIMIT ?""",
        (uid, module, module, count))]
    picked = []
    for qid in wrong_ids[: max(1, count // 2)]:
        q = get_question(qid)
        if q:
            picked.append(q)
    if len(picked) < count:
        seen = {q["id"] for q in picked}
        pool = [q for q in list_questions(module=module, difficulty=difficulty, limit=500)
                if q["id"] not in seen]
        random.shuffle(pool)
        picked += pool[: count - len(picked)]
    return picked[:count]


def grade(question: dict, user_answer) -> bool:
    """单题判分。user_answer 可为 str 或 list。"""
    qtype = question["qtype"]
    correct = question["answers"]
    if qtype == "multi":
        ua = user_answer if isinstance(user_answer, list) else [str(user_answer)]
        return sorted(str(x) for x in ua) == sorted(str(x) for x in correct)
    ua = user_answer[0] if isinstance(user_answer, list) and user_answer else str(user_answer or "")
    return str(ua).strip() == str(correct[0]).strip()


def submit(uid: int, mode: str, module: str, questions: list, answers: dict, duration: int = 0) -> dict:
    """交卷：计算得分、写成绩记录、维护错题本。"""
    if not uid:
        raise auth.AuthError("请先登录后参加测评")
    total = len(questions)
    correct = 0
    detail = []
    for q in questions:
        ua = answers.get(str(q["id"]))
        ok = grade(q, ua)
        if ok:
            correct += 1
        else:
            _add_wrong(uid, q["id"])
        detail.append({"qid": q["id"], "stem": q["stem"], "your": ua,
                       "correct": q["answers"], "ok": ok, "analysis": q.get("analysis", "")})
    score = round(correct / total * 100, 1) if total else 0.0
    rid = db.execute(
        """INSERT INTO quiz_records(user_id,mode,module,total,correct,score,detail,duration,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (uid, mode, module, total, correct, score, json.dumps(detail, ensure_ascii=False),
         int(duration or 0), db.now_str()),
    )
    auth.add_points(uid, 3 if mode == "practice" else 8, "完成测评")
    auth.log(uid, "", "quiz_submit", f"{mode} {score}分 ({correct}/{total})")
    return {"record_id": rid, "total": total, "correct": correct, "score": score, "detail": detail}


def _add_wrong(uid: int, qid: int) -> None:
    db.execute(
        """INSERT INTO wrong_book(user_id,question_id,times,last_at) VALUES(?,?,1,?)
           ON CONFLICT(user_id,question_id) DO UPDATE SET times=wrong_book.times+1,
                                                          last_at=excluded.last_at""",
        (uid, qid, db.now_str()),
    )


def remove_wrong(uid: int, qid: int) -> None:
    db.execute("DELETE FROM wrong_book WHERE user_id=? AND question_id=?", (uid, qid))


def wrong_book(uid: int) -> list:
    rows = db.query(
        """SELECT w.*, q.stem, q.module, q.qtype, q.difficulty FROM wrong_book w
           JOIN questions q ON q.id=w.question_id WHERE w.user_id=?
           ORDER BY w.times DESC, w.last_at DESC""", (uid,))
    return rows


def my_records(uid: int, limit: int = 50) -> list:
    return db.query("SELECT * FROM quiz_records WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))


def get_record(rid: int):
    r = db.query_one("SELECT * FROM quiz_records WHERE id=?", (rid,))
    if r:
        r["detail"] = _loads(r["detail"])
    return r


def module_accuracy(uid: int) -> list:
    """各模块正确率（用于薄弱点分析）。"""
    out = []
    for m in modules():
        recs = db.query("SELECT total, correct FROM quiz_records WHERE user_id=? AND module=?",
                        (uid, m))
        if not recs:
            continue
        t = sum(r["total"] for r in recs)
        c = sum(r["correct"] for r in recs)
        out.append({"module": m, "accuracy": round(c / t * 100, 1) if t else 0.0, "total": t})
    out.sort(key=lambda x: x["accuracy"])
    return out


def add_question(module, qtype, stem, options, answer, analysis="", difficulty="入门") -> int:
    return db.execute(
        """INSERT INTO questions(module,qtype,stem,options,answer,analysis,difficulty,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (module, qtype, stem, json.dumps(options, ensure_ascii=False), answer, analysis,
         difficulty, db.now_str()),
    )

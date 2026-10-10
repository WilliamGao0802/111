"""练习测评：练习模式 / 考试模式 / 错题本 / 成绩记录 / 薄弱点分析。"""

from __future__ import annotations

import time
from datetime import datetime

import streamlit as st

from core import quiz
from ui import common as C

LETTERS = "ABCDEFGH"


def _question_widget(q: dict, idx: int, prefix: str):
    st.markdown(
        f"<div style='font-weight:600;margin-bottom:4px'>{idx + 1}. {C.esc(q['stem'])}</div>"
        f"<div style='margin-bottom:8px'>{C.chip(q['module'], 'gray')}{C.chip(q['difficulty'], 'warn')}"
        f"{C.chip({'single': '单选', 'multi': '多选', 'judge': '判断', 'blank': '填空'}.get(q['qtype'], q['qtype']), 'accent')}</div>",
        unsafe_allow_html=True)
    key = f"{prefix}_{q['id']}"
    opts = q["options"] or []
    if q["qtype"] == "multi":
        labels = [f"{LETTERS[i]}. {o}" for i, o in enumerate(opts)]
        picked = st.multiselect("选择所有正确项", labels, key=key, label_visibility="collapsed")
        return [p.split(".")[0] for p in picked]
    if q["qtype"] == "blank":
        return st.text_input("填写答案", key=key, label_visibility="collapsed")
    labels = [f"{LETTERS[i]}. {o}" for i, o in enumerate(opts)]
    pick = st.radio("选择答案", labels, key=key, index=None, label_visibility="collapsed")
    return pick.split(".")[0] if pick else ""


def _result_block(res: dict, questions: list) -> None:
    score = res["score"]
    correct = res["correct"]  # 先取值再进 f-string：表达式里复用同类引号在 3.12 以下会 SyntaxError
    color = "ok" if score >= 80 else ("warn" if score >= 60 else "danger")
    C.section("测评结果", f"得分 {score} 分 · 答对 {correct} / {res['total']} 题")
    st.markdown(f"<div style='margin-bottom:10px'>{C.chip(f'{score} 分', color)}"
                f"{C.chip(f'答对 {correct} 题', 'gray')}</div>", unsafe_allow_html=True)
    for i, d in enumerate(res["detail"]):
        icon = "✅" if d["ok"] else "❌"
        with st.expander(f"{icon} 第 {i + 1} 题：{d['stem'][:48]}"):
            st.markdown(f"**你的答案**：{C.esc(d['your'] if d['your'] else '（未作答）')}")
            st.markdown(f"**正确答案**：{C.esc('、'.join(map(str, d['correct'])))}")
            st.markdown(f"**解析**：{C.esc(d['analysis'] or '暂无解析')}")


def _practice(uid: int) -> None:
    st.caption("练习模式：随时提交、即时看解析，答错的题自动进入错题本。")
    c1, c2, c3 = st.columns(3)
    with c1:
        module = st.selectbox("知识模块", ["全部"] + quiz.modules(), key="qz_mod")
    with c2:
        count = st.slider("题目数量", 3, 20, 5, key="qz_cnt")
    with c3:
        mode_smart = st.toggle("优先重练错题", value=True, key="qz_smart")

    if st.button("生成练习", type="primary", key="qz_start"):
        if mode_smart and uid:
            qs = quiz.draw_smart(uid, module="" if module == "全部" else module, count=count)
        else:
            qs = quiz.draw(module="" if module == "全部" else module, count=count)
        if not qs:
            C.err("题库暂无匹配题目")
            return
        st.session_state.quiz_session = {
            "mode": "practice", "ids": [q["id"] for q in qs],
            "module": module, "started": time.time(), "submitted": None,
        }
        st.rerun()

    sess = st.session_state.get("quiz_session")
    if not sess or sess.get("mode") != "practice":
        C.empty_state("✍️", "还没有进行中的练习", "选择模块与题量后点击「生成练习」")
        return

    qs = [quiz.get_question(i) for i in sess["ids"]]
    qs = [q for q in qs if q]
    if sess.get("submitted") is not None:
        _result_block(sess["submitted"], qs)
        if st.button("再来一组", key="qz_again"):
            st.session_state.quiz_session = None
            st.rerun()
        return

    C.divider()
    with st.form("practice_form"):
        answers = {}
        for i, q in enumerate(qs):
            answers[str(q["id"])] = _question_widget(q, i, "pr")
            st.markdown("<hr class='bgl-divider'/>", unsafe_allow_html=True)
        done = st.form_submit_button("提交并查看解析", type="primary", width="stretch")
    if done:
        try:
            res = quiz.submit(uid, "practice", sess["module"], qs, answers,
                              duration=int(time.time() - sess["started"]))
            sess["submitted"] = res
            st.rerun()
        except Exception as e:  # noqa: BLE001
            C.err(str(e))


def _exam(uid: int) -> None:
    st.caption("考试模式：固定 10 题，交卷后一次性公布成绩与解析。")
    c1, c2 = st.columns(2)
    with c1:
        module = st.selectbox("知识模块", ["全部"] + quiz.modules(), key="ex_mod")
    with c2:
        count = st.slider("题目数量", 5, 20, 10, key="ex_cnt")
    if st.button("开始考试", type="primary", key="ex_start"):
        qs = quiz.draw(module="" if module == "全部" else module, count=count)
        if not qs:
            C.err("题库暂无匹配题目")
            return
        st.session_state.quiz_session = {
            "mode": "exam", "ids": [q["id"] for q in qs],
            "module": module, "started": time.time(), "submitted": None,
        }
        st.rerun()

    sess = st.session_state.get("quiz_session")
    if not sess or sess.get("mode") != "exam":
        C.empty_state("🎯", "还没有进行中的考试", "选择模块后点击「开始考试」")
        return
    qs = [q for q in (quiz.get_question(i) for i in sess["ids"]) if q]
    if sess.get("submitted") is not None:
        _result_block(sess["submitted"], qs)
        if st.button("结束本次考试", key="ex_done"):
            st.session_state.quiz_session = None
            st.rerun()
        return
    elapsed = int(time.time() - sess["started"])
    st.markdown(f"{C.chip(f'已用时 {elapsed // 60} 分 {elapsed % 60} 秒', 'gray')}"
                f"{C.chip(f'共 {len(qs)} 题', 'gray')}", unsafe_allow_html=True)
    with st.form("exam_form"):
        answers = {}
        for i, q in enumerate(qs):
            answers[str(q["id"])] = _question_widget(q, i, "ex")
            st.markdown("<hr class='bgl-divider'/>", unsafe_allow_html=True)
        done = st.form_submit_button("交卷", type="primary", width="stretch")
    if done:
        res = quiz.submit(uid, "exam", sess["module"], qs, answers, duration=elapsed)
        sess["submitted"] = res
        st.rerun()


def _wrongbook(uid: int) -> None:
    rows = quiz.wrong_book(uid)
    C.section("错题本", f"累计 {len(rows)} 道错题，按错误次数排序")
    if not rows:
        C.empty_state("🎉", "错题本是空的", "继续保持，或者去做一组练习")
        return
    for r in rows:
        times = r["times"]  # 先取值再进 f-string：表达式里复用同类引号在 3.12 以下会 SyntaxError
        with st.container(border=True):
            a, b = st.columns([4, 1])
            with a:
                st.markdown(f"**{C.esc(r['stem'])}** {C.chip(r['module'], 'gray')}"
                            f"{C.chip(f'错 {times} 次', 'danger')}", unsafe_allow_html=True)
            with b:
                if st.button("已掌握", key=f"wb_{r['question_id']}", width="stretch"):
                    quiz.remove_wrong(uid, r["question_id"])
                    st.rerun()
    if st.button("用错题重练一组", type="primary", key="wb_redo"):
        qs = quiz.draw_smart(uid, count=min(10, max(3, len(rows))))
        st.session_state.quiz_session = {"mode": "practice", "ids": [q["id"] for q in qs],
                                         "module": "错题重练", "started": time.time(), "submitted": None}
        st.rerun()


def _records(uid: int) -> None:
    rows = quiz.my_records(uid)
    C.section("成绩记录", f"共 {len(rows)} 条")
    if not rows:
        C.empty_state("📄", "还没有测评记录", "完成一次练习或考试后会显示在这里")
        return
    import altair as alt
    import pandas as pd
    df = pd.DataFrame([{"时间": r["created_at"][:16], "得分": r["score"], "模式": r["mode"],
                        "模块": r["module"]} for r in rows][::-1])
    chart = (alt.Chart(df).mark_area(opacity=0.45, line=True)
             .encode(x=alt.X("时间:N", sort=None, title=""), y=alt.Y("得分:Q", scale=alt.Scale(domain=[0, 100])))
             .properties(height=200))
    st.altair_chart(chart, width="stretch")
    st.dataframe(df.iloc[::-1], width="stretch", hide_index=True)


def _weakness(uid: int) -> None:
    import altair as alt
    import pandas as pd
    rows = quiz.module_accuracy(uid)
    C.section("薄弱点分析", "按各模块正确率排序，越低越需要加强")
    if not rows:
        C.empty_state("📊", "数据还不够", "完成几次测评后就能看到强弱项分析")
        return
    df = pd.DataFrame(rows)
    chart = (alt.Chart(df).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6)
             .encode(x=alt.X("accuracy:Q", title="正确率 (%)", scale=alt.Scale(domain=[0, 100])),
                     y=alt.Y("module:N", sort="x", title=""),
                     color=alt.Color("accuracy:Q", scale=alt.Scale(scheme="redyellowgreen"), legend=None))
             .properties(height=max(160, len(rows) * 34)))
    st.altair_chart(chart, width="stretch")
    worst = rows[0]
    C.note(f"建议优先复习 <b>{C.esc(worst['module'])}</b>（正确率 {worst['accuracy']}%），"
           f"可前往「知识点讲解」查看该模块内容。")
    if st.button("去复习这个模块", key="weak_go"):
        C.goto("knowledge", kb_mod=worst["module"])


def render() -> None:
    C.hero("ASSESSMENT", "练习测评", "练习模式巩固、考试模式检验、错题本智能重练、薄弱点可视化")
    s = quiz.stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        C.stat("题库总量", s["total"])
    with c2:
        C.stat("单选题", s["single"])
    with c3:
        C.stat("多选题", s["multi"])
    with c4:
        C.stat("判断题", s["judge"])

    uid = C.uid()
    tabs = st.tabs(["✍️ 练习模式", "🎯 考试模式", "📕 错题本", "📄 成绩记录", "📊 薄弱点分析"])
    with tabs[0]:
        _practice(uid)
    with tabs[1]:
        _exam(uid)
    with tabs[2]:
        if C.guard(uid, "查看错题本"):
            _wrongbook(uid)
    with tabs[3]:
        if C.guard(uid, "查看成绩记录"):
            _records(uid)
    with tabs[4]:
        if C.guard(uid, "查看薄弱点分析"):
            _weakness(uid)

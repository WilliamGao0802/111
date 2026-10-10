"""我的学习：已购课程、学习进度、结业证书、学习统计、有效期提醒。"""

from __future__ import annotations

import streamlit as st

from core import courses, db, quiz
from ui import common as C


def render() -> None:
    uid = C.uid()
    if not C.guard(uid, "查看我的学习"):
        return
    C.hero("MY LEARNING", "我的学习", "已购课程 · 学习进度 · 结业证书 · 学习统计")

    mine = courses.my_courses(uid)
    done = [e for e in mine if e["completed"]]
    avg = round(sum(float(e["progress"]) for e in mine) / len(mine), 1) if mine else 0.0
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        C.stat("已购课程", len(mine))
    with c2:
        C.stat("已完成", len(done))
    with c3:
        C.stat("平均进度", f"{avg}%")
    with c4:
        C.stat("证书", len([e for e in mine if e["certificate_code"]]))

    tabs = st.tabs(["📚 我的课程", "📈 学习统计", "🎓 我的证书"])
    with tabs[0]:
        if not mine:
            C.empty_state("📚", "还没有购买课程", "去「课程商城」或「AI 课程学习」看看")
            if st.button("去选购课程", type="primary", key="go_store"):
                C.goto("learn")
        for e in mine:
            expired = courses.is_expired(e)
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(
                        f"<b style='font-size:15px'>{C.esc(e['title'])}</b> {C.chip(e['category'])}"
                        f"{C.chip('已完成', 'ok') if e['completed'] else C.chip('学习中', 'warn')}"
                        f"{C.chip('已到期', 'danger') if expired else ''}"
                        f"<div class='bgl-muted' style='margin-top:5px'>"
                        f"{'永久有效' if not e['validity_days'] else '有效期至 ' + C.esc((e['expires_at'] or '')[:10])}"
                        f" · 购买于 {C.rel_time(e['created_at'])}</div>", unsafe_allow_html=True)
                    st.progress(min(1.0, float(e["progress"]) / 100),
                                text=f"学习进度 {e['progress']:.0f}%"
                                     + (f" · 证书 {e['certificate_code']}" if e["certificate_code"] else ""))
                with b:
                    if not expired:
                        if st.button("继续学习", key=f"mygo_{e['course_id']}", width="stretch",
                                     type="primary"):
                            C.goto("learn", sel_course=e["course_id"])
                    else:
                        if st.button("续费", key=f"myrenew_{e['course_id']}", width="stretch"):
                            C.goto("learn", sel_course=e["course_id"])
                    if st.button("评价课程", key=f"myrev_{e['course_id']}", width="stretch"):
                        C.goto("learn", sel_course=e["course_id"])
                # 问答与评价摘要
                with st.expander("课程问答 / 我的评价"):
                    qa = courses.course_qa(e["course_id"])[:5]
                    if not qa:
                        st.caption("暂无问答，可前往课程详情页提问。")
                    for q in qa:
                        st.markdown(f"**Q：** {C.esc(q['question'])}"
                                    + (f"<br/>**A：** {C.esc(q['answer'])}" if q.get("answer")
                                       else "<br/><span class='bgl-muted'>待讲师回复</span>"),
                                    unsafe_allow_html=True)
                    myrev = db.query_one("SELECT * FROM course_reviews WHERE user_id=? AND course_id=?",
                                         (uid, e["course_id"]))
                    if myrev:
                        st.markdown(f"我的评价：{C.chip('★' * int(myrev['rating']), 'warn')} "
                                    f"{C.esc(myrev['content'])}", unsafe_allow_html=True)

    with tabs[1]:
        recs = quiz.my_records(uid, 100)
        dbq = quiz.module_accuracy(uid)
        c1, c2 = st.columns(2)
        with c1:
            C.section("测评统计", "")
            if recs:
                import pandas as pd
                df = pd.DataFrame([{"时间": r["created_at"][:10], "得分": r["score"]} for r in recs][::-1])
                import altair as alt
                chart = (alt.Chart(df).mark_line(point=True)
                         .encode(x=alt.X("时间:N", sort=None), y=alt.Y("得分:Q", scale=alt.Scale(domain=[0, 100])))
                         .properties(height=240))
                st.altair_chart(chart, width="stretch")
            else:
                C.empty_state("📈", "还没有测评记录", "去「练习测评」做一组题吧")
        with c2:
            C.section("学习行为", "")
            from core import users as users_mod
            sc = users_mod.stat_counts(uid)
            for k, label in [("posts", "发帖"), ("liked", "点赞"), ("following", "关注"),
                             ("followers", "粉丝"), ("files", "上传文件"), ("orders", "订单")]:
                st.markdown(f"<div class='bgl-card' style='padding:9px 14px;margin-bottom:7px'>"
                            f"<b>{sc[k]}</b> <span class='bgl-muted'>{label}</span></div>",
                            unsafe_allow_html=True)
            wb = quiz.wrong_book(uid)
            C.note(f"错题本中有 <b>{len(wb)}</b> 道题待复习。")
            if wb and st.button("去重练错题", key="ml_wrong"):
                C.goto("quiz")

    with tabs[2]:
        certs = [e for e in mine if e["certificate_code"]]
        if not certs:
            C.empty_state("🎓", "还没有结业证书", "完成一门课程的全部课时即可获得")
        for e in certs:
            st.markdown(
                f"<div class='bgl-card' style='text-align:center;padding:26px;"
                f"background:linear-gradient(135deg,var(--bgl-primary-soft),var(--bgl-surface))'>"
                f"<div style='font-size:34px'>🏅</div>"
                f"<div style='font-size:18px;font-weight:700;margin:8px 0'>结业证书</div>"
                f"<div>{C.esc(e['title'])}</div>"
                f"<div class='bgl-muted' style='margin-top:8px'>证书编号 {C.esc(e['certificate_code'])}</div>"
                f"<div class='bgl-muted'>颁发于 {C.esc(e['created_at'][:10])}</div></div>",
                unsafe_allow_html=True)
            st.download_button("⬇ 下载证书信息", 
                               f"BGL 结业证书\n课程：{e['title']}\n证书编号：{e['certificate_code']}\n"
                               f"学员：{C.current_user().get('nickname') or C.current_user().get('username')}\n"
                               f"颁发日期：{e['created_at'][:10]}\n".encode("utf-8"),
                               file_name=f"certificate_{e['course_id']}.txt", key=f"cert_{e['course_id']}")

"""首页仪表盘：个人数据概览 + 推荐课程 + 热门直播 + 最新新闻 + 排行榜。"""

from __future__ import annotations

import streamlit as st

from core import auth, courses, db, knowledge, live, news, notify, quiz, users
from ui import common as C


def render() -> None:
    u = C.current_user()
    uid = C.uid()

    if uid:
        st_txt = f"欢迎回来，{u.get('nickname') or u.get('username')}"
    else:
        st_txt = "开始你的 AI 学习之旅"
    C.hero("BGL · AI LEARNING PLATFORM", st_txt,
           "AI 课程学习 · 知识点讲解 · 练习测评 · AI 新闻 · 讨论社区 · 直播课堂 · 网课交易")

    # ---------------- 个人数据概览 / 平台概览 ----------------
    if uid:
        sc = users.stat_counts(uid)
        uu = auth.get_user(uid)
        e_courses = courses.my_courses(uid)
        avg_progress = round(sum(float(e["progress"]) for e in e_courses) / len(e_courses), 1) if e_courses else 0.0
        recs = quiz.my_records(uid, 20)
        avg_score = round(sum(r["score"] for r in recs) / len(recs), 1) if recs else 0.0
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            C.stat("积分", uu["points"], f"Lv.{uu['level']} {auth.level_title(uu['level'])}")
        with c2:
            C.stat("已购课程", sc["courses"])
        with c3:
            C.stat("平均学习进度", f"{avg_progress}%")
        with c4:
            C.stat("测评平均分", f"{avg_score}")
        with c5:
            C.stat("关注 / 粉丝", f"{sc['following']} / {sc['followers']}")
    else:
        k = knowledge.counts()
        q = quiz.stats()
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            C.stat("注册用户", f"{auth.user_count()} / {auth.MAX_USERS}")
        with c2:
            C.stat("在售课程", len(courses.list_courses(limit=200)))
        with c3:
            C.stat("知识点", k["total"])
        with c4:
            C.stat("测评题库", q["total"])
        with c5:
            C.stat("今日新闻", len(news.list_news(limit=200)))

    # ---------------- 继续学习 ----------------
    if uid:
        my = [e for e in courses.my_courses(uid) if not e["completed"]]
        if my:
            C.section("继续学习", "接着上次的进度继续")
            cols = st.columns(3)
            for i, e in enumerate(my[:3]):
                with cols[i % 3]:
                    st.markdown(
                        f"""<div class="bgl-card"><h4>{C.esc(e['title'])}</h4>
                        <p>{C.esc(e['category'])} · 进度 {e['progress']:.0f}%</p></div>""",
                        unsafe_allow_html=True)
                    if st.button("继续学习 →", key=f"dash_go_{e['course_id']}", width="stretch"):
                        C.goto("learn", sel_course=e["course_id"])

    # ---------------- 推荐课程 ----------------
    left, right = st.columns([3, 2])
    with left:
        C.section("推荐课程", "按销量与评分排序")
        for c in courses.list_courses(sort="sales", limit=4):
            with st.container(border=True):
                a, b = st.columns([3, 1])
                with a:
                    st.markdown(
                        f"**{C.esc(c['title'])}**  {C.chip(c['category'])}"
                        f"{C.chip(courses.CTYPES.get(c['ctype'], c['ctype']), 'gray')}",
                        unsafe_allow_html=True)
                    st.markdown(
                        f"<div class='bgl-muted'>{C.esc((c['intro'] or '')[:70])}… · 讲师 "
                        f"{C.esc(c.get('instructor_nick') or '')} · 评分 {c['rating'] or '暂无'} · {c['sales']} 人已学</div>",
                        unsafe_allow_html=True)
                with b:
                    st.markdown(f"<div style='text-align:right'>{C.price_html(c['price'], c['original_price'])}</div>",
                                unsafe_allow_html=True)
                    if st.button("查看详情", key=f"dash_c_{c['id']}", width="stretch"):
                        C.goto("learn", sel_course=c["id"])

        C.section("最新 AI 新闻", "近一年重要进展")
        for n in news.list_news(sort="time", limit=4):
            with st.container(border=True):
                st.markdown(
                    f"**{C.esc(n['title'])}** {C.chip(n['category'])}"
                    f"<div class='bgl-muted'>{C.esc(n['summary'][:80])}…</div>"
                    f"<div class='bgl-muted'>{C.esc(n['publish_time'][:16])} · {C.esc(n['source'])}</div>",
                    unsafe_allow_html=True)
                if st.button("阅读全文", key=f"dash_n_{n['id']}"):
                    C.goto("news", sel_news=n["id"])

    with right:
        C.section("热门直播", "")
        for l in live.list_lives(limit=4):
            status_map = {"live": ("直播中", "danger"), "upcoming": ("即将开播", ""),
                          "replay": ("回放中", "ok"), "ended": ("已结束", "gray")}
            label, kind = status_map.get(l["status"], ("", "gray"))
            with st.container(border=True):
                st.markdown(
                    f"**{C.esc(l['title'])}** {C.chip(label, kind)}"
                    f"<div class='bgl-muted'>{C.esc(l.get('instructor_nick') or '')} · "
                    f"{C.esc(l['start_at'][:16])} · 在线 {l['online_count']}</div>",
                    unsafe_allow_html=True)
                if st.button("进入直播间", key=f"dash_l_{l['id']}", width="stretch"):
                    C.goto("live", sel_live=l["id"])

        C.section("知识模块", "")
        for m in knowledge.list_modules():
            st.markdown(
                f"<div class='bgl-card' style='padding:11px 14px;margin-bottom:8px'>"
                f"<b>{C.esc(m['name'])}</b> <span class='bgl-muted'>· {m['count']} 个知识点</span></div>",
                unsafe_allow_html=True)
        if st.button("进入知识点讲解 →", width="stretch", key="dash_kb"):
            C.goto("knowledge")

    # ---------------- 通知 / 排行榜 ----------------
    C.divider()
    c1, c2 = st.columns(2)
    with c1:
        C.section("我的通知", "点赞、评论、关注与系统消息")
        if uid:
            ns = notify.list_notifications(uid, 6)
            if ns:
                for n in ns:
                    dot = "🔵" if not n["is_read"] else "⚪"
                    st.markdown(
                        f"<div class='bgl-card' style='padding:10px 14px;margin-bottom:8px'>"
                        f"{dot} <span class='bgl-chip gray'>{C.esc(notify.NTYPE_LABEL.get(n['ntype'], n['ntype']))}</span>"
                        f" {C.esc(n['content'][:46])}"
                        f"<div class='bgl-muted'>{C.rel_time(n['created_at'])}</div></div>",
                        unsafe_allow_html=True)
            else:
                C.empty_state("🔔", "暂无通知", "有新的互动时会显示在这里")
        else:
            C.empty_state("🔐", "登录后查看", "登录即可查看你的通知与学习数据")
    with c2:
        C.section("排行榜", "最活跃用户")
        for i, r in enumerate(users.leaderboard("active", 6), 1):
            medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
            st.markdown(
                f"<div class='bgl-card' style='padding:9px 14px;margin-bottom:7px'>"
                f"{medal} <b>{C.esc(r.get('nickname') or r['username'])}</b>"
                f" <span class='bgl-muted'>· {r['points']} 积分 · Lv.{r['level']}</span></div>",
                unsafe_allow_html=True)

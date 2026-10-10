"""讲师工作台：课程创建与管理、章节课时编排、上下架、学员、评价问答、收入与提现。"""

from __future__ import annotations

import streamlit as st

from core import auth, commerce, courses, db, live, users
from ui import common as C


def _course_manager(uid: int) -> None:
    C.section("创建课程", "创建后可编排章节与课时")
    with st.form("new_course"):
        title = st.text_input("课程标题")
        intro = st.text_area("课程简介", height=90)
        c1, c2, c3 = st.columns(3)
        with c1:
            cat = st.selectbox("分类", courses.CATEGORIES)
        with c2:
            ctype = st.selectbox("课程类型", list(courses.CTYPES.keys()),
                                 format_func=lambda k: courses.CTYPES[k])
        with c3:
            validity = st.number_input("有效期（天，0 = 永久）", 0, 3650, 0)
        c4, c5 = st.columns(2)
        with c4:
            price = st.number_input("售价（元）", 0.0, 99999.0, 0.0, step=10.0)
        with c5:
            orig = st.number_input("划线价（元）", 0.0, 99999.0, 0.0, step=10.0)
        tags = st.text_input("标签（逗号分隔）")
        if st.form_submit_button("创建课程", type="primary"):
            try:
                cid = courses.create_course(uid, title, intro, cat, price, orig, ctype,
                                            tags=tags, validity_days=int(validity), status="draft")
                C.ok(f"课程已创建（草稿状态），请编排章节。")
                st.session_state.managing_course = cid
                st.rerun()
            except auth.AuthError as e:
                C.err(str(e))

    mine = courses.instructor_courses(uid)
    C.section("我的课程", f"{len(mine)} 门")
    if not mine:
        C.empty_state("📚", "还没有课程", "用上方表单创建第一门课")
    for c in mine:
        with st.container(border=True):
            a, b = st.columns([4, 2])
            with a:
                st.markdown(
                    f"<b style='font-size:15px'>{C.esc(c['title'])}</b> {C.chip(c['category'])}"
                    f"{C.chip({'draft': '草稿', 'on': '已上架', 'off': '已下架'}.get(c['status'], c['status']), 'ok' if c['status'] == 'on' else 'warn')}"
                    f"<div class='bgl-muted' style='margin-top:4px'>{C.price_html(c['price'], c['original_price'])}"
                    f" · {courses.lesson_count(c['id'])} 课时 · {c['sales']} 人已学 · ⭐ {c['rating'] or '暂无'}</div>",
                    unsafe_allow_html=True)
            with b:
                x, y, z = st.columns(3)
                with x:
                    label = "下架" if c["status"] == "on" else "上架"
                    if st.button(label, key=f"ic_toggle_{c['id']}", width="stretch"):
                        courses.set_status(c["id"], "off" if c["status"] == "on" else "on", by=uid)
                        if c["status"] != "on":
                            commerce.sync_course_products()
                        st.rerun()
                with y:
                    if st.button("编排", key=f"ic_edit_{c['id']}", width="stretch"):
                        st.session_state.managing_course = c["id"]
                        st.rerun()
                with z:
                    if st.button("预览", key=f"ic_view_{c['id']}", width="stretch"):
                        C.goto("learn", sel_course=c["id"])

    cid = st.session_state.get("managing_course")
    if cid:
        c = courses.get_course(cid)
        if c and c["instructor_id"] == uid:
            C.divider()
            C.section(f"编排：《{c['title']}》", "添加章节与课时；带「试看」的课时未购买也可观看")
            with st.form(f"add_ch_{cid}"):
                ch_title = st.text_input("新章节标题")
                if st.form_submit_button("添加章节", type="primary"):
                    if ch_title.strip():
                        courses.add_chapter(cid, ch_title.strip())
                        C.ok("章节已添加")
                        st.rerun()
            chs = courses.chapters(cid)
            if not chs:
                C.note("还没有章节，请先添加章节。", "warn")
            for ch in chs:
                with st.expander(f"{ch['title']}（{len(courses.lessons(cid, ch['id']))} 课时）", expanded=True):
                    for l in courses.lessons(cid, ch["id"]):
                        st.markdown(f"· {C.esc(l['title'])} {C.chip(courses.LTYPES.get(l['ltype'], ''), 'gray')}"
                                    f"{C.chip('试看', 'ok') if l['is_free'] else ''}"
                                    f"<span class='bgl-muted'> · {l['duration'] // 60} 分钟</span>",
                                    unsafe_allow_html=True)
                    with st.form(f"add_l_{ch['id']}"):
                        lc1, lc2, lc3 = st.columns([2, 1, 1])
                        with lc1:
                            ltitle = st.text_input("课时标题", key=f"lt_{ch['id']}")
                        with lc2:
                            ltype = st.selectbox("类型", list(courses.LTYPES.keys()),
                                                 format_func=lambda k: courses.LTYPES[k], key=f"ly_{ch['id']}")
                        with lc3:
                            ldur = st.number_input("时长(分)", 1, 600, 20, key=f"ld_{ch['id']}")
                        free = st.checkbox("设为试看课时", key=f"lf_{ch['id']}")
                        if st.form_submit_button("添加课时"):
                            if ltitle.strip():
                                courses.add_lesson(cid, ch["id"], ltitle.strip(), ltype,
                                                   content=f"{c['title']} · {ltitle.strip()}",
                                                   duration=int(ldur) * 60, is_free=free)
                                C.ok("课时已添加")
                                st.rerun()
            if st.button("完成编排", key=f"done_edit_{cid}"):
                st.session_state.pop("managing_course", None)
                st.rerun()


def _students(uid: int) -> None:
    mine = courses.instructor_courses(uid)
    ids = [c["id"] for c in mine]
    if not ids:
        C.empty_state("👥", "还没有学员", "上架课程后学员会出现在这里")
        return
    ph = ",".join("?" * len(ids))
    rows = db.query(
        f"""SELECT e.*, u.nickname, u.username, u.avatar, c.title AS course_title
            FROM enrollments e JOIN users u ON u.id=e.user_id JOIN courses c ON c.id=e.course_id
            WHERE e.course_id IN ({ph}) ORDER BY e.id DESC LIMIT 300""", tuple(ids))
    C.section("学员列表", f"共 {len(rows)} 条报名记录")
    if not rows:
        C.empty_state("👥", "暂无学员", "")
        return
    for r in rows:
        st.markdown(
            f"<div class='bgl-card' style='padding:10px 14px'>"
            f"{C.esc(users.avatar_of(r))} <b>{C.esc(users.display_name(r))}</b> · "
            f"{C.esc(r['course_title'])}"
            f"<div class='bgl-muted'>进度 {r['progress']:.0f}%"
            f"{' · 已完成 ✅' if r['completed'] else ''} · 报名于 {C.rel_time(r['created_at'])}</div></div>",
            unsafe_allow_html=True)


def _qa(uid: int) -> None:
    mine = courses.instructor_courses(uid)
    ids = [c["id"] for c in mine]
    if not ids:
        C.empty_state("❓", "还没有问答", "")
        return
    ph = ",".join("?" * len(ids))
    rows = db.query(f"""SELECT q.*, u.nickname, u.username, c.title AS course_title
                        FROM course_qa q JOIN users u ON u.id=q.user_id
                        JOIN courses c ON c.id=q.course_id
                        WHERE q.course_id IN ({ph}) ORDER BY q.id DESC LIMIT 200""", tuple(ids))
    C.section("学员提问", f"{len(rows)} 条")
    if not rows:
        C.empty_state("❓", "暂无提问", "")
    for q in rows:
        with st.container(border=True):
            st.markdown(f"**《{C.esc(q['course_title'])}》** · {C.esc(users.display_name(q))} "
                        f"<span class='bgl-muted'>{C.rel_time(q['created_at'])}</span>"
                        f"<div style='margin-top:6px'>{C.esc(q['question'])}</div>", unsafe_allow_html=True)
            if q.get("answer"):
                st.success(f"已回复：{q['answer']}")
            else:
                with st.form(f"ans_{q['id']}"):
                    ans = st.text_area("回复", key=f"anst_{q['id']}", height=80)
                    if st.form_submit_button("发布回复", type="primary"):
                        if ans.strip():
                            courses.answer_question(q["id"], uid, ans.strip())
                            st.rerun()

    revs = db.query(f"""SELECT r.*, u.nickname, u.username, c.title AS course_title
                        FROM course_reviews r JOIN users u ON u.id=r.user_id
                        JOIN courses c ON c.id=r.course_id
                        WHERE r.course_id IN ({ph}) ORDER BY r.id DESC LIMIT 100""", tuple(ids))
    C.section("学员评价", f"{len(revs)} 条")
    if not revs:
        C.empty_state("⭐", "暂无评价", "")
    for r in revs:
        st.markdown(f"<div class='bgl-card'><b>{C.esc(users.display_name(r))}</b> "
                    f"{C.chip('★' * int(r['rating']), 'warn')} · 《{C.esc(r['course_title'])}》"
                    f"<div style='margin-top:4px'>{C.esc(r['content'])}</div>"
                    f"<div class='bgl-muted'>{C.rel_time(r['created_at'])}</div></div>",
                    unsafe_allow_html=True)


def render() -> None:
    uid = C.uid()
    u = C.current_user()
    if not C.guard(uid, "进入讲师工作台"):
        return
    if u.get("instructor_status") != "approved" and u.get("role") != "admin":
        C.hero("INSTRUCTOR", "讲师工作台", "需要认证讲师权限")
        C.empty_state("🎓", "尚未开通讲师权限", "请在「个人中心 → 讲师认证」提交申请")
        if st.button("前往申请", type="primary"):
            C.goto("profile")
        return

    C.hero("INSTRUCTOR", f"讲师工作台 · {u.get('nickname') or ''}",
           f"{C.esc(u.get('instructor_field') or '')} · 讲师等级 Lv.{u.get('instructor_level', 1)}")

    mine = courses.instructor_courses(uid)
    bal = commerce.instructor_balance(uid)
    total_students = sum(c["sales"] for c in mine)
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        C.stat("课程数", len(mine))
    with c2:
        C.stat("已上架", len([c for c in mine if c["status"] == "on"]))
    with c3:
        C.stat("学员总数", total_students)
    with c4:
        C.stat("累计收益", f"¥{bal['income']:.2f}")
    with c5:
        C.stat("可提现", f"¥{bal['available']:.2f}")

    my_lives = live.list_lives(instructor_id=uid)
    tabs = st.tabs(["📚 课程管理", f"📺 我的直播（{len(my_lives)}）", "👥 学员", "❓ 评价与问答", "💰 收入明细"])
    with tabs[0]:
        _course_manager(uid)
    with tabs[1]:
        if not my_lives:
            C.empty_state("📺", "还没有直播", "前往「直播课堂 → 开播」创建一场")
            if st.button("去创建直播"):
                C.goto("live")
        for l in my_lives:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(f"<b>{C.esc(l['title'])}</b> {C.chip(l['status'], 'gray')}"
                                f"<div class='bgl-muted'>{C.esc(l['start_at'][:16])} · "
                                f"预约 {live.reservation_count(l['id'])} · 在线 {l['online_count']} · "
                                f"赞 {l['likes']}</div>", unsafe_allow_html=True)
                with b:
                    if st.button("进入直播间", key=f"iw_{l['id']}", width="stretch"):
                        C.goto("live", sel_live=l["id"])
    with tabs[2]:
        _students(uid)
    with tabs[3]:
        _qa(uid)
    with tabs[4]:
        rep = commerce.revenue_report(uid, "day")
        if rep:
            import pandas as pd
            st.dataframe(pd.DataFrame(rep).rename(columns={"period": "日期", "total": "收益(元)", "orders": "订单数"}),
                         width="stretch", hide_index=True)
        else:
            C.empty_state("📈", "暂无收益", "有订单成交后生成报表")
        det = commerce.income_detail(uid)
        if det:
            import pandas as pd
            st.dataframe(pd.DataFrame([{"时间": d["created_at"][:16], "课程": d["title"],
                                        "金额": d["amount"], "订单": d["order_no"]} for d in det]),
                         width="stretch", hide_index=True)
        C.divider()
        C.section("申请提现", "需完成实名认证")
        if not auth.is_realname_ok(uid):
            C.note("请先完成实名认证。", "warn")
        with st.form("wb_withdraw"):
            amount = st.number_input("金额", 0.0, max(0.0, float(bal["available"])), 0.0, step=10.0)
            account = st.text_input("收款账户")
            if st.form_submit_button("提交申请", type="primary"):
                try:
                    commerce.apply_withdraw(uid, amount, account)
                    C.ok("申请已提交")
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))

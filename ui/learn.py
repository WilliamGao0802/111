"""AI 课程学习：课程目录、筛选搜索、详情（大纲/试看/评价/问答）、学习页与进度。"""

from __future__ import annotations

import streamlit as st

from core import auth, commerce, courses, db
from ui import common as C


# --------------------------------------------------------------------------
# 课程详情 / 学习
# --------------------------------------------------------------------------
def _detail(cid: int) -> None:
    c = courses.get_course(cid)
    if not c:
        C.empty_state("📚", "课程不存在", "它可能已下架")
        if st.button("← 返回课程列表"):
            C.goto("learn")
        return
    uid = C.uid()
    enrolled = courses.is_enrolled(uid, cid)
    en = courses.get_enrollment(uid, cid) if uid else None
    expired = courses.is_expired(en) if en else False
    tree = courses.course_tree(cid)
    total_lessons = courses.lesson_count(cid)

    C.breadcrumb("AI 课程学习", c["category"], c["title"])
    if st.button("← 返回课程列表", key="learn_back"):
        C.goto("learn")

    head_l, head_r = st.columns([3, 2])
    with head_l:
        valid_label = "永久有效" if not c["validity_days"] else str(c["validity_days"]) + " 天有效"
        st.markdown(
            f"<div class='bgl-title' style='font-size:24px;margin-top:6px'>{C.esc(c['title'])}</div>"
            f"<div style='margin:8px 0'>{C.chip(c['category'])}"
            f"{C.chip(courses.CTYPES.get(c['ctype'], ''), 'accent')}"
            f"{C.chip(str(total_lessons) + ' 课时', 'gray')}{C.chip(valid_label, 'gray')}</div>",
            unsafe_allow_html=True)
        st.markdown(c["intro"] or "")
    with head_r:
        with st.container(border=True):
            st.markdown(f"<div style='text-align:center;font-size:22px'>{C.price_html(c['price'], c['original_price'])}</div>",
                        unsafe_allow_html=True)
            st.markdown(
                f"<div class='bgl-muted' style='text-align:center'>⭐ {c['rating'] or '暂无评分'} · "
                f"{c['sales']} 人已学 · {c['rating_count']} 条评价</div>", unsafe_allow_html=True)
            if enrolled and not expired:
                st.success("✅ 你已拥有本课程")
                if st.button("继续学习 →", type="primary", width="stretch", key="go_study"):
                    st.session_state.learning_course = cid
                    st.rerun()
            elif expired:
                C.note("课程已到期，续费后可继续学习。", "warn")
            else:
                if st.button("🛒 立即购买", type="primary", width="stretch", key="buy_now"):
                    p = db.query_one("SELECT * FROM products WHERE ptype='course' AND ref_id=?", (cid,))
                    if not p:
                        commerce.sync_course_products()
                        p = db.query_one("SELECT * FROM products WHERE ptype='course' AND ref_id=?", (cid,))
                    if p:
                        C.goto("store", sel_product=p["id"])
                    else:
                        C.err("该课程暂未上架为商品")
                if st.button("加入购物车", width="stretch", key="add_cart"):
                    p = db.query_one("SELECT * FROM products WHERE ptype='course' AND ref_id=?", (cid,))
                    if not p:
                        commerce.sync_course_products()
                        p = db.query_one("SELECT * FROM products WHERE ptype='course' AND ref_id=?", (cid,))
                    if p and C.guard(uid, "加入购物车"):
                        try:
                            commerce.add_to_cart(uid, p["id"])
                            C.ok(f"已加入购物车：{c['title']}")
                        except auth.AuthError as e:
                            C.err(str(e))

    # 讲师
    with st.container(border=True):
        st.markdown(
            f"<span class='bgl-avatar'>{C.esc(c.get('instructor_avatar') or '👨‍🏫')}</span>"
            f"<b>{C.esc(c.get('instructor_nick') or c.get('instructor_name') or '讲师')}</b>"
            f"{C.chip('认证讲师', 'accent')}{C.chip('Lv.' + str(c.get('instructor_level') or 1), 'gray')}"
            f"<div class='bgl-muted' style='margin-top:6px'>擅长：{C.esc(c.get('instructor_field') or '')}</div>",
            unsafe_allow_html=True)
        a, b = st.columns([1, 4])
        with a:
            if c.get("instructor_id") and st.button("查看讲师主页", key="ins_page"):
                C.goto("profile", sel_user=c["instructor_id"])

    # 购买后的学习区
    if enrolled and not expired:
        C.divider()
        _study_panel(uid, c, tree)
    else:
        C.note("未购买仅可试看标记为「试看」的课时。购买后可解锁全部内容并记录学习进度。", "warn")

    # 大纲（未购买时也展示）
    if not (enrolled and not expired):
        C.section("课程大纲", f"共 {len(tree)} 章 · {total_lessons} 课时")
        _outline(uid, c, tree, locked=True)

    # 评价与问答
    C.divider()
    t1, t2 = st.tabs(["⭐ 学员评价", "❓ 课程问答"])
    with t1:
        reviews = courses.course_reviews(cid)
        if enrolled and not expired:
            with st.form("review_form"):
                r = st.slider("评分", 1, 5, 5, key="rev_score")
                txt = st.text_area("写下你的评价", placeholder="课程内容、讲解方式、收获…", key="rev_txt")
                if st.form_submit_button("提交评价", type="primary"):
                    courses.review_course(uid, cid, r, txt)
                    C.ok("评价已提交")
                    st.rerun()
        if not reviews:
            C.empty_state("💬", "还没有评价", "成为第一个评价这门课的人")
        for rv in reviews:
            st.markdown(
                f"<div class='bgl-card'><b>{C.esc(rv.get('nickname') or rv.get('username') or '用户')}</b>"
                f" {C.chip('★' * int(rv['rating']), 'warn')}"
                f"<div style='margin-top:4px'>{C.esc(rv['content'])}</div>"
                f"<div class='bgl-muted'>{C.rel_time(rv['created_at'])}</div></div>",
                unsafe_allow_html=True)
    with t2:
        if uid:
            with st.form("qa_form"):
                q = st.text_area("向讲师提问", placeholder="描述你的问题，讲师会来回答")
                if st.form_submit_button("提交问题", type="primary"):
                    try:
                        courses.ask_question(uid, cid, q)
                        C.ok("问题已提交，讲师会尽快回复")
                        st.rerun()
                    except auth.AuthError as e:
                        C.err(str(e))
        for qa in courses.course_qa(cid):
            st.markdown(
                f"<div class='bgl-card'><b>Q：</b>{C.esc(qa['question'])}"
                f"<div class='bgl-muted'>提问者 {C.esc(qa.get('nickname') or qa.get('username') or '用户')} · "
                f"{C.rel_time(qa['created_at'])}</div>"
                + (f"<div style='margin-top:8px;padding-top:8px;border-top:1px solid var(--bgl-border)'>"
                   f"<b>A：</b>{C.esc(qa['answer'])}</div>" if qa.get("answer") else
                   "<div class='bgl-muted' style='margin-top:6px'>讲师暂未回复</div>") + "</div>",
                unsafe_allow_html=True)


def _outline(uid: int, c: dict, tree: list, locked: bool = False) -> None:
    for node in tree:
        ch = node["chapter"]
        with st.container(border=True):
            st.markdown(f"**{C.esc(ch['title'])}** <span class='bgl-muted'>· {len(node['lessons'])} 课时</span>",
                        unsafe_allow_html=True)
            for l in node["lessons"]:
                cols = st.columns([4, 1, 1])
                done = courses.lesson_done(uid, l["id"]) if uid else False
                with cols[0]:
                    tag = "✅ " if done else ""
                    free = C.chip("试看", "ok") if l["is_free"] else ""
                    st.markdown(
                        f"{tag}{C.esc(l['title'])} {free}"
                        f"<span class='bgl-muted'>· {courses.LTYPES.get(l['ltype'], l['ltype'])} · "
                        f"{l['duration'] // 60} 分钟</span>", unsafe_allow_html=True)
                with cols[1]:
                    st.markdown(f"<span class='bgl-muted'>{l['duration'] // 60}′</span>",
                                unsafe_allow_html=True)
                with cols[2]:
                    if l["is_free"] or not locked:
                        if st.button("学习", key=f"ol_{l['id']}", width="stretch"):
                            st.session_state.playing_lesson = l["id"]
                            st.session_state.learning_course = c["id"]
                            st.rerun()
                    else:
                        st.markdown("<span class='bgl-muted'>🔒</span>", unsafe_allow_html=True)


def _study_panel(uid: int, c: dict, tree: list) -> None:
    en = courses.get_enrollment(uid, c["id"])
    st.markdown("### 🎬 学习区")
    p1, p2, p3 = st.columns(3)
    with p1:
        C.stat("课程进度", f"{en['progress']:.0f}%")
    with p2:
        C.stat("已完成课时", f"{len(courses.completed_lesson_ids(uid, c['id']))} / {courses.lesson_count(c['id'])}")
    with p3:
        C.stat("证书", "已发放" if en["certificate_code"] else "未完成")
    st.progress(min(1.0, float(en["progress"]) / 100))

    if en["certificate_code"]:
        C.note(f"🎓 电子结业证书编号：<b>{C.esc(en['certificate_code'])}</b>　"
               f"（可截图分享，共 {courses.lesson_count(c['id'])} 课时全部完成）")
    if en["expires_at"]:
        C.note(f"课程有效期至 {C.esc(en['expires_at'][:10])}，到期前会提醒续费。")

    playing = st.session_state.get("playing_lesson")
    all_lessons = [l for node in tree for l in node["lessons"]]
    if not all_lessons:
        C.empty_state("🎬", "课程暂无课时", "讲师正在准备内容")
        return
    if not playing or playing not in [l["id"] for l in all_lessons]:
        playing = all_lessons[0]["id"]
    cur = db.query_one("SELECT * FROM lessons WHERE id=?", (playing,))

    left, right = st.columns([3, 2])
    with left:
        if cur:
            st.markdown(
                f"<div style='background:var(--bgl-surface2);border-radius:14px;padding:38px 20px;"
                f"text-align:center;border:1px solid var(--bgl-border)'>"
                f"<div style='font-size:44px'>▶️</div>"
                f"<div style='font-weight:600;margin-top:6px'>{C.esc(cur['title'])}</div>"
                f"<div class='bgl-muted' style='margin-top:4px'>"
                f"{C.esc(courses.LTYPES.get(cur['ltype'], ''))} · {cur['duration'] // 60} 分钟 · 演示播放器</div>"
                f"<div class='bgl-muted' style='margin-top:8px;font-size:11.5px'>"
                f"真实部署时此处接入视频点播地址（如腾讯云 VOD / OSS 直链）</div></div>",
                unsafe_allow_html=True)
            if cur.get("content"):
                st.caption(cur["content"])
            b1, b2 = st.columns(2)
            with b1:
                done = courses.lesson_done(uid, cur["id"])
                if st.button("✅ 已完成" if done else "标记为已完成", type="primary",
                             width="stretch", key="lesson_done"):
                    courses.mark_lesson(uid, cur["id"], not done)
                    st.rerun()
            with b2:
                if st.button("标记未完成", width="stretch", key="lesson_undo"):
                    courses.mark_lesson(uid, cur["id"], False)
                    st.rerun()
    with right:
        st.markdown("**课时列表**")
        for node in tree:
            st.markdown(f"<div class='bgl-muted' style='margin:8px 0 4px 0'>{C.esc(node['chapter']['title'])}</div>",
                        unsafe_allow_html=True)
            for l in node["lessons"]:
                done = courses.lesson_done(uid, l["id"])
                mark = "✅" if done else "▢"
                if st.button(f"{mark} {l['title']}", key=f"sp_{l['id']}", width="stretch"):
                    st.session_state.playing_lesson = l["id"]
                    st.rerun()


# --------------------------------------------------------------------------
# 课程目录
# --------------------------------------------------------------------------
def render() -> None:
    if st.session_state.get("sel_course"):
        cid = st.session_state.pop("sel_course")
        _detail(cid)
        return
    if st.session_state.get("learning_course"):
        # 从详情页跳入学习区，仍展示详情（含学习区）
        cid = st.session_state.pop("learning_course")
        _detail(cid)
        return

    C.hero("COURSES", "AI 课程学习", "章节化课程 · 支持试看 · 学习进度记录 · 结业证书")

    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        kw = st.text_input("🔍 搜索课程", key="crs_kw", placeholder="如：微调 / RAG / 提示词")
    with f2:
        cat = st.selectbox("分类", ["全部"] + courses.CATEGORIES, key="crs_cat")
    with f3:
        ctype = st.selectbox("类型", ["全部"] + list(courses.CTYPES.values()), key="crs_type")

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        price_range = st.selectbox("价格", ["全部", "免费", "0–150 元", "150–300 元", "300 元以上"], key="crs_price")
    with g2:
        min_rating = st.selectbox("评分", ["全部", "4 分以上", "4.5 分以上"], key="crs_rating")
    with g3:
        sort = st.selectbox("排序", ["按销量", "按评分", "最新上架", "价格从低到高", "价格从高到低"], key="crs_sort")
    with g4:
        st.write("")
        if st.button("🔄 刷新商品库", width="stretch", key="crs_sync"):
            n = commerce.sync_course_products()
            C.ok(f"已同步课程商品（新增 {n} 条）")

    price_map = {"全部": (-1, -1), "免费": (0, 0), "0–150 元": (0.01, 150),
                 "150–300 元": (150, 300), "300 元以上": (300, 1e9)}
    lo, hi = price_map[price_range]
    type_map = {v: k for k, v in courses.CTYPES.items()}
    rows = courses.list_courses(
        keyword=kw,
        category="" if cat == "全部" else cat,
        ctype=type_map.get(ctype, ""),
        min_price=lo, max_price=hi,
        min_rating=4.5 if min_rating == "4.5 分以上" else (4.0 if min_rating == "4 分以上" else 0),
        sort={"按销量": "sales", "按评分": "rating", "最新上架": "new",
              "价格从低到高": "price_asc", "价格从高到低": "price_desc"}[sort],
        limit=60)

    uid = C.uid()
    C.section("课程列表", f"共 {len(rows)} 门课程")
    if not rows:
        C.empty_state("🔍", "没有匹配的课程", "调整筛选条件试试")
        return

    cols = st.columns(3)
    for i, c in enumerate(rows):
        with cols[i % 3]:
            with st.container(border=True):
                owned = courses.is_enrolled(uid, c["id"]) if uid else False
                st.markdown(
                    f"<div style='font-weight:600;font-size:14.5px;min-height:42px'>{C.esc(c['title'])}</div>"
                    f"<div>{C.chip(c['category'])}{C.chip(courses.CTYPES.get(c['ctype'], ''), 'gray')}"
                    f"{C.chip('已购', 'ok') if owned else ''}</div>"
                    f"<div class='bgl-muted' style='margin:6px 0;min-height:38px'>{C.esc((c['intro'] or '')[:56])}…</div>"
                    f"<div>{C.price_html(c['price'], c['original_price'])}</div>"
                    f"<div class='bgl-muted' style='margin-top:4px'>⭐ {c['rating'] or '暂无'} · "
                    f"{c['sales']} 人已学 · {c['instructor_nick'] or c.get('instructor_name') or ''}</div>",
                    unsafe_allow_html=True)
                if st.button("查看详情", key=f"cl_{c['id']}", width="stretch", type="primary"):
                    C.goto("learn", sel_course=c["id"])

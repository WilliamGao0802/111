"""互动功能区 · 讨论区：发帖、多级评论、@提及、话题标签、点赞关注、草稿、举报、置顶加精。"""

from __future__ import annotations

import streamlit as st

from core import auth, forum, notify, users
from ui import common as C


def _comment_node(node: dict, pid: int, uid: int, depth: int = 0) -> None:
    indent = min(depth, 3) * 22
    st.markdown(
        f"<div style='margin-left:{indent}px;padding:10px 12px;border-left:2px solid var(--bgl-border);"
        f"margin-bottom:6px'>"
        f"<span class='bgl-avatar' style='width:28px;height:28px;font-size:14px'>"
        f"{C.esc(users.avatar_of(node))}</span>"
        f"<b>{C.esc(users.display_name(node))}</b>"
        f"{C.chip('讲师', 'accent') if node.get('instructor_status') == 'approved' else ''}"
        f"<span class='bgl-muted'>· {C.rel_time(node['created_at'])}</span>"
        f"<div style='margin-top:6px'>{C.esc(node['content']).replace(chr(10), '<br/>')}</div>"
        f"</div>", unsafe_allow_html=True)
    if uid:
        c1, c2 = st.columns([1, 6])
        with c1:
            if st.button("回复", key=f"rp_{node['id']}", width="stretch"):
                st.session_state[f"reply_to_{pid}"] = node["id"]
        with c2:
            st.write("")
    if st.session_state.get(f"reply_to_{pid}") == node["id"]:
        with st.form(f"reply_form_{node['id']}"):
            txt = st.text_area("回复内容", key=f"rptxt_{node['id']}", height=80,
                               placeholder="支持 @用户名 提及他人")
            sc1, sc2 = st.columns([1, 5])
            with sc1:
                sub = st.form_submit_button("发布回复", type="primary")
            with sc2:
                cancel = st.form_submit_button("取消")
        if cancel:
            st.session_state.pop(f"reply_to_{pid}", None)
            st.rerun()
        if sub:
            try:
                forum.add_comment(pid, uid, txt, parent_id=node["id"])
                st.session_state.pop(f"reply_to_{pid}", None)
                st.rerun()
            except auth.AuthError as e:
                C.err(str(e))
    for child in node.get("children", []):
        _comment_node(child, pid, uid, depth + 1)


def _detail(pid: int) -> None:
    p = forum.get_post(pid)
    if not p or p["status"] != "published":
        C.empty_state("💬", "帖子不存在或已隐藏", "它可能已被作者或管理员移除")
        if st.button("← 返回讨论区"):
            C.goto("forum")
        return
    uid = C.uid()
    if st.button("← 返回讨论区", key="forum_back"):
        C.goto("forum")
    C.breadcrumb("讨论区", p["topic"], (p["title"] or "发言详情"))
    if p["is_pinned"]:
        st.markdown(C.chip("📌 置顶", "danger") + C.chip("✨ 精华", "warn"), unsafe_allow_html=True)
    st.markdown(
        f"<div class='bgl-title' style='font-size:22px;margin-top:4px'>"
        f"{C.esc(p['title'] or '（无标题）')}</div>"
        f"<div style='margin:8px 0'>{C.chip(p['topic'])}"
        f"{C.chips(str(p['tags']).split(','), 'gray')}"
        f"{C.chip('已编辑', 'gray') if p['edited'] else ''}</div>", unsafe_allow_html=True)
    st.markdown(
        f"<span class='bgl-avatar'>{C.esc(users.avatar_of(p))}</span>"
        f"<b>{C.esc(users.display_name(p))}</b>"
        f"{C.chip('讲师', 'accent') if p.get('instructor_status') == 'approved' else ''}"
        f"{C.chip('Lv.' + str(p.get('level') or 1), 'gray')}"
        f"<span class='bgl-muted'>· {C.rel_time(p['created_at'])}</span>", unsafe_allow_html=True)
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    st.markdown(p["content"])

    liked = pid in forum.liked_ids(uid)
    c1, c2, c3, c4 = st.columns([1, 1, 1, 4])
    with c1:
        if st.button(("💙 " if liked else "🤍 ") + str(p["likes"]), key="post_like"):
            try:
                forum.toggle_like(uid, pid)
                st.rerun()
            except auth.AuthError as e:
                C.err(str(e))
    with c2:
        if uid and st.button("🔗 关注", key="post_follow"):
            try:
                if users.is_following(uid, p["user_id"]):
                    users.unfollow(uid, p["user_id"])
                    C.ok("已取消关注")
                else:
                    users.follow(uid, p["user_id"])
                    C.ok("已关注该用户")
                st.rerun()
            except auth.AuthError as e:
                C.err(str(e))
    with c3:
        if st.button("🚩 举报", key="post_report"):
            st.session_state.show_report = pid
    with c4:
        if uid == p["user_id"] or C.is_admin():
            e1, e2 = st.columns([1, 1])
            with e1:
                if st.button("✏️ 编辑", key="post_edit", width="stretch"):
                    st.session_state.edit_post = pid
            with e2:
                if st.button("🗑 删除", key="post_del", width="stretch"):
                    forum.delete_post(pid, uid, C.is_admin())
                    C.goto("forum")

    if st.session_state.get("show_report") == pid:
        with st.form("report_form"):
            reason = st.text_area("举报原因", placeholder="请说明违规内容")
            if st.form_submit_button("提交举报", type="primary"):
                try:
                    forum.report(uid, "post", pid, reason)
                    st.session_state.pop("show_report", None)
                    C.ok("举报已提交，管理员会尽快处理。")
                except auth.AuthError as e:
                    C.err(str(e))

    if st.session_state.get("edit_post") == pid:
        with st.form("edit_post_form"):
            nt = st.text_input("标题", value=p["title"])
            nc = st.text_area("正文", value=p["content"], height=200)
            if st.form_submit_button("保存修改", type="primary"):
                forum.update_post(pid, uid, title=nt, content=nc)
                st.session_state.pop("edit_post", None)
                C.ok("已保存")
                st.rerun()

    if C.is_admin():
        with st.expander("🛡️ 管理员操作"):
            a, b = st.columns(2)
            with a:
                if st.button("切换置顶", key="adm_pin"):
                    forum.set_pin(pid, not p["is_pinned"])
                    st.rerun()
            with b:
                if st.button("切换精华", key="adm_ess"):
                    forum.set_essence(pid, not p["is_essence"])
                    st.rerun()

    C.divider()
    C.section("评论", f"{forum.comment_count(pid)} 条讨论")
    if uid:
        with st.form("comment_form"):
            txt = st.text_area("发表评论", key="cmt_txt", height=90,
                               placeholder="支持 @用户名 提及他人，支持 Markdown")
            if st.form_submit_button("发布评论", type="primary"):
                try:
                    forum.add_comment(pid, uid, txt)
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))
    else:
        C.note("登录后即可参与讨论。", "warn")

    tree = forum.comment_tree(pid)
    if not tree:
        C.empty_state("💭", "还没有评论", "来说点什么吧")
    for node in tree:
        _comment_node(node, pid, uid)


def _compose(uid: int) -> None:
    C.section("发布新帖", "支持 Markdown：#标题、**加粗**、`代码`、> 引用；输入 #标签# 会自动识别")
    draft = st.session_state.get("draft_loaded")
    with st.form("new_post"):
        title = st.text_input("标题（可选）", value=(draft or {}).get("title", ""))
        topic = st.selectbox("话题分区", forum.TOPICS,
                             index=forum.TOPICS.index((draft or {}).get("topic", "综合讨论")))
        content = st.text_area("正文", value=(draft or {}).get("content", ""), height=220,
                               placeholder="分享你的学习心得、踩坑经验或提问…\n\n用 @讲师用户名 可以直接提及他人。")
        tags = st.text_input("标签（逗号分隔，可留空）", placeholder="如：微调,RAG")
        a, b, c = st.columns(3)
        with a:
            publish = st.form_submit_button("发布", type="primary", width="stretch")
        with b:
            save_d = st.form_submit_button("存草稿", width="stretch")
        with c:
            st.write("")
    if save_d:
        forum.save_draft(uid, title, content, topic)
        C.ok("已保存到草稿箱")
    if publish:
        try:
            pid = forum.create_post(uid, title, content, topic, tags)
            st.session_state.pop("draft_loaded", None)
            C.goto("forum", sel_post=pid)
        except auth.AuthError as e:
            C.err(str(e))


def render() -> None:
    if st.session_state.get("sel_post"):
        pid = st.session_state.pop("sel_post")
        _detail(pid)
        return

    C.hero("COMMUNITY", "讨论区", "发帖、多级评论、@提及、话题分区、点赞关注 —— 一起把 AI 学明白")
    uid = C.uid()

    tabs = st.tabs(["🏛 广场", "✏️ 发帖", "📝 草稿箱", "🙋 我的发言"])
    with tabs[0]:
        f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
        with f1:
            kw = st.text_input("🔍 搜索帖子", key="fm_kw", placeholder="标题或正文关键词")
        with f2:
            topic = st.selectbox("话题", ["全部"] + forum.TOPICS, key="fm_topic")
        with f3:
            sort = st.selectbox("排序", ["最新", "最热", "最多点赞"], key="fm_sort")
        with f4:
            only_follow = st.toggle("只看关注", value=False, key="fm_follow")

        rows = forum.list_posts(
            sort={"最新": "new", "最热": "hot", "最多点赞": "likes"}[sort],
            topic="" if topic == "全部" else topic,
            keyword=kw, following_only=only_follow, uid=uid, limit=40)
        C.section("帖子列表", f"共 {len(rows)} 条")
        if not rows:
            C.empty_state("💬", "还没有帖子", "点击「发帖」成为第一个发言的人")
        liked = forum.liked_ids(uid)
        for p in rows:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    badges = (C.chip("📌 置顶", "danger") if p["is_pinned"] else "") + \
                             (C.chip("✨ 精华", "warn") if p["is_essence"] else "")
                    st.markdown(
                        f"{badges}<b style='font-size:15px'>{C.esc(p['title'] or '（无标题）')}</b> "
                        f"{C.chip(p['topic'])}"
                        f"<div class='bgl-muted' style='margin-top:4px'>"
                        f"{C.esc(p['content'][:110])}…</div>"
                        f"<div class='bgl-muted' style='margin-top:5px'>"
                        f"{C.esc(users.avatar_of(p))} {C.esc(users.display_name(p))} · "
                        f"{C.rel_time(p['created_at'])} · 赞 {p['likes']} · 评论 {p['comment_count']}</div>",
                        unsafe_allow_html=True)
                with b:
                    if st.button("查看讨论", key=f"fp_{p['id']}", width="stretch", type="primary"):
                        C.goto("forum", sel_post=p["id"])
                    if st.button(("💙 已赞" if p["id"] in liked else "🤍 点赞"), key=f"fpl_{p['id']}",
                                 width="stretch"):
                        try:
                            forum.toggle_like(uid, p["id"])
                            st.rerun()
                        except auth.AuthError as e:
                            C.err(str(e))

    with tabs[1]:
        if C.guard(uid, "发帖"):
            _compose(uid)

    with tabs[2]:
        if not C.guard(uid, "查看草稿箱"):
            return
        drafts = forum.list_drafts(uid)
        if not drafts:
            C.empty_state("📝", "草稿箱是空的", "发帖时点击「存草稿」即可保存")
        for d in drafts:
            with st.container(border=True):
                a, b, c = st.columns([4, 1, 1])
                with a:
                    st.markdown(f"**{C.esc(d['title'] or '（无标题草稿）')}** {C.chip(d['topic'])}"
                                f"<div class='bgl-muted'>{C.esc(d['content'][:70])}…</div>"
                                f"<div class='bgl-muted'>更新于 {C.rel_time(d['updated_at'])}</div>",
                                unsafe_allow_html=True)
                with b:
                    if st.button("继续编辑", key=f"dr_{d['id']}", width="stretch"):
                        st.session_state.draft_loaded = d
                        C.ok("已载入草稿，请切换到「发帖」标签继续编辑")
                with c:
                    if st.button("删除", key=f"drd_{d['id']}", width="stretch"):
                        forum.delete_draft(d["id"], uid)
                        st.rerun()

    with tabs[3]:
        if not C.guard(uid, "查看我的发言"):
            return
        mine = forum.my_posts(uid)
        sc = users.stat_counts(uid)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            C.stat("发帖", sc["posts"])
        with c2:
            C.stat("点赞", sc["liked"])
        with c3:
            C.stat("关注", sc["following"])
        with c4:
            C.stat("粉丝", sc["followers"])
        for p in mine:
            with st.container(border=True):
                st.markdown(f"**{C.esc(p['title'] or '（无标题）')}** {C.chip(p['topic'])}"
                            f"<div class='bgl-muted'>{C.esc(p['content'][:80])}… · 赞 {p['likes']} · "
                            f"{C.rel_time(p['created_at'])}</div>", unsafe_allow_html=True)
                if st.button("查看", key=f"mp_{p['id']}"):
                    C.goto("forum", sel_post=p["id"])

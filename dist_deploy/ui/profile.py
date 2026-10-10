"""个人中心：资料修改、实名认证、讲师申请、关注与粉丝、活动记录、通知中心、私信、账号注销。
   同时包含「用户主页」视图（查看他人发言、关注数、粉丝数、一键关注）。"""

from __future__ import annotations

import streamlit as st

from core import auth, db, forum, notify, users
from ui import common as C


# --------------------------------------------------------------------------
# 用户主页（他人）
# --------------------------------------------------------------------------
def _user_home(target_id: int) -> None:
    t = auth.get_user(target_id)
    if not t:
        C.empty_state("👤", "用户不存在", "该账号可能已注销")
        if st.button("← 返回个人中心"):
            C.goto("profile")
        return
    uid = C.uid()
    if st.button("← 返回", key="uh_back"):
        st.session_state.pop("sel_user", None)
        C.goto("profile")
    sc = users.stat_counts(target_id)
    st.markdown(
        f"<div class='bgl-card'><span class='bgl-avatar' style='width:54px;height:54px;font-size:26px'>"
        f"{C.esc(users.avatar_of(t))}</span>"
        f"<b style='font-size:19px'>{C.esc(users.display_name(t))}</b>"
        f"{C.chip('管理员', 'danger') if t['role'] == 'admin' else ''}"
        f"{C.chip('认证讲师', 'accent') if t['instructor_status'] == 'approved' else ''}"
        f"{C.chip('Lv.' + str(t['level']) + ' ' + auth.level_title(t['level']), 'gray')}"
        f"<div class='bgl-muted' style='margin-top:8px'>{C.esc(t.get('bio') or '这个人很低调')}</div>"
        f"<div class='bgl-muted' style='margin-top:6px'>{C.esc(auth.presence_text(t))} · "
        f"加入于 {C.esc(t['created_at'][:10])}</div></div>", unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        C.stat("发言", sc["posts"])
    with c2:
        C.stat("粉丝", sc["followers"])
    with c3:
        C.stat("关注", sc["following"])
    with c4:
        C.stat("文件", sc["files"])
    with c5:
        C.stat("积分", t["points"])

    if uid and uid != target_id:
        a, b, c = st.columns(3)
        following = users.is_following(uid, target_id)
        with a:
            if st.button("✅ 已关注" if following else "➕ 关注", width="stretch", key="uh_follow"):
                try:
                    if following:
                        users.unfollow(uid, target_id)
                    else:
                        users.follow(uid, target_id)
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))
        with b:
            if users.mutual(uid, target_id):
                st.markdown(C.chip("互相关注", "ok"), unsafe_allow_html=True)
        with c:
            if st.button("💬 发私信", width="stretch", key="uh_dm"):
                st.session_state.dm_peer = target_id
                st.rerun()
        if st.session_state.get("dm_peer") == target_id:
            _dm_box(uid, target_id)

    C.divider()
    act = users.user_activity(target_id)
    tabs = st.tabs(["📝 发言", "💬 评论", "📁 文件", "📚 学习"])
    with tabs[0]:
        if not act["posts"]:
            C.empty_state("📝", "暂无发言", "")
        for p in act["posts"]:
            st.markdown(f"<div class='bgl-card'><b>{C.esc(p['title'] or '（无标题）')}</b>"
                        f"<div class='bgl-muted'>{C.esc(p['content'][:90])}…</div>"
                        f"<div class='bgl-muted'>{C.rel_time(p['created_at'])}</div></div>",
                        unsafe_allow_html=True)
            if st.button("查看", key=f"uhp_{p['id']}"):
                C.goto("forum", sel_post=p["id"])
    with tabs[1]:
        if not act["comments"]:
            C.empty_state("💬", "暂无评论", "")
        for c in act["comments"]:
            st.markdown(f"<div class='bgl-card'>{C.esc(c['content'][:110])}"
                        f"<div class='bgl-muted'>在《{C.esc(c.get('post_title') or '帖子')}》· "
                        f"{C.rel_time(c['created_at'])}</div></div>", unsafe_allow_html=True)
    with tabs[2]:
        if not act["files"]:
            C.empty_state("📁", "暂无公开文件", "")
        for f in act["files"]:
            st.markdown(f"<div class='bgl-card'><b>{C.esc(f['filename'])}</b> "
                        f"{C.chip(f['category'])}{C.chip('下载 ' + str(f['downloads']), 'gray')}</div>",
                        unsafe_allow_html=True)
    with tabs[3]:
        if not act["enrollments"]:
            C.empty_state("📚", "暂无学习记录", "")
        for e in act["enrollments"]:
            st.markdown(f"<div class='bgl-card'><b>{C.esc(e['title'])}</b>"
                        f"<div class='bgl-muted'>进度 {e['progress']:.0f}%"
                        f"{' · 已完成' if e['completed'] else ''}</div></div>", unsafe_allow_html=True)


def _dm_box(uid: int, peer: int) -> None:
    p = auth.get_user(peer)
    C.section("私信", f"与 {users.display_name(p)} 的对话")
    msgs = notify.conversation(uid, peer)
    notify.mark_conversation_read(uid, peer)
    box = "<div style='max-height:300px;overflow-y:auto;background:var(--bgl-surface2);"\
          "border-radius:12px;padding:10px 12px'>"
    if not msgs:
        box += "<div class='bgl-muted'>还没有消息，发一条打个招呼吧</div>"
    for m in msgs:
        mine = m["from_id"] == uid
        align = "right" if mine else "left"
        box += (f"<div style='text-align:{align};margin-bottom:6px'>"
                f"<span style='display:inline-block;background:{'var(--bgl-primary-soft)' if mine else 'var(--bgl-surface)'};"
                f"border:1px solid var(--bgl-border);border-radius:10px;padding:6px 10px;font-size:13px;max-width:80%'>"
                f"{C.esc(m['content'])}</span></div>")
    box += "</div>"
    st.markdown(box, unsafe_allow_html=True)
    with st.form(f"dm_{peer}", clear_on_submit=True):
        txt = st.text_input("消息", placeholder="输入消息…", label_visibility="collapsed")
        if st.form_submit_button("发送", type="primary"):
            if txt.strip():
                notify.send_message(uid, peer, txt.strip())
                st.rerun()
    if st.button("关闭会话", key=f"dm_close_{peer}"):
        st.session_state.pop("dm_peer", None)
        st.rerun()


# --------------------------------------------------------------------------
# 个人中心
# --------------------------------------------------------------------------
def _notifications(uid: int) -> None:
    C.section("通知中心", "点赞、评论、关注、@提及、直播与交易通知")
    c1, c2 = st.columns([1, 4])
    with c1:
        if st.button("全部标为已读", key="nt_readall"):
            notify.mark_all_read(uid)
            st.rerun()
    rows = notify.list_notifications(uid, 80)
    if not rows:
        C.empty_state("🔔", "暂无通知", "")
    for n in rows:
        dot = "🔵" if not n["is_read"] else "⚪"
        st.markdown(
            f"<div class='bgl-card' style='padding:10px 14px'>"
            f"{dot} {C.chip(notify.NTYPE_LABEL.get(n['ntype'], n['ntype']), 'gray')} "
            f"{C.esc(n['content'])}<div class='bgl-muted'>{C.rel_time(n['created_at'])}</div></div>",
            unsafe_allow_html=True)


def _inbox(uid: int) -> None:
    C.section("私信", "一对一沟通")
    cs = notify.contacts(uid)
    if not cs:
        C.empty_state("💬", "暂无会话", "可以在用户主页点击「发私信」开始对话")
        return
    for c in cs:
        a, b = st.columns([4, 1])
        with a:
            st.markdown(f"<div class='bgl-card' style='padding:10px 14px'>"
                        f"<b>{C.esc(users.display_name(c))}</b> <span class='bgl-muted'>"
                        f"{C.esc(c.get('last') or '')[:36]}</span>"
                        f"<div class='bgl-muted'>{C.rel_time(c.get('last_at') or '')}</div></div>",
                        unsafe_allow_html=True)
        with b:
            if st.button("打开", key=f"ib_{c['id']}", width="stretch"):
                st.session_state.dm_peer = c["id"]
                st.rerun()
    if st.session_state.get("dm_peer"):
        _dm_box(uid, st.session_state["dm_peer"])


def render() -> None:
    if st.session_state.get("sel_user"):
        tgt = st.session_state.pop("sel_user")
        if tgt != C.uid():
            _user_home(tgt)
            return
    uid = C.uid()
    if not C.guard(uid, "查看个人中心"):
        return
    u = auth.get_user(uid)
    C.hero("PROFILE", "个人中心", "资料 · 实名认证 · 讲师申请 · 关注粉丝 · 通知与私信 · 账号安全")

    st.markdown(
        f"<div class='bgl-card'><span class='bgl-avatar' style='width:54px;height:54px;font-size:26px'>"
        f"{C.esc(users.avatar_of(u))}</span><b style='font-size:19px'>{C.esc(users.display_name(u))}</b>"
        f"{C.chip('管理员', 'danger') if u['role'] == 'admin' else ''}"
        f"{C.chip('认证讲师', 'accent') if u['instructor_status'] == 'approved' else ''}"
        f"{C.chip('已实名', 'ok') if u['realname_status'] == 'approved' else C.chip('未实名', 'gray')}"
        f"{C.chip('Lv.' + str(u['level']) + ' ' + auth.level_title(u['level']), 'gray')}"
        f"<div class='bgl-muted' style='margin-top:8px'>{C.esc(u.get('bio') or '还没有个性签名')}</div>"
        f"<div class='bgl-muted'>{u['points']} 积分 · {C.esc(auth.presence_text(u))} · "
        f"用户名 {C.esc(u['username'])}</div></div>", unsafe_allow_html=True)

    unread = notify.unread_count(uid)
    umsg = notify.unread_messages(uid)
    tabs = st.tabs([f"👤 资料", f"🪪 实名与讲师", "📋 我的记录",
                    f"🔔 通知（{unread}）", f"💬 私信（{umsg}）", "🔐 账号安全"])

    # ---------------- 资料 ----------------
    with tabs[0]:
        with st.form("profile_form"):
            nick = st.text_input("昵称", value=u.get("nickname") or "")
            av = st.text_input("头像（Emoji 或图片地址）", value=u.get("avatar") or "",
                               help="例如 🐼 或 https://…/avatar.png")
            bio = st.text_area("个性签名", value=u.get("bio") or "", height=80)
            if st.form_submit_button("保存资料", type="primary"):
                try:
                    users.update_profile(uid, nickname=nick, avatar=av, bio=bio)
                    C.ok("资料已更新")
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))
        st.markdown(f"邮箱：{C.esc(u.get('email') or '未绑定')}"
                    f"{C.chip('已验证', 'ok') if u.get('email_verified') else ''}　"
                    f"手机：{C.esc(u.get('phone') or '未绑定')}"
                    f"{C.chip('已验证', 'ok') if u.get('phone_verified') else ''}", unsafe_allow_html=True)
        with st.expander("绑定 / 更换邮箱、手机号"):
            b1, b2 = st.columns(2)
            with b1:
                with st.form("bind_email"):
                    em = st.text_input("邮箱")
                    ec = st.text_input("邮箱验证码")
                    if st.form_submit_button("发送验证码"):
                        try:
                            c = auth.send_code(em, "email", "bind")
                            st.info(f"【演示】邮箱验证码：{c}")
                        except auth.AuthError as e:
                            C.err(str(e))
                    if st.form_submit_button("绑定邮箱", type="primary"):
                        try:
                            auth.bind_email(uid, em, ec)
                            C.ok("邮箱已绑定")
                            st.rerun()
                        except auth.AuthError as e:
                            C.err(str(e))
            with b2:
                with st.form("bind_phone"):
                    ph = st.text_input("手机号")
                    pc = st.text_input("短信验证码")
                    if st.form_submit_button("发送验证码 "):
                        try:
                            c = auth.send_code(ph, "sms", "bind")
                            st.info(f"【演示】短信验证码：{c}")
                        except auth.AuthError as e:
                            C.err(str(e))
                    if st.form_submit_button("绑定手机号", type="primary"):
                        try:
                            auth.bind_phone(uid, ph, pc)
                            C.ok("手机号已绑定")
                            st.rerun()
                        except auth.AuthError as e:
                            C.err(str(e))

    # ---------------- 实名与讲师 ----------------
    with tabs[1]:
        C.section("实名认证", "购买课程、成为讲师、提现均需实名认证")
        st.markdown(f"当前状态：{C.chip({'none': '未提交', 'pending': '审核中', 'approved': '已通过', 'rejected': '已驳回'}.get(u['realname_status'], u['realname_status']), 'warn')}",
                    unsafe_allow_html=True)
        if u["realname_status"] in ("none", "rejected"):
            with st.form("rn_form"):
                rn = st.text_input("真实姓名")
                ic = st.text_input("身份证号（将脱敏存储）", type="password")
                ph = st.text_input("手机号", value=u.get("phone") or "")
                if st.form_submit_button("提交实名认证", type="primary"):
                    try:
                        auth.submit_realname(uid, rn, ic, ph)
                        C.ok("已提交，等待管理员审核")
                        st.rerun()
                    except auth.AuthError as e:
                        C.err(str(e))
        elif u["realname_status"] == "approved":
            st.markdown(f"实名信息：{C.esc(u.get('real_name') or '')} · {C.esc(u.get('id_card') or '')}",
                        unsafe_allow_html=True)

        C.divider()
        C.section("讲师认证", "通过后可开课、开播")
        st.markdown(f"当前状态：{C.chip({'none': '未申请', 'pending': '审核中', 'approved': '已通过', 'rejected': '已驳回'}.get(u['instructor_status'], u['instructor_status']), 'accent')}",
                    unsafe_allow_html=True)
        if u["instructor_status"] in ("none", "rejected"):
            with st.form("ins_form"):
                intro = st.text_area("讲师简介", height=100, placeholder="教学经历、代表项目…")
                field = st.text_input("擅长领域", placeholder="如：大模型基础 / 微调实战")
                proof = st.text_input("资质证明（链接或说明）", placeholder="论文 / GitHub / 作品链接")
                if st.form_submit_button("提交申请", type="primary"):
                    try:
                        users.apply_instructor(uid, intro, field, proof)
                        C.ok("申请已提交，等待管理员审核")
                        st.rerun()
                    except auth.AuthError as e:
                        C.err(str(e))
        elif u["instructor_status"] == "approved":
            st.markdown(f"简介：{C.esc(u.get('instructor_intro') or '')}　"
                        f"领域：{C.esc(u.get('instructor_field') or '')}", unsafe_allow_html=True)
            if st.button("进入讲师工作台 →", type="primary", key="to_workbench"):
                C.goto("instructor")

        C.divider()
        C.section("关注与粉丝", "")
        fc1, fc2 = st.columns(2)
        with fc1:
            st.markdown(f"**我的关注（{len(users.following_list(uid))}）**")
            for f in users.following_list(uid):
                a, b = st.columns([3, 1])
                with a:
                    st.markdown(f"{C.esc(users.avatar_of(f))} {C.esc(users.display_name(f))}"
                                f"{' ' + C.chip('互关', 'ok') if users.mutual(uid, f['id']) else ''}",
                                unsafe_allow_html=True)
                with b:
                    if st.button("主页", key=f"fl_{f['id']}", width="stretch"):
                        C.goto("profile", sel_user=f["id"])
        with fc2:
            st.markdown(f"**我的粉丝（{len(users.follower_list(uid))}）**")
            for f in users.follower_list(uid):
                a, b = st.columns([3, 1])
                with a:
                    st.markdown(f"{C.esc(users.avatar_of(f))} {C.esc(users.display_name(f))}"
                                f"{' ' + C.chip('互关', 'ok') if users.mutual(uid, f['id']) else ''}",
                                unsafe_allow_html=True)
                with b:
                    if st.button("主页", key=f"fr_{f['id']}", width="stretch"):
                        C.goto("profile", sel_user=f["id"])

    # ---------------- 我的记录 ----------------
    with tabs[2]:
        mine = st.radio("分类", ["我的发帖", "我点赞的", "我上传的", "我购买的", "我的学习"],
                        horizontal=True, key="rec_kind")
        if mine == "我的发帖":
            rows = forum.my_posts(uid)
            if not rows:
                C.empty_state("📝", "还没有发帖", "")
            for p in rows:
                st.markdown(f"<div class='bgl-card'><b>{C.esc(p['title'] or '（无标题）')}</b>"
                            f"<div class='bgl-muted'>{C.esc(p['content'][:80])}…</div></div>",
                            unsafe_allow_html=True)
                if st.button("查看", key=f"recp_{p['id']}"):
                    C.goto("forum", sel_post=p["id"])
        elif mine == "我点赞的":
            rows = db.query("""SELECT p.* FROM post_likes l JOIN posts p ON p.id=l.post_id
                               WHERE l.user_id=? ORDER BY l.created_at DESC""", (uid,))
            if not rows:
                C.empty_state("💙", "还没有点赞", "")
            for p in rows:
                st.markdown(f"<div class='bgl-card'>{C.esc(p['title'] or p['content'][:40])}</div>",
                            unsafe_allow_html=True)
        elif mine == "我上传的":
            rows = db.query("SELECT * FROM files WHERE user_id=? AND deleted=0 ORDER BY id DESC", (uid,))
            if not rows:
                C.empty_state("📁", "还没有上传文件", "")
            for f in rows:
                st.markdown(f"<div class='bgl-card'>{C.esc(f['filename'])} "
                            f"{C.chip(f['category'])} · {f['size'] / 1024:.1f} KB</div>",
                            unsafe_allow_html=True)
        elif mine == "我购买的":
            from core import commerce
            rows = commerce.list_orders(uid)
            if not rows:
                C.empty_state("📦", "还没有订单", "")
            for o in rows:
                items_txt = "、".join(i["title"] for i in commerce.order_items(o["id"]))
                st.markdown(f"<div class='bgl-card'>{C.esc(o['order_no'])} · {C.esc(items_txt)} · "
                            f"¥{o['final_amount']:.2f} · {C.chip(o['status'], 'gray')}</div>",
                            unsafe_allow_html=True)
        else:
            from core import courses
            rows = courses.my_courses(uid)
            if not rows:
                C.empty_state("📚", "还没有课程", "")
            for e in rows:
                st.markdown(f"<div class='bgl-card'>{C.esc(e['title'])} · 进度 {e['progress']:.0f}%</div>",
                            unsafe_allow_html=True)

    # ---------------- 通知 / 私信 ----------------
    with tabs[3]:
        _notifications(uid)
    with tabs[4]:
        _inbox(uid)

    # ---------------- 账号安全 ----------------
    with tabs[5]:
        C.section("修改密码", "密码必须为 6 位数字")
        with st.form("pwd_form"):
            old = st.text_input("原密码", type="password")
            new1 = st.text_input("新密码", type="password")
            new2 = st.text_input("确认新密码", type="password")
            if st.form_submit_button("修改密码", type="primary"):
                try:
                    if new1 != new2:
                        raise auth.AuthError("两次输入的新密码不一致")
                    auth.change_password(uid, old, new1)
                    C.ok("密码已修改")
                except auth.AuthError as e:
                    C.err(str(e))
        ok, msg = auth.validate_password(new1) if new1 else (True, "")
        if new1:
            score, label = auth.password_strength(new1)
            st.progress(score / 100, text=f"密码强度：{label}")
            if not ok:
                C.err(msg)

        C.divider()
        C.section("账号注销", "注销后你的发言将被匿名化，账号不可恢复")
        st.warning("⚠️ 此操作不可逆。注销前请确认已处理完订单与提现。")
        with st.expander("我确认要注销账号"):
            strategy = st.radio("发言处理方式", ["anonymize", "delete"],
                                format_func=lambda x: "匿名化（保留内容）" if x == "anonymize" else "彻底删除发言",
                                horizontal=True)
            confirm = st.text_input("输入用户名以确认", placeholder=u["username"])
            if st.button("注销账号", type="primary", key="cancel_acc"):
                if confirm != u["username"]:
                    C.err("用户名不匹配，操作已取消")
                else:
                    auth.cancel_account(uid, strategy)
                    st.session_state.user = None
                    C.goto("dashboard")

"""直播讲课系列：直播列表、预约提醒、直播间（播放器 + 弹幕 + 互动 + 连麦）、回放、讲师开播。"""

from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from core import auth, courses, db, live, users
from ui import common as C

STATUS_META = {
    "live": ("🔴 直播中", "danger"), "upcoming": ("⏰ 即将开播", ""),
    "replay": ("▶️ 回放中", "ok"), "ended": ("✅ 已结束", "gray"),
}


def _room(lid: int) -> None:
    l = live.get_live(lid)
    if not l:
        C.empty_state("📺", "直播不存在", "它可能已被删除")
        if st.button("← 返回直播列表"):
            C.goto("live")
        return
    uid = C.uid()
    ok, msg = live.can_watch_replay(l, uid)
    if not ok:
        C.breadcrumb("直播课堂", l["title"])
        if st.button("← 返回直播列表", key="lv_back0"):
            C.goto("live")
        C.empty_state("🔒", "暂不可观看", msg)
        if l["course_id"] and st.button("前往购买对应课程", type="primary"):
            C.goto("learn", sel_course=l["course_id"])
        return

    if uid and lid not in st.session_state.live_joined:
        live.join_room(lid)
        st.session_state.live_joined.add(lid)

    # 沉浸式深色布局
    st.markdown(
        "<div style='background:#0b0d13;border-radius:16px;padding:14px 16px;color:#e8eaf2;"
        "border:1px solid #232838;margin-bottom:12px'>"
        f"<div style='font-size:11px;letter-spacing:2px;opacity:.7'>LIVE ROOM</div>"
        f"<div style='font-size:20px;font-weight:700;margin:4px 0'>{C.esc(l['title'])}</div>"
        f"<div style='opacity:.8;font-size:13px'>{C.esc(l.get('instructor_nick') or '')} · "
        f"{C.esc(l['start_at'][:16])} · 在线 {l['online_count']} 人 · 点赞 {l['likes']}</div></div>",
        unsafe_allow_html=True)

    left, right = st.columns([3, 2])
    with left:
        if l["status"] == "upcoming":
            st.markdown(
                "<div style='background:#12151f;border-radius:14px;padding:56px 20px;text-align:center;"
                "border:1px dashed #2b3145;color:#c9cede'>"
                "<div style='font-size:44px'>⏰</div>"
                "<div style='margin-top:8px;font-size:15px'>直播尚未开始</div>"
                f"<div style='opacity:.7;font-size:12.5px;margin-top:6px'>"
                f"开播时间 {C.esc(l['start_at'][:16])} · 开播前 15 分钟会提醒已预约用户</div></div>",
                unsafe_allow_html=True)
        else:
            st.markdown(
                "<div style='background:radial-gradient(circle at 50% 40%,#1b2030,#0b0d13);"
                "border-radius:14px;padding:58px 20px;text-align:center;border:1px solid #232838;color:#dfe3ee'>"
                f"<div style='font-size:46px'>{'🔴' if l['status'] == 'live' else '▶️'}</div>"
                f"<div style='margin-top:8px;font-size:15px'>"
                f"{'直播进行中' if l['status'] == 'live' else '回放播放中'}</div>"
                f"<div style='opacity:.65;font-size:11.5px;margin-top:8px'>演示播放器 · "
                f"推流地址 {C.esc(live.player_placeholder(l))}</div>"
                "<div style='opacity:.55;font-size:11px;margin-top:6px'>"
                "真实部署时接入腾讯云直播 / 阿里云直播 / OBS-RTMP 拉流地址</div></div>",
                unsafe_allow_html=True)
        st.caption(l["intro"] or "")

        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("👍 点赞", width="stretch", key="lv_like"):
                live.toggle_like(lid, uid)
                st.rerun()
        with b2:
            if uid and st.button("✋ 申请连麦", width="stretch", key="lv_hand"):
                live.raise_hand(lid, uid)
                C.ok("连麦申请已提交，等待讲师同意。")
        with b3:
            if st.button("🔄 刷新", width="stretch", key="lv_refresh"):
                st.rerun()

        # 互动工具
        inter = live.list_interactions(lid)
        if inter:
            C.section("互动", "投票 / 问卷 / 答题卡")
            for it in inter[:4]:
                with st.container(border=True):
                    st.markdown(f"**{C.esc(it['question'])}** "
                                f"{C.chip({'poll': '投票', 'question': '问卷', 'lottery': '抽奖', 'quiz': '答题卡'}.get(it['itype'], it['itype']), 'accent')}",
                                unsafe_allow_html=True)
                    myv = live.my_vote(it["id"], uid) if uid else None
                    opts = it["options"] or []
                    pick = st.radio("选择", opts, index=opts.index(myv) if myv in opts else None,
                                    key=f"vote_{it['id']}", label_visibility="collapsed")
                    if st.button("提交选择", key=f"vsub_{it['id']}"):
                        try:
                            live.vote(it["id"], uid, pick)
                            st.rerun()
                        except auth.AuthError as e:
                            C.err(str(e))
                    stt = it["votes"]
                    total = sum(stt.values()) or 1
                    for o in opts:
                        n = stt.get(o, 0)
                        st.progress(min(1.0, n / total), text=f"{o}　{n} 票（{n * 100 // total}%）")

    with right:
        C.section("聊天区", "仅登录用户可发言，支持 @讲师")
        if not uid:
            C.note("登录后可在直播间发言。", "warn")
        chats = live.list_chat(lid, 60)
        box = "<div style='max-height:340px;overflow-y:auto;background:var(--bgl-surface2);"\
              "border-radius:12px;padding:10px 12px'>"
        if not chats:
            box += "<div class='bgl-muted'>还没有人发言，来打个招呼吧～</div>"
        for m in chats:
            is_inst = m.get("instructor_status") == "approved"
            # 注意：徽标先算成变量再进 f-string —— 表达式里含 \" 转义在
            # Python 3.12 以下会直接 SyntaxError（云端沙箱实测踩过）。
            badge = "<span class='bgl-chip accent'>讲师</span>" if is_inst else ""
            box += (f"<div style='margin-bottom:7px;font-size:13px'>"
                    f"{C.esc(m.get('nickname') or m.get('username') or '用户')}"
                    f"{badge}："
                    f"{C.esc(m['content'])}</div>")
        box += "</div>"
        st.markdown(box, unsafe_allow_html=True)
        with st.form(f"chat_form_{lid}", clear_on_submit=True):
            msg = st.text_input("发一条弹幕", placeholder="说点什么…", label_visibility="collapsed")
            if st.form_submit_button("发送", type="primary", width="stretch"):
                try:
                    live.send_chat(lid, uid, msg)
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))

        # 讲师控场
        if uid == l["instructor_id"] or C.is_admin():
            C.section("讲师控制台", "开始 / 结束直播、发布互动")
            cc = st.columns(3)
            with cc[0]:
                if st.button("🔴 开始", key="lv_start", width="stretch"):
                    live.set_status(lid, "live", by=uid)
                    st.rerun()
            with cc[1]:
                if st.button("⏸ 暂停", key="lv_pause", width="stretch"):
                    C.ok("已暂停（演示）")
            with cc[2]:
                if st.button("⏹ 结束", key="lv_end", width="stretch"):
                    live.set_status(lid, "replay", by=uid)
                    st.rerun()
            with st.form("poll_form"):
                q = st.text_input("投票问题", key="poll_q")
                opts = st.text_input("选项（逗号分隔）", key="poll_opts")
                if st.form_submit_button("发布投票"):
                    if q and opts:
                        live.create_interaction(lid, "poll", q,
                                                [o.strip() for o in opts.split(",") if o.strip()])
                        C.ok("投票已发布")
                        st.rerun()
            hands = live.hand_queue(lid)
            if hands:
                with st.expander(f"✋ 连麦申请（{len(hands)}）"):
                    for h in hands:
                        a, b = st.columns([3, 1])
                        with a:
                            st.markdown(f"{C.esc(h.get('nickname') or h.get('username'))} · {h['status']}",
                                        unsafe_allow_html=True)
                        with b:
                            if st.button("同意", key=f"ha_{h['user_id']}"):
                                live.set_hand(lid, h["user_id"], "approved")
                                st.rerun()

    if st.button("← 返回直播列表", key="lv_back"):
        C.goto("live")


def _list_card(l: dict, uid: int) -> None:
    label, kind = STATUS_META.get(l["status"], ("", "gray"))
    with st.container(border=True):
        a, b = st.columns([4, 1])
        with a:
            st.markdown(
                f"<b style='font-size:15px'>{C.esc(l['title'])}</b> {C.chip(label, kind)}"
                f"{C.chip('回放 · ' + live.REPLAY_ACCESS.get(l['replay_access'], ''), 'gray')}"
                f"{C.price_html(l['price'])}"
                f"<div class='bgl-muted' style='margin-top:5px'>{C.esc(l['intro'][:90])}…</div>"
                f"<div class='bgl-muted' style='margin-top:4px'>讲师 {C.esc(l.get('instructor_nick') or '')} · "
                f"{C.esc(l['start_at'][:16])} · 预约 {live.reservation_count(l['id'])} 人 · "
                f"在线 {l['online_count']} · 赞 {l['likes']}</div>",
                unsafe_allow_html=True)
        with b:
            if st.button("进入直播间", key=f"lr_{l['id']}", width="stretch", type="primary"):
                C.goto("live", sel_live=l["id"])
            if l["status"] == "upcoming":
                reserved = live.is_reserved(l["id"], uid) if uid else False
                if st.button("✅ 已预约" if reserved else "🔔 预约", key=f"rv_{l['id']}", width="stretch"):
                    if C.guard(uid, "预约直播"):
                        try:
                            if reserved:
                                live.unreserve(l["id"], uid)
                            else:
                                live.reserve(l["id"], uid)
                                C.ok("预约成功，开播前 15 分钟会提醒你。")
                            st.rerun()
                        except auth.AuthError as e:
                            C.err(str(e))


def render() -> None:
    if st.session_state.get("sel_live"):
        lid = st.session_state.pop("sel_live")
        _room(lid)
        return

    C.hero("LIVE CLASS", "直播课堂", "预约提醒 · 实时弹幕 · 互动投票 · 连麦 · 回放自动进课程")
    uid = C.uid()
    g = live.grouped_lives()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        C.stat("直播中", len(g["live"]))
    with c2:
        C.stat("即将开播", len(g["upcoming"]))
    with c3:
        C.stat("可看回放", len(g["replay"]))
    with c4:
        C.stat("我的预约", len(live.my_reservations(uid)) if uid else 0)

    tabs = st.tabs(["🔴 直播中", "⏰ 即将开播", "▶️ 回放", "🔔 我的预约", "🎬 开播（讲师）"])
    with tabs[0]:
        if not g["live"]:
            C.empty_state("📺", "暂无正在进行的直播", "去「即将开播」看看，先预约一场")
        for l in g["live"]:
            _list_card(l, uid)
    with tabs[1]:
        if not g["upcoming"]:
            C.empty_state("⏰", "暂无待开播的课程", "讲师创建直播后会显示在这里")
        for l in g["upcoming"]:
            _list_card(l, uid)
    with tabs[2]:
        if not g["replay"]:
            C.empty_state("▶️", "暂无回放", "直播结束后会自动生成回放")
        for l in g["replay"]:
            _list_card(l, uid)
    with tabs[3]:
        if not C.guard(uid, "查看预约"):
            return
        mine = live.my_reservations(uid)
        if not mine:
            C.empty_state("🔔", "还没有预约", "在「即将开播」里点击预约")
        for l in mine:
            _list_card(l, uid)
        if st.button("📩 立即检查开播提醒", key="chk_remind"):
            n = live.remind_due(15)
            C.ok(f"已发送 {n} 条开播提醒（15 分钟内开播的场次）")

    with tabs[4]:
        u = C.current_user()
        if u.get("instructor_status") != "approved" and u.get("role") != "admin":
            C.empty_state("🎓", "需要讲师权限", "请在「个人中心 → 申请成为讲师」提交申请")
            if st.button("去申请", key="to_inst"):
                C.goto("profile")
            return
        if u.get("instructor_status") == "approved" and not auth.is_realname_ok(uid):
            C.note("开播需要先完成实名认证。", "warn")
        with st.form("new_live"):
            title = st.text_input("直播标题")
            intro = st.text_area("直播简介", height=90)
            c1, c2, c3 = st.columns(3)
            with c1:
                date = st.date_input("开播日期", value=(datetime.now() + timedelta(days=1)).date())
            with c2:
                hour = st.number_input("开播小时", 0, 23, 20)
            with c3:
                price = st.number_input("票价（0 = 免费）", 0.0, 9999.0, 0.0, step=10.0)
            c4, c5 = st.columns(2)
            with c4:
                access = st.selectbox("回放权限", list(live.REPLAY_ACCESS.keys()),
                                      format_func=lambda k: live.REPLAY_ACCESS[k])
            with c5:
                my_courses = courses.instructor_courses(uid) if uid else []
                csel = st.selectbox("关联课程（回放将进入该课程）",
                                    [0] + [c["id"] for c in my_courses],
                                    format_func=lambda i: "不关联" if i == 0 else
                                    next((c["title"] for c in my_courses if c["id"] == i), str(i)))
            if st.form_submit_button("创建直播", type="primary"):
                start = datetime.combine(date, datetime.min.time()).replace(hour=int(hour))
                try:
                    live.create_live(uid, title, start.strftime("%Y-%m-%d %H:%M:%S"), intro,
                                     price, access, csel)
                    C.ok("直播已创建，学员可以开始预约了。")
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))

        my_lives = live.list_lives(instructor_id=uid) if uid else []
        if my_lives:
            C.section("我的直播", f"{len(my_lives)} 场")
            for l in my_lives:
                _list_card(l, uid)

    # 讲师榜
    C.divider()
    C.section("最受欢迎讲师", "按课程销量与评分")
    for i, r in enumerate(users.leaderboard("instructors", 5), 1):
        st.markdown(
            f"<div class='bgl-card' style='padding:10px 14px;margin-bottom:7px'>"
            f"{['🥇', '🥈', '🥉'][i - 1] if i <= 3 else str(i) + '.'} "
            f"{C.esc(r.get('nickname') or r['username'])} <span class='bgl-muted'>· "
            f"售出 {r['sales']} 份 · 评分 {round(float(r['rating'] or 0), 2)}</span></div>",
            unsafe_allow_html=True)

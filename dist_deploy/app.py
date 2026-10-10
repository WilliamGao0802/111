"""BGL 的 AI 学习 · 应用入口。

职责（技能「八条铁律」第 2 条）：只做 UI 与路由，业务逻辑全部在 core/。
启动：streamlit run app.py
"""

from __future__ import annotations

import traceback
from datetime import datetime

import streamlit as st

import version as ver
from core import auth, db, notify, ratelimit, search, seed, users
from ui import common as C

# 需要登录才能访问的页面
REQUIRE_LOGIN = {"my", "profile", "instructor", "admin"}


# --------------------------------------------------------------------------
# 会话状态
# --------------------------------------------------------------------------
def init_state() -> None:
    ss = st.session_state
    ss.setdefault("page", "dashboard")
    ss.setdefault("theme", "light")
    ss.setdefault("user", None)
    ss.setdefault("loaded", False)
    ss.setdefault("toast", "")
    ss.setdefault("quiz_session", None)
    ss.setdefault("live_joined", set())


def handle_query_params() -> None:
    """把 URL 参数同步进会话状态。

    ⚠️ 只在**首次加载**时应用：sync_query_params() 会把当前页写回 URL，
    若每次重跑都读取，就会用 URL 里的旧值覆盖用户刚点击的导航，
    表现为「点任何菜单都停在仪表盘」。（回归用例见 tests/test_app.py）
    """
    if st.session_state.get("qp_applied"):
        return
    st.session_state.qp_applied = True
    qp = st.query_params
    if "theme" in qp and qp["theme"] in ("light", "dark"):
        st.session_state.theme = qp["theme"]
    if "p" in qp and qp["p"] in C.PAGES:
        st.session_state.page = qp["p"]
    if "q" in qp and qp["q"]:
        st.session_state.global_q = qp["q"]


def sync_query_params() -> None:
    qp = st.query_params
    qp["theme"] = C.theme()
    qp["p"] = C.current_page()


# --------------------------------------------------------------------------
# 登录 / 注册
# --------------------------------------------------------------------------
def login_gate() -> None:
    C.hero("BGL · AI LEARNING PLATFORM", "登录后开始学习",
           "一个面向 AI 学习者的在线平台：课程、知识点、测评、社区与直播课堂")
    left, right = st.columns([1, 1])

    with left:
        st.markdown("### 为什么在这里学 AI")
        for icon, t, d in [
            ("🧠", "知识点讲解", "24 个核心知识点，配公式、代码与难度分级"),
            ("✍️", "练习测评", "题库随机组卷、自动判分、错题本智能重练"),
            ("📚", "AI 课程学习", "章节化课程 + 试看 + 学习进度 + 结业证书"),
            ("💬", "讨论社区", "发帖、多级评论、@提及、文件共享"),
            ("📺", "直播课堂", "预约提醒、实时弹幕、互动投票、回放"),
        ]:
            st.markdown(
                f"<div class='bgl-card' style='padding:11px 14px;margin-bottom:8px'>"
                f"<b>{icon} {C.esc(t)}</b><div class='bgl-muted'>{C.esc(d)}</div></div>",
                unsafe_allow_html=True)
        C.note("演示账号：<b>admin / 123456</b>（管理员）、<b>fangyuan / 123456</b>（学员）、"
               "<b>liyuan / 123456</b>（讲师）。密码规则：恰好 6 位数字。")

    with right:
        tabs = st.tabs(["密码登录", "验证码登录", "注册", "忘记密码"])
        with tabs[0]:
            with st.form("login_form"):
                uname = st.text_input("用户名", placeholder="请输入用户名")
                pwd = st.text_input("密码", type="password", placeholder="6 位数字")
                submitted = st.form_submit_button("登录", type="primary", width="stretch")
            if submitted:
                try:
                    ratelimit.hit("login", raise_error=True)
                    u = auth.login(uname, pwd)
                    st.session_state.user = u
                    st.session_state.toast = f"欢迎回来，{u.get('nickname') or u['username']}"
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))
                except Exception as e:  # noqa: BLE001
                    C.err(f"登录失败：{e}")

        with tabs[1]:
            with st.form("sms_form"):
                phone = st.text_input("手机号", placeholder="11 位手机号", key="sms_phone")
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    code = st.text_input("验证码", placeholder="6 位验证码", key="sms_code")
                with col_b:
                    st.write("")
                    send = st.form_submit_button("获取验证码", width="stretch")
                go = st.form_submit_button("登录 / 注册", type="primary", width="stretch")
            if send and phone:
                try:
                    c = auth.send_code(phone, "sms", "login")
                    st.info(f"【演示模式】验证码为 **{c}**（真实环境将通过短信下发，{auth.CODE_TTL_SECONDS} 秒内有效）")
                except auth.AuthError as e:
                    C.err(str(e))
            if go:
                try:
                    if auth.get_user_by_name(f"u{phone[-6:]}") or db.query_one(
                            "SELECT 1 FROM users WHERE phone=?", (phone,)):
                        u = auth.login_by_phone(phone, code)
                    else:
                        uid = auth.register_by_phone(phone, code, "123456")
                        u = auth.get_user(uid)
                    st.session_state.user = u
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))

        with tabs[2]:
            with st.form("reg_form"):
                r_name = st.text_input("用户名", placeholder="2–20 位中文/字母/数字")
                r_pwd = st.text_input("密码（6 位数字）", type="password")
                r_pwd2 = st.text_input("确认密码", type="password")
                r_email = st.text_input("邮箱（可选，用于找回密码）")
                agree = st.checkbox("我已阅读并同意《用户协议》与《隐私政策》")
                reg = st.form_submit_button("注册", type="primary", width="stretch")
            if reg:
                try:
                    if not agree:
                        raise auth.AuthError("请先阅读并同意《用户协议》与《隐私政策》")
                    if r_pwd != r_pwd2:
                        raise auth.AuthError("两次输入的密码不一致")
                    ratelimit.hit("register", raise_error=True)
                    uid = auth.register(r_name, r_pwd, email=r_email)
                    st.session_state.user = auth.get_user(uid)
                    st.session_state.toast = "注册成功，欢迎加入！"
                    st.rerun()
                except auth.AuthError as e:
                    C.err(str(e))
            st.caption(f"当前注册用户 {auth.user_count()} / {auth.MAX_USERS} 人")

        with tabs[3]:
            st.caption("通过已绑定邮箱接收验证码重置密码")
            with st.form("reset_form"):
                r_email = st.text_input("注册邮箱", key="reset_email")
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    r_code = st.text_input("邮箱验证码", key="reset_code")
                with col_b:
                    st.write("")
                    r_send = st.form_submit_button("发送验证码", width="stretch")
                r_new = st.text_input("新密码（6 位数字）", type="password", key="reset_new")
                r_go = st.form_submit_button("重置密码", type="primary", width="stretch")
            if r_send and r_email:
                try:
                    c = auth.send_code(r_email, "email", "reset")
                    st.info(f"【演示模式】邮箱验证码为 **{c}**")
                except auth.AuthError as e:
                    C.err(str(e))
            if r_go:
                try:
                    auth.reset_password_by_email(r_email, r_code, r_new)
                    st.success("密码已重置，请使用新密码登录。")
                except auth.AuthError as e:
                    C.err(str(e))


# --------------------------------------------------------------------------
# 侧边栏
# --------------------------------------------------------------------------
def sidebar() -> None:
    with st.sidebar:
        st.markdown(
            f"<div style='padding:6px 2px 10px 2px'>"
            f"<div style='font-size:19px;font-weight:800;letter-spacing:.5px'>🎓 {C.esc(ver.APP_NAME)}</div>"
            f"<div class='bgl-muted'>v{ver.VERSION} · AI 学习平台</div></div>",
            unsafe_allow_html=True)

        u = C.current_user()
        if C.uid():
            st.markdown(
                f"<div class='bgl-card' style='padding:10px 12px'>{C.user_html(u)}"
                f"<div class='bgl-muted' style='margin-top:4px'>{C.esc(auth.presence_text(u))} · "
                f"{u.get('points', 0)} 积分</div></div>", unsafe_allow_html=True)
        else:
            C.note("当前未登录，登录后可发帖、购课与学习。", "warn")

        # 全站搜索
        with st.form("global_search", clear_on_submit=False):
            q = st.text_input("🔍 全站搜索", value=st.session_state.get("global_q", ""),
                              placeholder="新闻 / 帖子 / 文件 / 课程 / 用户…", label_visibility="collapsed")
            if st.form_submit_button("搜索", width="stretch"):
                st.session_state.global_q = q
                st.session_state.page = "dashboard"
                st.rerun()

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        # 分组导航
        groups: dict[str, list[str]] = {}
        for key, (icon, label, group) in C.PAGES.items():
            if key == "admin" and u.get("role") != "admin":
                continue
            if key == "instructor" and u.get("instructor_status") != "approved" and u.get("role") != "admin":
                continue
            groups.setdefault(group, []).append(key)

        cur = C.current_page()
        for group, keys in groups.items():
            st.markdown(f"<div class='bgl-muted' style='margin:10px 0 4px 2px'>{C.esc(group)}</div>",
                        unsafe_allow_html=True)
            for key in keys:
                icon, label, _ = C.PAGES[key]
                if st.button(f"{icon} {label}", key=f"nav_{key}", width="stretch",
                             type="primary" if key == cur else "secondary"):
                    C.goto(key)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            t_label = "🌙 深色" if C.theme() == "light" else "☀️ 浅色"
            if st.button(t_label, width="stretch", key="theme_btn"):
                C.toggle_theme()
                st.rerun()
        with c2:
            if C.uid() and st.button("退出", width="stretch", key="logout_btn"):
                auth.logout(C.uid())
                st.session_state.user = None
                st.session_state.page = "dashboard"
                st.rerun()

        if C.uid():
            un = notify.unread_count(C.uid()) + notify.unread_messages(C.uid())
            if un:
                st.markdown(f"<div class='bgl-muted' style='margin-top:6px'>🔔 {un} 条未读消息/通知</div>",
                            unsafe_allow_html=True)
        st.markdown(
            f"<div class='bgl-muted' style='margin-top:14px;font-size:11px'>"
            f"数据存储于本地 SQLite · 演示环境<br/>构建 {ver.BUILD_DATE}</div>",
            unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 内容区
# --------------------------------------------------------------------------
def search_results() -> None:
    kw = st.session_state.get("global_q", "").strip()
    if not kw:
        return
    res = search.global_search(kw, C.uid())
    total = search.total_hits(res)
    C.section(f"搜索「{kw}」", f"共命中 {total} 条")
    if not res:
        C.empty_state("🔍", "没有找到相关内容", "试试更换关键词，或浏览左侧各模块")
    route = {"新闻": "news", "帖子": "forum", "文件": "files", "用户": "profile",
             "课程": "learn", "直播": "live", "知识点": "knowledge"}
    for group, rows in res.items():
        st.markdown(f"**{group}**")
        for r in rows:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(
                        f"**{C.esc(r['title'])}**<div class='bgl-muted'>{C.esc(r.get('sub') or '')}</div>",
                        unsafe_allow_html=True)
                with b:
                    if st.button("前往", key=f"sr_{group}_{r['id']}", width="stretch"):
                        kw_id = {"新闻": "sel_news", "课程": "sel_course", "直播": "sel_live",
                                 "帖子": "sel_post", "知识点": "sel_kid", "文件": "sel_file"}.get(group, "")
                        C.goto(route.get(group, "dashboard"), **({kw_id: r["id"]} if kw_id else {}))
    if st.button("清除搜索", key="clear_search"):
        st.session_state.global_q = ""
        st.rerun()
    C.divider()


def render_current() -> None:
    from ui import (admin_view, dashboard, files_view, forum_view, instructor,
                    knowledge_view, learn, live_view, my_learning, news_view,
                    profile, quiz_view, store)

    renderers = {
        "dashboard": dashboard.render, "learn": learn.render, "knowledge": knowledge_view.render,
        "quiz": quiz_view.render, "my": my_learning.render, "news": news_view.render,
        "forum": forum_view.render, "files": files_view.render, "live": live_view.render,
        "store": store.render, "profile": profile.render, "instructor": instructor.render,
        "admin": admin_view.render,
    }
    page = C.current_page()
    if page in REQUIRE_LOGIN and not C.uid():
        C.hero("访问受限", C.PAGES[page][1], "该页面需要登录后访问")
        C.note("请在左侧完成登录或注册。", "warn")
        return
    renderers[page]()


@st.cache_resource(show_spinner=False)
def ensure_ready() -> str:
    """首启自举：确保数据库可用。

    云端/容器里 data/ 是空的，若不自举，第一次查询就会撞上「no such table: users」。
    这里在进程内只跑一次（st.cache_resource 保证），且**幂等**：
    已有数据的库不会被覆盖，因此本地开发库照旧。
    """
    db.init_db()
    if seed.is_seeded():
        return "ready"
    seed.seed_all()
    return "seeded"


def main() -> None:
    C.setup_page()
    C.inject()
    init_state()
    handle_query_params()
    sync_query_params()
    ensure_ready()

    u = st.session_state.get("user")
    if u:
        auth.heartbeat(u["id"])
        # 每次刷新同步一次用户信息，保证积分/等级实时
        fresh = auth.get_user(u["id"])
        if fresh:
            st.session_state.user = fresh

    sidebar()

    toast = st.session_state.pop("toast", "")
    if toast:
        st.toast(toast, icon="✅")

    if not C.uid():
        login_gate()
        return

    if st.session_state.get("global_q"):
        search_results()

    try:
        render_current()
    except auth.AuthError as e:
        C.err(f"操作未完成：{e}")
    except Exception as e:  # noqa: BLE001
        st.markdown(
            "<div class='bgl-empty'><span class='bgl-emoji'>🛠️</span>"
            "<div class='bgl-et'>页面出现了一点问题</div>"
            "<div>已记录错误信息，可返回首页或重试</div></div>", unsafe_allow_html=True)
        with st.expander("错误详情（供排查）"):
            st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)))
        if st.button("返回首页"):
            C.goto("dashboard")

    st.markdown(
        f"<div class='bgl-muted' style='text-align:center;margin-top:36px'>"
        f"{C.esc(ver.APP_NAME)} v{ver.VERSION} · 共 {C.esc(str(len(C.PAGES)))} 个功能模块 · "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()

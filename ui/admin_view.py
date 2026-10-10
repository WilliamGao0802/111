"""管理员后台：数据看板、审核队列、用户管理、内容管理、交易对账、访问日志、备份与系统设置。"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import admin, auth, backup, commerce, courses, db, forum, news, notify, seed, users
from ui import common as C


def _dashboard() -> None:
    d = admin.dashboard()
    r1 = st.columns(5)
    vals = [("注册用户", d["users"]), ("在线用户", d["active_users"]), ("认证讲师", d["instructors"]),
            ("在售课程", d["courses"]), ("报名人次", d["enrollments"])]
    for col, (lab, v) in zip(r1, vals):
        with col:
            C.stat(lab, v)
    r2 = st.columns(5)
    vals2 = [("发帖", d["posts"]), ("评论", d["comments"]), ("新闻", d["news"]),
             ("文件", d["files"]), ("知识点", d["knowledge"])]
    for col, (lab, v) in zip(r2, vals2):
        with col:
            C.stat(lab, v)
    r3 = st.columns(5)
    vals3 = [("GMV(元)", f"{d['gmv']:.2f}"), ("平台佣金", f"{d['commission']:.2f}"),
             ("已退款", f"{d['refunded']:.2f}"), ("待支付订单", d["pending_orders"]), ("风控订单", d["risk_orders"])]
    for col, (lab, v) in zip(r3, vals3):
        with col:
            C.stat(lab, v)

    C.divider()
    import altair as alt
    import pandas as pd
    c1, c2 = st.columns(2)
    with c1:
        C.section("近 14 天趋势", "注册 / 发帖 / 订单 / 学习")
        df = pd.DataFrame(admin.trend_data(14))
        long_df = df.melt("date", var_name="指标", value_name="数量")
        chart = (alt.Chart(long_df).mark_line(point=True)
                 .encode(x=alt.X("date:N", sort=None, title=""), y=alt.Y("数量:Q"),
                         color=alt.Color("指标:N"), strokeDash="指标:N")
                 .properties(height=280))
        st.altair_chart(chart, width="stretch")
    with c2:
        C.section("课程分类分布", "")
        cd = pd.DataFrame(admin.category_distribution())
        chart2 = (alt.Chart(cd).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                  .encode(x=alt.X("category:N", sort=None, title=""), y=alt.Y("count:Q", title="课程数"))
                  .properties(height=280))
        st.altair_chart(chart2, width="stretch")


def _moderation() -> None:
    q = admin.moderation_queue()
    C.section("审核队列", "所有需要人工处理的事项集中在这里")
    counts = {k: len(v) for k, v in q.items()}
    cols = st.columns(len(counts) or 1)
    for col, (k, v) in zip(cols, counts.items()):
        with col:
            C.stat({"reports": "举报", "news": "待审新闻", "instructors": "讲师申请",
                    "realnames": "实名申请", "refunds": "退款", "withdrawals": "提现",
                    "invoices": "发票"}.get(k, k), v)

    t = st.tabs(["🚩 举报", "📰 待审新闻", "🎓 讲师申请", "🪪 实名认证", "↩️ 退款", "💰 提现", "🧾 发票"])
    with t[0]:
        if not q["reports"]:
            C.empty_state("🚩", "没有待处理举报", "")
        for r in q["reports"]:
            with st.container(border=True):
                a, b = st.columns([4, 2])
                with a:
                    st.markdown(f"**{C.esc(r['target_type'])} #{r['target_id']}** · 举报人 "
                                f"{C.esc(r['reporter'] or '')}<div class='bgl-muted'>{C.esc(r['reason'])}</div>",
                                unsafe_allow_html=True)
                with b:
                    x, y, z = st.columns(3)
                    with x:
                        if st.button("隐藏内容", key=f"rp_h_{r['id']}"):
                            admin.hide_content(r["target_type"], r["target_id"])
                            forum.handle_report(r["id"], "handled")
                            st.rerun()
                    with y:
                        if st.button("驳回", key=f"rp_r_{r['id']}"):
                            forum.handle_report(r["id"], "rejected")
                            st.rerun()
                    with z:
                        if st.button("查看", key=f"rp_v_{r['id']}"):
                            if r["target_type"] == "post":
                                C.goto("forum", sel_post=r["target_id"])
    with t[1]:
        if not q["news"]:
            C.empty_state("📰", "没有待审新闻", "")
        for n in q["news"]:
            with st.container(border=True):
                a, b = st.columns([4, 2])
                with a:
                    st.markdown(f"**{C.esc(n['title'])}** {C.chip(n['category'])}"
                                f"<div class='bgl-muted'>{C.esc(n['summary'][:90])}…</div>"
                                f"<div class='bgl-muted'>来源 {C.esc(n['source'])}</div>", unsafe_allow_html=True)
                with b:
                    x, y = st.columns(2)
                    with x:
                        if st.button("发布", key=f"nw_p_{n['id']}", type="primary"):
                            news.publish_news(n["id"])
                            st.rerun()
                    with y:
                        if st.button("驳回", key=f"nw_r_{n['id']}"):
                            news.reject_news(n["id"])
                            st.rerun()
        if st.button("🔄 立即从可信源抓取", key="nw_fetch"):
            tpl = news.fetch_from_sources()
            for x in tpl:
                news.create_news(x["title"], x["summary"], x["content"], x["category"],
                                 x["tags"], x["source"], x["url"], status="pending")
            C.ok(f"已抓取 {len(tpl)} 条，进入待审核队列")
            st.rerun()
    with t[2]:
        if not q["instructors"]:
            C.empty_state("🎓", "没有待审讲师申请", "")
        for u_ in q["instructors"]:
            with st.container(border=True):
                st.markdown(f"**{C.esc(users.display_name(u_))}**（{C.esc(u_['username'])}）"
                            f"<div class='bgl-muted'>领域：{C.esc(u_.get('instructor_field') or '')}</div>"
                            f"<div class='bgl-muted'>简介：{C.esc(u_.get('instructor_intro') or '')}</div>"
                            f"<div class='bgl-muted'>资质：{C.esc(u_.get('instructor_proof') or '未提供')}</div>",
                            unsafe_allow_html=True)
                x, y = st.columns(2)
                with x:
                    if st.button("通过", key=f"ins_ok_{u_['id']}", type="primary"):
                        users.grant_instructor(u_["id"], True)
                        st.rerun()
                with y:
                    if st.button("驳回", key=f"ins_no_{u_['id']}"):
                        users.grant_instructor(u_["id"], False)
                        st.rerun()
    with t[3]:
        if not q["realnames"]:
            C.empty_state("🪪", "没有待审实名申请", "")
        for u_ in q["realnames"]:
            with st.container(border=True):
                st.markdown(f"**{C.esc(u_.get('real_name') or '')}** · {C.esc(u_.get('id_card') or '')} · "
                            f"{C.esc(u_.get('phone') or '')}", unsafe_allow_html=True)
                x, y = st.columns(2)
                with x:
                    if st.button("通过", key=f"rn_ok_{u_['id']}", type="primary"):
                        auth.review_realname(u_["id"], True)
                        st.rerun()
                with y:
                    if st.button("驳回", key=f"rn_no_{u_['id']}"):
                        auth.review_realname(u_["id"], False)
                        st.rerun()
    with t[4]:
        if not q["refunds"]:
            C.empty_state("↩️", "没有待处理退款", "")
        for r in q["refunds"]:
            with st.container(border=True):
                st.markdown(f"订单 {C.esc(r['order_no'])} · ¥{r['amount']:.2f} · "
                            f"{C.esc(r['username'] or '')}<div class='bgl-muted'>{C.esc(r['reason'])}</div>",
                            unsafe_allow_html=True)
                x, y = st.columns(2)
                with x:
                    if st.button("同意退款", key=f"rf_ok_{r['id']}", type="primary"):
                        commerce.review_refund(r["id"], True, C.uid())
                        st.rerun()
                with y:
                    if st.button("驳回", key=f"rf_no_{r['id']}"):
                        commerce.review_refund(r["id"], False, C.uid())
                        st.rerun()
    with t[5]:
        if not q["withdrawals"]:
            C.empty_state("💰", "没有待处理提现", "")
        for w in q["withdrawals"]:
            with st.container(border=True):
                st.markdown(f"{C.esc(w['username'] or '')} 申请提现 ¥{w['amount']:.2f} → "
                            f"{C.esc(w['account'])}<div class='bgl-muted'>{C.rel_time(w['created_at'])}</div>",
                            unsafe_allow_html=True)
                x, y = st.columns(2)
                with x:
                    if st.button("已打款", key=f"wd_ok_{w['id']}", type="primary"):
                        commerce.review_withdraw(w["id"], True, C.uid())
                        st.rerun()
                with y:
                    if st.button("驳回", key=f"wd_no_{w['id']}"):
                        commerce.review_withdraw(w["id"], False, C.uid())
                        st.rerun()
    with t[6]:
        if not q["invoices"]:
            C.empty_state("🧾", "没有待处理发票", "")
        for i in q["invoices"]:
            with st.container(border=True):
                st.markdown(f"订单 #{i['order_id']} · 抬头 {C.esc(i['title'])} · 税号 {C.esc(i['tax_no'] or '—')}",
                            unsafe_allow_html=True)
                x, y = st.columns(2)
                with x:
                    if st.button("开具", key=f"iv_ok_{i['id']}", type="primary"):
                        admin.review_invoice(i["id"], True)
                        st.rerun()
                with y:
                    if st.button("拒绝", key=f"iv_no_{i['id']}"):
                        admin.review_invoice(i["id"], False)
                        st.rerun()


def _user_admin() -> None:
    C.section("用户管理", "查看、封禁、调整角色与权限")
    f1, f2, f3 = st.columns(3)
    with f1:
        kw = st.text_input("🔍 搜索用户名/昵称/邮箱", key="au_kw")
    with f2:
        role = st.selectbox("角色", ["全部", "user", "instructor", "admin"], key="au_role")
    with f3:
        status = st.selectbox("状态", ["全部", "active", "banned", "cancelled"], key="au_status")
    rows = users.admin_list_users(kw, "" if role == "全部" else role,
                                 "" if status == "全部" else status)
    st.caption(f"共 {len(rows)} 个用户（上限 {auth.MAX_USERS} 人）")
    for u_ in rows:
        with st.container(border=True):
            a, b = st.columns([4, 2])
            with a:
                st.markdown(
                    f"{C.esc(users.avatar_of(u_))} <b>{C.esc(users.display_name(u_))}</b>"
                    f"（{C.esc(u_['username'])}）"
                    f"{C.chip(u_['role'], 'danger' if u_['role'] == 'admin' else 'gray')}"
                    f"{C.chip(u_['status'], 'ok' if u_['status'] == 'active' else 'danger')}"
                    f"{C.chip('已实名', 'ok') if u_['realname_status'] == 'approved' else ''}"
                    f"<div class='bgl-muted'>{C.esc(u_.get('email') or '未绑定邮箱')} · "
                    f"{u_['points']} 积分 · Lv.{u_['level']} · 注册于 {u_['created_at'][:10]}</div>",
                    unsafe_allow_html=True)
            with b:
                x, y, z = st.columns(3)
                with x:
                    if u_["status"] == "active":
                        if st.button("封禁", key=f"ub_{u_['id']}", width="stretch"):
                            users.set_user_status(u_["id"], "banned", "管理员操作")
                            st.rerun()
                    else:
                        if st.button("解封", key=f"uu_{u_['id']}", width="stretch"):
                            users.set_user_status(u_["id"], "active")
                            st.rerun()
                with y:
                    if st.button("设讲师", key=f"ur_{u_['id']}", width="stretch"):
                        users.grant_instructor(u_["id"], True)
                        st.rerun()
                with z:
                    if st.button("查看主页", key=f"uv_{u_['id']}", width="stretch"):
                        C.goto("profile", sel_user=u_["id"])


def _content_admin() -> None:
    C.section("内容管理", "帖子置顶/加精/隐藏、课程强制下架")
    t1, t2 = st.tabs(["💬 帖子", "📚 课程"])
    with t1:
        posts = forum.list_posts(sort="new", limit=50)
        for p in posts:
            with st.container(border=True):
                a, b = st.columns([4, 3])
                with a:
                    st.markdown(f"**{C.esc(p['title'] or p['content'][:30])}** {C.chip(p['topic'])}"
                                f"{C.chip('置顶', 'danger') if p['is_pinned'] else ''}"
                                f"{C.chip('精华', 'warn') if p['is_essence'] else ''}"
                                f"<div class='bgl-muted'>{C.esc(users.display_name(p))} · "
                                f"赞 {p['likes']} · 评论 {p['comment_count']}</div>", unsafe_allow_html=True)
                with b:
                    x, y, z = st.columns(3)
                    with x:
                        if st.button("置顶", key=f"ap_{p['id']}", width="stretch"):
                            forum.set_pin(p["id"], not p["is_pinned"])
                            st.rerun()
                    with y:
                        if st.button("加精", key=f"ae_{p['id']}", width="stretch"):
                            forum.set_essence(p["id"], not p["is_essence"])
                            st.rerun()
                    with z:
                        if st.button("隐藏", key=f"ah_{p['id']}", width="stretch"):
                            admin.hide_content("post", p["id"])
                            st.rerun()
    with t2:
        all_c = courses.list_courses(status="", limit=100)
        for c in all_c:
            with st.container(border=True):
                a, b = st.columns([4, 2])
                with a:
                    st.markdown(f"**{C.esc(c['title'])}** {C.chip(c['category'])}"
                                f"{C.chip({'on': '已上架', 'off': '已下架', 'draft': '草稿'}.get(c['status'], c['status']), 'gray')}"
                                f"<div class='bgl-muted'>讲师 {C.esc(c.get('instructor_nick') or '')} · "
                                f"{c['sales']} 人已学 · ⭐ {c['rating'] or '暂无'}</div>", unsafe_allow_html=True)
                with b:
                    if st.button("强制下架" if c["status"] == "on" else "恢复上架",
                                 key=f"ac_{c['id']}", width="stretch"):
                        courses.set_status(c["id"], "off" if c["status"] == "on" else "on",
                                           is_admin=True)
                        st.rerun()


def _trade_admin() -> None:
    C.section("交易对账", "订单流水、平台佣金、退款与提现")
    s = commerce.platform_summary()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        C.stat("GMV", f"¥{s['gmv']:.2f}")
    with c2:
        C.stat("平台佣金", f"¥{s['commission']:.2f}")
    with c3:
        C.stat("待处理退款", s["pending_refunds"])
    with c4:
        C.stat("待处理提现", s["pending_withdraws"])
    import pandas as pd
    t1, t2, t3 = st.tabs(["订单流水", "退款记录", "提现记录"])
    with t1:
        rows = commerce.order_flow(200)
        if rows:
            st.dataframe(pd.DataFrame([{
                "订单号": r["order_no"], "用户": r["username"], "金额": r["final_amount"],
                "状态": r["status"], "支付方式": r["pay_method"] or "—",
                "风控": r["risk_flag"] or "正常", "时间": r["created_at"][:16]} for r in rows]),
                width="stretch", hide_index=True)
        else:
            C.empty_state("📦", "暂无订单", "")
    with t2:
        rows = commerce.list_refunds()
        if rows:
            st.dataframe(pd.DataFrame([{
                "订单号": r["order_no"], "用户": r["username"], "金额": r["amount"],
                "状态": r["status"], "原因": r["reason"], "时间": r["created_at"][:16]} for r in rows]),
                width="stretch", hide_index=True)
        else:
            C.empty_state("↩️", "暂无退款", "")
    with t3:
        rows = commerce.list_withdrawals()
        if rows:
            st.dataframe(pd.DataFrame([{
                "用户": r["username"], "金额": r["amount"], "账户": r["account"],
                "状态": r["status"], "时间": r["created_at"][:16]} for r in rows]),
                width="stretch", hide_index=True)
        else:
            C.empty_state("💰", "暂无提现", "")


def _logs_and_data() -> None:
    t1, t2, t3 = st.tabs(["📜 访问日志", "💾 备份与恢复", "📢 公告与系统"])
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            action = st.text_input("按操作筛选（如 login / order）", key="lg_action")
        with c2:
            uname = st.text_input("按用户筛选", key="lg_user")
        rows = admin.recent_logs(300, action, uname)
        st.caption(f"共 {len(rows)} 条（最新在前）")
        import pandas as pd
        if rows:
            st.dataframe(pd.DataFrame([{
                "时间": r["created_at"], "用户": r["username"], "操作": r["action"],
                "详情": r["detail"]} for r in rows]), width="stretch", hide_index=True)
        else:
            C.empty_state("📜", "暂无日志", "")
    with t2:
        st.caption("备份文件保存在 data/backups/ 目录，可下载留存或用于一键恢复。")
        a, b = st.columns(2)
        with a:
            if st.button("💾 立即备份", type="primary", width="stretch", key="bk_new"):
                path = backup.create_backup("manual")
                C.ok(f"备份完成：{Path(path).name}")
        with b:
            data = backup.export_all()
            import json
            st.download_button("⬇ 导出全库 JSON", json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"),
                               file_name="bgl_backup.json", mime="application/json", width="stretch")
        bks = backup.list_backups()
        C.section("备份列表", f"{len(bks)} 个文件")
        if not bks:
            C.empty_state("💾", "还没有备份", "点击「立即备份」创建第一个")
        for bk in bks[:20]:
            a, b = st.columns([4, 1])
            with a:
                st.markdown(f"**{C.esc(bk['name'])}** <span class='bgl-muted'>· {bk['size_kb']} KB</span>",
                            unsafe_allow_html=True)
            with b:
                if st.button("恢复", key=f"rs_{bk['name']}", width="stretch"):
                    backup.restore_backup(bk["path"])
                    C.ok("已从备份恢复数据")
                    st.rerun()
        C.divider()
        st.caption("⚠️ 重置将清空当前全部数据并重新灌入演示数据，操作不可撤销。")
        with st.expander("危险操作：重置演示数据"):
            if st.button("确认重置（清空并重建）", key="reset_demo"):
                seed.reset_and_seed()
                st.session_state.user = auth.get_user_by_name("admin")
                C.ok("已重置为初始演示数据")
                st.rerun()
    with t3:
        with st.form("broadcast"):
            title = st.text_input("公告标题")
            content = st.text_area("公告内容", height=90)
            if st.form_submit_button("全站推送", type="primary"):
                if title.strip() and content.strip():
                    n = admin.broadcast(title.strip(), content.strip())
                    C.ok(f"已推送给 {n} 位用户")
        C.divider()
        st.markdown(f"**平台名称**：{C.esc(db.get_setting('platform_name', 'BGL 的 AI 学习'))}")
        st.markdown(f"**注册上限**：{auth.MAX_USERS} 人（当前 {auth.user_count()} 人）")
        st.markdown(f"**退款观看上限**：{int(commerce.REFUND_WATCH_LIMIT * 100)}%")
        st.markdown(f"**数据文件**：`{db.DB_PATH}`")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🧹 清理回收站过期文件", key="purge_files"):
                from core import files as files_mod
                n = files_mod.purge_expired()
                C.ok(f"已清理 {n} 个文件")
        with c2:
            if st.button("⏰ 关闭超时未支付订单", key="close_orders"):
                n = commerce.close_expired_orders()
                C.ok(f"已关闭 {n} 笔超时订单")


def render() -> None:
    if not C.is_admin():
        C.hero("ADMIN", "管理后台", "需要管理员权限")
        C.empty_state("🔒", "无权访问", "请使用管理员账号登录（演示：admin / 123456）")
        return
    C.hero("ADMIN CONSOLE", "管理后台", "数据看板 · 审核队列 · 用户与内容管理 · 交易对账 · 运维工具")
    tabs = st.tabs(["📊 数据看板", "🔍 审核队列", "👥 用户管理", "📚 内容管理", "💳 交易对账", "⚙️ 运维工具"])
    with tabs[0]:
        _dashboard()
    with tabs[1]:
        _moderation()
    with tabs[2]:
        _user_admin()
    with tabs[3]:
        _content_admin()
    with tabs[4]:
        _trade_admin()
    with tabs[5]:
        _logs_and_data()

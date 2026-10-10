"""课程商城与线上交易：商品、购物车、优惠券、积分抵扣、下单、支付、退款、发票、收益结算与提现。"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import auth, commerce, courses, db, notify
from ui import common as C

PTYPE_LABEL = {"course": "单课", "column": "专栏打包", "member": "会员订阅", "live_ticket": "直播单场票"}


# --------------------------------------------------------------------------
# 结算
# --------------------------------------------------------------------------
def _checkout(uid: int, product_ids: list[int]) -> None:
    items = [p for p in (commerce.get_product(i) for i in product_ids) if p]
    if not items:
        C.err("没有可结算的商品")
        return
    amount = round(sum(float(p["price"]) for p in items), 2)
    st.markdown("#### 确认订单")
    for p in items:
        st.markdown(f"- {C.esc(p['title'])}　{C.price_html(p['price'], p['original_price'])}",
                    unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        code = st.text_input("优惠券码", placeholder="如 WELCOME10 / NEW20 / VIP88", key="ck_coupon")
        coupon, discount, msg = commerce.validate_coupon(uid, code, amount)
        if code and msg:
            C.err(msg)
        elif coupon:
            C.ok(f"优惠券可用，立减 ¥{discount:.2f}")
    with c2:
        after_coupon = max(amount - discount, 0)
        max_pts = commerce.max_usable_points(uid, after_coupon)
        pts = st.slider(f"积分抵扣（可用 {max_pts} 分，100 分 = 1 元，最多抵 20%）",
                        0, max(0, max_pts), 0, key="ck_pts")

    pts_discount = commerce.points_discount(pts, after_coupon)
    final = round(max(after_coupon - pts_discount, 0), 2)
    st.markdown(
        f"<div class='bgl-card'>商品金额 ¥{amount:.2f}　－　优惠券 ¥{discount:.2f}　－　"
        f"积分抵扣 ¥{pts_discount:.2f}　＝　<b style='font-size:19px;color:var(--bgl-danger)'>应付 ¥{final:.2f}</b></div>",
        unsafe_allow_html=True)

    pay_method = st.selectbox("支付方式", list(commerce.PAY_METHODS.keys()),
                              format_func=lambda k: commerce.PAY_METHODS[k], key="ck_pay")
    a, b = st.columns(2)
    with a:
        simulate_fail = st.toggle("模拟支付失败（演示失败处理路径）", value=False, key="ck_fail")
    with b:
        st.caption("支付完成后自动开通课程权限（演示环境为本地模拟回调）")

    if st.button("提交订单", type="primary", width="stretch", key="ck_submit"):
        try:
            no = commerce.create_order(uid, [p["id"] for p in items], coupon_code=code,
                                       use_points=pts, pay_method=pay_method)
            st.session_state.pending_order = no
            st.rerun()
        except auth.AuthError as e:
            C.err(str(e))

    no = st.session_state.get("pending_order")
    if no:
        o = commerce.get_order(no)
        if o and o["status"] == "pending":
            C.divider()
            C.note(f"订单号 <b>{C.esc(no)}</b> 已创建，待支付金额 ¥{o['final_amount']:.2f}。")
            sig = commerce.sign_payload({"order_no": no, "amount": o["final_amount"],
                                         "method": pay_method})
            st.code(f"支付签名（二次校验用）：{sig}")
            p1, p2 = st.columns(2)
            with p1:
                if st.button("💳 立即支付", type="primary", width="stretch", key="ck_paynow"):
                    if simulate_fail:
                        st.session_state.pay_error = "支付失败：银行卡余额不足（演示）"
                        st.rerun()
                    else:
                        commerce.pay_order(no, pay_method, sig)
                        st.session_state.pending_order = None
                        C.ok("支付成功！课程已开通，可在「我的学习」查看。")
                        st.rerun()
            with p2:
                if st.button("关闭订单", width="stretch", key="ck_close"):
                    commerce.close_order(no)
                    st.session_state.pending_order = None
                    st.rerun()
            if st.session_state.get("pay_error"):
                C.err(st.session_state.pop("pay_error") + "　可修改支付方式后重新支付。")
        elif o and o["status"] == "paid":
            st.session_state.pending_order = None
            C.ok(f"订单 {no} 已支付。")


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------
def render() -> None:
    C.hero("COURSE STORE", "课程商城", "单课 / 专栏 / 会员 / 单场票 · 优惠券 · 积分抵扣 · 在线支付 · 退款售后")
    uid = C.uid()

    if st.session_state.get("sel_product"):
        pid = st.session_state.pop("sel_product")
        if not C.guard(uid, "购买课程"):
            return
        _checkout(uid, [pid])
        return

    s = commerce.platform_summary()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        C.stat("在售商品", len(commerce.list_products()))
    with c2:
        C.stat("我的购物车", len(commerce.list_cart(uid)) if uid else 0)
    with c3:
        C.stat("我的订单", len(commerce.list_orders(uid)) if uid else 0)
    with c4:
        C.stat("可提现余额", f"¥{commerce.instructor_balance(uid)['available']:.2f}" if uid else "—")

    tabs = st.tabs(["🛍 商品", "🛒 购物车", "📦 我的订单", "↩️ 退款售后", "💰 收益结算"])

    # ---------------- 商品 ----------------
    with tabs[0]:
        f1, f2 = st.columns([1, 3])
        with f1:
            ptype = st.selectbox("商品类型", ["全部"] + list(PTYPE_LABEL.keys()),
                                 format_func=lambda k: "全部" if k == "全部" else PTYPE_LABEL[k],
                                 key="st_type")
        with f2:
            kw = st.text_input("🔍 搜索商品", key="st_kw")
        rows = commerce.list_products("" if ptype == "全部" else ptype, keyword=kw)
        if not rows:
            C.empty_state("🛍", "暂无商品", "管理员同步课程商品后会显示在这里")
        cols = st.columns(3)
        owned_ids = set()
        if uid:
            owned_ids = {p["id"] for p in rows if commerce.is_purchased(uid, p["id"])}
        for i, p in enumerate(rows):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(
                        f"<b>{C.esc(p['title'])}</b> {C.chip(PTYPE_LABEL.get(p['ptype'], p['ptype']))}"
                        f"{C.chip('已拥有', 'ok') if p['id'] in owned_ids else ''}"
                        f"<div class='bgl-muted' style='margin:6px 0;min-height:36px'>"
                        f"{C.esc((p['description'] or '')[:56])}…</div>"
                        f"<div>{C.price_html(p['price'], p['original_price'])}</div>",
                        unsafe_allow_html=True)
                    a, b = st.columns(2)
                    with a:
                        if st.button("加入购物车", key=f"padd_{p['id']}", width="stretch"):
                            if C.guard(uid, "加入购物车"):
                                try:
                                    commerce.add_to_cart(uid, p["id"])
                                    C.ok("已加入购物车")
                                except auth.AuthError as e:
                                    C.err(str(e))
                    with b:
                        if st.button("立即购买", key=f"pbuy_{p['id']}", width="stretch",
                                     type="primary"):
                            if C.guard(uid, "购买商品"):
                                _checkout(uid, [p["id"]])

    # ---------------- 购物车 ----------------
    with tabs[1]:
        if not C.guard(uid, "使用购物车"):
            return
        items = commerce.list_cart(uid)
        if not items:
            C.empty_state("🛒", "购物车是空的", "去「商品」标签挑一门课程")
        else:
            for it in items:
                with st.container(border=True):
                    a, b = st.columns([4, 1])
                    with a:
                        st.markdown(f"**{C.esc(it['title'])}** {C.chip(PTYPE_LABEL.get(it['ptype'], ''))}"
                                    f"<div>{C.price_html(it['price'], it['original_price'])} × {it['qty']}</div>",
                                    unsafe_allow_html=True)
                    with b:
                        if st.button("移除", key=f"crm_{it['product_id']}", width="stretch"):
                            commerce.remove_from_cart(uid, it["product_id"])
                            st.rerun()
            total = commerce.cart_total(uid)
            st.markdown(f"**合计：¥{total:.2f}**")
            a, b = st.columns(2)
            with a:
                if st.button("批量结算", type="primary", width="stretch", key="cart_ck"):
                    _checkout(uid, [i["product_id"] for i in items])
            with b:
                if st.button("清空购物车", width="stretch", key="cart_clear"):
                    commerce.clear_cart(uid)
                    st.rerun()

    # ---------------- 订单 ----------------
    with tabs[2]:
        if not C.guard(uid, "查看订单"):
            return
        status_filter = st.selectbox("订单状态", ["全部", "pending", "paid", "refunded", "closed"],
                                     format_func=lambda x: {"全部": "全部", "pending": "待支付", "paid": "已支付",
                                                            "refunded": "已退款", "closed": "已关闭"}.get(x, x),
                                     key="od_status")
        orders = commerce.list_orders(uid, "" if status_filter == "全部" else status_filter)
        C.section("我的订单", f"共 {len(orders)} 笔")
        if not orders:
            C.empty_state("📦", "还没有订单", "购买课程后会显示在这里")
        for o in orders:
            label, kind = {"pending": ("待支付", "warn"), "paid": ("已支付", "ok"),
                           "refunded": ("已退款", "gray"), "closed": ("已关闭", "gray")}.get(o["status"], (o["status"], "gray"))
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    items_txt = "、".join(i["title"] for i in commerce.order_items(o["id"]))
                    st.markdown(
                        f"**{C.esc(o['order_no'])}** {C.chip(label, kind)}"
                        f"{C.chip(commerce.PAY_METHODS.get(o['pay_method'], '未选择'), 'gray')}"
                        f"{C.chip('风控:' + o['risk_flag'], 'danger') if o['risk_flag'] else ''}"
                        f"<div class='bgl-muted' style='margin-top:4px'>{C.esc(items_txt)}</div>"
                        f"<div class='bgl-muted'>应付 ¥{o['final_amount']:.2f}"
                        f"（原价 ¥{o['amount']:.2f} · 优惠 ¥{o['discount']:.2f}） · "
                        f"{C.rel_time(o['created_at'])}</div>", unsafe_allow_html=True)
                with b:
                    if o["status"] == "pending":
                        if st.button("去支付", key=f"op_{o['order_no']}", width="stretch", type="primary"):
                            st.session_state.pending_order = o["order_no"]
                            _checkout(uid, [i["product_id"] for i in commerce.order_items(o["id"])])
                    if o["status"] == "paid":
                        if st.button("申请发票", key=f"inv_{o['order_no']}", width="stretch"):
                            st.session_state.invoice_order = o["order_no"]
            if st.session_state.get("invoice_order") == o["order_no"]:
                with st.form(f"inv_form_{o['order_no']}"):
                    t = st.text_input("发票抬头", value=(C.current_user().get("nickname") or ""))
                    tn = st.text_input("税号（企业适用）")
                    em = st.text_input("接收邮箱", value=C.current_user().get("email") or "")
                    if st.form_submit_button("提交申请", type="primary"):
                        commerce.apply_invoice(uid, o["order_no"], t, tn, em)
                        st.session_state.pop("invoice_order", None)
                        C.ok("发票申请已提交，管理员审核后开具。")

    # ---------------- 退款 ----------------
    with tabs[3]:
        if not C.guard(uid, "退款售后"):
            return
        C.section("可申请退款的订单", f"规则：未开课或学习进度不超过 {int(commerce.REFUND_WATCH_LIMIT * 100)}%")
        paid = commerce.list_orders(uid, "paid")
        if not paid:
            C.empty_state("↩️", "暂无可退款的订单", "已支付的订单会显示在这里")
        for o in paid:
            okr, msg = commerce.refundable(o)
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    items_txt = "、".join(i["title"] for i in commerce.order_items(o["id"]))
                    st.markdown(f"**{C.esc(o['order_no'])}** · {C.esc(items_txt)}"
                                f"<div class='bgl-muted'>¥{o['final_amount']:.2f} · "
                                f"{'✅ 可申请退款' if okr else '⛔ ' + C.esc(msg)}</div>",
                                unsafe_allow_html=True)
                with b:
                    if okr and st.button("申请退款", key=f"rf_{o['order_no']}", width="stretch"):
                        st.session_state.refund_order = o["order_no"]
            if st.session_state.get("refund_order") == o["order_no"]:
                with st.form(f"rf_form_{o['order_no']}"):
                    r = st.text_area("退款原因", placeholder="请说明退款原因")
                    if st.form_submit_button("提交申请", type="primary"):
                        try:
                            commerce.apply_refund(uid, o["order_no"], r)
                            st.session_state.pop("refund_order", None)
                            C.ok("退款申请已提交，等待审核。")
                            st.rerun()
                        except auth.AuthError as e:
                            C.err(str(e))
        C.divider()
        C.section("退款记录", "")
        mine = [r for r in commerce.list_refunds() if r["user_id"] == uid]
        if not mine:
            C.empty_state("📄", "暂无退款记录", "")
        for r in mine:
            st.markdown(f"<div class='bgl-card'>订单 {C.esc(r['order_no'])} · ¥{r['amount']:.2f} · "
                        f"{C.chip({'pending': '处理中', 'approved': '已通过', 'rejected': '已驳回'}.get(r['status'], r['status']), 'warn')}"
                        f"<div class='bgl-muted'>{C.esc(r['reason'])} · {C.rel_time(r['created_at'])}</div></div>",
                        unsafe_allow_html=True)
        C.note("售后客服入口：可提交工单至 support@bgl.ai，或在讨论区 @管理员 反馈。")

    # ---------------- 收益 ----------------
    with tabs[4]:
        if not C.guard(uid, "查看收益"):
            return
        bal = commerce.instructor_balance(uid)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            C.stat("累计收益", f"¥{bal['income']:.2f}")
        with c2:
            C.stat("退款冲销", f"¥{bal['refunded']:.2f}")
        with c3:
            C.stat("已提现", f"¥{bal['withdrawn']:.2f}")
        with c4:
            C.stat("可提现", f"¥{bal['available']:.2f}")

        u = C.current_user()
        if u.get("instructor_status") == "approved":
            C.section("申请提现", "需绑定收款账户并完成实名认证")
            if not auth.is_realname_ok(uid):
                C.note("请先完成实名认证后再申请提现。", "warn")
            with st.form("wd_form"):
                amount = st.number_input("提现金额", 0.0, max(0.0, float(bal["available"])), 0.0, step=10.0)
                account = st.text_input("收款账户", placeholder="如 支付宝账号 / 银行卡号（脱敏展示）")
                if st.form_submit_button("提交提现申请", type="primary"):
                    try:
                        commerce.apply_withdraw(uid, amount, account)
                        C.ok("提现申请已提交，管理员审核后打款。")
                        st.rerun()
                    except auth.AuthError as e:
                        C.err(str(e))
            C.section("收益报表", "按日汇总")
            rep = commerce.revenue_report(uid, "day")
            if rep:
                import pandas as pd
                st.dataframe(pd.DataFrame(rep).rename(columns={"period": "日期", "total": "收益(元)", "orders": "订单数"}),
                             width="stretch", hide_index=True)
            else:
                C.empty_state("📈", "暂无收益数据", "有订单成交后会生成报表")
            C.section("收益明细", "")
            det = commerce.income_detail(uid)
            if det:
                import pandas as pd
                st.dataframe(pd.DataFrame([{"时间": d["created_at"][:16], "课程": d["title"],
                                            "金额": d["amount"], "订单": d["order_no"]} for d in det]),
                             width="stretch", hide_index=True)
        else:
            C.note("收益功能面向认证讲师开放。可前往「个人中心 → 申请成为讲师」。")

        C.divider()
        C.section("优惠券中心", "可用优惠券（平台发放）")
        mine_cp = commerce.my_coupons(uid, usable_only=True)
        if not mine_cp:
            C.empty_state("🎫", "暂无可用优惠券", "领取新人券后可在此使用")
        cols = st.columns(3)
        for i, cp in enumerate(mine_cp):
            with cols[i % 3]:
                desc = (f"满 {cp['min_amount']:.0f} 减 {cp['value']:.0f}"
                        if cp["ctype"] == "full_reduce" else
                        (f"{cp['value'] * 10:.1f} 折" if cp["ctype"] == "discount" else
                         f"新人券 ¥{cp['value']:.0f}"))
                st.markdown(f"<div class='bgl-card' style='text-align:center'>"
                            f"<div style='font-size:20px'>🎫</div><b>{C.esc(cp['code'])}</b>"
                            f"<div class='bgl-muted'>{desc}</div>"
                            f"<div class='bgl-muted'>有效期至 {C.esc(cp['expires_at'][:10])}</div></div>",
                            unsafe_allow_html=True)
        # 会员订阅商品（若无则提供创建入口）
        members = commerce.list_products("member")
        if not members:
            C.divider()
            C.note("尚未配置会员订阅商品。管理员可在「管理后台 → 商品管理」创建月卡 / 年卡。")

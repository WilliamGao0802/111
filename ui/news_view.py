"""AI 新闻：Top5 影响力、分类标签、搜索排序、详情、收藏点赞、归档、RSS、每日精选。"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import news
from ui import common as C


def _detail(nid: int) -> None:
    n = news.get_news(nid)
    if not n:
        C.empty_state("📰", "新闻不存在", "它可能已被移除")
        if st.button("← 返回列表"):
            C.goto("news")
        return
    C.breadcrumb("AI 新闻", n["category"], n["title"])
    if st.button("← 返回新闻列表", key="news_back"):
        C.goto("news")
    st.markdown(
        f"<div class='bgl-title' style='font-size:24px;margin-top:6px'>{C.esc(n['title'])}</div>"
        f"<div style='margin:8px 0 12px 0'>{C.chip(n['category'])}"
        f"{C.chips(str(n['tags']).split(','), 'gray')}"
        f"{C.chip('阅读 ' + str(n['views']), 'gray')}</div>"
        f"<div class='bgl-muted'>{C.esc(n['source'])} · 发布于 {C.esc(n['publish_time'][:16])}</div>",
        unsafe_allow_html=True)

    C.note(f"<b>摘要</b>：{C.esc(n['summary'])}")

    if n.get("image"):
        st.image(n["image"], width="stretch")

    body = (n.get("content") or n["summary"]).split("【要点】")
    st.markdown("#### 正文")
    for para in body[0].split("\n\n"):
        if para.strip():
            st.markdown(para.strip())
    if len(body) > 1:
        st.markdown("#### 关键要点")
        for line in body[1].strip().split("\n"):
            if line.strip():
                st.markdown(f"- {line.strip().lstrip('· ')}")

    uid = C.uid()
    liked = nid in news.liked_ids(uid)
    faved = nid in news.faved_ids(uid)
    c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
    with c1:
        if st.button(("💙 已赞" if liked else "🤍 点赞") + f" {n['likes']}", key="news_like"):
            try:
                news.toggle_like(uid, nid)
                st.rerun()
            except Exception as e:  # noqa: BLE001
                C.err(str(e))
    with c2:
        if st.button(("⭐ 已收藏" if faved else "☆ 收藏"), key="news_fav"):
            try:
                news.toggle_fav(uid, nid)
                st.rerun()
            except Exception as e:  # noqa: BLE001
                C.err(str(e))
    with c3:
        if n.get("url"):
            st.link_button("🔗 原文出处", n["url"], width="stretch")

    rel = news.related_news(nid, n["category"])
    if rel:
        C.section("相关新闻", f"同属「{n['category']}」")
        for r in rel:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                with a:
                    st.markdown(f"**{C.esc(r['title'])}**"
                                f"<div class='bgl-muted'>{C.esc(r['summary'][:70])}…</div>",
                                unsafe_allow_html=True)
                with b:
                    if st.button("阅读", key=f"nrel_{r['id']}", width="stretch"):
                        C.goto("news", sel_news=r["id"])
    if st.button("← 返回新闻列表", key="news_back2"):
        C.goto("news")


def render() -> None:
    if st.session_state.get("sel_news"):
        nid = st.session_state.pop("sel_news")
        _detail(nid)
        return

    C.hero("AI NEWS", "AI 新闻", "近一年最具影响力的进展 · 分类标签 · 实时更新 · 支持 RSS")

    # 每日精选 + 订阅
    pick = news.daily_pick()
    c1, c2 = st.columns([3, 2])
    with c1:
        if pick:
            C.section("今日精选", "每天为你挑一条")
            with st.container(border=True):
                st.markdown(f"**{C.esc(pick['title'])}** {C.chip(pick['category'])}"
                            f"<div class='bgl-muted'>{C.esc(pick['summary'][:88])}…</div>",
                            unsafe_allow_html=True)
                if st.button("阅读这条", key="daily_read"):
                    C.goto("news", sel_news=pick["id"])
    with c2:
        C.section("订阅与输出", "保持信息同步")
        uid = C.uid()
        if st.button("📩 推送今日精选到站内消息", width="stretch", key="sub_daily"):
            if C.guard(uid, "订阅推送"):
                news.push_daily([uid])
                C.ok("已推送，可在「个人中心 → 通知」查看。")
        st.download_button("📡 导出 RSS", news.to_rss(), file_name="bgl_ai_news.xml",
                           mime="application/rss+xml", width="stretch")
        if st.button("🗂 清理一年前新闻到「往期」", width="stretch", key="arch"):
            n = news.archive_old()
            C.ok(f"已归档 {n} 条超过一年的新闻。")

    # Top 5
    C.section("近一年最具影响力的 5 条", "按阅读量与点赞量综合排序")
    tops = news.top_news(5)
    if not tops:
        C.empty_state("📰", "暂无新闻", "请稍后再来")
        return
    cols = st.columns(5)
    for i, n in enumerate(tops):
        with cols[i]:
            rank = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
            st.markdown(
                f"<div class='bgl-card' style='min-height:190px'>"
                f"<div style='font-size:20px'>{rank}</div>"
                f"<div style='font-weight:600;font-size:13.5px;line-height:1.5;margin:6px 0'>{C.esc(n['title'][:40])}…</div>"
                f"<div>{C.chip(n['category'])}</div>"
                f"<div class='bgl-muted' style='margin-top:6px'>阅读 {n['views']} · 赞 {n['likes']}</div></div>",
                unsafe_allow_html=True)
            if st.button("阅读", key=f"top_{n['id']}", width="stretch"):
                C.goto("news", sel_news=n["id"])

    C.divider()
    # 筛选与排序
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    with f1:
        kw = st.text_input("🔍 搜索标题与摘要", key="news_kw", placeholder="如：微调 / 政策 / 芯片")
    with f2:
        cat = st.selectbox("分类", ["全部"] + news.CATEGORIES, key="news_cat")
    with f3:
        tag = st.selectbox("标签", ["全部"] + news.all_tags(), key="news_tag")
    with f4:
        sort = st.selectbox("排序", ["按时间", "按阅读量", "按点赞数"], key="news_sort")

    sort_key = {"按时间": "time", "按阅读量": "views", "按点赞数": "likes"}[sort]
    rows = news.list_news(category="" if cat == "全部" else cat,
                          tag="" if tag == "全部" else tag,
                          keyword=kw, sort=sort_key, limit=40)
    C.section("新闻列表", f"共 {len(rows)} 条")
    if not rows:
        C.empty_state("🔍", "没有匹配的新闻", "换个关键词或分类试试")

    uid = C.uid()
    liked = news.liked_ids(uid)
    faved = news.faved_ids(uid)
    for n in rows:
        with st.container(border=True):
            a, b = st.columns([4, 1])
            with a:
                st.markdown(
                    f"**{C.esc(n['title'])}** {C.chip(n['category'])}"
                    f"{C.chips(str(n['tags']).split(','), 'gray')}"
                    f"<div class='bgl-muted' style='margin-top:4px'>{C.esc(n['summary'][:96])}…</div>"
                    f"<div class='bgl-muted'>{C.esc(n['publish_time'][:16])} · {C.esc(n['source'])} · "
                    f"阅读 {n['views']} · 点赞 {n['likes']}</div>",
                    unsafe_allow_html=True)
            with b:
                if st.button("阅读全文", key=f"nl_{n['id']}", width="stretch"):
                    C.goto("news", sel_news=n["id"])
                lc, fc = st.columns(2)
                with lc:
                    mark = "💙" if n["id"] in liked else "🤍"
                    if st.button(mark, key=f"nlk_{n['id']}", width="stretch"):
                        try:
                            news.toggle_like(uid, n["id"])
                            st.rerun()
                        except Exception as e:  # noqa: BLE001
                            C.err(str(e))
                with fc:
                    mark2 = "⭐" if n["id"] in faved else "☆"
                    if st.button(mark2, key=f"nfv_{n['id']}", width="stretch"):
                        try:
                            news.toggle_fav(uid, n["id"])
                            st.rerun()
                        except Exception as e:  # noqa: BLE001
                            C.err(str(e))

    # 我的收藏 + 往期新闻
    C.divider()
    t1, t2 = st.tabs(["⭐ 我的收藏", "🗂 往期新闻（一年前）"])
    with t1:
        if not C.guard(uid, "查看收藏"):
            return
        favs = news.my_favs(uid)
        if not favs:
            C.empty_state("⭐", "还没有收藏", "点击新闻卡片上的 ☆ 即可收藏")
        for n in favs:
            with st.container(border=True):
                st.markdown(f"**{C.esc(n['title'])}** {C.chip(n['category'])}"
                            f"<div class='bgl-muted'>{C.esc(n['summary'][:80])}…</div>",
                            unsafe_allow_html=True)
                if st.button("阅读", key=f"fav_{n['id']}"):
                    C.goto("news", sel_news=n["id"])
    with t2:
        arch = news.list_news(archived=True, limit=30)
        if not arch:
            C.empty_state("🗂", "暂无归档新闻", "超过一年的新闻会自动归档到这里")
        for n in arch:
            st.markdown(f"- {C.esc(n['publish_time'][:10])} · {C.esc(n['title'])}",
                        unsafe_allow_html=True)

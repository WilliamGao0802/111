"""知识点讲解：模块浏览、搜索、难度筛选、详情（讲解 + 公式 + 代码 + 关联课程）。"""

from __future__ import annotations

import streamlit as st

from core import courses, knowledge
from ui import common as C


def _detail(kid: int) -> None:
    k = knowledge.get_knowledge(kid)
    if not k:
        C.empty_state("❓", "知识点不存在", "它可能已被移除")
        if st.button("← 返回列表"):
            C.goto("knowledge")
        return
    C.breadcrumb("知识点讲解", k["module"], k["title"])
    if st.button("← 返回知识点列表", key="kb_back"):
        C.goto("knowledge")
    st.markdown(
        f"<div class='bgl-title' style='font-size:23px;margin-top:6px'>{C.esc(k['title'])}</div>"
        f"<div style='margin:8px 0 12px 0'>{C.chip(k['module'])}{C.chip(k['difficulty'], 'warn')}"
        f"{C.chip('阅读 ' + str(k['views']), 'gray')}</div>",
        unsafe_allow_html=True)
    C.note(C.esc(k["summary"]))
    st.markdown("#### 📖 讲解")
    for para in (k["body"] or "").split("\n\n"):
        if para.strip():
            st.markdown(para.strip())
    if k.get("formula"):
        st.markdown("#### 🧮 关键公式")
        C.code_block(k["formula"])
    if k.get("code"):
        st.markdown("#### 💻 示例代码")
        C.code_block(k["code"])

    rel = knowledge.related(kid, k["module"])
    if rel:
        C.section("同模块知识点")
        cols = st.columns(2)
        for i, r in enumerate(rel):
            with cols[i % 2]:
                with st.container(border=True):
                    st.markdown(f"**{C.esc(r['title'])}** {C.chip(r['difficulty'], 'gray')}",
                                unsafe_allow_html=True)
                    if st.button("查看", key=f"kbrel_{r['id']}", width="stretch"):
                        C.goto("knowledge", sel_kid=r["id"])

    C.section("配套课程", "把这些原理落到动手实践")
    linked = [c for c in courses.list_courses(limit=50)
              if k["module"].split()[0] in (c["category"] or "") or c["category"] == k["module"]]
    if not linked:
        linked = courses.list_courses(limit=2)
    for c in linked[:3]:
        with st.container(border=True):
            a, b = st.columns([3, 1])
            with a:
                st.markdown(f"**{C.esc(c['title'])}** {C.chip(c['category'])}"
                            f"<div class='bgl-muted'>{C.esc((c['intro'] or '')[:70])}…</div>",
                            unsafe_allow_html=True)
            with b:
                st.markdown(f"<div style='text-align:right'>{C.price_html(c['price'], c['original_price'])}</div>",
                            unsafe_allow_html=True)
                if st.button("查看课程", key=f"kbc_{c['id']}", width="stretch"):
                    C.goto("learn", sel_course=c["id"])


def render() -> None:
    if st.session_state.get("sel_kid"):
        kid = st.session_state.pop("sel_kid")
        _detail(kid)
        return

    C.hero("KNOWLEDGE", "知识点讲解", "按模块组织的 AI 知识卡：讲解 + 公式 + 代码 + 难度分级")
    stats = knowledge.counts()
    c1, c2, c3 = st.columns(3)
    with c1:
        C.stat("知识点总数", stats["total"])
    with c2:
        C.stat("知识模块", stats["modules"])
    with c3:
        C.stat("累计阅读", stats["views"])

    st.markdown("")
    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        kw = st.text_input("🔍 搜索知识点", placeholder="如：注意力 / LoRA / 幻觉", key="kb_kw")
    with f2:
        mod = st.selectbox("模块", ["全部"] + knowledge.MODULES, key="kb_mod")
    with f3:
        diff = st.selectbox("难度", ["全部"] + knowledge.DIFFICULTIES, key="kb_diff")

    rows = knowledge.list_knowledge(
        module="" if mod == "全部" else mod,
        keyword=kw, difficulty="" if diff == "全部" else diff)
    C.divider()
    if not rows:
        C.empty_state("🔍", "没有匹配的知识点", "换个关键词或放宽筛选条件试试")
        return

    # 按模块分组展示
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["module"], []).append(r)
    for m, items in groups.items():
        C.section(f"{m}", f"{len(items)} 个知识点")
        cols = st.columns(2)
        for i, k in enumerate(items):
            with cols[i % 2]:
                with st.container(border=True):
                    st.markdown(
                        f"**{C.esc(k['title'])}** {C.chip(k['difficulty'], 'warn')}"
                        f"<div class='bgl-muted' style='margin-top:4px'>{C.esc(k['summary'][:76])}…</div>"
                        f"<div class='bgl-muted' style='margin-top:4px'>阅读 {k['views']}</div>",
                        unsafe_allow_html=True)
                    if st.button("开始学习 →", key=f"kb_{k['id']}", width="stretch"):
                        C.goto("knowledge", sel_kid=k["id"])

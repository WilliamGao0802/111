"""UI 共享层：主题、设计系统 CSS、通用组件与页面辅助函数。"""

from __future__ import annotations

import html
from datetime import datetime

import streamlit as st

import version as ver

# --------------------------------------------------------------------------
# 主题
# --------------------------------------------------------------------------
PALETTE = {
    "light": {
        "bg": "#f5f6fb", "surface": "#ffffff", "surface2": "#f0f2f9",
        "text": "#181a20", "muted": "#6b7280", "border": "#e4e7f0",
        "primary": "#5b5bd6", "primary_soft": "#eceafe", "accent": "#0ea5a4",
        "hero1": "#5b5bd6", "hero2": "#0ea5a4", "danger": "#d64545",
        "ok": "#1f9d55", "warn": "#c98a15", "shadow": "0 1px 2px rgba(20,22,40,.06), 0 8px 24px rgba(20,22,40,.06)",
    },
    "dark": {
        "bg": "#0c0e14", "surface": "#151824", "surface2": "#1b1f2e",
        "text": "#e9ebf3", "muted": "#98a1b3", "border": "#272c3b",
        "primary": "#8b8cf7", "primary_soft": "#23254a", "accent": "#38d9c9",
        "hero1": "#6d6ef0", "hero2": "#22b8ab", "danger": "#f0736f",
        "ok": "#3ecf8e", "warn": "#e2b04a", "shadow": "0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35)",
    },
}


def theme() -> str:
    return st.session_state.get("theme", "light")


def P() -> dict:
    return PALETTE[theme()]


def toggle_theme() -> None:
    st.session_state.theme = "dark" if theme() == "light" else "light"


def is_admin() -> bool:
    return (st.session_state.get("user") or {}).get("role") == "admin"


def uid() -> int:
    return int((st.session_state.get("user") or {}).get("id") or 0)


def current_user() -> dict:
    return st.session_state.get("user") or {}


# --------------------------------------------------------------------------
# 路由
# --------------------------------------------------------------------------
PAGES: dict[str, tuple[str, str, str]] = {
    "dashboard":  ("🏠", "首页仪表盘", "学习"),
    "learn":      ("📚", "AI 课程学习", "学习"),
    "knowledge":  ("🧠", "知识点讲解", "学习"),
    "quiz":       ("✍️", "练习测评", "学习"),
    "my":         ("🎯", "我的学习", "学习"),
    "news":       ("📰", "AI 新闻", "社区"),
    "forum":      ("💬", "讨论区", "社区"),
    "files":      ("📁", "文件区", "社区"),
    "live":       ("📺", "直播课堂", "社区"),
    "store":      ("🛒", "课程商城", "交易"),
    "profile":    ("👤", "个人中心", "我的"),
    "instructor": ("🎓", "讲师工作台", "我的"),
    "admin":      ("⚙️", "管理后台", "我的"),
}
PAGE_ORDER = list(PAGES.keys())


def goto(page: str, **state) -> None:
    """切换页面并带入上下文（如选中课程、新闻、直播）。"""
    st.session_state.page = page
    for k, v in state.items():
        st.session_state[k] = v
    st.rerun()


def current_page() -> str:
    pg = st.session_state.get("page", "dashboard")
    return pg if pg in PAGES else "dashboard"


# --------------------------------------------------------------------------
# 设计系统 CSS
# --------------------------------------------------------------------------
def _css() -> str:
    p = P()
    return f"""
<style>
:root, .stApp {{
  --bgl-bg:{p['bg']}; --bgl-surface:{p['surface']}; --bgl-surface2:{p['surface2']};
  --bgl-text:{p['text']}; --bgl-muted:{p['muted']}; --bgl-border:{p['border']};
  --bgl-primary:{p['primary']}; --bgl-primary-soft:{p['primary_soft']};
  --bgl-accent:{p['accent']}; --bgl-danger:{p['danger']}; --bgl-ok:{p['ok']}; --bgl-warn:{p['warn']};
  --background-color:{p['bg']}; --secondary-background-color:{p['surface']};
  --text-color:{p['text']}; --primary-color:{p['primary']};
}}
html, body, .stApp {{ background: var(--bgl-bg); color: var(--bgl-text); }}
* {{ font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{
  background: var(--bgl-surface); border-right: 1px solid var(--bgl-border);
}}
[data-testid="stSidebar"] * {{ color: var(--bgl-text); }}
.block-container {{ padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1180px; }}
h1,h2,h3,h4 {{ color: var(--bgl-text); letter-spacing:.2px; }}
a {{ color: var(--bgl-primary); }}

/* ---------- 基础组件 ---------- */
.bgl-hero {{
  background: linear-gradient(120deg, {p['hero1']} 0%, {p['hero2']} 100%);
  border-radius: 18px; padding: 22px 26px; color: #fff; margin-bottom: 18px;
  box-shadow: {p['shadow']};
}}
.bgl-hero h1 {{ color:#fff; margin:0 0 6px 0; font-size: 26px; font-weight: 700; }}
.bgl-hero p {{ margin:0; opacity:.92; font-size: 14px; line-height:1.7; }}
.bgl-hero .bgl-kicker {{ font-size:12px; letter-spacing:2px; text-transform:uppercase; opacity:.85; }}

.bgl-card {{
  background: var(--bgl-surface); border:1px solid var(--bgl-border); border-radius:14px;
  padding:16px 18px; margin-bottom:12px; box-shadow: {p['shadow']};
  transition: transform .16s ease, border-color .16s ease;
}}
.bgl-card:hover {{ transform: translateY(-2px); border-color: var(--bgl-primary); }}
.bgl-card h4 {{ margin:0 0 6px 0; font-size:15.5px; }}
.bgl-card p {{ margin:0; color: var(--bgl-muted); font-size:13px; line-height:1.7; }}

.bgl-title {{ font-size:19px; font-weight:700; margin:0 0 4px 0; }}
.bgl-sub {{ color: var(--bgl-muted); font-size:13px; margin:0 0 10px 0; }}
.bgl-muted {{ color: var(--bgl-muted); font-size:12.5px; }}
.bgl-divider {{ height:1px; background: var(--bgl-border); margin:14px 0; border:0; }}

.bgl-chip {{
  display:inline-block; padding:2px 9px; border-radius:999px; font-size:11.5px;
  background: var(--bgl-primary-soft); color: var(--bgl-primary); margin:0 6px 6px 0;
  border:1px solid transparent;
}}
.bgl-chip.gray {{ background: var(--bgl-surface2); color: var(--bgl-muted); }}
.bgl-chip.ok {{ background: rgba(31,157,85,.12); color: var(--bgl-ok); }}
.bgl-chip.warn {{ background: rgba(201,138,21,.14); color: var(--bgl-warn); }}
.bgl-chip.danger {{ background: rgba(214,69,69,.12); color: var(--bgl-danger); }}
.bgl-chip.accent {{ background: rgba(14,165,164,.13); color: var(--bgl-accent); }}

.bgl-stat {{
  background: var(--bgl-surface); border:1px solid var(--bgl-border); border-radius:14px;
  padding:14px 16px; text-align:left;
}}
.bgl-stat .bgl-num {{ font-size:22px; font-weight:700; color: var(--bgl-text); }}
.bgl-stat .bgl-lab {{ font-size:12px; color: var(--bgl-muted); margin-top:2px; }}

.bgl-price {{ color: var(--bgl-danger); font-weight:700; font-size:17px; }}
.bgl-price .bgl-old {{ color: var(--bgl-muted); font-weight:400; font-size:12px; text-decoration: line-through; margin-left:6px; }}
.bgl-free {{ color: var(--bgl-ok); font-weight:700; }}

.bgl-empty {{
  border:1.5px dashed var(--bgl-border); border-radius:16px; padding:34px 20px; text-align:center;
  color: var(--bgl-muted); background: var(--bgl-surface);
}}
.bgl-empty .bgl-emoji {{ font-size:34px; display:block; margin-bottom:8px; }}
.bgl-empty .bgl-et {{ font-size:15px; color: var(--bgl-text); font-weight:600; margin-bottom:4px; }}

.bgl-note {{
  border-left:3px solid var(--bgl-primary); background: var(--bgl-primary-soft);
  padding:10px 14px; border-radius:8px; font-size:13px; color: var(--bgl-text); margin:8px 0 12px 0;
}}
.bgl-note.warn {{ border-color: var(--bgl-warn); background: rgba(201,138,21,.10); }}
.bgl-note.danger {{ border-color: var(--bgl-danger); background: rgba(214,69,69,.09); }}

.bgl-quote {{
  background: var(--bgl-surface2); border-radius:10px; padding:12px 14px; font-size:13px;
  white-space: pre-wrap; line-height:1.85; color: var(--bgl-text);
}}
.bgl-code {{
  background: var(--bgl-surface2); border:1px solid var(--bgl-border); border-radius:10px;
  padding:12px 14px; font-family: ui-monospace, Consolas, monospace; font-size:12.5px;
  white-space: pre-wrap; overflow-x:auto; color: var(--bgl-text);
}}
.bgl-breadcrumb {{ font-size:12.5px; color: var(--bgl-muted); margin-bottom:10px; }}
.bgl-breadcrumb b {{ color: var(--bgl-text); font-weight:600; }}

.bgl-avatar {{
  display:inline-flex; align-items:center; justify-content:center; width:38px; height:38px;
  border-radius:50%; background: var(--bgl-primary-soft); font-size:19px; margin-right:10px;
  vertical-align: middle;
}}

@keyframes bglpulse {{ 0%{{opacity:.45}} 50%{{opacity:.95}} 100%{{opacity:.45}} }}
.bgl-skel {{
  background: linear-gradient(90deg, var(--bgl-surface2) 0%, var(--bgl-border) 50%, var(--bgl-surface2) 100%);
  background-size: 200% 100%; border-radius:10px; height: 15px; margin-bottom:10px;
  animation: bglpulse 1.4s ease-in-out infinite;
}}
@keyframes bglrise {{ from{{opacity:0; transform:translateY(6px)}} to{{opacity:1; transform:none}} }}
.bgl-anim {{ animation: bglrise .35s ease both; }}

/* ---------- Streamlit 控件微调 ---------- */
.stButton > button {{
  border-radius: 10px; border:1px solid var(--bgl-border); background: var(--bgl-surface);
  color: var(--bgl-text); font-size:13.5px; transition: all .15s ease;
}}
.stButton > button:hover {{ border-color: var(--bgl-primary); color: var(--bgl-primary); }}
.stButton > button[kind="primary"] {{
  background: var(--bgl-primary); border-color: var(--bgl-primary); color:#fff;
}}
.stButton > button[kind="primary"]:hover {{ filter: brightness(1.08); color:#fff; }}
.stTextInput input, .stTextArea textarea, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {{
  background: var(--bgl-surface); color: var(--bgl-text); border-radius:10px;
}}
/* 表单标签与页签的可读性（深色主题下默认灰字对比度不足，违反 WCAG AA）。
 * 注意：Streamlit 的控件标签是 <label data-testid="stWidgetLabel">，
 * 选择器不能带 div 标签限定符，否则主区标签一条都匹配不上。 */
[data-testid="stWidgetLabel"] p {{ color: var(--bgl-text); opacity:.88; }}
[data-testid="stTabs"] button {{ color: var(--bgl-muted) !important; }}
[data-testid="stTabs"] button p {{ color: inherit !important; }}
[data-testid="stTabs"] button[aria-selected="true"],
[data-testid="stTabs"] button[aria-selected="true"] p {{
  color: var(--bgl-text) !important; font-weight:600;
}}
[data-testid="stTabs"] button:hover p {{ color: var(--bgl-primary) !important; }}
[data-testid="stExpander"] summary span {{ color: var(--bgl-text); }}
[data-testid="stMarkdownContainer"] .bgl-muted {{ color: var(--bgl-muted); }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{
  color: var(--bgl-muted);
}}
[data-testid="stTabs"] button {{ font-size:13.5px; }}
[data-testid="stExpander"] {{ border:1px solid var(--bgl-border); border-radius:12px; background: var(--bgl-surface); }}
[data-testid="stMetricValue"] {{ font-size:22px; }}
.stDataFrame {{ border-radius:12px; overflow:hidden; }}
div[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius:14px; }}
</style>
"""


def setup_page(title_suffix: str = "") -> None:
    from core import db, seed
    db.init_db()
    if not seed.is_seeded():
        seed.seed_all()
    st.set_page_config(
        page_title=(ver.APP_NAME + (f" · {title_suffix}" if title_suffix else "")),
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def inject() -> None:
    st.markdown(_css(), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 通用组件
# --------------------------------------------------------------------------
def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def hero(kicker: str, title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""<div class="bgl-hero bgl-anim">
        <div class="bgl-kicker">{esc(kicker)}</div>
        <h1>{esc(title)}</h1>
        <p>{esc(subtitle)}</p></div>""",
        unsafe_allow_html=True,
    )


def breadcrumb(*items: str) -> None:
    parts = ['<span>首页</span>']
    for i, it in enumerate(items):
        parts.append("<span> / </span>")
        parts.append(f"<b>{esc(it)}</b>" if i == len(items) - 1 else f"<span>{esc(it)}</span>")
    st.markdown(f'<div class="bgl-breadcrumb">{"".join(parts)}</div>', unsafe_allow_html=True)


def section(title: str, desc: str = "") -> None:
    sub = f'<div class="bgl-sub">{esc(desc)}</div>' if desc else ""
    st.markdown(f'<div style="margin:18px 0 8px 0"><div class="bgl-title">{esc(title)}</div>{sub}</div>',
                unsafe_allow_html=True)


def chip(text: str, kind: str = "") -> str:
    cls = f"bgl-chip {kind}".strip()
    return f'<span class="{cls}">{esc(text)}</span>'


def chips(items, kind: str = "") -> str:
    return "".join(chip(x, kind) for x in (items or []) if str(x).strip())


def card(title: str, body_html: str = "", footer: str = "") -> None:
    st.markdown(
        f"""<div class="bgl-card bgl-anim"><h4>{esc(title)}</h4>
        <p>{body_html}</p>{footer}</div>""",
        unsafe_allow_html=True,
    )


def stat(label: str, value, delta: str = "") -> None:
    d = f'<span class="bgl-muted">　{esc(delta)}</span>' if delta else ""
    st.markdown(
        f"""<div class="bgl-stat bgl-anim"><div class="bgl-num">{esc(value)}</div>
        <div class="bgl-lab">{esc(label)}{d}</div></div>""",
        unsafe_allow_html=True,
    )


def empty_state(emoji: str, title: str, desc: str) -> None:
    st.markdown(
        f"""<div class="bgl-empty bgl-anim"><span class="bgl-emoji">{emoji}</span>
        <div class="bgl-et">{esc(title)}</div><div>{esc(desc)}</div></div>""",
        unsafe_allow_html=True,
    )


def note(text_html: str, kind: str = "") -> None:
    cls = f"bgl-note {kind}".strip()
    st.markdown(f'<div class="{cls}">{text_html}</div>', unsafe_allow_html=True)


def quote(text: str) -> None:
    st.markdown(f'<div class="bgl-quote">{esc(text)}</div>', unsafe_allow_html=True)


def code_block(code: str) -> None:
    st.markdown(f'<div class="bgl-code">{esc(code)}</div>', unsafe_allow_html=True)


def divider() -> None:
    st.markdown('<hr class="bgl-divider"/>', unsafe_allow_html=True)


def skeleton(lines: int = 3) -> None:
    st.markdown("".join(
        f'<div class="bgl-skel" style="width:{100 - i * 12}%"></div>' for i in range(lines)
    ), unsafe_allow_html=True)


def price_html(price: float, original: float = 0) -> str:
    if not price or float(price) <= 0:
        return '<span class="bgl-free">免费</span>'
    out = f'<span class="bgl-price">¥{float(price):.2f}</span>'
    if original and float(original) > float(price):
        out += f'<span class="bgl-old">¥{float(original):.2f}</span>'
    return out


def ok(msg: str) -> None:
    st.success(msg)


def err(msg: str) -> None:
    st.error(msg)


def guard(uid_value: int, action: str = "该操作") -> bool:
    """登录守卫：未登录时给出提示并返回 False。"""
    if not uid_value:
        note(f"{esc(action)}需要先登录。请在左侧登录或注册。", "warn")
        return False
    return True


def require_realname(u: dict) -> bool:
    if (u or {}).get("realname_status") == "approved":
        return True
    note("该操作需要完成<b>实名认证</b>，请前往「个人中心 → 实名认证」提交。", "warn")
    return False


def rel_time(ts: str) -> str:
    if not ts:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(ts, fmt)
            break
        except ValueError:
            dt = None
    if not dt:
        return ts
    sec = int((datetime.now() - dt).total_seconds())
    if sec < 60:
        return "刚刚"
    if sec < 3600:
        return f"{sec // 60} 分钟前"
    if sec < 86400:
        return f"{sec // 3600} 小时前"
    if sec < 86400 * 30:
        return f"{sec // 86400} 天前"
    return ts[:10]


def user_html(user: dict, show_level: bool = True) -> str:
    from core import auth, users as users_mod
    if not user:
        return '<span class="bgl-muted">已注销用户</span>'
    name = esc(users_mod.display_name(user))
    av = esc(users_mod.avatar_of(user))
    lv = ""
    if show_level:
        lv = f' <span class="bgl-chip gray">Lv.{user.get("level", 1)} {esc(auth.level_title(user.get("level", 1)))}</span>'
    role = ""
    if user.get("role") == "admin":
        role = ' <span class="bgl-chip danger">管理员</span>'
    elif user.get("instructor_status") == "approved":
        role = ' <span class="bgl-chip accent">讲师</span>'
    return f'<span class="bgl-avatar">{av}</span><b>{name}</b>{role}{lv}'


def news_card(n: dict, extra_html: str = "") -> str:
    return f"""<div class="bgl-card bgl-anim">
      <h4>{esc(n['title'])}</h4>
      <p>{esc(n['summary'])}</p>
      <div style="margin-top:8px">{chip(n['category'])}{chips(str(n.get('tags') or '').split(','), 'gray')}</div>
      <div class="bgl-muted" style="margin-top:6px">{esc(n.get('source') or '')} · {esc(n.get('publish_time','')[:16])}
      · 阅读 {n.get('views',0)} · 点赞 {n.get('likes',0)}</div>{extra_html}</div>"""

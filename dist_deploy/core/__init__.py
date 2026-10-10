"""BGL 的 AI 学习 —— 业务逻辑层（core）。

约定（技能「八条铁律」第 2 条）：本包内**不允许 import streamlit**，
所有业务逻辑必须能脱离 UI 独立运行与测试。
"""

from . import (  # noqa: F401
    admin,
    auth,
    backup,
    commerce,
    courses,
    db,
    files,
    forum,
    knowledge,
    live,
    news,
    notify,
    quiz,
    ratelimit,
    search,
    seed,
    users,
)

__all__ = [
    "admin", "auth", "backup", "commerce", "courses", "db", "files", "forum",
    "knowledge", "live", "news", "notify", "quiz", "ratelimit", "search", "seed", "users",
]

__version__ = "1.0.0"

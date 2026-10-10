"""限流与防刷：对登录、发帖、上传、下单等接口做频率限制。"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import auth, db

DEFAULT_LIMITS = {
    "login": (10, 300),      # 5 分钟内最多 10 次
    "register": (5, 600),
    "post": (10, 600),
    "comment": (30, 600),
    "upload": (20, 600),
    "order": (10, 600),
    "chat": (60, 300),
    "search": (60, 300),
}


def _cleanup() -> None:
    db.execute("DELETE FROM rate_events WHERE created_at < ?", (db.days_ago_str(1),))


def count(bucket: str, window: int) -> int:
    since = (datetime.now() - timedelta(seconds=window)).strftime("%Y-%m-%d %H:%M:%S")
    return int(db.scalar("SELECT COUNT(*) FROM rate_events WHERE bucket=? AND created_at>=?",
                         (bucket, since), 0))


def hit(bucket: str, limit: int | None = None, window: int | None = None, raise_error: bool = True) -> bool:
    """记一次事件。超限返回 False（raise_error=True 时抛 AuthError）。"""
    if limit is None or window is None:
        d_limit, d_window = DEFAULT_LIMITS.get(bucket, (60, 600))
        limit = limit if limit is not None else d_limit
        window = window if window is not None else d_window
    _cleanup()
    if count(bucket, window) >= limit:
        if raise_error:
            raise auth.AuthError(f"操作过于频繁，请稍后再试（{window // 60} 分钟内最多 {limit} 次）")
        return False
    db.execute("INSERT INTO rate_events(bucket,created_at) VALUES(?,?)", (bucket, db.now_str()))
    return True


def remaining(bucket: str) -> int:
    limit, window = DEFAULT_LIMITS.get(bucket, (60, 600))
    return max(0, limit - count(bucket, window))

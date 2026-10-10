"""数据库层：SQLite 连接管理 + 全量建表。

本模块是 core 包的底座，**不 import streamlit**，可在离线环境独立测试。
设计原则（见技能「八条铁律」第 2 条）：业务逻辑与 UI 框架解耦，
未来换成 PostgreSQL 时只需替换本文件的实现，上层模块无需改动。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.environ.get("BGL_DB_PATH", str(DATA_DIR / "bgl.db")))

_local = threading.local()
_write_lock = threading.RLock()

# --------------------------------------------------------------------------
# 表结构：覆盖需求书全部数据实体（用户/新闻/互动/直播/课程/交易/风控/日志）
# --------------------------------------------------------------------------
SCHEMA = """
PRAGMA foreign_keys = ON;

-- ============ 一、用户系统 ============
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    salt            TEXT    NOT NULL,
    nickname        TEXT    DEFAULT '',
    avatar          TEXT    DEFAULT '',
    bio             TEXT    DEFAULT '',
    email           TEXT    DEFAULT '',
    phone           TEXT    DEFAULT '',
    role            TEXT    NOT NULL DEFAULT 'user',      -- user/instructor/admin
    real_name       TEXT    DEFAULT '',
    id_card         TEXT    DEFAULT '',
    realname_status TEXT    NOT NULL DEFAULT 'none',      -- none/pending/approved/rejected
    phone_verified  INTEGER NOT NULL DEFAULT 0,
    email_verified  INTEGER NOT NULL DEFAULT 0,
    points          INTEGER NOT NULL DEFAULT 0,
    level           INTEGER NOT NULL DEFAULT 1,
    status          TEXT    NOT NULL DEFAULT 'active',    -- active/banned/cancelled
    instructor_status TEXT  NOT NULL DEFAULT 'none',      -- none/pending/approved/rejected
    instructor_intro  TEXT  DEFAULT '',
    instructor_field  TEXT  DEFAULT '',
    instructor_proof  TEXT  DEFAULT '',
    instructor_level  INTEGER NOT NULL DEFAULT 1,
    online          INTEGER NOT NULL DEFAULT 0,
    fail_count      INTEGER NOT NULL DEFAULT 0,
    locked_until    TEXT    DEFAULT '',
    created_at      TEXT    NOT NULL,
    last_active_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS follows (
    follower_id INTEGER NOT NULL,
    followee_id INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,
    PRIMARY KEY (follower_id, followee_id),
    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (followee_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS verifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target      TEXT NOT NULL,             -- 手机号或邮箱
    channel     TEXT NOT NULL,             -- sms/email
    code        TEXT NOT NULL,
    purpose     TEXT NOT NULL,             -- login/register/reset
    expires_at  TEXT NOT NULL,
    tries       INTEGER NOT NULL DEFAULT 0,
    used        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS points_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    delta       INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- ============ 二、AI 新闻模块 ============
CREATE TABLE IF NOT EXISTS news (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    content      TEXT NOT NULL DEFAULT '',
    category     TEXT NOT NULL DEFAULT '大模型',
    tags         TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT '',
    url          TEXT NOT NULL DEFAULT '',
    image        TEXT NOT NULL DEFAULT '',
    publish_time TEXT NOT NULL,
    views        INTEGER NOT NULL DEFAULT 0,
    likes        INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'published',   -- pending/published
    archived     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS news_likes (
    user_id INTEGER NOT NULL, news_id INTEGER NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, news_id)
);
CREATE TABLE IF NOT EXISTS news_favs (
    user_id INTEGER NOT NULL, news_id INTEGER NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, news_id)
);

-- ============ 三、互动功能区 ============
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL,
    topic      TEXT NOT NULL DEFAULT '综合讨论',
    tags       TEXT NOT NULL DEFAULT '',
    is_pinned  INTEGER NOT NULL DEFAULT 0,
    is_essence INTEGER NOT NULL DEFAULT 0,
    edited     INTEGER NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'published',   -- published/hidden
    likes      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id    INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    parent_id  INTEGER NOT NULL DEFAULT 0,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS post_likes (
    user_id INTEGER NOT NULL, post_id INTEGER NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, post_id)
);
CREATE TABLE IF NOT EXISTS drafts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    title      TEXT DEFAULT '',
    content    TEXT DEFAULT '',
    topic      TEXT DEFAULT '综合讨论',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT NOT NULL,      -- post/comment/file/user
    target_id   INTEGER NOT NULL,
    reporter_id INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',   -- pending/handled/rejected
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    ntype      TEXT NOT NULL,       -- like/comment/follow/mention/live/system/order
    content    TEXT NOT NULL,
    link       TEXT DEFAULT '',
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id    INTEGER NOT NULL,
    to_id      INTEGER NOT NULL,
    content    TEXT NOT NULL,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    filename      TEXT NOT NULL,
    stored_name   TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT '其他',
    tags          TEXT NOT NULL DEFAULT '',
    size          INTEGER NOT NULL DEFAULT 0,
    mime          TEXT NOT NULL DEFAULT '',
    visibility    TEXT NOT NULL DEFAULT 'public',   -- public/login/private
    downloads     INTEGER NOT NULL DEFAULT 0,
    last_download TEXT DEFAULT '',
    version       INTEGER NOT NULL DEFAULT 1,
    root_id       INTEGER NOT NULL DEFAULT 0,       -- 同名文件归组，0 表示自身为最新
    is_latest     INTEGER NOT NULL DEFAULT 1,
    deleted       INTEGER NOT NULL DEFAULT 0,
    deleted_at    TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);

-- ============ 四、课程 / 直播 / 讲师 ============
CREATE TABLE IF NOT EXISTS courses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    instructor_id INTEGER NOT NULL,
    title         TEXT NOT NULL,
    cover         TEXT DEFAULT '',
    intro         TEXT DEFAULT '',
    outline       TEXT DEFAULT '',
    category      TEXT NOT NULL DEFAULT '大模型基础',
    tags          TEXT DEFAULT '',
    price         REAL NOT NULL DEFAULT 0,
    original_price REAL NOT NULL DEFAULT 0,
    ctype         TEXT NOT NULL DEFAULT 'recorded',  -- live/recorded/text
    status        TEXT NOT NULL DEFAULT 'on',        -- draft/on/off
    rating        REAL NOT NULL DEFAULT 0,
    rating_count  INTEGER NOT NULL DEFAULT 0,
    sales         INTEGER NOT NULL DEFAULT 0,
    validity_days INTEGER NOT NULL DEFAULT 0,        -- 0 表示永久
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chapters (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    title     TEXT NOT NULL,
    order_no  INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS lessons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id  INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    title      TEXT NOT NULL,
    ltype      TEXT NOT NULL DEFAULT 'video',  -- video/live/doc/quiz
    content    TEXT DEFAULT '',
    duration   INTEGER NOT NULL DEFAULT 0,
    is_free    INTEGER NOT NULL DEFAULT 0,
    order_no   INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS enrollments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    course_id        INTEGER NOT NULL,
    order_id         INTEGER NOT NULL DEFAULT 0,
    progress         REAL NOT NULL DEFAULT 0,
    completed        INTEGER NOT NULL DEFAULT 0,
    certificate_code TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    expires_at       TEXT DEFAULT '',
    UNIQUE (user_id, course_id)
);
CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id    INTEGER NOT NULL,
    lesson_id  INTEGER NOT NULL,
    course_id  INTEGER NOT NULL,
    completed  INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, lesson_id)
);
CREATE TABLE IF NOT EXISTS course_reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id  INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    rating     INTEGER NOT NULL DEFAULT 5,
    content    TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS course_qa (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id  INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT DEFAULT '',
    answer_by  INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lives (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id     INTEGER NOT NULL DEFAULT 0,
    instructor_id INTEGER NOT NULL,
    title         TEXT NOT NULL,
    cover         TEXT DEFAULT '',
    intro         TEXT DEFAULT '',
    start_at      TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'upcoming',  -- upcoming/live/replay/ended
    price         REAL NOT NULL DEFAULT 0,
    replay_access TEXT NOT NULL DEFAULT 'paid',      -- free/paid/limited
    online_count  INTEGER NOT NULL DEFAULT 0,
    likes         INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS live_reservations (
    live_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    reminded INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
    PRIMARY KEY (live_id, user_id)
);
CREATE TABLE IF NOT EXISTS live_chat (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    live_id    INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS live_interactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    live_id    INTEGER NOT NULL,
    itype      TEXT NOT NULL,      -- poll/question/lottery/quiz
    question   TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS live_votes (
    interaction_id INTEGER NOT NULL, user_id INTEGER NOT NULL, choice TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (interaction_id, user_id)
);
CREATE TABLE IF NOT EXISTS live_handraise (
    live_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL,
    PRIMARY KEY (live_id, user_id)
);

-- ============ 五、网课售卖与线上交易 ============
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ptype        TEXT NOT NULL,        -- course/column/member/live_ticket
    ref_id       INTEGER NOT NULL DEFAULT 0,
    title        TEXT NOT NULL,
    cover        TEXT DEFAULT '',
    description  TEXT DEFAULT '',
    price        REAL NOT NULL DEFAULT 0,
    original_price REAL NOT NULL DEFAULT 0,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cart (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    qty        INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, product_id)
);
CREATE TABLE IF NOT EXISTS coupons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    ctype       TEXT NOT NULL,        -- full_reduce/discount/newcomer
    value       REAL NOT NULL,
    min_amount  REAL NOT NULL DEFAULT 0,
    expires_at  TEXT NOT NULL,
    max_uses    INTEGER NOT NULL DEFAULT 1,
    used_count  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS user_coupons (
    user_id INTEGER NOT NULL, coupon_id INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, coupon_id)
);
CREATE TABLE IF NOT EXISTS orders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no      TEXT NOT NULL UNIQUE,
    user_id       INTEGER NOT NULL,
    amount        REAL NOT NULL DEFAULT 0,
    discount      REAL NOT NULL DEFAULT 0,
    points_used   INTEGER NOT NULL DEFAULT 0,
    final_amount  REAL NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending/paid/refunded/closed
    pay_method    TEXT DEFAULT '',
    coupon_id     INTEGER NOT NULL DEFAULT 0,
    is_flashsale  INTEGER NOT NULL DEFAULT 0,
    group_buy     INTEGER NOT NULL DEFAULT 0,
    risk_flag     TEXT DEFAULT '',
    paid_at       TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    title      TEXT NOT NULL,
    price      REAL NOT NULL DEFAULT 0,
    qty        INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS refunds (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    amount     REAL NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'pending',   -- pending/approved/rejected
    created_at TEXT NOT NULL,
    handled_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS transactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    ttype      TEXT NOT NULL,     -- income/commission/withdraw/refund/purchase
    amount     REAL NOT NULL DEFAULT 0,
    order_id   INTEGER NOT NULL DEFAULT 0,
    status     TEXT NOT NULL DEFAULT 'done',
    note       TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS withdrawals (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    amount     REAL NOT NULL DEFAULT 0,
    account    TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'pending',   -- pending/paid/rejected
    created_at TEXT NOT NULL,
    handled_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS invoices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    title      TEXT NOT NULL,
    tax_no     TEXT DEFAULT '',
    email      TEXT DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

-- ============ 六、知识点 / 练习测评 ============
CREATE TABLE IF NOT EXISTS knowledge (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    module     TEXT NOT NULL,        -- 所属知识模块
    title      TEXT NOT NULL,
    summary    TEXT DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    formula    TEXT DEFAULT '',
    code       TEXT DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT '入门',
    order_no   INTEGER NOT NULL DEFAULT 1,
    views      INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    module      TEXT NOT NULL,
    qtype       TEXT NOT NULL DEFAULT 'single',   -- single/multi/judge/blank
    stem        TEXT NOT NULL,
    options     TEXT NOT NULL DEFAULT '[]',
    answer      TEXT NOT NULL,
    analysis    TEXT DEFAULT '',
    difficulty  TEXT NOT NULL DEFAULT '入门',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    mode         TEXT NOT NULL DEFAULT 'practice',  -- practice/exam
    module       TEXT NOT NULL DEFAULT '',
    total        INTEGER NOT NULL DEFAULT 0,
    correct      INTEGER NOT NULL DEFAULT 0,
    score        REAL NOT NULL DEFAULT 0,
    detail       TEXT NOT NULL DEFAULT '[]',
    duration     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wrong_book (
    user_id    INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    times      INTEGER NOT NULL DEFAULT 1,
    last_at    TEXT NOT NULL,
    PRIMARY KEY (user_id, question_id)
);

-- ============ 七、数据、安全与运维 ============
CREATE TABLE IF NOT EXISTS access_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL DEFAULT 0,
    username   TEXT DEFAULT '',
    action     TEXT NOT NULL,
    detail     TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket     TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


# 从建表语句中解析出全部表名（供重置、备份使用），避免手工维护两份清单
TABLE_NAMES: list[str] = re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", SCHEMA)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def days_ago_str(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


@contextmanager
def tx():
    """写事务：加锁串行化，异常回滚。"""
    conn = get_conn()
    with _write_lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query(sql: str, params=()) -> list:
    cur = get_conn().execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params=()):
    cur = get_conn().execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else None


def execute(sql: str, params=()) -> int:
    """执行写语句，返回 lastrowid。"""
    with tx() as conn:
        cur = conn.execute(sql, params)
        return cur.lastrowid


def execute_many(sql: str, seq) -> int:
    with tx() as conn:
        cur = conn.executemany(sql, seq)
        return cur.rowcount


def scalar(sql: str, params=(), default=0):
    row = query_one(sql, params)
    if not row:
        return default
    v = list(row.values())[0]
    return default if v is None else v


def get_setting(key: str, default=None):
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def set_setting(key: str, value) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


def init_db(force: bool = False) -> None:
    """建表。force=True 时先删表再重建（不删除数据库文件）。

    注意：不使用「删除 .db 文件」的方式重置——在 Windows 上，只要还有打开的连接
    就无法删除文件（WinError 32），而同一进程内不同线程各持有连接是常态。
    用 DROP TABLE 的方式在任何平台都可靠。
    """
    conn = get_conn()
    with _write_lock:
        if force:
            for t in TABLE_NAMES:
                try:
                    conn.execute(f"DROP TABLE IF EXISTS {t}")
                except sqlite3.Error:
                    pass
        conn.executescript(SCHEMA)
        conn.commit()


def reset_db() -> None:
    """清空全部业务数据并重建（演示数据重置用）。"""
    init_db(force=True)

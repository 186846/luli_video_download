"""SQLite 连接与表结构（用户 / 会话 / 订单 / Stripe 事件）。"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from app import config

_lock = threading.Lock()
_initialized_paths: set[str] = set()


def db_path() -> Path:
    return config.DB_PATH


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """创建表（幂等）。"""
    path_key = str(db_path().resolve())
    with _lock:
        if path_key in _initialized_paths:
            return
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    is_vip INTEGER NOT NULL DEFAULT 0,
                    stripe_customer_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    stripe_checkout_session_id TEXT UNIQUE,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    amount_cents INTEGER NOT NULL DEFAULT 990,
                    currency TEXT NOT NULL DEFAULT 'usd',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    paid_at TEXT
                );

                CREATE TABLE IF NOT EXISTS stripe_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    processed_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS ai_daily_usage (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    usage_date TEXT NOT NULL,
                    summarize_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, usage_date)
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
                CREATE INDEX IF NOT EXISTS idx_ai_usage_date ON ai_daily_usage(usage_date);
                """
            )
            conn.commit()
            _initialized_paths.add(path_key)
        finally:
            conn.close()


def get_conn() -> sqlite3.Connection:
    init_db()
    return _connect()


def configure_db_path(path: Path) -> None:
    """测试用：切换库文件并强制下次 init。"""
    global _initialized_paths
    config.DB_PATH = Path(path)
    with _lock:
        _initialized_paths.discard(str(Path(path).resolve()))
    if Path(path).exists():
        Path(path).unlink()
    init_db()

"""用户注册 / 登录 / 会话与 VIP 状态。"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from base64 import b64decode, b64encode
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db import get_conn

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SESSION_DAYS = 30
COOKIE_NAME = "speedydl_session"
MIN_PASSWORD_LEN = 8


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized or not EMAIL_RE.match(normalized) or len(normalized) > 254:
        raise ValueError("请输入有效邮箱")
    return normalized


def validate_password(password: str) -> str:
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"密码至少 {MIN_PASSWORD_LEN} 位")
    if len(password) > 128:
        raise ValueError("密码过长")
    return password


def hash_password(password: str) -> str:
    """scrypt 哈希，格式 scrypt$n$r$p$salt_b64$hash_b64。"""
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=32,
    )
    return (
        f"scrypt${n}${r}${p}$"
        f"{b64encode(salt).decode('ascii')}$"
        f"{b64encode(dk).decode('ascii')}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        parts = password_hash.split("$")
        if len(parts) != 6 or parts[0] != "scrypt":
            return False
        _, n_s, r_s, p_s, salt_b64, hash_b64 = parts
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt = b64decode(salt_b64.encode("ascii"))
        expected = b64decode(hash_b64.encode("ascii"))
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError, AttributeError):
        return False


def _row_user(row: Any) -> dict:
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "is_vip": bool(row["is_vip"]),
        "stripe_customer_id": row["stripe_customer_id"],
        "created_at": row["created_at"],
    }


def create_user(email: str, password: str) -> dict:
    email = validate_email(email)
    password = validate_password(password)
    conn = get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()
        if existing:
            raise ValueError("该邮箱已注册")
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, hash_password(password)),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_user(row)
    finally:
        conn.close()


def authenticate(email: str, password: str) -> dict:
    email = validate_email(email)
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise ValueError("邮箱或密码错误")
        return _row_user(row)
    finally:
        conn.close()


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires.isoformat()),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def delete_session(token: str | None) -> None:
    if not token:
        return
    conn = get_conn()
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def get_user_by_session(token: str | None) -> dict | None:
    if not token:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            return None
        sess = conn.execute(
            "SELECT expires_at FROM sessions WHERE token = ?", (token,)
        ).fetchone()
        if not sess:
            return None
        expires = datetime.fromisoformat(sess["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return None
        return _row_user(row)
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return _row_user(row) if row else None
    finally:
        conn.close()


def set_user_vip(user_id: int, is_vip: bool = True) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET is_vip = ? WHERE id = ?",
            (1 if is_vip else 0, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_stripe_customer_id(user_id: int, customer_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
            (customer_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()

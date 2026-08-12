"""Stripe Checkout 创建与 Webhook 履约（httpx + 官方签名算法，幂等）。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app import auth_store
from app.config import (
    PUBLIC_BASE_URL,
    STRIPE_PRICE_ID,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    VIP_CURRENCY,
    VIP_PRICE_CENTS,
    VIP_PRODUCT_NAME,
)
from app.db import get_conn

logger = logging.getLogger(__name__)
STRIPE_API = "https://api.stripe.com/v1"


def _require_stripe_key() -> str:
    if not STRIPE_SECRET_KEY:
        raise RuntimeError(
            "未配置 SPEEDYDL_STRIPE_SECRET_KEY，请在 .env 写入 Stripe Test Secret Key"
        )
    return STRIPE_SECRET_KEY


def _stripe_request(
    method: str,
    path: str,
    *,
    data: dict[str, Any] | list[tuple[str, str]] | None = None,
    idempotency_key: str | None = None,
) -> dict:
    key = _require_stripe_key()
    headers = {"Authorization": f"Bearer {key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    url = f"{STRIPE_API}{path}"
    with httpx.Client(timeout=30.0) as client:
        if method.upper() == "GET":
            resp = client.get(url, headers=headers, params=data or {})
        else:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            if isinstance(data, list):
                body = urlencode(data)
            elif isinstance(data, dict):
                body = urlencode(data)
            else:
                body = ""
            resp = client.request(
                method.upper(),
                url,
                headers=headers,
                content=body,
            )
    try:
        body_json = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Stripe 响应无效：{resp.status_code}") from exc
    if resp.status_code >= 400:
        err = body_json.get("error", {}) if isinstance(body_json, dict) else {}
        msg = err.get("message") or resp.text or f"HTTP {resp.status_code}"
        raise RuntimeError(f"Stripe 错误：{msg}")
    return body_json

def _flatten_stripe_params(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    """将嵌套 dict/list 展平为 Stripe form 字段。"""
    items: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}[{k}]" if prefix else str(k)
            items.extend(_flatten_stripe_params(v, key))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            key = f"{prefix}[{i}]"
            items.extend(_flatten_stripe_params(v, key))
    elif obj is None:
        return items
    elif isinstance(obj, bool):
        items.append((prefix, "true" if obj else "false"))
    else:
        items.append((prefix, str(obj)))
    return items


def create_checkout_session(user: dict) -> dict:
    """为已登录用户创建一次性 VIP Checkout；返回 {url, session_id, order_id}。"""
    if user.get("is_vip"):
        raise ValueError("您已是会员，无需重复购买")

    _require_stripe_key()

    idempotency_key = f"vip-{user['id']}-{secrets.token_hex(8)}"
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO orders (user_id, idempotency_key, amount_cents, currency, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (user["id"], idempotency_key, VIP_PRICE_CENTS, VIP_CURRENCY),
        )
        order_id = int(cur.lastrowid)
        conn.commit()
    finally:
        conn.close()

    success_url = (
        f"{PUBLIC_BASE_URL}/?billing=success"
        "&session_id={CHECKOUT_SESSION_ID}"
    )
    cancel_url = f"{PUBLIC_BASE_URL}/?billing=cancel"

    payload: dict[str, Any] = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(user["id"]),
        "metadata": {
            "user_id": str(user["id"]),
            "order_id": str(order_id),
            "product": "lifetime_vip",
        },
    }
    if user.get("stripe_customer_id"):
        payload["customer"] = user["stripe_customer_id"]
    else:
        payload["customer_email"] = user["email"]

    if STRIPE_PRICE_ID:
        payload["line_items"] = [{"price": STRIPE_PRICE_ID, "quantity": 1}]
    else:
        payload["line_items"] = [
            {
                "price_data": {
                    "currency": VIP_CURRENCY,
                    "unit_amount": VIP_PRICE_CENTS,
                    "product_data": {"name": VIP_PRODUCT_NAME},
                },
                "quantity": 1,
            }
        ]

    form_pairs = _flatten_stripe_params(payload)

    try:
        session = _stripe_request(
            "POST",
            "/checkout/sessions",
            data=form_pairs,
            idempotency_key=idempotency_key,
        )
    except RuntimeError:
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE orders SET status = 'failed' WHERE id = ?",
                (order_id,),
            )
            conn.commit()
        finally:
            conn.close()
        raise

    session_id = session["id"]
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE orders
            SET stripe_checkout_session_id = ?
            WHERE id = ?
            """,
            (session_id, order_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "url": session.get("url"),
        "session_id": session_id,
        "order_id": order_id,
    }


def construct_webhook_event(
    payload: bytes, sig_header: str, secret: str, tolerance: int = 300
) -> dict:
    """校验 Stripe-Signature（HMAC-SHA256），返回 event dict。"""
    if isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    else:
        payload_bytes = payload
    payload_text = payload_bytes.decode("utf-8")

    items = [p.split("=", 1) for p in sig_header.split(",") if "=" in p]
    timestamp = None
    signatures: list[str] = []
    for k, v in items:
        if k == "t":
            timestamp = int(v)
        elif k == "v1":
            signatures.append(v)
    if timestamp is None or not signatures:
        raise ValueError("Webhook 签名头无效")

    if abs(time.time() - timestamp) > tolerance:
        raise ValueError("Webhook 时间戳超出容差")

    signed = f"{timestamp}.{payload_text}".encode("utf-8")
    expected = hmac.new(
        secret.encode("utf-8"), signed, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise ValueError("Webhook 签名校验失败")

    try:
        return json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError("无效 Webhook 载荷") from exc


def event_already_processed(event_id: str) -> bool:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM stripe_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_event_processed(event_id: str, event_type: str) -> bool:
    """写入事件表；若已存在返回 False。"""
    conn = get_conn()
    try:
        try:
            conn.execute(
                "INSERT INTO stripe_events (event_id, event_type) VALUES (?, ?)",
                (event_id, event_type),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            return False
    finally:
        conn.close()


def fulfill_checkout_session(session_id: str) -> dict:
    """拉取 Session，确认 paid 后开通 VIP（可安全重复调用）。"""
    session = _stripe_request("GET", f"/checkout/sessions/{session_id}")
    if session.get("payment_status") != "paid":
        return {"fulfilled": False, "reason": "not_paid"}

    metadata = session.get("metadata") or {}
    user_id_raw = metadata.get("user_id") or session.get("client_reference_id")
    if not user_id_raw:
        logger.warning("checkout session %s missing user_id", session_id)
        return {"fulfilled": False, "reason": "missing_user"}

    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError):
        return {"fulfilled": False, "reason": "bad_user_id"}

    customer_id = session.get("customer")
    if customer_id:
        auth_store.set_stripe_customer_id(user_id, str(customer_id))

    auth_store.set_user_vip(user_id, True)

    paid_at = datetime.now(timezone.utc).isoformat()
    order_id = metadata.get("order_id")
    conn = get_conn()
    try:
        conn.execute(
            """
            UPDATE orders
            SET status = 'paid',
                paid_at = COALESCE(paid_at, ?),
                stripe_checkout_session_id = COALESCE(stripe_checkout_session_id, ?)
            WHERE stripe_checkout_session_id = ?
               OR id = ?
            """,
            (
                paid_at,
                session_id,
                session_id,
                int(order_id) if order_id else -1,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {"fulfilled": True, "user_id": user_id, "session_id": session_id}


def handle_webhook(payload: bytes, sig_header: str | None) -> dict:
    """验签并处理 Checkout 履约事件。"""
    if not STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("未配置 SPEEDYDL_STRIPE_WEBHOOK_SECRET")
    if not sig_header:
        raise ValueError("缺少 Stripe-Signature")

    event = construct_webhook_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    event_id = event["id"]
    event_type = event["type"]

    if event_already_processed(event_id):
        return {"ok": True, "duplicate": True}

    if event_type in (
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ):
        session_obj = event["data"]["object"]
        session_id = session_obj.get("id")
        if session_id:
            result = fulfill_checkout_session(session_id)
            if not mark_event_processed(event_id, event_type):
                return {"ok": True, "duplicate": True}
            return {"ok": True, "result": result}

    mark_event_processed(event_id, event_type)
    return {"ok": True, "ignored": event_type}


def get_session_status(session_id: str, user_id: int) -> dict:
    """回跳页查询；若已 paid 则幂等补履约（Webhook 丢失时的兜底）。"""
    session = _stripe_request("GET", f"/checkout/sessions/{session_id}")
    meta = session.get("metadata") or {}
    owner = meta.get("user_id") or session.get("client_reference_id")
    if str(owner) != str(user_id):
        raise PermissionError("无权查看该支付会话")

    payment_status = session.get("payment_status")
    fulfilled = False
    if payment_status == "paid":
        result = fulfill_checkout_session(session_id)
        fulfilled = bool(result.get("fulfilled"))

    return {
        "session_id": session["id"],
        "status": session.get("status"),
        "payment_status": payment_status,
        "fulfilled": fulfilled,
    }

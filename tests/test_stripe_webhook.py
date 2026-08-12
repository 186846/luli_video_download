"""Stripe Webhook 验签与幂等履约。"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import patch


def _sign(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    signed = f"{ts}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setattr("app.billing.STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr("app.config.STRIPE_WEBHOOK_SECRET", "whsec_test")
    # billing 模块已绑定常量，直接 patch handle 用的模块属性
    import app.billing as billing_mod

    monkeypatch.setattr(billing_mod, "STRIPE_WEBHOOK_SECRET", "whsec_test")
    r = client.post(
        "/api/billing/webhook",
        content=b'{"id":"evt_1"}',
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )
    assert r.status_code == 400


def test_webhook_idempotent_fulfill(client, registered_user, monkeypatch):
    import app.billing as billing_mod

    secret = "whsec_test_secret"
    monkeypatch.setattr(billing_mod, "STRIPE_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(billing_mod, "STRIPE_SECRET_KEY", "sk_test_x")

    user_id = registered_user["user"]["id"]
    session_id = "cs_test_123"

    event = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {"object": {"id": session_id}},
    }
    payload = json.dumps(event).encode("utf-8")
    header = _sign(payload, secret)

    def fake_fulfill(sid: str):
        assert sid == session_id
        from app import auth_store

        auth_store.set_user_vip(user_id, True)
        return {"fulfilled": True, "user_id": user_id, "session_id": sid}

    with patch.object(billing_mod, "fulfill_checkout_session", side_effect=fake_fulfill):
        r1 = client.post(
            "/api/billing/webhook",
            content=payload,
            headers={"stripe-signature": header},
        )
        assert r1.status_code == 200
        r2 = client.post(
            "/api/billing/webhook",
            content=payload,
            headers={"stripe-signature": header},
        )
        assert r2.status_code == 200
        assert r2.json().get("duplicate") is True

    me = client.get("/api/auth/me").json()["user"]
    assert me["is_vip"] is True

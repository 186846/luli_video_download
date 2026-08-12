"""AI 总结：登录 + 免费每日配额 + VIP 无限。"""

from __future__ import annotations

from unittest.mock import patch


def test_summarize_requires_login(client):
    r = client.post(
        "/api/summarize",
        json={"url": "https://www.bilibili.com/video/BV1GJ411x7h7"},
    )
    assert r.status_code == 401


def test_free_user_daily_quota(client, registered_user, monkeypatch):
    monkeypatch.setattr(
        "app.main.create_summary_task",
        lambda *a, **k: type("T", (), {"id": "sum-q"})(),
    )
    url = "https://www.bilibili.com/video/BV1GJ411x7h7"
    for i in range(3):
        r = client.post("/api/summarize", json={"url": url})
        assert r.status_code == 200, r.text
        assert r.json()["quota"]["remaining"] == 2 - i

    r4 = client.post("/api/summarize", json={"url": url})
    assert r4.status_code == 403
    assert "用完" in r4.json()["detail"]

    me = client.get("/api/auth/me").json()["user"]
    assert me["ai_summarize_remaining"] == 0
    assert me["ai_summarize_used_today"] == 3


def test_vip_unlimited_summarize(client, vip_user, monkeypatch):
    monkeypatch.setattr(
        "app.main.create_summary_task",
        lambda *a, **k: type("T", (), {"id": "sum-vip"})(),
    )
    url = "https://www.bilibili.com/video/BV1GJ411x7h7"
    for _ in range(5):
        r = client.post("/api/summarize", json={"url": url})
        assert r.status_code == 200
        assert r.json()["quota"]["remaining"] is None

    me = client.get("/api/auth/me").json()["user"]
    assert me["is_vip"] is True
    assert me["ai_summarize_remaining"] is None


def test_ask_requires_login(client):
    r = client.post(
        "/api/summarize/ask",
        json={
            "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
            "question": "讲了什么？",
        },
    )
    assert r.status_code == 401

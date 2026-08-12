"""账号注册登录与 VIP 门禁。"""

from __future__ import annotations


def test_register_login_me(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "a@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "a@example.com"
    assert body["user"]["is_vip"] is False
    assert "speedydl_session" in r.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "a@example.com"

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["user"] is None

    login = client.post(
        "/api/auth/login",
        json={"email": "a@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "a@example.com"


def test_register_duplicate(client, registered_user):
    r = client.post(
        "/api/auth/register",
        json={"email": registered_user["email"], "password": "password123"},
    )
    assert r.status_code == 400


def test_checkout_requires_login(client):
    r = client.post("/api/billing/checkout")
    assert r.status_code == 401


def test_checkout_rejects_existing_vip(client, vip_user):
    r = client.post("/api/billing/checkout")
    assert r.status_code == 400
    assert "会员" in r.json()["detail"]


def test_demo_vip_disabled_by_default(client):
    r = client.post(
        "/api/download",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "format_id": "bestvideo[height<=1080]+bestaudio/best",
            "height": 1080,
            "vip_token": "demo-vip",
        },
    )
    assert r.status_code == 403


def test_download_vip_with_session(client, vip_user, monkeypatch):
    def fake_create(url, format_id):
        class T:
            id = "t1"
            status = type("S", (), {"value": "pending"})()
            progress = 0
            error = None
            filepath = None
            filename = None
            speed = None
            eta = None

        return T()

    monkeypatch.setattr("app.main.create_task", fake_create)
    monkeypatch.setattr(
        "app.main.task_to_dict",
        lambda t: {"id": t.id, "status": "pending", "progress": 0},
    )
    r = client.post(
        "/api/download",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "format_id": "bestvideo[height<=1080]+bestaudio/best",
            "height": 1080,
        },
    )
    assert r.status_code == 200


def test_summarize_requires_vip(client):
    r = client.post(
        "/api/summarize",
        json={"url": "https://www.bilibili.com/video/BV1GJ411x7h7"},
    )
    assert r.status_code == 401


def test_summarize_ok_for_vip(client, vip_user, monkeypatch):
    monkeypatch.setattr(
        "app.main.create_summary_task",
        lambda *a, **k: type("T", (), {"id": "sum-1"})(),
    )
    r = client.post(
        "/api/summarize",
        json={"url": "https://www.bilibili.com/video/BV1GJ411x7h7"},
    )
    assert r.status_code == 200
    assert r.json()["task_id"] == "sum-1"

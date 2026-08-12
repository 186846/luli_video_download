"""pytest fixtures：隔离 SQLite，默认关闭 demo VIP。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# 须在 import app.main 之前设置
os.environ.setdefault("SPEEDYDL_ALLOW_DEMO_VIP", "0")
os.environ.setdefault("SPEEDYDL_AI_REQUIRE_VIP", "1")


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("SPEEDYDL_DB_PATH", str(db_file))
    from app import config
    from app.db import configure_db_path

    config.DB_PATH = db_file
    configure_db_path(db_file)
    yield db_file


@pytest.fixture()
def client(tmp_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def registered_user(client):
    email = "user@example.com"
    password = "password123"
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200
    return {"email": email, "password": password, "user": r.json()["user"]}


@pytest.fixture()
def vip_user(client, registered_user):
    from app import auth_store

    auth_store.set_user_vip(registered_user["user"]["id"], True)
    # 刷新会话用户态：再 login 或直接 cookie 已有，me 会读库
    return registered_user

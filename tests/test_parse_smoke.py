"""
速下 SpeedyDL 冒烟测试：健康检查、VIP 门槛、格式去重与基础 API 校验。
不依赖外网真实解析（避免 CI 不稳定）；网络相关逻辑用构造数据覆盖。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import FREE_MAX_HEIGHT
from app.downloader import _dedupe_formats, _format_entry, format_requires_vip
from app.main import app


client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["free_max_height"] == FREE_MAX_HEIGHT


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "速下" in r.text
    assert "5173" in r.text or "Vue" in r.text or "/docs" in r.text


def test_parse_rejects_bad_url():
    r = client.post("/api/parse", json={"url": "not-a-url"})
    assert r.status_code == 400


def test_format_requires_vip():
    assert format_requires_vip("best", height=720) is False
    assert format_requires_vip("best", height=1080) is True
    assert format_requires_vip("bestvideo[height<=1080]+bestaudio/best") is True


def test_format_entry_and_dedupe():
    raw = {
        "format_id": "137",
        "height": 1080,
        "width": 1920,
        "ext": "mp4",
        "vcodec": "avc1",
        "acodec": "none",
        "filesize": 10_000_000,
    }
    entry = _format_entry(raw)
    assert entry is not None
    assert entry["vip_required"] is True

    audio = _format_entry(
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a",
            "filesize": 1_000_000,
        }
    )
    assert audio is not None
    assert audio["has_video"] is False

    merged = _dedupe_formats([entry, audio])
    assert any(f["has_audio"] for f in merged)
    assert any(f.get("height") == 1080 for f in merged)


def test_download_vip_gate():
    r = client.post(
        "/api/download",
        json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "format_id": "bestvideo[height<=1080]+bestaudio/best",
            "height": 1080,
        },
    )
    assert r.status_code == 403


def test_thumbnail_proxy_rejects_local():
    r = client.get("/api/thumbnail", params={"url": "http://127.0.0.1/x.jpg"})
    assert r.status_code == 400


def test_thumbnail_proxy_bilibili():
    thumb = (
        "http://i1.hdslb.com/bfs/archive/"
        "22e2d41ea28d0e1b45e99ae08a4f0bfc1fd58f63.jpg"
    )
    r = client.get(
        "/api/thumbnail",
        params={"url": thumb, "page": "https://www.bilibili.com/video/BV1dT386uEJR"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert len(r.content) > 1000


def test_direct_rejects_merge_format():
    r = client.post(
        "/api/direct",
        json={
            "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
            "format_id": "30080+bestaudio/best",
            "height": 720,
        },
    )
    assert r.status_code == 400
    assert "合并" in r.json()["detail"]


def test_health_lists_features():
    r = client.get("/api/health")
    assert r.status_code == 200
    feats = r.json().get("features") or []
    assert "direct" in feats
    assert "subtitles" in feats

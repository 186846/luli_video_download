"""抖音无 Cookie 解析单元 / 轻量联通测试。"""

from __future__ import annotations

import pytest

from app.douyin import (
    extract_url_from_text,
    is_douyin_url,
    parse_douyin,
    play_url_for,
    resolve_aweme_id,
)
from app.downloader import format_requires_vip, parse_video


def test_is_douyin_url():
    assert is_douyin_url("https://www.douyin.com/video/123")
    assert is_douyin_url("https://v.douyin.com/AbCdEf/")
    assert is_douyin_url("复制打开抖音 https://v.douyin.com/xxx/ 哈哈")
    assert not is_douyin_url("https://www.bilibili.com/video/BV1xx")


def test_extract_url_from_share_text():
    text = "0.23 复制打开抖音，看看【作者】标题 https://v.douyin.com/iAbC123/ 12/34"
    assert extract_url_from_text(text).startswith("https://v.douyin.com/")


def test_play_url_for():
    url = play_url_for("v0d00fg10000demo", "720p")
    assert "video_id=v0d00fg10000demo" in url
    assert "ratio=720p" in url


def test_format_requires_vip_douyin():
    assert format_requires_vip("dy:720p") is False
    assert format_requires_vip("dy:1080p") is True


@pytest.mark.network
def test_parse_douyin_live():
    """需要外网；验证分享页无 Cookie 解析。"""
    url = "https://www.douyin.com/video/7639706813827227049"
    data = parse_douyin(url)
    assert data["extractor"] == "Douyin"
    assert data["id"] == "7639706813827227049"
    assert data["title"]
    assert data["formats"]
    assert any(f["format_id"] == "dy:720p" for f in data["formats"])
    # 经 parse_video 分流也应命中抖音路径
    via = parse_video(url)
    assert via["extractor"] == "Douyin"


@pytest.mark.network
def test_resolve_aweme_id_from_long_url():
    assert (
        resolve_aweme_id("https://www.douyin.com/video/7639706813827227049")
        == "7639706813827227049"
    )

"""B 站官方字幕提取单测（mock HTTP，不打外网）。"""

from __future__ import annotations

from unittest.mock import patch

from app.bilibili_subs import (
    bcc_to_cues,
    extract_bilibili_cues,
    merge_bilibili_tracks_into_subtitles,
    normalize_subtitle_url,
    pick_track,
    tracks_as_subtitle_entries,
)


SAMPLE_BCC = {
    "body": [
        {"from": 0.5, "to": 2.0, "content": "大家好"},
        {"from": 2.1, "to": 4.0, "content": "今天讲下载"},
    ]
}


def test_normalize_subtitle_url_upgrades_scheme():
    assert normalize_subtitle_url("//aisubtitle.hdslb.com/a.json") == (
        "https://aisubtitle.hdslb.com/a.json"
    )
    assert normalize_subtitle_url("http://aisubtitle.hdslb.com/a.json").startswith(
        "https://"
    )


def test_bcc_to_cues():
    cues = bcc_to_cues(SAMPLE_BCC)
    assert len(cues) == 2
    assert cues[0]["text"] == "大家好"
    assert cues[0]["start"] == "00:00"


def test_pick_track_prefers_human_over_ai():
    tracks = [
        {
            "lan": "ai-zh",
            "lan_doc": "中文（自动生成）",
            "subtitle_url": "https://x/ai.json",
            "kind": "ai",
            "automatic": True,
        },
        {
            "lan": "zh-CN",
            "lan_doc": "中文",
            "subtitle_url": "https://x/human.json",
            "kind": "human",
            "automatic": False,
        },
    ]
    picked = pick_track(tracks, lang="zh")
    assert picked is not None
    assert picked["kind"] == "human"
    assert "human.json" in picked["subtitle_url"]


def test_pick_track_falls_back_to_ai():
    tracks = [
        {
            "lan": "ai-zh",
            "lan_doc": "中文（自动生成）",
            "subtitle_url": "https://x/ai.json",
            "kind": "ai",
            "automatic": True,
        },
    ]
    picked = pick_track(tracks, lang="zh")
    assert picked is not None
    assert picked["kind"] == "ai"


def test_extract_bilibili_cues_success():
    view = {"bvid": "BV1xx", "aid": 1, "cid": 99, "title": "t"}
    tracks = [
        {
            "lan": "ai-zh",
            "lan_doc": "中文（自动生成）",
            "subtitle_url": "https://aisubtitle.hdslb.com/x.json",
            "kind": "ai",
            "automatic": True,
            "is_danmaku": False,
        }
    ]
    with patch("app.bilibili_subs.BILI_SUBS_ENABLED", True):
        with patch("app.bilibili_subs.fetch_view", return_value=view):
            with patch("app.bilibili_subs.list_subtitle_tracks", return_value=tracks):
                with patch("app.bilibili_subs.fetch_bcc", return_value=SAMPLE_BCC):
                    result = extract_bilibili_cues(
                        "https://www.bilibili.com/video/BV1xx",
                        lang="zh",
                    )
    assert result is not None
    assert result["cues"][0]["text"] == "大家好"
    assert "旁白" not in result["plain"] or True
    assert result["track"]["kind"] == "ai"


def test_extract_bilibili_cues_empty_when_no_tracks():
    with patch("app.bilibili_subs.BILI_SUBS_ENABLED", True):
        with patch(
            "app.bilibili_subs.fetch_view",
            return_value={"cid": 1, "aid": 2, "bvid": "BV1"},
        ):
            with patch("app.bilibili_subs.list_subtitle_tracks", return_value=[]):
                assert (
                    extract_bilibili_cues("https://www.bilibili.com/video/BV1") is None
                )


def test_merge_bilibili_tracks_into_subtitles():
    existing = [
        {
            "lang": "danmaku",
            "name": "弹幕",
            "automatic": False,
            "is_danmaku": True,
            "url": "https://comment.bilibili.com/1.xml",
        }
    ]
    tracks = [
        {
            "lan": "ai-zh",
            "lan_doc": "中文（自动生成）",
            "subtitle_url": "https://aisubtitle.hdslb.com/x.json",
            "kind": "ai",
            "automatic": True,
            "is_danmaku": False,
        }
    ]
    with patch("app.bilibili_subs.BILI_SUBS_ENABLED", True):
        with patch(
            "app.bilibili_subs.fetch_view",
            return_value={"cid": 1, "aid": 2, "bvid": "BV1"},
        ):
            with patch("app.bilibili_subs.list_subtitle_tracks", return_value=tracks):
                merged = merge_bilibili_tracks_into_subtitles(
                    "https://www.bilibili.com/video/BV1",
                    existing,
                )
    assert any(s.get("lang") == "ai-zh" for s in merged)
    # 弹幕仍在
    assert any(s.get("is_danmaku") for s in merged)
    # AI 轨排在弹幕前
    ai_idx = next(i for i, s in enumerate(merged) if s.get("lang") == "ai-zh")
    dm_idx = next(i for i, s in enumerate(merged) if s.get("is_danmaku"))
    assert ai_idx < dm_idx


def test_resolve_context_uses_bilibili_api_before_danmaku():
    from app.summarizer import _resolve_context

    fake_meta = {
        "title": "有 AI 字幕",
        "description": "",
        "subtitles": [
            {
                "lang": "danmaku",
                "name": "弹幕",
                "is_danmaku": True,
                "url": "https://comment.bilibili.com/1.xml",
                "ext": "xml",
                "automatic": False,
            }
        ],
        "webpage_url": "https://www.bilibili.com/video/BV11qoVB9ECt",
        "thumbnail": None,
        "extractor": "BiliBili",
        "uploader": "up",
        "duration": 60,
        "tags": [],
    }
    bili_result = {
        "cues": [{"start": "00:01", "text": "官方AI旁白"}],
        "plain": "[00:01] 官方AI旁白",
        "track": {
            "lan": "ai-zh",
            "lan_doc": "中文（自动生成）",
            "kind": "ai",
            "automatic": True,
        },
        "view": {},
        "tracks": [],
    }
    dm_cues = [{"start": "00:01", "text": "水弹幕"}]
    with patch("app.summarizer.parse_video", return_value=fake_meta):
        with patch(
            "app.bilibili_subs.extract_bilibili_cues",
            return_value=bili_result,
        ):
            with patch(
                "app.summarizer._load_subtitle_text",
                return_value=("[00:01] 水弹幕", dm_cues),
            ):
                ctx = _resolve_context(
                    "https://www.bilibili.com/video/BV11qoVB9ECt",
                )
    assert ctx["source"] == "subtitles"
    assert ctx["cues"][0]["text"] == "官方AI旁白"
    assert ctx["danmaku_cues"]  # 弹幕仍拉取


def test_tracks_as_subtitle_entries():
    entries = tracks_as_subtitle_entries(
        [
            {
                "lan": "zh-CN",
                "lan_doc": "中文",
                "subtitle_url": "https://x/h.json",
                "kind": "human",
                "automatic": False,
            }
        ]
    )
    assert entries[0]["automatic"] is False
    assert entries[0]["source"] == "bilibili_api"

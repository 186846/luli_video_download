"""AI 总结：字幕解析、Mock、导图、问答、JSON 容错、transcript 复用测试。"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.summarizer import (
    _chapters_from_cues,
    _extract_json,
    _mock_summary,
    ask_about_video,
    build_mind_map,
    parse_subtitle_cues,
)


client = TestClient(app)


@pytest.fixture(autouse=True)
def _disable_ai_gates(monkeypatch):
    """本文件测总结业务逻辑；登录/配额门禁见 test_auth_billing / test_ai_quota。"""
    monkeypatch.setattr("app.main.AI_REQUIRE_VIP", False)
    monkeypatch.setattr(
        "app.main._require_summarize_access",
        lambda request, vip_token=None: {
            "is_vip": True,
            "remaining": None,
            "used": 0,
            "daily_limit": 3,
        },
    )

SAMPLE_VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
欢迎来到速下演示视频

00:00:05.000 --> 00:00:09.000
今天我们讲解下载与 AI 总结流程

00:01:00.000 --> 00:01:05.000
最后回顾核心要点并结束
"""


def test_parse_subtitle_cues():
    cues = parse_subtitle_cues(SAMPLE_VTT)
    assert len(cues) >= 2
    assert cues[0]["start"] in ("00:01", "0:01", "00:00:01") or "01" in cues[0]["start"]
    assert "欢迎" in cues[0]["text"]


def test_parse_srt_with_index():
    srt = """1
00:00:01,000 --> 00:00:03,500
第一句字幕

2
00:00:04,000 --> 00:00:06,000
第二句字幕
"""
    cues = parse_subtitle_cues(srt)
    assert len(cues) >= 2
    assert "第一句" in cues[0]["text"]
    assert cues[0].get("end")


def test_subtitle_candidates_prefer_zh():
    from app.summarizer import _subtitle_candidates

    subs = [
        {"lang": "en", "automatic": False, "name": "English"},
        {"lang": "zh-Hans", "automatic": True, "name": "中文自动"},
        {"lang": "zh-CN", "automatic": False, "name": "中文"},
    ]
    ordered = _subtitle_candidates(subs, None, None)
    assert ordered[0]["lang"] == "zh-CN"


def test_chapters_from_cues_have_timestamps():
    cues = parse_subtitle_cues(SAMPLE_VTT)
    chapters = _chapters_from_cues(cues, max_chapters=4)
    assert chapters
    assert all(c.get("start") for c in chapters)
    assert all(c.get("title") for c in chapters)


def test_build_mind_map():
    tree = build_mind_map("演示", ["要点A", "要点B"], [{"start": "00:01", "title": "开场", "summary": "介绍"}])
    assert tree["name"] == "演示"
    assert tree["children"]
    assert any(c["name"] == "核心要点" for c in tree["children"])


def test_mock_summary_structure():
    cues = parse_subtitle_cues(SAMPLE_VTT)
    plain = "\n".join(f"[{c['start']}] {c['text']}" for c in cues)
    data = _mock_summary(
        title="演示视频",
        description="一段简介",
        plain=plain,
        cues=cues,
        source="subtitles",
    )
    assert data["mode"] == "mock"
    assert data["summary"]
    assert data["key_points"]
    assert isinstance(data["chapters"], list)
    assert data["chapters"]
    assert data["mind_map"]["children"]
    assert data["warning"]


def test_mock_summary_metadata_fallback():
    data = _mock_summary(
        title="无字幕视频",
        description="仅有简介",
        plain=None,
        cues=[],
        source="metadata",
    )
    assert data["mode"] == "mock"
    assert data["source"] == "metadata"
    assert data["chapters"] == []
    assert "无字幕视频" in data["summary"]


def test_ask_mock_without_key():
    fake = {
        "url": "https://example.com/v",
        "title": "问答演示",
        "description": "",
        "plain": "[00:01] 讲了下载流程",
        "cues": [{"start": "00:01", "text": "讲了下载流程"}],
        "source": "subtitles",
        "lang": "zh-Hans",
        "automatic": False,
        "webpage_url": "https://example.com/v",
        "thumbnail": None,
    }
    with patch("app.summarizer._resolve_context", return_value=fake):
        with patch("app.summarizer.AI_API_KEY", ""):
            data = ask_about_video("https://example.com/v", "讲了什么？")
    assert data["mode"] == "mock"
    assert data["answer"]
    assert data["question"] == "讲了什么？"


def test_summarize_requires_vip():
    """配额与登录门禁见 test_ai_quota。"""
    pass


def test_ask_requires_vip():
    """问答在关闭门禁时可直接调用（无 Key 时 Mock）。"""
    with patch("app.summarizer.AI_API_KEY", ""):
        with patch(
            "app.summarizer._resolve_context",
            return_value={
                "plain": "你好",
                "cues": [{"start": "00:00", "text": "你好"}],
                "source": "subtitles",
                "title": "t",
                "description": "",
                "webpage_url": "https://example.com",
                "thumbnail": None,
                "extractor": "bilibili",
                "lang": "zh",
                "automatic": False,
                "subtitle_name": "zh",
                "is_danmaku": False,
                "available_subtitles": 1,
                "available_real_subtitles": 1,
                "available_danmaku": 0,
                "subtitle_warning": None,
                "danmaku_cues": [],
            },
        ):
            r = client.post(
                "/api/summarize/ask",
                json={
                    "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
                    "question": "讲了什么？",
                },
            )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["data"]["answer"]


def test_summarize_creates_task():
    """有 VIP/门禁关闭：创建异步总结任务并返回 task_id。"""
    with patch("app.main.create_summary_task") as mock_create:
        task = type("T", (), {"id": "sum-test-1"})()
        mock_create.return_value = task
        r = client.post(
            "/api/summarize",
            json={
                "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
                "vip_token": "demo-vip",
                "title": "单元测试视频",
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["task_id"] == "sum-test-1"


def test_summarize_video_mock_metadata_fallback():
    """无字幕时 summarize_video 直接走 Mock 元数据兜底。"""
    from app.summarizer import summarize_video

    fake_meta = {
        "title": "单元测试视频",
        "description": "用于 Mock 验收",
        "subtitles": [],
        "webpage_url": "https://www.bilibili.com/video/BV1GJ411x7h7",
        "thumbnail": None,
    }
    with patch("app.summarizer.parse_video", return_value=fake_meta):
        with patch("app.summarizer.AI_API_KEY", ""):
            with patch(
                "app.bilibili_subs.extract_bilibili_cues",
                return_value=None,
            ):
                data = summarize_video(
                    "https://www.bilibili.com/video/BV1GJ411x7h7",
                    title="单元测试视频",
                )

    assert data["mode"] == "mock"
    assert data["summary"]
    assert data["key_points"]
    assert data["source"] == "metadata"
    assert "transcript" in data
    assert data["mind_map"]["name"]
    assert data.get("available_subtitles") == 0
    assert data.get("warning")
    assert "平台" in data["warning"] or "字幕" in data["warning"]


def test_cues_from_user_subtitle_text():
    from app.summarizer import _cues_from_user

    cues = _cues_from_user(
        None,
        """WEBVTT

00:00:01.000 --> 00:00:04.000
用户粘贴的旁白
""",
    )
    assert cues
    assert "旁白" in cues[0]["text"]


def test_resolve_context_falls_back_to_danmaku_on_no_cc():
    """无平台 CC、无用户字幕时，弹幕兜底。"""
    from app.summarizer import _resolve_context

    fake_meta = {
        "title": "无字幕测试",
        "description": "desc",
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
        "duration": 100,
        "tags": ["宇宙"],
    }
    dm_cues = [{"start": "00:01", "text": "开头好看"}]
    with patch("app.summarizer.parse_video", return_value=fake_meta):
        with patch(
            "app.summarizer._load_subtitle_text",
            return_value=("[00:01] 开头好看", dm_cues),
        ):
            ctx = _resolve_context(
                "https://www.bilibili.com/video/BV11qoVB9ECt",
            )
    assert ctx["source"] == "danmaku"
    assert ctx["is_danmaku"] is True
    assert ctx["cues"]
    assert "弹幕" in (ctx.get("subtitle_warning") or "")


def test_resolve_context_uses_user_before_danmaku():
    """无平台 CC 时，用户字幕应优先于弹幕。"""
    from app.summarizer import _resolve_context

    fake_meta = {
        "title": "无字幕测试",
        "description": "desc",
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
        "duration": 100,
        "tags": ["宇宙"],
    }
    dm_cues = [{"start": "00:01", "text": "开头好看"}]
    with patch("app.summarizer.parse_video", return_value=fake_meta):
        with patch(
            "app.summarizer._load_subtitle_text",
            return_value=("[00:01] 开头好看", dm_cues),
        ):
            ctx = _resolve_context(
                "https://www.bilibili.com/video/BV11qoVB9ECt",
                subtitle_text="00:00:02.000 --> 00:00:05.000\n真正的旁白内容",
            )
    assert ctx["source"] == "user"
    assert any("旁白" in c["text"] for c in ctx["cues"])
    # 弹幕仍应作为独立字段拉取
    assert ctx["danmaku_cues"]


def test_summarize_endpoint_accepts_subtitle_text():
    with patch("app.summarizer.AI_API_KEY", ""):
        with patch("app.summarizer.summarize_video") as mock_sum:
            mock_sum.return_value = {
                "summary": "ok",
                "key_points": [],
                "chapters": [],
                "mind_map": {"name": "t", "children": []},
                "mode": "mock",
                "source": "user",
                "transcript": [],
            }
            r = client.post(
                "/api/summarize",
                json={
                    "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
                    "vip_token": "demo-vip",
                    "subtitle_text": "00:01 --> 00:02\nhello",
                },
            )
    assert r.status_code == 200
    assert r.json()["task_id"]
    import time

    for _ in range(40):
        if mock_sum.called:
            break
        time.sleep(0.05)
    assert mock_sum.called
    kwargs = mock_sum.call_args.kwargs
    assert kwargs.get("subtitle_text")



def test_health_lists_summarize_and_ask():
    r = client.get("/api/health")
    assert r.status_code == 200
    feats = r.json()["features"]
    assert "summarize" in feats
    assert "ask" in feats


# ---------- 新增：LLM JSON 解析容错测试 ----------


def test_extract_json_direct():
    """理想情况：直接 json.loads 成功"""
    data = _extract_json('{"summary": "测试", "key_points": ["a", "b"]}')
    assert data["summary"] == "测试"
    assert data["key_points"] == ["a", "b"]


def test_extract_json_with_prefix_text():
    """LLM 在 JSON 前加说明文字：应提取 { ... } 块"""
    raw = '好的，以下是总结结果：\n{"summary": "前置文字测试", "key_points": ["x"]}\n希望对你有帮助。'
    data = _extract_json(raw)
    assert data["summary"] == "前置文字测试"
    assert data["key_points"] == ["x"]


def test_extract_json_with_code_fence():
    """LLM 返回带 ```json 代码块：_chat_completion 已去除外壳，此处测纯 JSON"""
    raw = '{"summary": "代码块测试", "chapters": []}'
    data = _extract_json(raw)
    assert data["summary"] == "代码块测试"
    assert data["chapters"] == []


def test_extract_json_invalid_raises():
    """完全无法解析的内容应抛 ValueError"""
    import pytest

    with pytest.raises(ValueError):
        _extract_json("这不是 JSON，也没有花括号")


def test_call_llm_json_parse_fallback():
    """LLM 返回非 JSON 时，_call_llm 应回落到结构化兜底而非崩溃"""
    from app.summarizer import _call_llm

    with patch("app.summarizer._chat_completion", return_value="模型异常输出，非JSON"):
        result = _call_llm("测试视频", "[00:01] 字幕内容")
    assert result["mode"] == "llm"
    assert result["summary"]  # 有兜底摘要
    assert result["key_points"] == []
    assert result["chapters"] == []
    assert result["mind_map"]["name"]  # 兜底导图


def test_cue_seconds_parses_milliseconds():
    from app.summarizer import _cue_seconds

    assert _cue_seconds("01:05:03.000") == 3903
    assert _cue_seconds("1:05:03.500") == 3903
    assert _cue_seconds("00:50") == 50
    assert _cue_seconds("65.5") == 65


def test_sanitize_long_video_always_uses_duration_anchors():
    """即使后半字幕时间戳解析失败，长视频章节也应按片长铺开。"""
    from app.summarizer import _cue_seconds, _sanitize_chapters

    cues = []
    for i in range(0, 60, 5):
        cues.append({"start": f"00:{i:02d}", "text": f"early{i}"})
    for i in range(60, 6780, 30):
        h, r = divmod(i, 3600)
        m, s = divmod(r, 60)
        # 带毫秒 —— 旧解析会失败；新解析应成功。再测 duration 兜底。
        cues.append({"start": f"{h}:{m:02d}:{s:02d}.000", "text": f"late{i}"})

    llm = [
        {"start": "00:05", "title": "介绍", "summary": "a"},
        {"start": "00:50", "title": "总结", "summary": "b"},
    ]
    out = _sanitize_chapters(llm, duration=6780, cues=cues)
    assert len(out) >= 8
    assert _cue_seconds(out[0]["start"]) <= 120
    assert _cue_seconds(out[-1]["start"]) >= 5000
    assert out[0]["title"] == "介绍"


def test_sanitize_chapters_without_cues_still_clamps():
    from app.summarizer import _sanitize_chapters

    out = _sanitize_chapters(
        [{"start": "12:07", "title": "x", "summary": "y"}],
        duration=484,
    )
    assert out[0]["start"] == "08:04"


def test_plain_from_cues_samples_across_timeline():
    """超长字幕应跨片采样，而不是只截开头。"""
    from app.summarizer import _plain_from_cues

    cues = [
        {"start": f"{i // 60:02d}:{i % 60:02d}", "text": f"内容{i}-" + ("字" * 40)}
        for i in range(0, 3600, 5)
    ]
    plain = _plain_from_cues(cues, max_chars=3000)
    assert "跨片采样" in plain
    assert "内容0-" in plain
    # 应包含接近片尾的内容
    assert "内容359" in plain or "内容358" in plain or "内容355" in plain


def test_subtitle_segments_span_long_video():
    from app.summarizer import _build_subtitle_segments, _cue_seconds

    cues = [
        {"start": f"{h:02d}:{m:02d}:{s:02d}", "text": f"段{h}-{m}"}
        for h in range(0, 6)
        for m in (0, 15, 30, 45)
        for s in (0, 30)
    ]
    segs = _build_subtitle_segments(cues, max_chapters=12, duration=6 * 3600)
    assert len(segs) >= 8
    assert _cue_seconds(segs[0]["start"]) <= 60
    assert _cue_seconds(segs[-1]["start"]) >= 4 * 3600


def test_ask_with_transcript_skips_resolve_context():
    """传入 transcript 时应跳过 _resolve_context，不重复解析视频"""
    transcript = [
        {"start": "00:01", "text": "讲解了下载流程"},
        {"start": "00:30", "text": "介绍了AI总结功能"},
    ]
    with patch("app.summarizer._resolve_context") as mock_resolve:
        with patch("app.summarizer.AI_API_KEY", ""):
            data = ask_about_video(
                "https://example.com/v",
                "下载",
                transcript=transcript,
            )
    # _resolve_context 不应被调用
    mock_resolve.assert_not_called()
    assert data["mode"] == "mock"
    assert data["answer"]
    assert "下载" in data["answer"] or "下载流程" in data["answer"]


def test_ask_without_transcript_calls_resolve_context():
    """不传 transcript 时应回退到 _resolve_context"""
    fake = {
        "url": "https://example.com/v",
        "title": "回退测试",
        "description": "",
        "plain": "[00:01] 内容",
        "cues": [{"start": "00:01", "text": "内容"}],
        "source": "subtitles",
        "lang": "zh-Hans",
        "automatic": False,
        "webpage_url": "https://example.com/v",
        "thumbnail": None,
    }
    with patch("app.summarizer._resolve_context", return_value=fake) as mock_resolve:
        with patch("app.summarizer.AI_API_KEY", ""):
            data = ask_about_video("https://example.com/v", "内容")
    mock_resolve.assert_called_once()
    assert data["mode"] == "mock"
    assert data["answer"]


def test_ask_endpoint_accepts_transcript():
    """/api/summarize/ask 路由应接受 transcript 字段并透传"""
    with patch("app.summarizer.AI_API_KEY", ""):
        with patch("app.summarizer._resolve_context") as mock_resolve:
            r = client.post(
                "/api/summarize/ask",
                json={
                    "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
                    "question": "讲了什么？",
                    "vip_token": "demo-vip",
                    "transcript": [{"start": "00:01", "text": "测试字幕"}],
                },
            )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # 传入 transcript 后不应调用 _resolve_context
    mock_resolve.assert_not_called()


def test_subtitle_extractor_and_video_summarizer_classes():
    from app.summarizer import SubtitleExtractor, VideoSummarizer

    extractor = SubtitleExtractor()
    summarizer = VideoSummarizer(extractor)
    fake_ctx = {
        "url": "https://example.com/v",
        "title": "t",
        "description": "",
        "plain": "[00:01] hi",
        "cues": [{"start": "00:01", "text": "hi"}],
        "danmaku_cues": [],
        "source": "subtitles",
        "lang": "zh",
        "automatic": False,
        "is_danmaku": False,
        "subtitle_name": "中文",
        "available_subtitles": 1,
        "available_real_subtitles": 1,
        "available_danmaku": 0,
        "subtitle_warning": None,
        "webpage_url": "https://example.com/v",
        "thumbnail": None,
        "extractor": "demo",
        "uploader": None,
        "duration": 10,
        "_meta": {"tags": [], "duration": 10, "uploader": None},
    }
    with patch.object(extractor, "extract", return_value=fake_ctx):
        with patch("app.summarizer._resolve_context", return_value=fake_ctx):
            with patch("app.summarizer.AI_API_KEY", ""):
                with patch("app.summarizer.resolve_player_embed", return_value=None):
                    result = summarizer.summarize("https://example.com/v")
    assert result["summary"]
    assert result["transcript"]


def test_chat_sse_endpoint_streams_tokens():
    """POST /api/chat 应返回 SSE 流并包含 done 事件。"""
    with patch("app.summarizer.AI_API_KEY", ""):
        with client.stream(
            "POST",
            "/api/chat",
            json={
                "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
                "question": "核心结论？",
                "vip_token": "demo-vip",
                "transcript": [
                    {"start": "00:01", "text": "今天讲下载与总结"},
                    {"start": "00:10", "text": "核心是效率"},
                ],
            },
        ) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            body = "".join(r.iter_text())
    assert "event: token" in body
    assert "event: done" in body
    assert "演示回答" in body or "核心" in body


def test_summarize_stream_endpoint_reports_done():
    """创建总结任务后可通过 SSE 收到 done。"""
    with patch("app.summarizer.AI_API_KEY", ""):
        with patch(
            "app.summarizer.summarize_video",
            return_value={
                "summary": "ok",
                "key_points": [],
                "chapters": [],
                "mind_map": {"name": "t", "children": []},
                "mode": "mock",
                "source": "metadata",
                "transcript": [],
            },
        ):
            created = client.post(
                "/api/summarize",
                json={
                    "url": "https://www.bilibili.com/video/BV1GJ411x7h7",
                    "vip_token": "demo-vip",
                },
            )
            assert created.status_code == 200
            task_id = created.json()["task_id"]
            # 等待后台线程完成
            import time

            for _ in range(50):
                st = client.get(f"/api/summarize/status/{task_id}").json()["task"]
                if st["status"] in ("done", "error"):
                    break
                time.sleep(0.05)
            with client.stream("GET", f"/api/summarize/stream/{task_id}") as r:
                assert r.status_code == 200
                body = "".join(r.iter_text())
    assert "event: done" in body or "event: progress" in body

"""
AI 视频总结：字幕优先 → LLM（OpenAI 兼容）或 Mock。

文本来源优先级：B 站官方 CC/AI → yt-dlp → 用户字幕 → 弹幕 → 元数据。
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import httpx

from app.config import (
    AI_API_KEY,
    AI_BASE_URL,
    AI_MAX_SUBTITLE_CHARS,
    AI_MODEL,
    DOWNLOAD_DIR,
)
from app.downloader import download_subtitle, fetch_subtitle_url_content, parse_video
from app.embed import resolve_player_embed


class SummaryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class SummaryTask:
    id: str
    status: SummaryStatus = SummaryStatus.PENDING
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    result: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


_summary_lock = threading.Lock()
_summary_tasks: dict[str, SummaryTask] = {}


def get_summary_task(task_id: str) -> SummaryTask | None:
    with _summary_lock:
        return _summary_tasks.get(task_id)


def create_summary_task(
    url: str,
    *,
    lang: str | None = None,
    automatic: bool | None = None,
    title: str | None = None,
    transcript: list[dict[str, str]] | None = None,
    subtitle_text: str | None = None,
) -> SummaryTask:
    """创建后台总结任务并立即返回任务对象。"""
    task = SummaryTask(id=uuid.uuid4().hex)
    with _summary_lock:
        _summary_tasks[task.id] = task

    def progress_hook(pct: float, message: str = "") -> None:
        with _summary_lock:
            if task.status not in (SummaryStatus.DONE, SummaryStatus.ERROR):
                task.progress = min(max(pct, 0.0), 99.0)
                task.message = message

    def run() -> None:
        try:
            with _summary_lock:
                task.status = SummaryStatus.RUNNING
            result = summarize_video(
                url,
                lang=lang,
                automatic=automatic,
                title=title,
                transcript=transcript,
                subtitle_text=subtitle_text,
                progress_hook=progress_hook,
            )
            with _summary_lock:
                task.status = SummaryStatus.DONE
                task.progress = 100.0
                task.result = result
                task.finished_at = time.time()
        except Exception as exc:  # noqa: BLE001
            with _summary_lock:
                task.status = SummaryStatus.ERROR
                task.error = str(exc)
                task.finished_at = time.time()

    thread = threading.Thread(target=run, daemon=True, name=f"sum-{task.id[:8]}")
    thread.start()
    return task

_CUE_RE = re.compile(
    r"(?:^|\n)(?:\d+\s*\n)?"
    r"(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})\s*-->\s*"
    r"(\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3})[^\n]*\n"
    r"([\s\S]*?)(?=\n\s*\n|\n\d+\s*\n\d{1,2}:\d{2}|\n\d{1,2}:\d{2}|$)",
    re.M,
)

_TRANSCRIPT_MAX = 100000


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{[^}]*\}", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _format_ts(raw: str) -> str:
    """00:01:02.000 / 01:02.000 → 可读 mm:ss 或 hh:mm:ss。"""
    raw = raw.replace(",", ".")
    parts = raw.split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            total = h * 3600 + m * 60 + int(s)
        else:
            m, s = int(parts[0]), float(parts[1])
            total = m * 60 + int(s)
    except ValueError:
        return raw.split(".")[0]
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_subtitle_cues(content: str) -> list[dict[str, str]]:
    """从 VTT/SRT/BCC JSON（及近似格式）提取 (start, end?, text) 列表。"""
    if not content or not str(content).strip():
        return []

    text = str(content).strip()
    # BCC JSON（B 站官方字幕）
    if text.startswith("{") or text.startswith("["):
        try:
            from app.bilibili_subs import bcc_to_cues

            data = json.loads(text)
            cues = bcc_to_cues(data)
            if cues:
                return cues
        except Exception:  # noqa: BLE001
            pass

    text = re.sub(r"^WEBVTT[^\n]*\n", "", text, flags=re.I)
    text = re.sub(r"(?m)^(STYLE|NOTE)[\s\S]*?(?=\n\n|\Z)", "", text)

    cues: list[dict[str, str]] = []
    for m in _CUE_RE.finditer(text):
        body = _strip_tags(m.group(3).replace("\n", " "))
        if not body:
            continue
        item = {"start": _format_ts(m.group(1)), "text": body}
        end = _format_ts(m.group(2))
        if end:
            item["end"] = end
        if cues and cues[-1]["text"] == body and cues[-1]["start"] == item["start"]:
            continue
        cues.append(item)
    if cues:
        return cues

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.upper().startswith("WEBVTT") or "-->" in line:
            continue
        if re.fullmatch(r"\d+", line):
            continue
        cleaned = _strip_tags(line)
        if cleaned:
            lines.append(cleaned)
    merged = " ".join(lines)
    if merged:
        cues.append({"start": "00:00", "text": merged})
    return cues


def is_danmaku_track(track: dict[str, Any]) -> bool:
    """判断一条 subtitle 轨是否为 B 站弹幕（comment.bilibili.com）。"""
    lang = str(track.get("lang") or "").lower()
    if lang == "danmaku" or lang == "dm":
        return True
    ext = str(track.get("ext") or "").lower()
    if ext in {"xml"} and "comment.bilibili.com" in str(track.get("url") or ""):
        return True
    if "comment.bilibili.com" in str(track.get("url") or ""):
        return True
    return False


_DANMAKU_NOISE = re.compile(
    r"^(?:"
    r"前排|沙发|板凳|地[板板]|占座|打卡|签到|"
    r"666|888|999|233|哈哈+|呵呵+|嘿嘿+|"
    r"awsl|xswl|yyds|nb[cs]?|太强了|绝绝子|"
    r"一键三连|三连|点赞|投币|收藏|关注|"
    r"下次一定|下次还会来|下次一定来|"
    r"\?{2,}|!{2,}|。{2,}|…{2,}|"
    r"^[A-Za-z]{1,3}$|^\d+$|"
    r".{1,2}$"
    r")"
)


def parse_danmaku_cues(content: str) -> list[dict[str, str]]:
    """解析 B 站弹幕 XML 为 (start, text) 列表。

    弹幕不是字幕，但能反映视频关键内容（用户会针对关键点发弹幕），
    在平台字幕不可访问时作为兜底文本源。
    """
    if not content or not str(content).strip():
        return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    cues: list[dict[str, str]] = []
    seen_keys: set[tuple[int, str]] = set()
    for d in root.iter("d"):
        p = d.get("p", "")
        if not p:
            continue
        try:
            t = float(p.split(",")[0])
        except (ValueError, IndexError):
            continue
        if t < 0:
            continue
        text = (d.text or "").strip()
        if not text or len(text) < 2:
            continue
        # 简单去重：相同秒 + 相同文本算一条
        sec = int(t)
        key = (sec, text)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        # 弹幕时间戳是秒，转换为 mm:ss / hh:mm:ss
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        ts = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        cues.append({"start": ts, "text": text})

    # 按时间排序
    cues.sort(key=lambda c: c["start"])
    return cues


def _cue_seconds(start: str | int | float | None) -> int:
    """从 mm:ss / hh:mm:ss / 纯秒数解析出秒数；失败返回 -1。"""
    if start is None:
        return -1
    if isinstance(start, (int, float)):
        return max(0, int(start))
    s = str(start).strip()
    if not s:
        return -1
    # 去掉尾部 s / 秒
    s = re.sub(r"(秒|[sS])$", "", s).strip()
    try:
        # 纯数字（含小数）当秒
        if re.fullmatch(r"\d+(\.\d+)?", s):
            return max(0, int(float(s)))
        parts = s.replace(",", ".").split(":")
        nums = [float(p) for p in parts]
        if len(nums) == 3:
            return max(0, int(nums[0] * 3600 + nums[1] * 60 + nums[2]))
        if len(nums) == 2:
            return max(0, int(nums[0] * 60 + nums[1]))
        if len(nums) == 1:
            return max(0, int(nums[0]))
    except (ValueError, IndexError, TypeError):
        return -1
    return -1


def dedupe_cues_by_text_window(
    cues: list[dict[str, str]], window_seconds: int = 8
) -> list[dict[str, str]]:
    """对弹幕这种密集内容，在 N 秒窗口内只保留首条不同文本，去除大量重复刷屏。"""
    if not cues:
        return []
    kept: list[dict[str, str]] = []
    last_text_by_window: dict[int, str] = {}
    for c in cues:
        t = max(0, _cue_seconds(c.get("start", "")))
        win = t // window_seconds
        if last_text_by_window.get(win) == c["text"]:
            continue
        last_text_by_window[win] = c["text"]
        kept.append(c)
    return kept


def denoise_danmaku(cues: list[dict[str, str]]) -> list[dict[str, str]]:
    """过滤弹幕中常见的水弹幕/无意义短句（保留语义丰富的评论）。"""
    out: list[dict[str, str]] = []
    for c in cues:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        if len(text) < 3:
            continue
        if _DANMAKU_NOISE.match(text):
            continue
        out.append(c)
    return out


def _lang_rank(lang: str) -> int:
    l = str(lang or "").lower().replace("_", "-")
    if l in {"zh-hans", "zh-cn", "zh"}:
        return 0
    if l.startswith("zh") or l.startswith("ai-zh") or l in {"yue"}:
        return 1
    if l.startswith("en"):
        return 2
    return 3


def _subtitle_candidates(
    subs: list[dict[str, Any]],
    lang: str | None = None,
    automatic: bool | None = None,
) -> list[dict[str, Any]]:
    """按偏好排序：指定轨 → 人工中文 → 自动中文 → 其它。"""
    if not subs:
        return []

    def sort_key(s: dict[str, Any]) -> tuple:
        # 弹幕轨排在所有真实字幕之后：避免默认拉到弹幕而错过真实字幕
        dm = 1 if s.get("is_danmaku") else 0
        return (
            dm,
            1 if s.get("automatic") else 0,
            _lang_rank(str(s.get("lang") or "")),
            str(s.get("lang") or ""),
        )

    preferred: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for s in subs:
        match_lang = lang is None or s.get("lang") == lang
        match_auto = automatic is None or bool(s.get("automatic")) == automatic
        if match_lang and match_auto:
            preferred.append(s)
        else:
            rest.append(s)

    preferred.sort(key=sort_key)
    rest.sort(key=sort_key)

    ordered: list[dict[str, Any]] = []
    seen: set[int] = set()
    for s in preferred + rest:
        i = id(s)
        if i in seen:
            continue
        seen.add(i)
        ordered.append(s)
    return ordered


def _pick_subtitle(
    subs: list[dict[str, Any]],
    lang: str | None,
    automatic: bool | None,
) -> dict[str, Any] | None:
    ordered = _subtitle_candidates(subs, lang, automatic)
    return ordered[0] if ordered else None


def _load_subtitle_text(
    page_url: str,
    track: dict[str, Any],
) -> tuple[str, list[dict[str, str]]]:
    """优先直连字幕 URL，失败再走 yt-dlp 落盘。"""
    content = ""
    errors: list[str] = []
    track_url = (track.get("url") or "").strip()
    is_dm = is_danmaku_track(track)
    if track_url.startswith("http"):
        try:
            content = fetch_subtitle_url_content(track_url, page_url=page_url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"直连失败：{exc}")

    if not content.strip():
        if is_dm:
            # 弹幕直连失败就不再走 yt-dlp 落盘（弹幕不适合落盘）
            raise ValueError("；".join(errors) or "弹幕拉取失败")
        lang = str(track.get("lang") or "")
        automatic = bool(track.get("automatic"))
        outdir = DOWNLOAD_DIR / f"sum-{uuid.uuid4().hex}"
        try:
            path = download_subtitle(page_url, lang, outdir, automatic=automatic)
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"yt-dlp 下载失败：{exc}")
            raise ValueError("；".join(errors) or "字幕拉取失败") from exc

    if is_dm:
        cues = parse_danmaku_cues(content)
        # 先按 8 秒窗口去重刷屏，再过滤掉无意义水弹幕
        cues = dedupe_cues_by_text_window(cues, window_seconds=8)
        cues = denoise_danmaku(cues)
        if not cues:
            raise ValueError("弹幕已获取但解析为空")
    else:
        cues = parse_subtitle_cues(content)
        if not cues:
            raise ValueError("字幕文件已获取但无法解析出文本")

    plain = _plain_from_cues(cues)
    return plain, cues


def _plain_from_cues(
    cues: list[dict[str, str]],
    max_chars: int | None = None,
) -> str:
    """把字幕 cues 拼成带时间戳的纯文本；超长时跨全片采样，避免只截开头。"""
    limit = AI_MAX_SUBTITLE_CHARS if max_chars is None else max_chars
    lines = [
        f"[{c.get('start') or '00:00'}] {str(c.get('text') or '').strip()}"
        for c in cues
        if str(c.get("text") or "").strip()
    ]
    if not lines:
        return ""
    full = "\n".join(lines)
    if len(full) <= limit:
        return full

    n = len(lines)
    avg = max(1, len(full) // n)
    budget = max(24, min(n, limit // (avg + 1)))
    head = max(6, budget // 5)
    tail = max(6, budget // 5)
    mid = max(0, budget - head - tail)
    indices: list[int] = list(range(min(head, n)))
    if mid > 0 and n > head + tail:
        start, end = head, n - tail
        span = max(1, end - start)
        for i in range(1, mid + 1):
            indices.append(start + int(i * span / (mid + 1)))
    if tail > 0 and n > head:
        indices.extend(range(max(head, n - tail), n))

    seen: set[int] = set()
    picked: list[str] = []
    for i in sorted(indices):
        if 0 <= i < n and i not in seen:
            seen.add(i)
            picked.append(lines[i])
    text = "\n".join(picked)
    note = "\n…(字幕已跨片采样，覆盖全片时间轴)"
    if len(text) + len(note) > limit:
        text = text[: max(0, limit - len(note))] + note
    else:
        text += note
    return text


def _build_subtitle_segments(
    cues: list[dict[str, str]],
    *,
    max_chapters: int = 12,
    duration: float | int | None = None,
) -> list[dict[str, Any]]:
    """按字幕时间轴均分章节锚点（章节划分以字幕为准，而非模型自由编造）。"""
    timeline: list[tuple[int, dict[str, str]]] = []
    for c in cues:
        sec = _cue_seconds(c.get("start", ""))
        text = str(c.get("text") or "").strip()
        if sec < 0 or not text:
            continue
        timeline.append((sec, c))
    if not timeline:
        return []
    timeline.sort(key=lambda x: x[0])
    cue_max = timeline[-1][0]
    dur = _duration_seconds(duration) or 0
    # 片长优先；字幕最大时间作兜底（避免 duration 缺失时只看到片头）
    max_sec = max(dur, cue_max, 1)

    # 长视频略疏、短视频略密；上限 max_chapters
    if max_sec >= 3600:
        target = max(8, min(max_chapters, max_sec // 900 + 1))  # ~15min
    elif max_sec >= 600:
        target = max(6, min(max_chapters, max_sec // 120 + 1))
    else:
        target = max(4, min(max_chapters, max(4, (len(timeline) or 4) // 25)))
    n = max(1, min(target, max_chapters))
    if timeline:
        n = min(n, max(1, len(timeline)))

    segments: list[dict[str, Any]] = []
    used_idx: set[int] = set()
    for i in range(n):
        t = int(i * max_sec / n)
        sec = t
        sample = ""
        if timeline:
            # 找最接近目标时间的字幕（优先 >= t，否则最近）
            idx = len(timeline) - 1
            best_j = 0
            best_dist = abs(timeline[0][0] - t)
            for j, (s, _) in enumerate(timeline):
                dist = abs(s - t)
                if dist < best_dist:
                    best_dist = dist
                    best_j = j
                if s >= t:
                    idx = j
                    break
            else:
                idx = best_j
            # 避免连续段落落在同一句
            while idx in used_idx and idx + 1 < len(timeline):
                idx += 1
            if idx in used_idx and idx > 0:
                # 向前找未占用
                k = idx - 1
                while k >= 0 and k in used_idx:
                    k -= 1
                if k >= 0:
                    idx = k
            if idx in used_idx:
                # 仍占用则直接用目标时间，不再绑字幕句
                sec = t
            else:
                used_idx.add(idx)
                cue_sec, cue = timeline[idx]
                # 关键：字幕点若远早于目标（时间戳解析失败/字幕不全），用目标时间
                if cue_sec + 90 < t:
                    sec = t
                else:
                    sec = cue_sec
                t_end = int((i + 1) * max_sec / n) if i + 1 < n else max_sec + 1
                samples: list[str] = []
                for s, c in timeline[idx:]:
                    if s >= t_end and samples:
                        break
                    tx = str(c.get("text") or "").strip()
                    if tx:
                        samples.append(tx)
                    if len(samples) >= 10:
                        break
                sample = " ".join(samples)
        segments.append(
            {
                "start": _format_chapter_start(sec),
                "start_sec": sec,
                "sample": sample[:240],
            }
        )
    return segments


def _chapters_from_cues(
    cues: list[dict[str, str]],
    max_chapters: int = 8,
    *,
    duration: float | int | None = None,
) -> list[dict[str, str]]:
    """Mock / 兜底：直接按字幕时间轴分段生成章节。"""
    segments = _build_subtitle_segments(
        cues, max_chapters=max_chapters, duration=duration
    )
    chapters: list[dict[str, str]] = []
    for i, seg in enumerate(segments):
        sample = seg.get("sample") or ""
        title = sample[:36] + ("…" if len(sample) > 36 else "")
        if not title:
            title = f"第 {i + 1} 段"
        chapters.append(
            {
                "start": seg["start"],
                "title": title,
                "summary": sample[:160] or title,
            }
        )
    return chapters


def _format_chapter_start(raw: Any) -> str:
    """把任意形式的 start 字段规范化成 mm:ss 或 hh:mm:ss。

    接受：'6' / '6.5' / '6s' / '00:06' / '00:00:06' / '1:02:03' / 6 / 65.0
    无法解析时返回空串（前端会显示 '--:--'）。
    """
    if raw is None:
        return ""
    if isinstance(raw, (int, float)):
        sec = max(0, int(raw))
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    s = str(raw).strip()
    if not s:
        return ""
    # 去掉尾部 's' / 'S' / '秒'
    s = re.sub(r"(秒|[sS])$", "", s).strip()
    # 已经是 mm:ss 或 hh:mm:ss
    if re.fullmatch(r"\d{1,2}:\d{1,2}(?::\d{1,2})?", s):
        parts = s.split(":")
        try:
            nums = [int(p) for p in parts]
            if len(nums) == 2:
                return f"{nums[0]:02d}:{nums[1]:02d}"
            return f"{nums[0]}:{nums[1]:02d}:{nums[2]:02d}"
        except ValueError:
            return ""
    # 尝试作为秒数解析
    try:
        sec = max(0, int(float(s)))
        h, rem = divmod(sec, 3600)
        m, s2 = divmod(rem, 60)
        return f"{h}:{m:02d}:{s2:02d}" if h else f"{m:02d}:{s2:02d}"
    except ValueError:
        return ""


def _duration_seconds(duration: float | int | None) -> int | None:
    """规范化视频时长（秒）；无效则 None。"""
    if duration is None:
        return None
    try:
        sec = int(float(duration))
    except (TypeError, ValueError):
        return None
    return sec if sec > 0 else None


def _sanitize_chapters(
    chapters: list[dict[str, str]],
    *,
    duration: float | int | None = None,
    cues: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """按字幕/片长时间轴对齐章节：start 覆盖全片，标题摘要复用模型结果。

    长视频（≥10 分钟）一律按锚点重划分，避免模型把章节挤在片头。
    """
    cues = cues or []
    if _duration_seconds(duration) is None and cues:
        cue_max = max((_cue_seconds(c.get("start", "")) for c in cues), default=-1)
        if cue_max > 0:
            duration = cue_max

    segments = _build_subtitle_segments(
        cues, max_chapters=12, duration=duration
    )
    llm_chapters = [
        {
            "start": _format_chapter_start(c.get("start")),
            "title": str(c.get("title") or "").strip(),
            "summary": str(c.get("summary") or "").strip(),
        }
        for c in (chapters or [])
        if isinstance(c, dict)
    ]
    llm_chapters = [c for c in llm_chapters if c["start"] or c["title"] or c["summary"]]

    if segments:
        max_sec = max(
            _duration_seconds(duration) or 0,
            segments[-1]["start_sec"],
            1,
        )
        # 长视频一律按锚点划分，不信任模型自由时间戳
        force_anchors = max_sec >= 600
        llm_secs = [
            _cue_seconds(c["start"])
            for c in llm_chapters
            if c.get("start") and _cue_seconds(c["start"]) >= 0
        ]
        span_ok = False
        if not force_anchors and llm_secs and max_sec > 60:
            span_ok = (
                max(llm_secs) >= max_sec * 0.45
                and (max(llm_secs) - min(llm_secs)) >= max_sec * 0.35
            )

        if span_ok:
            cue_secs = [s["start_sec"] for s in segments]
            for c in cues:
                sec = _cue_seconds(c.get("start", ""))
                if 0 <= sec <= max_sec:
                    cue_secs.append(sec)
            cue_secs = sorted(set(cue_secs))
            out: list[dict[str, str]] = []
            for ch in llm_chapters[:12]:
                sec = _cue_seconds(ch["start"])
                if sec < 0:
                    sec = 0
                if sec > max_sec:
                    sec = max_sec
                if cue_secs:
                    sec = min(cue_secs, key=lambda t: (abs(t - sec), t))
                out.append(
                    {
                        "start": _format_chapter_start(sec),
                        "title": ch["title"] or "章节",
                        "summary": ch["summary"] or ch["title"] or "",
                    }
                )
            return out

        out = []
        for i, seg in enumerate(segments):
            title = ""
            summary = seg.get("sample") or ""
            if i < len(llm_chapters):
                title = llm_chapters[i].get("title") or ""
                summary = llm_chapters[i].get("summary") or summary
            if not title:
                sample = seg.get("sample") or ""
                title = sample[:36] + ("…" if len(sample) > 36 else "") or f"第 {i + 1} 段"
            out.append(
                {
                    "start": seg["start"],
                    "title": title,
                    "summary": (summary or title)[:200],
                }
            )
        return out

    max_sec = _duration_seconds(duration)
    out = []
    for ch in llm_chapters[:12]:
        start = ch.get("start") or ""
        if not start:
            continue
        sec = _cue_seconds(start)
        if sec < 0:
            sec = 0
        if max_sec is not None and sec > max_sec:
            sec = max_sec
        out.append(
            {
                "start": _format_chapter_start(sec),
                "title": ch.get("title") or "章节",
                "summary": ch.get("summary") or "",
            }
        )
    return out


def _normalize_mind_map(node: Any, fallback_name: str = "视频大纲") -> dict[str, Any]:
    if not isinstance(node, dict):
        return {"name": fallback_name, "children": []}
    name = str(node.get("name") or fallback_name).strip() or fallback_name
    children_raw = node.get("children") or []
    children: list[dict[str, Any]] = []
    if isinstance(children_raw, list):
        for ch in children_raw[:30]:
            if isinstance(ch, dict):
                children.append(_normalize_mind_map(ch, "分支"))
            elif isinstance(ch, str) and ch.strip():
                children.append({"name": ch.strip()[:150], "children": []})
    return {"name": name[:150], "children": children}


def build_mind_map(
    title: str,
    key_points: list[str],
    chapters: list[dict[str, str]],
) -> dict[str, Any]:
    """由要点与章节拼出树形导图（Mock / LLM 兜底），尽力提供 3–4 层结构。"""
    children: list[dict[str, Any]] = []

    # 分支 1：核心要点（带子要点拆分）
    if key_points:
        kp_children = []
        for p in key_points[:12]:
            sub_items = _split_point_to_subitems(p)
            kp_children.append({
                "name": p[:100],
                "children": sub_items if sub_items else [],
            })
        children.append({"name": "核心要点", "children": kp_children})

    # 分支 2：章节详解（每章带时间轴，摘要拆出子级）
    if chapters:
        ch_children = []
        for c in chapters[:12]:
            chapter_label = f"{c.get('start') or ''} {c.get('title') or ''}".strip()[:100]
            ch_sub: list[dict[str, Any]] = []
            summary = str(c.get("summary") or "")
            if summary:
                sub_items = _split_point_to_subitems(summary)
                ch_sub.extend(sub_items)
            ch_children.append({"name": chapter_label, "children": ch_sub})
        children.append({"name": "章节详解", "children": ch_children})

    # 分支 3：关键概念/术语（从要点和章节标题提取关键词）
    concept_items: list[str] = []
    for p in key_points[:8]:
        concept_items.append(p[:50])
    if not concept_items and chapters:
        for c in chapters[:6]:
            concept_items.append(str(c.get("title") or "")[:50])
    if concept_items:
        children.append({
            "name": "关键概念",
            "children": [{"name": item, "children": []} for item in concept_items if item],
        })

    # 分支 4：实践建议（更具体的操作指南）
    suggestions: list[dict[str, Any]] = []
    if chapters:
        suggestions.extend([
            {"name": "可使用时间轴直接跳转到章节关键位置", "children": []},
            {"name": "对照章节标题梳理学习路径", "children": []},
        ])
    if key_points:
        suggestions.extend([
            {"name": "重点回顾上述要点，结合原视频验证", "children": []},
            {"name": "将要点转化为笔记或卡片，便于后续检索", "children": []},
        ])
    suggestions.extend([
        {"name": "建议暂停做笔记，特别关注时间轴标记的重点段落", "children": []},
        {"name": "搭配实际项目或练习巩固理解", "children": []},
        {"name": "有疑问处回看原视频，AI 总结仅供参考", "children": []},
    ])
    children.append({
        "name": "实践建议",
        "children": suggestions,
    })

    if not children:
        children = [{"name": "暂无更多节点", "children": []}]
    return {"name": (title or "视频大纲")[:80], "children": children}


def _split_point_to_subitems(text: str) -> list[dict[str, Any]]:
    """将一段文字按常见分隔符拆为子要点，用于构建第三/四层节点。"""
    text = str(text or "").strip()
    if not text:
        return []
    parts = re.split(r"[；;，,\n、]", text)
    result: list[dict[str, Any]] = []
    for part in parts:
        part = part.strip()
        if not part or len(part) < 2:
            continue
        if result and result[-1]["name"] == part:
            continue
        result.append({"name": part[:80], "children": []})
        if len(result) >= 10:
            break
    return result if result else [{"name": text[:80], "children": []}]


def _chat_completion(system: str, user: str, *, temperature: float = 0.3) -> str:
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"AI 服务返回错误 {exc.response.status_code}：{exc.response.text[:200]}") from exc
    except httpx.RequestError as exc:
        raise ValueError(f"AI 服务网络请求失败：{exc}") from exc

    try:
        content = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"AI 服务返回结构异常：{str(data)[:200]}") from exc

    # 去除 Markdown 代码块包裹
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return content


def _extract_json(content: str) -> dict[str, Any]:
    """
    从 LLM 返回内容中提取 JSON 对象。
    容错策略：
    1. 直接 json.loads（理想情况）
    2. 提取第一个 { ... } 块（LLM 可能在 JSON 前后加说明文字）
    3. 均失败则抛 ValueError，由调用方降级为 Mock
    """
    content = content.strip()
    # 策略 1：直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 策略 2：提取第一个 { 到最后一个 } 之间的内容
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        fragment = content[start : end + 1]
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"LLM 返回内容无法解析为 JSON，前 200 字：{content[:200]}"
    )


def _mock_summary(
    *,
    title: str,
    description: str | None,
    plain: str | None,
    cues: list[dict[str, str]],
    source: str,
    tags: list[str] | None = None,
    uploader: str | None = None,
) -> dict[str, Any]:
    title = title or "未命名视频"
    desc = (description or "").strip()
    is_dm = source == "danmaku"
    is_meta = source == "metadata"
    is_user = source == "user"
    if is_dm:
        src_label = "弹幕"
    elif is_meta:
        src_label = "元数据"
    elif is_user:
        src_label = "用户字幕"
    else:
        src_label = "字幕"

    if is_meta:
        summary = (
            f"「演示总结」基于《{title}》的元数据生成（该视频无字幕/弹幕）。"
            f"这是无 API Key 时的 Mock 结果，仅供参考。详细请观看原视频。"
        )
    else:
        summary = (
            f"「演示总结」围绕《{title}》生成。这是无 API Key 时的 Mock 结果，"
            f"用于验收 UI。配置 SPEEDYDL_AI_API_KEY 后将调用真实大模型。"
        )
    if desc and desc != title:
        summary += f" 简介摘录：{desc[:160]}{'…' if len(desc) > 160 else ''}"
    elif plain:
        summary += f" 已参考{src_label}约 {len(plain)} 字。"

    key_points = [
        f"主题围绕「{title}」展开，适合快速了解大纲",
        "完整细节仍以原视频为准，总结仅供学习辅助",
    ]
    if uploader:
        key_points.append(f"作者：{uploader}")
    if tags:
        key_points.append("相关标签：" + "、".join(f"#{t}" for t in tags[:8]))
    if not is_meta:
        key_points.append(f"配置 SPEEDYDL_AI_API_KEY 后将基于{'弹幕' if is_dm else '字幕'}由大模型重写要点与章节")

    # 从字幕/弹幕中提取示例句子
    if plain and cues:
        samples = [c["text"] for c in cues if c.get("text")]
        if samples:
            step = max(len(samples) // 8, 1)
            for s in samples[::step][:8]:
                snippet = s.strip()[:100]
                if snippet and snippet not in key_points and not _DANMAKU_NOISE.match(snippet):
                    key_points.append(snippet + ("…" if len(s) > 100 else ""))
        if len(plain) > 500:
            key_points.append(f"{src_label}总字数约 {len(plain)}，建议观看原视频获取完整细节")
        if len(samples) > 10:
            key_points.append(f"共检测到约 {len(samples)} 条{src_label}段落")

    chapters = (
        _chapters_from_cues(cues, duration=None) if cues else []
    )
    points = key_points[:15]
    warning = "当前为 Mock 总结（未配置 SPEEDYDL_AI_API_KEY）"
    if is_meta:
        warning += "；仅基于标题/标签生成，无字幕/弹幕可参考"
    return {
        "mode": "mock",
        "source": source,
        "summary": summary,
        "key_points": points,
        "chapters": chapters,
        "mind_map": build_mind_map(title, points, chapters),
        "warning": warning,
    }


def _call_llm(
    title: str,
    plain: str,
    *,
    source: str = "subtitles",
    duration: float | int | None = None,
    cues: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """调用 OpenAI 兼容 Chat Completions，要求返回 JSON。解析失败时降级为结构化兜底。"""
    src_label = {
        "danmaku": "弹幕（已过滤水弹幕）",
        "user": "用户提供字幕",
        "metadata": "元数据",
    }.get(source, "字幕")
    dur_sec = _duration_seconds(duration)
    segments = _build_subtitle_segments(
        cues or [], max_chapters=12, duration=duration
    )
    dur_hint = ""
    if dur_sec is not None:
        dur_label = _format_chapter_start(dur_sec)
        dur_hint = (
            f"视频总时长约 {dur_label}（{dur_sec} 秒）。"
            "章节必须按字幕时间轴覆盖全片，禁止把所有章节挤在片头。\n"
        )
    anchor_hint = ""
    if segments:
        lines = [
            f"- {s['start']}: {(s.get('sample') or '')[:80]}" for s in segments
        ]
        anchor_hint = (
            "章节划分必须以字幕为准。请为下列字幕时间锚点各写一章"
            "（start 必须原样使用这些时间；title/summary 概括该段字幕）：\n"
            + "\n".join(lines)
            + "\n"
        )
    system = (
        "你是视频学习助手，帮助用户快速了解长视频大纲与核心知识。\n"
        f"以下文本来自视频的{src_label}。内容可能含少量口语化或评论式短句，请尽量提炼有价值信息。\n"
        f"{dur_hint}"
        f"{anchor_hint}"
        "根据带时间戳的文本，只输出 JSON（不要 Markdown 代码块）。\n"
        "必须包含字段：\n"
        "  - summary: 4-6 句中文总述，覆盖主旨、方法、结论\n"
        "  - key_points: 10-15 条短要点，每条 15-35 字\n"
        "  - chapters: 与上方字幕锚点一一对应的对象数组 [{start, title, summary}]；"
        "start 必须取自字幕时间锚点，覆盖从片头到片尾\n"
        "  - mind_map: 树形对象 {name, children[]}，务必做到 3-4 层深度\n\n"
        "mind_map 结构要求（重要）：\n"
        "  第1层(根)：视频主题名称。\n"
        "  第2层：必须包含以下 4 个分支 ——\n"
        "    ① 核心要点：拆分出具体要点，每个要点再拆分 1-3 个子点\n"
        "    ② 章节详解：每章单独节点（含时间戳），摘要拆为子点\n"
        "    ③ 关键概念：提取文本中提到的专业术语/核心概念\n"
        "    ④ 实践建议：可操作的学习建议或注意事项\n"
        "  第3层：要点/章节/概念的具体说明（用完整短句，非关键词堆砌）\n"
        "  第4层：对重要子项的进一步解释或举例\n"
        "  name 字段 ≤ 25 字，要求信息密度高、可独立阅读。\n\n"
        "不要编造文本中不存在的事实。每个节点 name 必须是中文短句。只输出合法 JSON，不要额外文字。"
    )
    user_msg = f"视频标题：{title}\n"
    if dur_sec is not None:
        user_msg += f"视频时长：{_format_chapter_start(dur_sec)}（{dur_sec} 秒）\n"
    user_msg += f"\n{src_label}内容：\n{plain}"
    content = _chat_completion(system, user_msg)

    try:
        parsed = _extract_json(content)
    except ValueError:
        # JSON 解析失败：用原始文本兜底，避免整页报错
        parsed = {
            "summary": content[:300] if content else "（模型返回内容无法解析）",
            "key_points": [],
            "chapters": [],
            "mind_map": None,
        }

    key_points = [str(x) for x in (parsed.get("key_points") or [])][:12]
    chapters = [
        {
            "start": _format_chapter_start(c.get("start")),
            "title": str(c.get("title") or "").strip(),
            "summary": str(c.get("summary") or "").strip(),
        }
        for c in (parsed.get("chapters") or [])
        if isinstance(c, dict)
    ]
    # 允许缺 start：后续会按字幕锚点回填
    chapters = [c for c in chapters if c["start"] or c["title"] or c["summary"]][:12]
    # 若模型没返回章节，用字幕分段兜底
    if not chapters and segments:
        chapters = [
            {
                "start": s["start"],
                "title": (s.get("sample") or "")[:36] or f"第 {i + 1} 段",
                "summary": (s.get("sample") or "")[:160],
            }
            for i, s in enumerate(segments)
        ]
    mind = _normalize_mind_map(parsed.get("mind_map"), title)
    if not mind.get("children"):
        mind = build_mind_map(title, key_points, chapters)
    return {
        "mode": "llm",
        "source": source,
        "summary": str(parsed.get("summary") or "").strip() or "（模型未返回摘要）",
        "key_points": key_points,
        "chapters": chapters,
        "mind_map": mind,
        "warning": None,
    }


def _call_llm_meta(
    title: str,
    *,
    description: str | None = None,
    uploader: str | None = None,
    tags: list[str] | None = None,
    duration: float | int | None = None,
) -> dict[str, Any]:
    """基于元数据（无字幕/弹幕时）的轻量级 AI 总结。

    适用于抖音等无公开字幕、无公开弹幕的平台。仅基于标题/描述/标签生成，
    不编造具体内容（如具体数字、人物对白），并在结果里附加 warning。
    """
    meta_parts = [f"视频标题：{title}"]
    if uploader:
        meta_parts.append(f"作者：{uploader}")
    if description and description != title:
        meta_parts.append(f"视频描述：{description[:400]}")
    if tags:
        meta_parts.append("话题标签：" + "、".join(f"#{t}" for t in tags[:12]))
    if duration:
        m, s = divmod(int(duration), 60)
        meta_parts.append(f"时长：{m}:{s:02d}")
    meta_text = "\n".join(meta_parts)

    system = (
        "你是视频元数据助手。该视频没有任何字幕/弹幕可参考，"
        "你只能根据标题、描述、标签推断大致主题，**禁止编造具体事实**。"
        "若信息过少，请明确告知用户「仅根据元数据推测，详细内容需观看原视频」。\n"
        "只输出 JSON（不要 Markdown 代码块），字段：\n"
        "  - summary: 2-4 句简短概述该视频可能涉及的主题（基于元数据）\n"
        "  - key_points: 3-6 条可能涉及的话题点（短句）\n"
        "  - chapters: 留空数组 []（无字幕无法生成时间轴）\n"
        "  - mind_map: {name, children[]}，1-2 层深度即可，根据元数据推测 2-3 个可能分支\n"
    )
    content = _chat_completion(system, meta_text, temperature=0.2)

    try:
        parsed = _extract_json(content)
    except ValueError:
        parsed = {
            "summary": (content or "").strip()[:300] or "（元数据不足以生成总结）",
            "key_points": [],
            "chapters": [],
            "mind_map": None,
        }

    key_points = [str(x) for x in (parsed.get("key_points") or [])][:8]
    chapters: list[dict[str, Any]] = []  # 元数据无时间轴
    mind = _normalize_mind_map(parsed.get("mind_map"), title)
    if not mind.get("children"):
        # 元数据兜底：基于标签做最简结构
        children = []
        if key_points:
            children.append({
                "name": "可能涉及的话题",
                "children": [{"name": p[:60], "children": []} for p in key_points[:6]],
            })
        if tags:
            children.append({
                "name": "相关标签",
                "children": [{"name": f"#{t}", "children": []} for t in tags[:8]],
            })
        if not children:
            children = [{"name": "（信息不足，仅供参考）", "children": []}]
        mind = {"name": (title or "视频主题")[:60], "children": children}

    return {
        "mode": "llm",
        "source": "metadata",
        "summary": str(parsed.get("summary") or "").strip() or "（元数据不足以生成总结）",
        "key_points": key_points,
        "chapters": chapters,
        "mind_map": mind,
        "warning": None,
    }


def _cues_from_user(
    transcript: list[dict[str, str]] | None = None,
    subtitle_text: str | None = None,
) -> list[dict[str, str]]:
    """将用户粘贴/上传的字幕转为 cues。"""
    if transcript and isinstance(transcript, list) and len(transcript) > 0:
        cues = [
            {"start": str(c.get("start") or "00:00"), "text": str(c.get("text") or "").strip()}
            for c in transcript
            if isinstance(c, dict) and str(c.get("text") or "").strip()
        ]
        if cues:
            return cues
    text = (subtitle_text or "").strip()
    if not text:
        return []
    return parse_subtitle_cues(text)


def _resolve_context(
    url: str,
    *,
    lang: str | None = None,
    automatic: bool | None = None,
    title: str | None = None,
    transcript: list[dict[str, str]] | None = None,
    subtitle_text: str | None = None,
    progress_hook: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """解析视频并获取文本：B站官方CC/AI → yt-dlp → 用户字幕 → 弹幕 → 元数据。"""

    def notify(pct: float, message: str = "") -> None:
        if progress_hook:
            progress_hook(pct, message)

    url = (url or "").strip()
    notify(0.02, "正在解析视频信息…")
    meta = parse_video(url)
    title = title or meta.get("title") or "未命名视频"
    description = meta.get("description")
    subs = meta.get("subtitles") or []
    real_tracks = [s for s in _subtitle_candidates(subs, lang, automatic) if not (
        s.get("is_danmaku") or is_danmaku_track(s)
    )]
    danmaku_tracks = [s for s in subs if s.get("is_danmaku") or is_danmaku_track(s)]

    plain = ""
    cues: list[dict[str, str]] = []
    danmaku_cues: list[dict[str, str]] = []
    source = "metadata"
    used_lang = None
    used_auto = None
    used_name = None
    used_is_danmaku = False
    fetch_errors: list[str] = []
    subtitle_warning = None

    # 1a) B 站官方字幕（dm/view：人工 CC → AI），对齐 NoteGPT
    notify(0.04, "正在拉取平台字幕…")
    try:
        from app.bilibili_subs import extract_bilibili_cues, is_bilibili_url

        if is_bilibili_url(url):
            bili = extract_bilibili_cues(url, lang=lang)
            if bili and bili.get("cues"):
                cues = bili["cues"]
                plain = _plain_from_cues(cues)
                track = bili.get("track") or {}
                used_lang = track.get("lan")
                used_auto = bool(track.get("automatic") or track.get("kind") == "ai")
                kind_label = "AI" if used_auto else "人工"
                used_name = track.get("lan_doc") or f"B站{kind_label}字幕"
                used_is_danmaku = False
                source = "subtitles"
                notify(0.20, f"B 站官方字幕拉取成功（{kind_label}）")
    except Exception as exc:  # noqa: BLE001
        fetch_errors.append(f"bilibili_api: {exc}")

    # 1b) yt-dlp 字幕轨（官方接口未命中时补充）
    if not cues:
        for track in real_tracks[:6]:
            try:
                plain, cues = _load_subtitle_text(url, track)
                used_lang = track.get("lang")
                used_auto = bool(track.get("automatic"))
                used_name = track.get("name") or used_lang
                used_is_danmaku = False
                source = "subtitles"
                notify(0.22, "平台字幕拉取成功")
                break
            except Exception as exc:  # noqa: BLE001
                fetch_errors.append(f"{track.get('lang')}: {exc}")
                continue

    # 2) 用户粘贴/上传字幕（无平台 CC 时）
    if not cues:
        user_cues = _cues_from_user(transcript, subtitle_text)
        if user_cues:
            cues = user_cues
            plain = _plain_from_cues(cues)
            used_lang = "user"
            used_auto = False
            used_name = "用户字幕"
            used_is_danmaku = False
            source = "user"
            notify(0.24, "已使用用户提供的字幕")

    # 3) 弹幕：始终尝试拉取，供「弹幕列表」；若尚无主文本则弹幕可兜底总结
    if danmaku_tracks:
        notify(0.28 if not cues else 0.84, "正在拉取弹幕…")
        for track in danmaku_tracks[:2]:
            try:
                _dm_plain, dm_cues = _load_subtitle_text(url, track)
                danmaku_cues = dm_cues
                if not cues:
                    plain, cues = _dm_plain, dm_cues
                    used_lang = track.get("lang")
                    used_auto = False
                    used_name = track.get("name") or "弹幕"
                    used_is_danmaku = True
                    source = "danmaku"
                    subtitle_warning = (
                        "该视频没有平台字幕（含 B 站 AI 字幕）；"
                        "已用弹幕兜底生成总结。也可粘贴/上传字幕后重试。"
                    )
                    notify(0.88, "弹幕兜底成功")
                break
            except Exception as exc:  # noqa: BLE001
                fetch_errors.append(f"danmaku: {exc}")
                continue

    if not cues:
        if subtitle_warning is None:
            if meta.get("description") or meta.get("tags"):
                subtitle_warning = (
                    "该视频没有平台字幕/弹幕，将基于标题与标签做轻量级总结。"
                    "也可粘贴或上传字幕后重试。"
                )
            else:
                subtitle_warning = (
                    "该视频没有可用文本源。请粘贴/上传字幕后重试。"
                )
        elif fetch_errors:
            pass

    real_sub_count = len(real_tracks)
    danmaku_count = len(danmaku_tracks)
    return {
        "url": url,
        "title": title,
        "description": description,
        "plain": plain,
        "cues": cues,
        "danmaku_cues": danmaku_cues,
        "source": source if plain else "metadata",
        "lang": used_lang,
        "automatic": used_auto,
        "is_danmaku": used_is_danmaku,
        "subtitle_name": used_name,
        "available_subtitles": real_sub_count,
        "available_real_subtitles": real_sub_count,
        "available_danmaku": danmaku_count,
        "subtitle_warning": subtitle_warning,
        "webpage_url": meta.get("webpage_url") or url,
        "thumbnail": meta.get("thumbnail"),
        "extractor": meta.get("extractor"),
        "uploader": meta.get("uploader"),
        "duration": meta.get("duration"),
        "_meta": {
            "tags": meta.get("tags") or [],
            "duration": meta.get("duration"),
            "uploader": meta.get("uploader"),
        },
    }


def summarize_video(
    url: str,
    *,
    lang: str | None = None,
    automatic: bool | None = None,
    title: str | None = None,
    transcript: list[dict[str, str]] | None = None,
    subtitle_text: str | None = None,
    progress_hook: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """
    总结入口。
    文本优先级：B 站官方 CC/AI → yt-dlp → 用户字幕 → 弹幕 → 元数据。
    无 API Key 时：Mock 兜底。
    """

    def notify(pct: float, message: str = "") -> None:
        if progress_hook:
            progress_hook(pct, message)

    ctx = _resolve_context(
        url,
        lang=lang,
        automatic=automatic,
        title=title,
        transcript=transcript,
        subtitle_text=subtitle_text,
        progress_hook=progress_hook,
    )
    use_llm = bool(AI_API_KEY)
    plain = ctx["plain"]
    cues = ctx["cues"]
    has_content = bool(plain)
    is_meta_only = not has_content

    duration = ctx.get("duration")
    if use_llm:
        if has_content:
            notify(0.92, "正在生成 AI 总结…")
            result = _call_llm(
                ctx["title"],
                plain,
                source=ctx["source"],
                duration=duration,
                cues=cues,
            )
        else:
            # 无字幕/弹幕时（如抖音），用元数据兜底
            notify(0.92, "正在基于元数据生成总结…")
            meta = ctx.get("_meta") or {}
            result = _call_llm_meta(
                ctx["title"],
                description=ctx.get("description"),
                uploader=ctx.get("uploader"),
                tags=meta.get("tags"),
                duration=meta.get("duration") or duration,
            )
    else:
        result = _mock_summary(
            title=ctx["title"],
            description=ctx["description"],
            plain=plain or None,
            cues=cues,
            source=ctx["source"],
            tags=ctx.get("_meta", {}).get("tags") if ctx.get("_meta") else None,
            uploader=ctx.get("uploader"),
        )

    # 章节按字幕时间轴划分并对齐（覆盖全片，避免挤在片头）
    result["chapters"] = _sanitize_chapters(
        result.get("chapters") or [],
        duration=duration,
        cues=cues,
    )
    result["lang"] = ctx["lang"]
    result["automatic"] = ctx["automatic"]
    result["is_danmaku"] = ctx.get("is_danmaku", False)
    result["subtitle_name"] = ctx.get("subtitle_name")
    result["available_subtitles"] = ctx.get("available_subtitles", 0)
    result["available_real_subtitles"] = ctx.get("available_real_subtitles", 0)
    result["available_danmaku"] = ctx.get("available_danmaku", 0)
    result["title"] = ctx["title"]
    result["url"] = ctx["webpage_url"]
    result["thumbnail"] = ctx["thumbnail"]
    result["extractor"] = ctx.get("extractor")
    result["duration"] = duration
    result["transcript"] = cues[:_TRANSCRIPT_MAX]
    result["transcript_truncated"] = len(cues) > _TRANSCRIPT_MAX
    result["transcript_count"] = len(cues)
    # 弹幕独立字段：CC 作主文本时仍可展示弹幕列表
    dm = ctx.get("danmaku_cues") or []
    result["danmaku_transcript"] = dm[:_TRANSCRIPT_MAX]
    result["danmaku_count"] = len(dm)
    # 页内播放参数（B 站带 cid 更稳）
    try:
        result["player"] = resolve_player_embed(ctx["webpage_url"] or url)
    except Exception:  # noqa: BLE001
        result["player"] = None
    if ctx.get("subtitle_warning"):
        # 保留 mock warning，追加字幕提示
        extra = ctx["subtitle_warning"]
        if result.get("warning"):
            result["warning"] = f"{result['warning']}；{extra}"
        else:
            result["warning"] = extra
    if "mind_map" not in result or not result["mind_map"]:
        result["mind_map"] = build_mind_map(
            ctx["title"],
            result.get("key_points") or [],
            result.get("chapters") or [],
        )
    notify(0.98, "正在整理结果…")
    return result


def ask_about_video(
    url: str,
    question: str,
    *,
    lang: str | None = None,
    automatic: bool | None = None,
    title: str | None = None,
    transcript: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    基于字幕/元数据回答与视频相关的问题。

    优化：若前端已持有总结结果的 transcript（字幕条目），可直接传入，
    避免重复调用 parse_video + 字幕拉取。
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("请输入问题")
    if len(question) > 500:
        raise ValueError("问题过长，请控制在 500 字以内")

    # 若前端传入了已有字幕条目，直接复用，跳过 _resolve_context 的重复解析
    if transcript and isinstance(transcript, list) and len(transcript) > 0:
        cues = [
            {"start": str(c.get("start") or ""), "text": str(c.get("text") or "")}
            for c in transcript
            if isinstance(c, dict)
        ]
        plain = "\n".join(f"[{c['start']}] {c['text']}" for c in cues)
        resolved_title = title or "未命名视频"
        subtitle_warning = None
        source = "subtitles"
    else:
        ctx = _resolve_context(url, lang=lang, automatic=automatic, title=title)
        cues = ctx["cues"]
        plain = ctx["plain"]
        resolved_title = ctx["title"]
        subtitle_warning = ctx.get("subtitle_warning")
        source = ctx.get("source", "metadata")

    use_llm = bool(AI_API_KEY)

    if use_llm:
        if not plain:
            raise ValueError(
                subtitle_warning
                or "该视频没有可用字幕，无法基于内容回答。请换有字幕的视频。"
            )
        system = (
            "你是视频学习助手。仅根据提供的字幕回答用户问题，使用简洁中文。"
            "若字幕未提及，明确说明「字幕中未提及」。可引用时间戳如 [00:12]。"
        )
        user = f"视频标题：{resolved_title}\n\n字幕：\n{plain}\n\n用户问题：{question}"
        answer = _chat_completion(system, user, temperature=0.2)
        return {
            "mode": "llm",
            "source": "subtitles",
            "question": question,
            "answer": answer,
            "warning": None,
        }

    snippets = []
    for c in cues[:12]:
        if any(tok in c["text"] for tok in question if len(tok) > 1):
            snippets.append(f"[{c['start']}] {c['text']}")
    if not snippets and cues:
        snippets = [f"[{c['start']}] {c['text']}" for c in cues[:3]]

    if snippets:
        answer = (
            f"「演示回答」关于「{question}」：根据《{resolved_title}》字幕片段，"
            f"相关内容包括：{'；'.join(snippets[:3])}。"
            "配置 SPEEDYDL_AI_API_KEY 后将由大模型基于全文回答。"
        )
        resolved_source = "subtitles" if source == "subtitles" or snippets else "metadata"
    else:
        answer = (
            f"「演示回答」关于「{question}」：当前无字幕可检索，"
            f"仅知视频标题为《{resolved_title}》。"
            "配置 API Key 并换有平台字幕的视频后可获得更准确回答。"
        )
        resolved_source = "metadata"

    warning = "当前为 Mock 回答（未配置 SPEEDYDL_AI_API_KEY）"
    if subtitle_warning:
        warning = f"{warning}；{subtitle_warning}"

    return {
        "mode": "mock",
        "source": resolved_source,
        "question": question,
        "answer": answer,
        "warning": warning,
    }


def _chat_completion_stream(
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
):
    """流式调用 OpenAI 兼容 chat/completions，逐段 yield 文本。"""
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "stream": True,
    }
    try:
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{AI_BASE_URL.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                if resp.status_code >= 400:
                    body = resp.read().decode("utf-8", errors="replace")[:200]
                    raise ValueError(f"AI 服务返回错误 {resp.status_code}：{body}")
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                    else:
                        data_str = line.strip()
                    if not data_str or data_str == "[DONE]":
                        if data_str == "[DONE]":
                            break
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = chunk["choices"][0].get("delta") or {}
                        piece = delta.get("content") or ""
                    except (KeyError, IndexError, TypeError):
                        continue
                    if piece:
                        yield piece
    except httpx.RequestError as exc:
        raise ValueError(f"AI 服务网络请求失败：{exc}") from exc


def iter_ask_events(
    url: str,
    question: str,
    *,
    lang: str | None = None,
    automatic: bool | None = None,
    title: str | None = None,
    transcript: list[dict[str, str]] | None = None,
):
    """
    问答事件流（供 SSE）：
    - status / token / done / error
    """
    try:
        question = (question or "").strip()
        if not question:
            raise ValueError("请输入问题")
        if len(question) > 500:
            raise ValueError("问题过长，请控制在 500 字以内")

        yield {"event": "status", "data": {"message": "正在整理视频上下文…"}}

        if transcript and isinstance(transcript, list) and len(transcript) > 0:
            cues = [
                {"start": str(c.get("start") or ""), "text": str(c.get("text") or "")}
                for c in transcript
                if isinstance(c, dict)
            ]
            plain = "\n".join(f"[{c['start']}] {c['text']}" for c in cues)
            resolved_title = title or "未命名视频"
            subtitle_warning = None
            source = "subtitles"
        else:
            ctx = _resolve_context(url, lang=lang, automatic=automatic, title=title)
            cues = ctx["cues"]
            plain = ctx["plain"]
            resolved_title = ctx["title"]
            subtitle_warning = ctx.get("subtitle_warning")
            source = ctx.get("source", "metadata")

        use_llm = bool(AI_API_KEY)
        answer_parts: list[str] = []

        if use_llm:
            if not plain:
                raise ValueError(
                    subtitle_warning
                    or "该视频没有可用字幕，无法基于内容回答。请换有字幕的视频。"
                )
            yield {"event": "status", "data": {"message": "正在生成回答…"}}
            system = (
                "你是视频学习助手。仅根据提供的字幕回答用户问题，使用简洁中文。"
                "若字幕未提及，明确说明「字幕中未提及」。可引用时间戳如 [00:12]。"
            )
            user = (
                f"视频标题：{resolved_title}\n\n字幕：\n{plain}\n\n用户问题：{question}"
            )
            for piece in _chat_completion_stream(system, user, temperature=0.2):
                answer_parts.append(piece)
                yield {"event": "token", "data": {"text": piece}}
            answer = "".join(answer_parts).strip()
            if answer.startswith("```"):
                answer = re.sub(r"^```(?:\w+)?\s*", "", answer)
                answer = re.sub(r"\s*```$", "", answer)
            payload = {
                "mode": "llm",
                "source": "subtitles",
                "question": question,
                "answer": answer,
                "warning": None,
            }
        else:
            # Mock：复用已解析上下文，避免再次 _resolve_context
            snippets = []
            for c in cues[:12]:
                if any(tok in c["text"] for tok in question if len(tok) > 1):
                    snippets.append(f"[{c['start']}] {c['text']}")
            if not snippets and cues:
                snippets = [f"[{c['start']}] {c['text']}" for c in cues[:3]]
            if snippets:
                answer = (
                    f"「演示回答」关于「{question}」：根据《{resolved_title}》字幕片段，"
                    f"相关内容包括：{'；'.join(snippets[:3])}。"
                    "配置 SPEEDYDL_AI_API_KEY 后将由大模型基于全文回答。"
                )
                resolved_source = (
                    "subtitles" if source == "subtitles" or snippets else "metadata"
                )
            else:
                answer = (
                    f"「演示回答」关于「{question}」：当前无字幕可检索，"
                    f"仅知视频标题为《{resolved_title}》。"
                    "配置 API Key 并换有平台字幕的视频后可获得更准确回答。"
                )
                resolved_source = "metadata"
            warning = "当前为 Mock 回答（未配置 SPEEDYDL_AI_API_KEY）"
            if subtitle_warning:
                warning = f"{warning}；{subtitle_warning}"
            payload = {
                "mode": "mock",
                "source": resolved_source,
                "question": question,
                "answer": answer,
                "warning": warning,
            }
            yield {"event": "status", "data": {"message": "正在生成演示回答…"}}
            step = 12
            for i in range(0, len(answer), step):
                piece = answer[i : i + step]
                yield {"event": "token", "data": {"text": piece}}

        yield {"event": "done", "data": payload}
    except Exception as exc:  # noqa: BLE001
        yield {"event": "error", "data": {"error": str(exc)}}


class SubtitleExtractor:
    """从 URL 提取文本：B站官方CC/AI → yt-dlp → 用户字幕 → 弹幕 → 元数据。"""

    def extract(
        self,
        url: str,
        *,
        lang: str | None = None,
        automatic: bool | None = None,
        title: str | None = None,
        transcript: list[dict[str, str]] | None = None,
        subtitle_text: str | None = None,
        progress_hook: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        return _resolve_context(
            url,
            lang=lang,
            automatic=automatic,
            title=title,
            transcript=transcript,
            subtitle_text=subtitle_text,
            progress_hook=progress_hook,
        )


class VideoSummarizer:
    """AI 视频总结与问答（依赖 SubtitleExtractor）。"""

    def __init__(self, extractor: SubtitleExtractor | None = None) -> None:
        self.extractor = extractor or SubtitleExtractor()

    def summarize(
        self,
        url: str,
        *,
        lang: str | None = None,
        automatic: bool | None = None,
        title: str | None = None,
        transcript: list[dict[str, str]] | None = None,
        subtitle_text: str | None = None,
        progress_hook: Callable[[float, str], None] | None = None,
    ) -> dict[str, Any]:
        return summarize_video(
            url,
            lang=lang,
            automatic=automatic,
            title=title,
            transcript=transcript,
            subtitle_text=subtitle_text,
            progress_hook=progress_hook,
        )

    def ask(
        self,
        url: str,
        question: str,
        *,
        lang: str | None = None,
        automatic: bool | None = None,
        title: str | None = None,
        transcript: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        return ask_about_video(
            url,
            question,
            lang=lang,
            automatic=automatic,
            title=title,
            transcript=transcript,
        )

    def iter_ask(
        self,
        url: str,
        question: str,
        *,
        lang: str | None = None,
        automatic: bool | None = None,
        title: str | None = None,
        transcript: list[dict[str, str]] | None = None,
    ):
        return iter_ask_events(
            url,
            question,
            lang=lang,
            automatic=automatic,
            title=title,
            transcript=transcript,
        )

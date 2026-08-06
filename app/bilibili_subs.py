"""
B 站官方字幕提取（对齐 NoteGPT / BibiGPT 管线）。

BV → view(aid/cid) → dm/view 字幕轨 → 人工 CC 优先 / AI 后补 → BCC JSON。
不下载视频、不做 Whisper ASR。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.config import BILI_SESSDATA, BILI_SUBS_ENABLED

logger = logging.getLogger(__name__)

_BV_RE = re.compile(r"(BV[\w]+)", re.I)
_AV_RE = re.compile(r"(?:/av|aid=)(\d+)", re.I)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def is_bilibili_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return False
    if "bilibili.com" in host or "b23.tv" in host:
        return True
    return bool(_BV_RE.search(url or ""))


def extract_bvid(url: str) -> str | None:
    m = _BV_RE.search(url or "")
    return m.group(1) if m else None


def extract_aid(url: str) -> str | None:
    m = _AV_RE.search(url or "")
    return m.group(1) if m else None


def extract_page_index(url: str) -> int:
    """分 P：?p=2 → 2；默认 1。"""
    try:
        qs = parse_qs(urlparse(url).query)
        raw = (qs.get("p") or ["1"])[0]
        return max(1, int(raw))
    except Exception:  # noqa: BLE001
        return 1


def _headers(*, page_url: str | None = None) -> dict[str, str]:
    h = {
        "User-Agent": _UA,
        "Referer": page_url or "https://www.bilibili.com/",
        "Accept": "application/json,text/plain,*/*",
    }
    if BILI_SESSDATA:
        h["Cookie"] = f"SESSDATA={BILI_SESSDATA}"
    return h


def normalize_subtitle_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return u
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http://"):
        # HTTPS 页面 / CDN 均支持 https
        return "https://" + u[len("http://") :]
    return u


def _format_seconds(sec: float) -> str:
    total = max(0, int(sec))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fetch_view(
    *,
    bvid: str | None = None,
    aid: str | None = None,
    page_index: int = 1,
    page_url: str | None = None,
) -> dict[str, Any]:
    """调用 /x/web-interface/view，返回 aid/cid/title/pages 等。"""
    params: dict[str, str] = {}
    if bvid:
        params["bvid"] = bvid
    elif aid:
        params["aid"] = aid
    else:
        return {}
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(
                "https://api.bilibili.com/x/web-interface/view",
                params=params,
                headers=_headers(page_url=page_url),
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("B 站 view 失败: %s", exc)
        return {}
    if payload.get("code") != 0:
        return {}
    data = payload.get("data") or {}
    pages = data.get("pages") or []
    cid = data.get("cid")
    if pages:
        idx = min(max(page_index, 1), len(pages)) - 1
        page = pages[idx] or {}
        cid = page.get("cid") or cid
    out: dict[str, Any] = {
        "bvid": data.get("bvid") or bvid,
        "aid": data.get("aid"),
        "cid": cid,
        "title": data.get("title"),
        "desc": data.get("desc"),
        "duration": data.get("duration"),
        "pages": pages,
    }
    return out


def list_subtitle_tracks(
    *,
    cid: int | str,
    aid: int | str | None = None,
    page_url: str | None = None,
) -> list[dict[str, Any]]:
    """
    列出字幕轨。优先 dm/view，失败再试 player/v2。
    每项保留原始字段并补充 kind=human|ai。
    """
    cid_s = str(cid)
    tracks = _list_from_dm_view(cid_s, page_url=page_url)
    if not tracks and aid is not None:
        tracks = _list_from_player_v2(aid=str(aid), cid=cid_s, page_url=page_url)
    return tracks


def _normalize_track(raw: dict[str, Any]) -> dict[str, Any]:
    lan = str(raw.get("lan") or "").strip()
    lan_doc = str(raw.get("lan_doc") or raw.get("name") or lan).strip()
    url = normalize_subtitle_url(str(raw.get("subtitle_url") or raw.get("url") or ""))
    ai_status = raw.get("ai_status")
    lan_l = lan.lower()
    doc_l = lan_doc.lower()
    is_ai = (
        lan_l.startswith("ai-")
        or "ai" in doc_l
        or (isinstance(ai_status, int) and ai_status > 0)
    )
    # type: 0=人工 1=AI（常见约定）；lan 明确 ai- 时强制 AI
    if lan_l.startswith("ai-"):
        is_ai = True
    elif raw.get("type") == 0:
        is_ai = False
    elif raw.get("type") == 1 and not lan_l:
        is_ai = True
    return {
        "lan": lan or ("ai-zh" if is_ai else "zh-CN"),
        "lan_doc": lan_doc or lan,
        "subtitle_url": url,
        "ai_status": ai_status,
        "type": raw.get("type"),
        "kind": "ai" if is_ai else "human",
        "automatic": is_ai,
        "is_danmaku": False,
    }


def _list_from_dm_view(cid: str, *, page_url: str | None = None) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(
                "https://api.bilibili.com/x/v2/dm/view",
                params={"oid": cid, "type": "1"},
                headers=_headers(page_url=page_url),
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("B 站 dm/view 失败: %s", exc)
        return []
    code = payload.get("code")
    if code not in (0, None):
        logger.info("dm/view code=%s msg=%s", code, payload.get("message"))
        # 部分环境仍可能带 data，继续尝试解析
    data = payload.get("data") or {}
    sub = data.get("subtitle") or {}
    raw_list = sub.get("subtitles") or []
    return [
        _normalize_track(t)
        for t in raw_list
        if isinstance(t, dict) and (t.get("subtitle_url") or t.get("url"))
    ]


def _list_from_player_v2(
    *,
    aid: str,
    cid: str,
    page_url: str | None = None,
) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(
                "https://api.bilibili.com/x/player/v2",
                params={"aid": aid, "cid": cid},
                headers=_headers(page_url=page_url),
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("B 站 player/v2 失败: %s", exc)
        return []
    if payload.get("code") != 0:
        return []
    data = payload.get("data") or {}
    sub = data.get("subtitle") or {}
    raw_list = sub.get("subtitles") or []
    return [_normalize_track(t) for t in raw_list if isinstance(t, dict) and (
        t.get("subtitle_url") or t.get("url")
    )]


def _lang_match_score(lan: str, want: str | None) -> int:
    """越小越优先。"""
    lan_l = (lan or "").lower()
    want_l = (want or "").lower().strip()
    if not want_l:
        # 默认偏好中文
        if lan_l in {"zh-hans", "zh-cn", "zh", "zh-hans"} or lan_l.startswith("ai-zh"):
            return 0
        if lan_l.startswith("zh") or "zh" in lan_l:
            return 1
        return 5
    if lan_l == want_l or lan_l.replace("_", "-") == want_l.replace("_", "-"):
        return 0
    if want_l.startswith("zh") and (lan_l.startswith("zh") or lan_l.startswith("ai-zh")):
        return 1
    if want_l in lan_l or lan_l in want_l:
        return 2
    return 9


def pick_track(
    tracks: list[dict[str, Any]],
    lang: str | None = None,
) -> dict[str, Any] | None:
    """人工轨优先，同语言 AI 后补。"""
    if not tracks:
        return None
    scored: list[tuple[tuple, dict[str, Any]]] = []
    for t in tracks:
        kind_rank = 0 if t.get("kind") == "human" else 1
        lang_rank = _lang_match_score(str(t.get("lan") or ""), lang)
        scored.append(((lang_rank, kind_rank, str(t.get("lan") or "")), t))
    scored.sort(key=lambda x: x[0])
    best = scored[0][1]
    # 若最优语言完全不匹配且用户指定了语言，仍返回最优中文/第一条
    return best


def fetch_bcc(subtitle_url: str, *, page_url: str | None = None) -> dict[str, Any]:
    url = normalize_subtitle_url(subtitle_url)
    if not url:
        raise ValueError("字幕 URL 为空")
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(url, headers=_headers(page_url=page_url))
        resp.raise_for_status()
        text = resp.text
    if not text or not text.strip():
        raise RuntimeError("BCC 字幕内容为空")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"BCC 不是合法 JSON：{exc}") from exc


def bcc_to_cues(bcc: dict[str, Any] | list | None) -> list[dict[str, str]]:
    """BCC JSON → [{start, text, end?}]。"""
    if bcc is None:
        return []
    if isinstance(bcc, list):
        body = bcc
    else:
        body = bcc.get("body") or []
    cues: list[dict[str, str]] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        try:
            start = float(item.get("from") or 0)
        except (TypeError, ValueError):
            start = 0.0
        cue: dict[str, str] = {"start": _format_seconds(start), "text": content}
        try:
            end = float(item.get("to"))
            cue["end"] = _format_seconds(end)
        except (TypeError, ValueError):
            pass
        cues.append(cue)
    return cues


def tracks_as_subtitle_entries(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """转为 parse_video 使用的 subtitles 条目格式。"""
    out: list[dict[str, Any]] = []
    for t in tracks:
        lan = str(t.get("lan") or "zh")
        name = str(t.get("lan_doc") or lan)
        is_ai = t.get("kind") == "ai" or bool(t.get("automatic"))
        if is_ai and "AI" not in name and "ai" not in name.lower():
            name = f"{name}（AI）"
        out.append(
            {
                "lang": lan,
                "name": name,
                "ext": "json",
                "automatic": is_ai,
                "is_danmaku": False,
                "url": t.get("subtitle_url"),
                "source": "bilibili_api",
            }
        )
    return out


def extract_bilibili_cues(
    url: str,
    *,
    lang: str | None = None,
) -> dict[str, Any] | None:
    """
    一站式：成功返回 {cues, plain, track, view}；失败返回 None。
    """
    if not BILI_SUBS_ENABLED:
        return None
    if not is_bilibili_url(url):
        return None

    bvid = extract_bvid(url)
    aid = extract_aid(url)
    page_index = extract_page_index(url)
    view = fetch_view(bvid=bvid, aid=aid, page_index=page_index, page_url=url)
    cid = view.get("cid")
    if not cid:
        return None
    tracks = list_subtitle_tracks(
        cid=cid,
        aid=view.get("aid") or aid,
        page_url=url,
    )
    if not tracks:
        return None
    track = pick_track(tracks, lang=lang)
    if not track or not track.get("subtitle_url"):
        return None
    try:
        bcc = fetch_bcc(track["subtitle_url"], page_url=url)
        cues = bcc_to_cues(bcc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("拉取 BCC 失败: %s", exc)
        return None
    if not cues:
        return None
    plain = "\n".join(f"[{c['start']}] {c['text']}" for c in cues)
    return {
        "cues": cues,
        "plain": plain,
        "track": track,
        "view": view,
        "tracks": tracks,
    }


def merge_bilibili_tracks_into_subtitles(
    url: str,
    existing: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """把官方轨合并进 yt-dlp 字幕列表（去重 by lang+automatic）。"""
    existing = list(existing or [])
    if not BILI_SUBS_ENABLED or not is_bilibili_url(url):
        return existing
    try:
        bvid = extract_bvid(url)
        aid = extract_aid(url)
        page_index = extract_page_index(url)
        view = fetch_view(bvid=bvid, aid=aid, page_index=page_index, page_url=url)
        cid = view.get("cid")
        if not cid:
            return existing
        tracks = list_subtitle_tracks(
            cid=cid,
            aid=view.get("aid") or aid,
            page_url=url,
        )
        entries = tracks_as_subtitle_entries(tracks)
    except Exception as exc:  # noqa: BLE001
        logger.warning("合并 B 站字幕轨失败: %s", exc)
        return existing

    seen = {
        f"{'a' if s.get('automatic') else 'm'}:{str(s.get('lang') or '').lower()}"
        for s in existing
        if not s.get("is_danmaku")
    }
    for e in entries:
        key = f"{'a' if e.get('automatic') else 'm'}:{str(e.get('lang') or '').lower()}"
        if key in seen:
            # 官方 URL 更可靠：替换同 key 条目
            for i, old in enumerate(existing):
                okey = f"{'a' if old.get('automatic') else 'm'}:{str(old.get('lang') or '').lower()}"
                if okey == key and not old.get("is_danmaku"):
                    existing[i] = {**old, **e}
                    break
            continue
        seen.add(key)
        # 插到弹幕之前
        insert_at = len(existing)
        for i, old in enumerate(existing):
            if old.get("is_danmaku"):
                insert_at = i
                break
        existing.insert(insert_at, e)

    # 无 yt-dlp listsubtitles 时补一条官方弹幕轨（供总结兜底）
    if cid and not any(s.get("is_danmaku") for s in existing):
        existing.append(
            {
                "lang": "danmaku",
                "name": "弹幕（B 站兜底）",
                "ext": "xml",
                "automatic": False,
                "is_danmaku": True,
                "url": f"https://comment.bilibili.com/{cid}.xml",
            }
        )
    return existing

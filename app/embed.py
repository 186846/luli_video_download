"""
页内播放：解析平台嵌入地址（B 站需 bvid/cid，YouTube 用 embed）。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

_BV_RE = re.compile(r"(BV[\w]+)", re.I)
_AV_RE = re.compile(r"/av(\d+)", re.I)


def _youtube_id(url: str) -> str | None:
    try:
        u = urlparse(url)
    except Exception:  # noqa: BLE001
        return None
    host = (u.hostname or "").lower()
    if "youtu.be" in host:
        return (u.pathname or "").strip("/").split("/")[0] or None
    if "youtube.com" in host:
        qs = parse_qs(u.query)
        if qs.get("v"):
            return qs["v"][0]
        parts = [p for p in (u.pathname or "").split("/") if p]
        if parts and parts[0] in {"embed", "shorts", "live"} and len(parts) > 1:
            return parts[1]
    return None


def _bilibili_ids_from_api(bvid: str | None = None, aid: str | None = None) -> dict[str, Any]:
    """调用 B 站公开 view 接口拿 aid/cid（嵌入播放更稳）。"""
    params: dict[str, str] = {}
    if bvid:
        params["bvid"] = bvid
    elif aid:
        params["aid"] = aid
    else:
        return {}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
    }
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            resp = client.get(
                "https://api.bilibili.com/x/web-interface/view",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            payload = resp.json()
    except Exception:  # noqa: BLE001
        return {}
    if payload.get("code") != 0:
        return {}
    data = payload.get("data") or {}
    cid = data.get("cid")
    pages = data.get("pages") or []
    if not cid and pages:
        cid = pages[0].get("cid")
    out: dict[str, Any] = {}
    if data.get("bvid"):
        out["bvid"] = data["bvid"]
    if data.get("aid"):
        out["aid"] = str(data["aid"])
    if cid:
        out["cid"] = str(cid)
    return out


def resolve_player_embed(url: str, *, start_seconds: int = 0) -> dict[str, Any] | None:
    """
    返回可嵌入播放信息：
    { provider, embed_url, page_url, bvid?, aid?, cid? }
    """
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    start_seconds = max(0, int(start_seconds or 0))

    # —— B 站 ——
    if re.search(r"bilibili\.com|b23\.tv", url, re.I):
        bv_m = _BV_RE.search(url)
        av_m = _AV_RE.search(url)
        bvid = bv_m.group(1) if bv_m else None
        aid = av_m.group(1) if av_m else None
        meta = _bilibili_ids_from_api(bvid=bvid, aid=aid)
        bvid = meta.get("bvid") or bvid
        aid = meta.get("aid") or aid
        cid = meta.get("cid")
        if not bvid and not aid:
            return None
        params = {
            "page": "1",
            "high_quality": "1",
            "danmaku": "0",
            "autoplay": "0",
            "as_wide": "1",
        }
        if bvid:
            params["bvid"] = bvid
        if aid:
            params["aid"] = str(aid)
        if cid:
            params["cid"] = str(cid)
        if start_seconds > 0:
            params["t"] = str(start_seconds)
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return {
            "provider": "bilibili",
            "embed_url": f"https://player.bilibili.com/player.html?{qs}",
            "page_url": url,
            "bvid": bvid,
            "aid": aid,
            "cid": cid,
        }

    # —— YouTube ——
    yt = _youtube_id(url)
    if yt:
        qs = f"rel=0&modestbranding=1"
        if start_seconds > 0:
            qs += f"&start={start_seconds}"
        return {
            "provider": "youtube",
            "embed_url": f"https://www.youtube.com/embed/{yt}?{qs}",
            "page_url": url,
            "video_id": yt,
        }

    return None

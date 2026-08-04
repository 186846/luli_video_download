"""
抖音无 Cookie 解析（学习向）。

思路参考开源项目 Unmark / douyin-direct-parser：
请求移动端分享页 https://www.iesdouyin.com/share/video/{id}/，
从 HTML 中的 window._ROUTER_DATA 取公开作品数据，再构造
https://aweme.snssdk.com/aweme/v1/play/ 无水印播放地址。

用户无需导出 Cookie；私密/已删除内容仍会失败。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import httpx

from app.config import FREE_MAX_HEIGHT

ProgressHook = Callable[[dict[str, Any]], None]

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 8.0.0; SM-G955U) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36"
)

_DEFAULT_HEADERS = {
    "User-Agent": MOBILE_UA,
    "Referer": "https://www.douyin.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 清晰度选项（与 aweme play API 的 ratio 对应）
_RATIO_CHOICES: list[tuple[str, int]] = [
    ("1080p", 1080),
    ("720p", 720),
    ("540p", 540),
]

_AWEME_ID_RE = re.compile(
    r"(?:/video/|/note/|share/video/|share/note/|modal_id=)(\d{6,})",
    re.I,
)
_URL_IN_TEXT_RE = re.compile(
    r"https?://(?:v\.|www\.)?(?:douyin|iesdouyin)\.com/[^\s]+",
    re.I,
)


def is_douyin_url(url: str) -> bool:
    """判断是否为抖音相关链接（含分享文案中的短链）。"""
    text = (url or "").strip()
    if not text:
        return False
    if _URL_IN_TEXT_RE.search(text):
        return True
    host = urlparse(text).netloc.lower()
    return any(h in host for h in ("douyin.com", "iesdouyin.com"))


def extract_url_from_text(text: str) -> str:
    """从「复制口令」文案中抽出第一条抖音 URL；否则原样返回。"""
    m = _URL_IN_TEXT_RE.search(text or "")
    return m.group(0).rstrip(")/，。,. ") if m else (text or "").strip()


def _client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        headers=_DEFAULT_HEADERS,
        timeout=timeout,
    )


def resolve_aweme_id(url: str) -> str:
    """短链 / 长链 → aweme_id。"""
    cleaned = extract_url_from_text(url)
    m = _AWEME_ID_RE.search(cleaned)
    if m and "v.douyin.com" not in cleaned.lower():
        return m.group(1)

    with _client() as client:
        resp = client.get(cleaned)
        final = str(resp.url)
    m = _AWEME_ID_RE.search(final)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{15,})", final)
    if m:
        return m.group(1)
    raise ValueError("无法从抖音链接提取作品 ID，请换标准分享链接重试")


def _extract_balanced_json(html: str, marker: str) -> dict[str, Any]:
    start = html.find(marker)
    if start < 0:
        raise ValueError(f"页面缺少 {marker.strip()}")
    i = start + len(marker)
    while i < len(html) and html[i].isspace():
        i += 1
    if i >= len(html) or html[i] != "{":
        raise ValueError("ROUTER_DATA 不是 JSON 对象")
    depth = 0
    in_str = False
    escape = False
    for j in range(i, len(html)):
        ch = html[j]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[i : j + 1])
    raise ValueError("ROUTER_DATA JSON 不完整")


def _fetch_share_item(aweme_id: str) -> dict[str, Any]:
    """拉取分享页并返回 item_list[0]。"""
    paths = (
        f"https://www.iesdouyin.com/share/video/{aweme_id}/",
        f"https://www.iesdouyin.com/share/note/{aweme_id}/",
    )
    last_err: Exception | None = None
    with _client() as client:
        for share_url in paths:
            try:
                html = client.get(share_url).text
                data = None
                for marker in ("window._ROUTER_DATA = ", "window._ROUTER_DATA="):
                    if marker in html:
                        data = _extract_balanced_json(html, marker)
                        break
                if data is None and "RENDER_DATA" in html:
                    m = re.search(
                        r'<script id="RENDER_DATA" type="application/json">(.*?)</script>',
                        html,
                        re.S,
                    )
                    if m:
                        data = json.loads(unquote(m.group(1)))
                if not data:
                    raise ValueError("分享页未包含可解析数据")

                loader = data.get("loaderData") or {}
                item = None
                filter_reason = None
                for val in loader.values():
                    if not isinstance(val, dict):
                        continue
                    info = val.get("videoInfoRes") or {}
                    items = info.get("item_list") or []
                    if items:
                        item = items[0]
                        break
                    filters = info.get("filter_list") or []
                    if filters and isinstance(filters[0], dict):
                        filter_reason = filters[0].get("filter_reason")

                if item:
                    return item
                if filter_reason:
                    raise ValueError(
                        f"抖音作品不可访问（{filter_reason}），可能已删除或仅作者可见"
                    )
                raise ValueError("分享页未返回作品详情")
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
    raise ValueError(str(last_err) if last_err else "抖音解析失败")


def _first_url(obj: dict[str, Any] | None) -> str | None:
    if not obj:
        return None
    urls = obj.get("url_list") or []
    return urls[0] if urls else None


def _to_no_watermark(url: str) -> str:
    if not url:
        return url
    return (
        url.replace("/playwm/", "/play/")
        .replace("playwm", "play")
        .replace("watermark=1", "watermark=0")
    )


def play_url_for(video_uri: str, ratio: str) -> str:
    """构造 aweme 播放接口（跟随跳转后即为 CDN mp4）。"""
    return (
        "https://aweme.snssdk.com/aweme/v1/play/"
        f"?video_id={video_uri}&ratio={ratio}&line=0"
    )


def parse_douyin(url: str) -> dict[str, Any]:
    """
    解析抖音公开作品，返回与 parse_video 同结构的 data。
    format_id 形如 dy:720p / dy:1080p，下载时再按 ratio 拉流。
    """
    cleaned = extract_url_from_text(url)
    aweme_id = resolve_aweme_id(cleaned)
    item = _fetch_share_item(aweme_id)

    if item.get("images"):
        raise ValueError("该链接是抖音图集，当前仅支持视频下载")

    video = item.get("video") or {}
    play_addr = video.get("play_addr") or {}
    video_uri = play_addr.get("uri") or play_addr.get("url_key")
    if not video_uri:
        # 退化：直接用 url_list 去水印
        raw = _first_url(play_addr)
        if not raw:
            raise ValueError("未找到可下载的视频地址")
        video_uri = None
        direct = _to_no_watermark(raw)
    else:
        direct = None

    author = item.get("author") or {}
    title = (item.get("desc") or "").strip() or f"抖音视频 {aweme_id}"
    cover = (
        _first_url(video.get("cover"))
        or _first_url(video.get("origin_cover"))
        or _first_url(video.get("dynamic_cover"))
        or _first_url(item.get("video", {}).get("cover"))
    )
    duration_ms = video.get("duration") or item.get("duration") or 0
    try:
        duration_sec = int(duration_ms) / 1000 if int(duration_ms) > 1000 else int(duration_ms)
    except (TypeError, ValueError):
        duration_sec = 0

    stats = item.get("statistics") or {}
    view_count = stats.get("play_count") or stats.get("digg_count")

    formats: list[dict[str, Any]] = []
    if video_uri:
        for ratio, height in _RATIO_CHOICES:
            formats.append(
                {
                    "format_id": f"dy:{ratio}",
                    "ext": "mp4",
                    "height": height,
                    "width": None,
                    "fps": None,
                    "filesize": None,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "has_video": True,
                    "has_audio": True,
                    "label": f"{ratio} · MP4 · 含音频",
                    "vip_required": height > FREE_MAX_HEIGHT,
                    "format_note": ratio,
                    "needs_merge": False,
                    "can_direct": True,
                    "douyin_uri": video_uri,
                    "douyin_ratio": ratio,
                }
            )
    elif direct:
        formats.append(
            {
                "format_id": "dy:direct",
                "ext": "mp4",
                "height": 720,
                "width": None,
                "fps": None,
                "filesize": None,
                "vcodec": "h264",
                "acodec": "aac",
                "has_video": True,
                "has_audio": True,
                "label": "默认 · MP4 · 含音频",
                "vip_required": False,
                "format_note": "direct",
                "needs_merge": False,
                "can_direct": True,
                "douyin_direct": direct,
                "douyin_ratio": "direct",
            }
        )

    webpage = f"https://www.douyin.com/video/{aweme_id}"
    return {
        "id": aweme_id,
        "title": title,
        "thumbnail": cover,
        "duration": duration_sec or None,
        "duration_string": _format_duration(duration_sec) if duration_sec else None,
        "uploader": author.get("nickname"),
        "description": title,
        "view_count": view_count,
        "webpage_url": webpage,
        "extractor": "Douyin",
        "formats": formats,
        "subtitles": [],
        "original_url": cleaned,
        "douyin_uri": video_uri,
    }


def _format_duration(seconds: float | int | None) -> str | None:
    if not seconds:
        return None
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _safe_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    return (cleaned[:80] or "douyin").rstrip(".")


def _pick_download_url(info: dict[str, Any], format_id: str) -> tuple[str, str]:
    """根据 format_id 选出下载 URL 与建议文件名后缀标签。"""
    fid = (format_id or "").strip()
    ratio = "720p"
    if fid.startswith("dy:"):
        ratio = fid.split(":", 1)[1] or "720p"

    if ratio == "direct":
        for fmt in info.get("formats") or []:
            if fmt.get("douyin_direct"):
                return fmt["douyin_direct"], "direct"
        raise ValueError("没有可用的抖音直链")

    uri = info.get("douyin_uri")
    if not uri:
        for fmt in info.get("formats") or []:
            if fmt.get("douyin_uri"):
                uri = fmt["douyin_uri"]
                break
    if not uri:
        raise ValueError("缺少抖音 video_id，无法下载")

    # 校验 ratio 合法性
    valid = {r for r, _ in _RATIO_CHOICES}
    if ratio not in valid:
        ratio = "720p"
    return play_url_for(uri, ratio), ratio


def download_douyin(
    url: str,
    format_id: str,
    outdir: Path,
    progress_hook: ProgressHook | None = None,
) -> Path:
    """服务端下载抖音视频到 outdir（httpx 流式，兼容 tasks 进度 hook）。"""
    outdir.mkdir(parents=True, exist_ok=True)
    info = parse_douyin(url)
    media_url, ratio = _pick_download_url(info, format_id)
    filename = f"{_safe_filename(info['title'])} [{info['id']}]_{ratio}.mp4"
    dest = outdir / filename

    with _client(timeout=120.0) as client:
        with client.stream("GET", media_url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            downloaded = 0
            started = time.time()
            with dest.open("wb") as f:
                for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_hook:
                        elapsed = max(time.time() - started, 1e-3)
                        progress_hook(
                            {
                                "status": "downloading",
                                "downloaded_bytes": downloaded,
                                "total_bytes": total or None,
                                "speed": downloaded / elapsed,
                                "eta": int((total - downloaded) / (downloaded / elapsed))
                                if total and downloaded
                                else None,
                            }
                        )
            if progress_hook:
                progress_hook({"status": "finished", "filename": str(dest)})

    if not dest.exists() or dest.stat().st_size <= 0:
        raise RuntimeError("抖音下载完成但文件为空")
    return dest


def resolve_douyin_direct(url: str, format_id: str) -> dict[str, Any]:
    """解析抖音单流直链（最终 CDN mp4，可能有时效）。"""
    info = parse_douyin(url)
    media_url, ratio = _pick_download_url(info, format_id)
    # 跟随一次跳转拿到签名 CDN（便于用户复制后短期可用）
    with _client(timeout=30.0) as client:
        resp = client.head(media_url)
        final = str(resp.url)
        # 部分 CDN 不支持 HEAD，退化 GET 读头
        if resp.status_code >= 400:
            with client.stream("GET", media_url) as r:
                final = str(r.url)
                r.close()

    return {
        "url": final,
        "ext": "mp4",
        "format_id": format_id or f"dy:{ratio}",
        "http_headers": {"User-Agent": MOBILE_UA, "Referer": "https://www.douyin.com/"},
        "note": "抖音直链有时效，失效请改用「立即下载」",
    }

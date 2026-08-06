"""
yt-dlp 薄封装：解析元数据、服务端下载、直链解析、字幕下载。

约定：不修改 yt-dlp 源码，只通过 YoutubeDL 官方 API / 选项使用能力。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import yt_dlp

from app.config import FREE_MAX_HEIGHT
from app.douyin import (
    download_douyin,
    is_douyin_url,
    parse_douyin,
    resolve_douyin_direct,
)


# yt-dlp progress_hooks 回调类型
ProgressHook = Callable[[dict[str, Any]], None]


class _QuietLogger:
    """吞掉 yt-dlp 控制台输出。

    Windows + uvicorn 下，stdout/stderr 句柄偶发异常时，yt-dlp 的 to_screen
    会抛出 OSError: [Errno 22] Invalid argument，导致「解析失败」。
    """

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass


def _base_ydl_opts(**extra: Any) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),
        # 勿开 listsubtitles：会 to_screen 打印字幕表，Windows 下易触发 Errno 22
        "listsubtitles": False,
    }
    opts.update(extra)
    return opts


def _safe_filename(title: str) -> str:
    """去掉 Windows 非法文件名字符。"""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title or "video")
    cleaned = cleaned.strip(" .")[:80] or "video"
    return cleaned


def _pick_thumbnail(info: dict[str, Any]) -> str | None:
    """优先用主 thumbnail，否则取 thumbnails 列表中分辨率较高的一项。"""
    thumb = info.get("thumbnail")
    if thumb:
        return thumb
    thumbs = info.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url")
    return None


def _format_entry(fmt: dict[str, Any]) -> dict[str, Any] | None:
    """把 yt-dlp 原始 format 字典转成前端友好的结构；无效项返回 None。"""
    format_id = fmt.get("format_id")
    if not format_id:
        return None

    height = fmt.get("height")
    width = fmt.get("width")
    vcodec = fmt.get("vcodec") or "none"
    acodec = fmt.get("acodec") or "none"
    ext = fmt.get("ext") or "unknown"
    filesize = fmt.get("filesize") or fmt.get("filesize_approx")
    fps = fmt.get("fps")
    tbr = fmt.get("tbr")

    has_video = vcodec != "none"
    has_audio = acodec != "none"

    # Skip storyboard / image-only
    if fmt.get("format_note") == "storyboard":
        return None
    if not has_video and not has_audio:
        return None

    label_parts: list[str] = []
    if has_video and height:
        label_parts.append(f"{height}p")
    elif has_video:
        label_parts.append("视频")
    if not has_video and has_audio:
        label_parts.append("仅音频")
    if ext:
        label_parts.append(ext.upper())
    if fps:
        label_parts.append(f"{int(fps)}fps")
    if tbr:
        label_parts.append(f"{int(tbr)}kbps")

    note = fmt.get("format_note") or fmt.get("resolution") or ""
    if note and note not in " ".join(label_parts):
        label_parts.append(str(note))

    vip_required = bool(has_video and height and height > FREE_MAX_HEIGHT)
    needs_merge = False  # single stream from extractor
    can_direct = True

    return {
        "format_id": str(format_id),
        "ext": ext,
        "height": height,
        "width": width,
        "fps": fps,
        "filesize": filesize,
        "vcodec": vcodec,
        "acodec": acodec,
        "has_video": has_video,
        "has_audio": has_audio,
        "label": " · ".join(label_parts),
        "vip_required": vip_required,
        "format_note": note,
        "needs_merge": needs_merge,
        "can_direct": can_direct,
    }


def _dedupe_formats(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    压缩 formats 列表，避免前端刷出几十条重复清晰度。
    同一高度优先 progressive；否则拼 video+bestaudio（需 ffmpeg）。
    """
    video_by_height: dict[int, dict[str, Any]] = {}
    audio_best: dict[str, Any] | None = None
    progressive: list[dict[str, Any]] = []

    for fmt in formats:
        height = fmt.get("height") or 0
        has_video = fmt["has_video"]
        has_audio = fmt["has_audio"]

        if has_video and has_audio:
            progressive.append(fmt)
            continue
        if has_video and height:
            prev = video_by_height.get(height)
            if not prev or (fmt.get("filesize") or 0) > (prev.get("filesize") or 0):
                video_by_height[height] = fmt
            continue
        if not has_video and has_audio:
            if audio_best is None or (fmt.get("filesize") or 0) > (
                audio_best.get("filesize") or 0
            ):
                audio_best = fmt

    merged: list[dict[str, Any]] = []

    # 同高度：有一体流用一体流，否则标记 needs_merge 让 yt-dlp + ffmpeg 合并
    prog_by_height = {
        f["height"]: f for f in progressive if f.get("height")
    }
    heights = sorted(
        set(video_by_height.keys()) | set(prog_by_height.keys()),
        reverse=True,
    )
    for h in heights:
        if h in prog_by_height:
            merged.append(prog_by_height[h])
        else:
            v = video_by_height[h]
            merged.append(
                {
                    **v,
                    "format_id": f"{v['format_id']}+bestaudio/best",
                    "label": f"{v['label']} · 自动合并音轨",
                    "has_audio": True,
                    "needs_merge": True,
                    "can_direct": False,
                }
            )

    if audio_best:
        merged.append(audio_best)

    # 通用直链等极端情况：extractor 几乎不给 formats 时用预设选择器
    if not merged:
        merged = [
            {
                "format_id": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                "ext": "mp4",
                "height": 720,
                "width": None,
                "fps": None,
                "filesize": None,
                "vcodec": "unknown",
                "acodec": "unknown",
                "has_video": True,
                "has_audio": True,
                "label": "720p · 最佳可用",
                "vip_required": False,
                "format_note": "preset",
                "needs_merge": True,
                "can_direct": False,
            },
            {
                "format_id": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                "ext": "mp4",
                "height": 1080,
                "width": None,
                "fps": None,
                "filesize": None,
                "vcodec": "unknown",
                "acodec": "unknown",
                "has_video": True,
                "has_audio": True,
                "label": "1080p · 最佳可用",
                "vip_required": True,
                "format_note": "preset",
                "needs_merge": True,
                "can_direct": False,
            },
            {
                "format_id": "bestaudio/best",
                "ext": "m4a",
                "height": None,
                "width": None,
                "fps": None,
                "filesize": None,
                "vcodec": "none",
                "acodec": "unknown",
                "has_video": False,
                "has_audio": True,
                "label": "仅音频 · 最佳",
                "vip_required": False,
                "format_note": "preset",
                "needs_merge": False,
                "can_direct": True,
            },
        ]

    for item in merged:
        if "needs_merge" not in item:
            fid = str(item.get("format_id") or "")
            item["needs_merge"] = "+" in fid
            item["can_direct"] = not item["needs_merge"]

    return merged


def _collect_subtitles(info: dict[str, Any]) -> list[dict[str, Any]]:
    """汇总人工字幕 + 自动字幕，供前端下拉选择。

    同时保留 B 站弹幕轨（lang=danmaku / comment.bilibili.com），
    作为字幕兜底源（前端可展示、AI 总结可用）。
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_group(group: dict[str, Any] | None, automatic: bool) -> None:
        if not group:
            return
        for lang, tracks in group.items():
            if not tracks:
                continue
            key = f"{'auto' if automatic else 'manual'}:{lang}"
            if key in seen:
                continue
            seen.add(key)
            preferred = None
            for t in tracks:
                ext = (t.get("ext") or "").lower()
                if ext in ("vtt", "srt", "ass", "ttml", "srv3", "json3"):
                    preferred = t
                    break
            preferred = preferred or tracks[0]
            lang_s = str(lang)
            name = preferred.get("name") or lang_s
            is_danmaku = lang_s.lower() == "danmaku" or "comment.bilibili.com" in str(
                preferred.get("url") or ""
            )
            if automatic and "自动" not in str(name) and "auto" not in str(name).lower():
                name = f"{name}（自动）"
            if is_danmaku:
                name = "弹幕（B 站兜底）"
            out.append(
                {
                    "lang": lang_s,
                    "name": name,
                    "ext": preferred.get("ext") or "vtt",
                    "automatic": automatic,
                    "is_danmaku": is_danmaku,
                    "url": preferred.get("url"),
                }
            )

    add_group(info.get("subtitles"), False)
    add_group(info.get("automatic_captions"), True)

    def _rank(s: dict[str, Any]) -> tuple:
        # 弹幕轨排在所有真实字幕之后：让前端默认选中真实字幕
        if s.get("is_danmaku"):
            return (1, 2, str(s.get("lang") or "danmaku"))
        lang = str(s.get("lang") or "").lower()
        auto = 1 if s.get("automatic") else 0
        if lang in {"zh-hans", "zh-cn", "zh"}:
            zh = 0
        elif lang.startswith("zh") or lang.startswith("ai-zh") or lang in {"yue", "zh-hant", "zh-tw"}:
            zh = 1
        else:
            zh = 2
        return (auto, zh, lang)

    out.sort(key=_rank)
    return out


def fetch_subtitle_url_content(track_url: str, *, page_url: str | None = None) -> str:
    """直接拉取字幕轨 URL（比再走一遍 yt-dlp 下载更稳、更快）。"""
    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }
    if page_url:
        headers["Referer"] = page_url
    with httpx.Client(timeout=45.0, follow_redirects=True) as client:
        resp = client.get(track_url, headers=headers)
        resp.raise_for_status()
        # 部分 CDN 返回 gzip 已由 httpx 解码
        text = resp.text
        if not text or not text.strip():
            raise RuntimeError("字幕内容为空")
        return text


def parse_video(url: str) -> dict[str, Any]:
    """解析视频信息（不下载文件），返回前端所需的 data 结构。"""
    # 抖音：yt-dlp 强依赖 Cookie；走分享页无 Cookie 方案
    if is_douyin_url(url):
        return parse_douyin(url)

    ydl_opts: dict[str, Any] = _base_ydl_opts(
        skip_download=True,
        noplaylist=True,  # 播放列表只取首条，避免一次解析过大
        writesubtitles=False,
        writeautomaticsub=False,
    )
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise ValueError("无法解析该链接，请检查 URL 是否有效")
        # sanitize_info：保证可 JSON 序列化
        info = ydl.sanitize_info(info)

    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            raise ValueError("播放列表为空")
        # MVP：仅处理第一条；flat 条目可能只有 url，需再解析一次
        first = entries[0]
        if isinstance(first, dict) and first.get("url") and not first.get("formats"):
            return parse_video(first["url"] if first.get("webpage_url") is None else first.get("webpage_url") or first["url"])
        info = first if isinstance(first, dict) else info

    raw_formats = info.get("formats") or []
    parsed = []
    for fmt in raw_formats:
        entry = _format_entry(fmt)
        if entry:
            parsed.append(entry)

    formats = _dedupe_formats(parsed)

    extractor = info.get("extractor_key") or info.get("extractor") or "unknown"
    duration = info.get("duration")
    webpage_url = info.get("webpage_url") or url
    subs = _collect_subtitles(info)
    try:
        from app.bilibili_subs import merge_bilibili_tracks_into_subtitles

        subs = merge_bilibili_tracks_into_subtitles(webpage_url, subs)
    except Exception:  # noqa: BLE001
        pass

    return {
        "id": info.get("id"),
        "title": info.get("title") or "未命名视频",
        "thumbnail": _pick_thumbnail(info),
        "duration": duration,
        "duration_string": info.get("duration_string")
        or (_format_duration(duration) if duration else None),
        "uploader": info.get("uploader") or info.get("channel"),
        "description": (info.get("description") or "")[:280] or None,
        "view_count": info.get("view_count"),
        "webpage_url": webpage_url,
        "extractor": extractor,
        "formats": formats,
        "subtitles": subs,
        "original_url": url,
    }


def _format_duration(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def download_video(
    url: str,
    format_id: str,
    outdir: Path,
    progress_hook: ProgressHook | None = None,
) -> Path:
    """下载到 outdir，返回最终文件路径（合并后扩展名可能变为 mp4）。"""
    if is_douyin_url(url) or str(format_id or "").startswith("dy:"):
        return download_douyin(url, format_id, outdir, progress_hook=progress_hook)

    outdir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(outdir / "%(title).80B [%(id)s].%(ext)s")

    hooks = [progress_hook] if progress_hook else []

    ydl_opts: dict[str, Any] = _base_ydl_opts(
        noplaylist=True,
        format=format_id,
        outtmpl=outtmpl,
        progress_hooks=hooks,
        restrictfilenames=False,
        windowsfilenames=True,
        merge_output_format="mp4",
    )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError("下载失败：未返回媒体信息")
        filename = ydl.prepare_filename(info)
        path = Path(filename)
        # 合并后 prepare_filename 的扩展名可能仍是原视频轨扩展名
        if not path.exists():
            for ext in ("mp4", "mkv", "webm", "m4a", "mp3", "opus"):
                candidate = path.with_suffix(f".{ext}")
                if candidate.exists():
                    path = candidate
                    break
        if not path.exists():
            files = sorted(outdir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            files = [f for f in files if f.is_file()]
            if not files:
                raise RuntimeError("下载完成但未找到输出文件")
            path = files[0]
        return path


def format_requires_vip(format_id: str, height: int | None = None) -> bool:
    """判断是否超过免费清晰度（供 API 层拦截）。"""
    if height is not None and height > FREE_MAX_HEIGHT:
        return True
    fid = format_id or ""
    # 抖音 dy:1080p
    m_dy = re.search(r"dy:(\d+)p", fid, re.I)
    if m_dy and int(m_dy.group(1)) > FREE_MAX_HEIGHT:
        return True
    # 预设选择器如 height<=1080 也要识别
    m = re.search(r"height<=(\d+)", fid)
    if m and int(m.group(1)) > FREE_MAX_HEIGHT:
        return True
    if "1080" in fid or "1440" in fid or "2160" in fid:
        return True
    return False


def resolve_direct_url(url: str, format_id: str) -> dict[str, Any]:
    """
    解析单流直链（不落盘）。
    format_id 含 '+' 或 requested_formats 多路时无法给单 URL，应改走服务端下载。
    """
    if is_douyin_url(url) or str(format_id or "").startswith("dy:"):
        return resolve_douyin_direct(url, format_id)

    fid = (format_id or "").strip()
    if not fid:
        raise ValueError("缺少 format_id")
    if "+" in fid:
        raise ValueError(
            "该清晰度需要合并音视频，无法提供单一直链，请使用「下载到本地」"
        )

    ydl_opts: dict[str, Any] = _base_ydl_opts(
        skip_download=True,
        noplaylist=True,
        format=fid,
    )
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info is None:
            raise ValueError("无法解析直链")
        info = ydl.sanitize_info(info)

    if info.get("requested_formats"):
        raise ValueError(
            "该清晰度需要合并多路流，无法提供单一直链，请使用「下载到本地」"
        )

    direct = info.get("url")
    if not direct:
        raise ValueError("平台未返回可访问直链（可能需登录或有时效限制）")

    return {
        "url": direct,
        "ext": info.get("ext"),
        "format_id": info.get("format_id") or fid,
        "http_headers": info.get("http_headers") or {},
        "note": "直链可能有时效与防盗链，部分平台浏览器无法直接打开；失败请改用服务端下载",
    }


def download_subtitle(
    url: str,
    lang: str,
    outdir: Path,
    *,
    automatic: bool = False,
) -> Path:
    """下载单条字幕到 outdir；automatic=True 时写自动字幕轨。"""
    outdir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(outdir / "%(title).80B [%(id)s]")

    ydl_opts: dict[str, Any] = _base_ydl_opts(
        noplaylist=True,
        skip_download=True,  # 只下字幕，不下视频
        writesubtitles=not automatic,
        writeautomaticsub=automatic,
        subtitleslangs=[lang],
        subtitlesformat="vtt/srt/best",
        outtmpl=outtmpl,
        windowsfilenames=True,
    )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError("字幕下载失败：未返回信息")

    # 输出名类似 title [id].lang.vtt，按扩展名/语言猜测落盘文件
    candidates = sorted(
        [p for p in outdir.iterdir() if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        name = path.name.lower()
        if path.suffix.lower() in {".vtt", ".srt", ".ass", ".ttml", ".srv3", ".json3"}:
            return path
        if lang.lower() in name:
            return path
    if candidates:
        return candidates[0]
    raise RuntimeError("未找到字幕文件（该语言可能不可用）")


def download_audio(
    url: str,
    outdir: Path,
    progress_hook: ProgressHook | None = None,
) -> tuple[Path, dict[str, Any]]:
    """仅下载并提取音频（不下载视频），返回 (音频文件路径, yt-dlp info)。"""
    outdir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(outdir / "%(title).80B [%(id)s].%(ext)s")

    hooks = [progress_hook] if progress_hook else []

    ydl_opts: dict[str, Any] = _base_ydl_opts(
        noplaylist=True,
        format="bestaudio/best",
        outtmpl=outtmpl,
        progress_hooks=hooks,
        restrictfilenames=False,
        windowsfilenames=True,
        postprocessors=[
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
    )

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError("音频下载失败：未返回媒体信息")

    # yt-dlp 合并后输出扩展名可能变化，按最近修改时间找文件
    candidates = sorted(
        [p for p in outdir.iterdir() if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if path.suffix.lower() in {".mp3", ".m4a", ".opus", ".aac", ".wav", ".webm", ".ogg", ".flac"}:
            return path, info
    if candidates:
        return candidates[0], info
    raise RuntimeError("音频下载完成但未找到输出文件")

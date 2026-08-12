"""
B 站解析/下载旁路（官方 API）：作为 yt-dlp 失败时的兜底。

主路径已改为 yt-dlp（wbi 签名，通常无需 SESSDATA）。
可选 SPEEDYDL_BILI_SESSDATA 仅提升官方 API 兜底时的成功率/清晰度。
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import httpx

from app.bilibili_subs import (
    extract_aid,
    extract_bvid,
    extract_page_index,
    fetch_view,
    is_bilibili_url,
    merge_bilibili_tracks_into_subtitles,
)
from app.config import BILI_SESSDATA, FREE_MAX_HEIGHT

logger = logging.getLogger(__name__)

ProgressHook = Callable[[dict[str, Any]], None]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_QN_HEIGHT = {
    6: 240,
    16: 360,
    32: 480,
    64: 720,
    74: 720,
    80: 1080,
    112: 1080,
    116: 1080,
    120: 2160,
    125: 1080,
    126: 2160,
    127: 2160,
}


def qn_to_height(qn: int) -> int | None:
    return _QN_HEIGHT.get(int(qn))


def _headers(*, page_url: str | None = None) -> dict[str, str]:
    h = {
        "User-Agent": _UA,
        "Referer": page_url or "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
        "Accept": "*/*",
    }
    if BILI_SESSDATA:
        h["Cookie"] = f"SESSDATA={BILI_SESSDATA}"
    return h


def _format_duration(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _safe_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title or "bilibili")
    cleaned = cleaned.strip(" .")[:80] or "bilibili"
    return cleaned


def _fetch_playurl(
    *,
    bvid: str | None,
    aid: int | str | None,
    cid: int | str,
    qn: int = 64,
    page_url: str | None = None,
    fnval: int = 16,
    try_look: int = 1,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "cid": str(cid),
        "qn": int(qn),
        "fnval": int(fnval),
        "fnver": 0,
        "fourk": 1,
        "platform": "pc",
        "high_quality": 1,
        "try_look": int(try_look),
    }
    if bvid:
        params["bvid"] = bvid
    if aid is not None:
        params["avid"] = str(aid)

    with httpx.Client(timeout=25.0, follow_redirects=True) as client:
        resp = client.get(
            "https://api.bilibili.com/x/player/playurl",
            params=params,
            headers=_headers(page_url=page_url),
        )
        resp.raise_for_status()
        payload = resp.json()

    if payload.get("code") != 0:
        raise ValueError(payload.get("message") or "B 站 playurl 失败")
    data = payload.get("data") or {}
    if not data:
        raise ValueError("B 站未返回播放地址")
    return data


def _dash_url(item: dict[str, Any]) -> str | None:
    return item.get("baseUrl") or item.get("base_url") or item.get("url")


def _pick_dash_video(play: dict[str, Any], qn: int) -> dict[str, Any] | None:
    videos = ((play.get("dash") or {}).get("video")) or []
    if not videos:
        return None
    height = qn_to_height(qn) or 0
    # 优先匹配 qn id，再按目标高度
    by_id = [v for v in videos if int(v.get("id") or 0) == int(qn)]
    pool = by_id or [v for v in videos if int(v.get("height") or 0) == height] or videos
    return max(pool, key=lambda v: int(v.get("bandwidth") or 0))


def _pick_dash_audio(play: dict[str, Any]) -> dict[str, Any] | None:
    audios = ((play.get("dash") or {}).get("audio")) or []
    if not audios:
        return None
    return max(audios, key=lambda a: int(a.get("bandwidth") or 0))


def _build_formats(
    play: dict[str, Any],
    *,
    bvid: str | None,
    aid: Any,
    cid: Any,
) -> list[dict[str, Any]]:
    """根据 accept_quality 生成前端清晰度（含 1080p+，按 VIP 门禁标记）。"""
    qualities = play.get("accept_quality") or []
    descriptions = play.get("accept_description") or []
    dash_videos = ((play.get("dash") or {}).get("video")) or []
    dash_heights = {int(v.get("height") or 0) for v in dash_videos if v.get("height")}

    formats: list[dict[str, Any]] = []
    seen: set[int] = set()

    for i, qn in enumerate(qualities):
        try:
            qn_i = int(qn)
        except (TypeError, ValueError):
            continue
        if qn_i in seen:
            continue
        seen.add(qn_i)
        height = qn_to_height(qn_i)
        label = ""
        if i < len(descriptions) and descriptions[i]:
            label = str(descriptions[i])
        elif height:
            label = f"{height}p"
        else:
            label = f"qn{qn_i}"

        needs_merge = bool(height and height > FREE_MAX_HEIGHT) or qn_i >= 80
        # 列表里若 dash 根本没有该高度，仍展示（开通会员/配置 SESSDATA 后再下）
        available_now = (not height) or (height in dash_heights) or (height <= FREE_MAX_HEIGHT)

        formats.append(
            {
                "format_id": f"bili:qn:{qn_i}",
                "ext": "mp4",
                "height": height,
                "width": None,
                "fps": None,
                "filesize": None,
                "vcodec": "h264",
                "acodec": "aac",
                "has_video": True,
                "has_audio": True,
                "label": (
                    f"{label} · MP4"
                    + (" · 需合并" if needs_merge else " · 含音频")
                    + ("" if available_now else " · 需登录Cookie")
                ),
                "vip_required": bool(height and height > FREE_MAX_HEIGHT),
                "format_note": f"bilibili qn={qn_i}",
                "needs_merge": needs_merge,
                "can_direct": not needs_merge,
                "bilibili_qn": qn_i,
                "bilibili_bvid": bvid,
                "bilibili_aid": aid,
                "bilibili_cid": cid,
            }
        )

    formats.sort(key=lambda f: (f.get("height") or 0), reverse=True)
    return formats


def parse_bilibili(url: str) -> dict[str, Any]:
    """解析 B 站公开稿件元数据与清晰度（含 1080p 列表）。"""
    cleaned = (url or "").strip()
    if not is_bilibili_url(cleaned):
        raise ValueError("不是 B 站链接")

    bvid = extract_bvid(cleaned)
    aid = extract_aid(cleaned)
    page_index = extract_page_index(cleaned)
    page_url = cleaned if cleaned.startswith("http") else (
        f"https://www.bilibili.com/video/{bvid}" if bvid else "https://www.bilibili.com/"
    )

    view = fetch_view(bvid=bvid, aid=aid, page_index=page_index, page_url=page_url)
    if not view.get("cid"):
        raise ValueError(
            "无法通过 B 站接口解析该视频（可能已删除、仅自见或需登录）。"
            "可在 .env 配置 SPEEDYDL_BILI_SESSDATA 后重试。"
        )

    bvid = view.get("bvid") or bvid
    aid = view.get("aid") or aid
    cid = view["cid"]
    title = view.get("title") or "未命名视频"
    duration = view.get("duration")
    desc = (view.get("desc") or "")[:280] or None
    pic = view.get("pic")
    owner = view.get("owner") or {}
    uploader = owner.get("name")
    stat = view.get("stat") or {}
    view_count = stat.get("view")

    # DASH + try_look：未登录也能列出 1080p+（实际下载仍受门禁/风控约束）
    play = _fetch_playurl(
        bvid=bvid, aid=aid, cid=cid, qn=80, page_url=page_url, fnval=16, try_look=1
    )
    formats = _build_formats(play, bvid=bvid, aid=aid, cid=cid)
    if not formats:
        raise ValueError("该视频暂无可用清晰度（可能受地区或登录限制）")

    webpage = page_url
    if bvid and "bilibili.com/video" not in webpage:
        webpage = f"https://www.bilibili.com/video/{bvid}"

    subs: list[dict[str, Any]] = []
    try:
        subs = merge_bilibili_tracks_into_subtitles(webpage, [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("合并 B 站字幕轨失败: %s", exc)

    return {
        "id": str(bvid or aid or cid),
        "title": title,
        "thumbnail": pic,
        "duration": duration,
        "duration_string": _format_duration(duration),
        "uploader": uploader,
        "description": desc,
        "view_count": view_count,
        "webpage_url": webpage,
        "extractor": "BiliBili",
        "formats": formats,
        "subtitles": subs,
        "original_url": cleaned,
        "bilibili_bvid": bvid,
        "bilibili_aid": aid,
        "bilibili_cid": cid,
    }


def _parse_qn(format_id: str, info: dict[str, Any]) -> int:
    fid = (format_id or "").strip()
    m = re.match(r"bili:qn:(\d+)$", fid)
    if m:
        return int(m.group(1))
    for fmt in info.get("formats") or []:
        if fmt.get("format_id") == fid and fmt.get("bilibili_qn"):
            return int(fmt["bilibili_qn"])
    return 64


def _download_http_file(
    url: str,
    dest: Path,
    headers: dict[str, str],
    progress_hook: ProgressHook | None = None,
    *,
    progress_offset: int = 0,
    progress_total: int | None = None,
) -> int:
    downloaded = 0
    with httpx.Client(timeout=None, follow_redirects=True, headers=headers) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            part_total = int(resp.headers.get("content-length") or 0)
            with dest.open("wb") as f:
                for chunk in resp.iter_bytes(1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_hook:
                        progress_hook(
                            {
                                "status": "downloading",
                                "downloaded_bytes": progress_offset + downloaded,
                                "total_bytes": progress_total or (progress_offset + part_total) or None,
                                "filename": str(dest),
                            }
                        )
    return downloaded


def _ffmpeg_merge(video: Path, audio: Path, dest: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("下载 1080p+ 需要本机 ffmpeg（未找到）")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not dest.exists():
        err = (proc.stderr or proc.stdout or "").strip()[-400:]
        raise RuntimeError(f"ffmpeg 合并失败：{err or proc.returncode}")


def download_bilibili(
    url: str,
    format_id: str,
    outdir: Path,
    progress_hook: ProgressHook | None = None,
) -> Path:
    """下载 B 站视频：≤720p 单流；更高清晰度 DASH+ffmpeg。"""
    outdir.mkdir(parents=True, exist_ok=True)
    info = parse_bilibili(url)
    qn = _parse_qn(format_id, info)
    height = qn_to_height(qn) or 0
    page_url = info.get("webpage_url") or url
    headers = _headers(page_url=page_url)
    title = _safe_filename(str(info.get("title") or "bilibili"))
    vid = info.get("id") or "video"
    dest = outdir / f"{title} [{vid}].mp4"

    # 免费档：合成 MP4（简单、可直链）
    if height <= FREE_MAX_HEIGHT:
        play = _fetch_playurl(
            bvid=info.get("bilibili_bvid"),
            aid=info.get("bilibili_aid"),
            cid=info.get("bilibili_cid"),
            qn=qn,
            page_url=page_url,
            fnval=0,
            try_look=1,
        )
        durl = (play.get("durl") or [None])[0]
        if not isinstance(durl, dict):
            raise ValueError("B 站未返回下载地址")
        media = durl.get("url") or (durl.get("backup_url") or [None])[0]
        if not media:
            raise ValueError("B 站播放地址为空")
        total = int(durl.get("size") or 0) or None
        size = _download_http_file(
            media, dest, headers, progress_hook, progress_total=total
        )
        if progress_hook:
            progress_hook(
                {
                    "status": "finished",
                    "downloaded_bytes": size,
                    "total_bytes": total or size,
                    "filename": str(dest),
                }
            )
        return dest

    # 高清：DASH 分离轨 + ffmpeg
    play = _fetch_playurl(
        bvid=info.get("bilibili_bvid"),
        aid=info.get("bilibili_aid"),
        cid=info.get("bilibili_cid"),
        qn=qn,
        page_url=page_url,
        fnval=16,
        try_look=1,
    )
    video_item = _pick_dash_video(play, qn)
    audio_item = _pick_dash_audio(play)
    if not video_item or not audio_item:
        raise ValueError(
            "无法获取 1080p+ 音视频流。可开通演示会员后重试，或在 .env 配置 SPEEDYDL_BILI_SESSDATA。"
        )
    v_url = _dash_url(video_item)
    a_url = _dash_url(audio_item)
    if not v_url or not a_url:
        raise ValueError("DASH 流地址为空")

    with tempfile.TemporaryDirectory(prefix="bili_") as tmp:
        tmp_dir = Path(tmp)
        v_path = tmp_dir / "video.m4s"
        a_path = tmp_dir / "audio.m4s"
        v_size = _download_http_file(v_url, v_path, headers, progress_hook)
        a_size = _download_http_file(
            a_url,
            a_path,
            headers,
            progress_hook,
            progress_offset=v_size,
        )
        if progress_hook:
            progress_hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": v_size + a_size,
                    "total_bytes": v_size + a_size,
                    "filename": str(dest),
                    "_speed_str": "合并中…",
                }
            )
        _ffmpeg_merge(v_path, a_path, dest)

    if progress_hook:
        progress_hook(
            {
                "status": "finished",
                "downloaded_bytes": dest.stat().st_size,
                "total_bytes": dest.stat().st_size,
                "filename": str(dest),
            }
        )
    return dest


def resolve_bilibili_direct(url: str, format_id: str) -> dict[str, Any]:
    """仅合成单流可提供直链；DASH 高清请用服务端下载。"""
    info = parse_bilibili(url)
    qn = _parse_qn(format_id, info)
    height = qn_to_height(qn) or 0
    if height > FREE_MAX_HEIGHT:
        raise ValueError("该清晰度需合并音视频，无法提供单一直链，请使用「下载到本地」")

    page_url = info.get("webpage_url") or url
    play = _fetch_playurl(
        bvid=info.get("bilibili_bvid"),
        aid=info.get("bilibili_aid"),
        cid=info.get("bilibili_cid"),
        qn=qn,
        page_url=page_url,
        fnval=0,
        try_look=1,
    )
    durl = (play.get("durl") or [None])[0]
    if not isinstance(durl, dict):
        raise ValueError("B 站未返回下载地址")
    media = durl.get("url") or (durl.get("backup_url") or [None])[0]
    if not media:
        raise ValueError("B 站播放地址为空")
    headers = _headers(page_url=page_url)
    return {
        "url": media,
        "ext": "mp4",
        "format_id": format_id,
        "http_headers": headers,
        "note": "B 站直链有时效与 Referer 校验；1080p+ 请用服务端下载",
        "title": info.get("title"),
    }


__all__ = [
    "is_bilibili_url",
    "parse_bilibili",
    "download_bilibili",
    "resolve_bilibili_direct",
    "qn_to_height",
]

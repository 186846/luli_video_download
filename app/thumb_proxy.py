"""
封面图代理。

问题：浏览器从 localhost 加载 B 站等 CDN 时会带本地 Referer，常被 403。
做法：后端用合法 Referer 拉取后原样返回图片；并拦截内网地址防 SSRF。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from fastapi.responses import Response

MAX_THUMB_BYTES = 5 * 1024 * 1024
ALLOWED_SCHEMES = {"http", "https"}


def _is_public_host(hostname: str) -> bool:
    """DNS 解析后拒绝私网 / 回环 / 链路本地等地址。"""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail="封面域名无法解析") from exc

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    return True


def validate_thumb_url(url: str) -> str:
    """校验并规范化封面 URL（http 升 https）。"""
    url = (url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="缺少封面地址")

    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(status_code=400, detail="封面仅支持 http(s)")
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="封面地址无效")
    if not _is_public_host(parsed.hostname):
        raise HTTPException(status_code=400, detail="不允许访问内网封面地址")

    if parsed.scheme == "http":
        url = "https://" + url[len("http://") :]
    return url


def fetch_thumbnail(url: str, page_url: str | None = None) -> Response:
    """拉取封面并返回 FastAPI Response。"""
    target = validate_thumb_url(url)
    # 默认 B 站 Referer；若传入视频页则用其 host，提高各站兼容性
    referer = "https://www.bilibili.com/"
    if page_url:
        try:
            host = urlparse(page_url).hostname or ""
            if host:
                referer = f"https://{host}/"
        except Exception:  # noqa: BLE001
            pass

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(target, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"封面拉取失败：{exc}") from exc

    if resp.status_code >= 400:
        # 部分 CDN 反而要求空 Referer，失败时再试一次
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                headers_no_ref = {**headers}
                headers_no_ref.pop("Referer", None)
                resp = client.get(target, headers=headers_no_ref)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"封面拉取失败：{exc}") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"封面源站返回 {resp.status_code}")

    content = resp.content
    if len(content) > MAX_THUMB_BYTES:
        raise HTTPException(status_code=502, detail="封面过大")

    content_type = resp.headers.get("content-type", "image/jpeg")
    if not content_type.startswith("image/") and "octet-stream" not in content_type:
        # 魔数兜底：jpeg/png/webp/gif/svg
        if not content.startswith((b"\xff\xd8", b"\x89PNG", b"RIFF", b"GIF8", b"<svg")):
            raise HTTPException(status_code=502, detail="封面不是图片")

    return Response(
        content=content,
        media_type=content_type.split(";")[0].strip() or "image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )

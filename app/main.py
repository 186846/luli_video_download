"""
FastAPI 入口：对外暴露 REST API，前端由 Vue(Vite) 独立运行。

阶段 3 主路径：parse → download → tasks → files
扩展能力：direct 直链、subtitles 字幕、summarize AI 总结、thumbnail 封面代理
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.config import (
    BRAND_EN,
    BRAND_NAME,
    DOWNLOAD_DIR,
    FREE_MAX_HEIGHT,
    AI_REQUIRE_VIP,
)
from app.downloader import (
    download_subtitle,
    format_requires_vip,
    parse_video,
    resolve_direct_url,
)
from app.embed import resolve_player_embed
from app.summarizer import (
    SummaryStatus,
    VideoSummarizer,
    create_summary_task,
    get_summary_task,
    iter_ask_events,
)
from app.tasks import create_task, get_task, task_to_dict
from app.thumb_proxy import fetch_thumbnail

_summarizer = VideoSummarizer()

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=f"{BRAND_NAME} / {BRAND_EN}",
    description="学习向万能视频下载演示（基于 yt-dlp）。请尊重版权。",
    version="0.4.0",
)

# 开发期允许 Vite 与局域网前端跨域；生产建议同源反代 /api
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParseRequest(BaseModel):
    url: str = Field(..., min_length=4, description="视频页面链接")


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=4)
    format_id: str = Field(..., min_length=1)
    height: int | None = None
    vip_token: str | None = Field(
        default=None,
        description="演示用 VIP 标记，值为 demo-vip 时解锁高清",
    )


class DirectRequest(BaseModel):
    url: str = Field(..., min_length=4)
    format_id: str = Field(..., min_length=1)
    height: int | None = None
    vip_token: str | None = None


class SubtitleDownloadRequest(BaseModel):
    url: str = Field(..., min_length=4)
    lang: str = Field(..., min_length=1)
    automatic: bool = False  # True = 机翻/自动字幕轨


class SummarizeRequest(BaseModel):
    url: str = Field(..., min_length=8)
    lang: str | None = None
    automatic: bool | None = None
    vip_token: str | None = None
    title: str | None = None
    transcript: list[dict] | None = Field(
        default=None,
        description="用户提供的字幕条目（可选），无平台 CC 时优先于弹幕",
    )
    subtitle_text: str | None = Field(
        default=None,
        description="用户粘贴的 SRT/VTT/纯文本（可选）",
    )


class AskRequest(BaseModel):
    url: str = Field(..., min_length=8)
    question: str = Field(..., min_length=1, max_length=500)
    lang: str | None = None
    automatic: bool | None = None
    vip_token: str | None = None
    title: str | None = None
    transcript: list[dict] | None = Field(
        default=None,
        description="前端已有字幕条目（可选），传入后避免重复解析视频",
    )


def _require_ai_vip(vip_token: str | None) -> None:
    """演示项目：VIP 校验已关闭，任何请求均可使用 AI 总结。"""
    return None


@app.get("/api/health")
def health() -> dict:
    """健康检查，供前端或探活使用。"""
    return {
        "ok": True,
        "brand": BRAND_NAME,
        "free_max_height": FREE_MAX_HEIGHT,
        "features": [
            "parse",
            "download",
            "direct",
            "subtitles",
            "bilibili_subs",
            "summarize",
            "ask",
            "chat",
            "progress",
            "sse",
        ],
        "notice": "仅供个人学习，请尊重版权，勿用于商业传播",
    }


@app.post("/api/parse")
def api_parse(body: ParseRequest) -> dict:
    """解析视频元数据、清晰度列表与字幕列表（不落盘视频）。"""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入以 http(s):// 开头的有效链接")
    try:
        data = parse_video(url)
    except Exception as exc:  # noqa: BLE001 — 透出 yt-dlp/网络错误给前端
        raise HTTPException(
            status_code=400,
            detail=f"解析失败：{exc}。请确认链接公开可访问，并尊重平台版权。",
        ) from exc
    return {"ok": True, "data": data}


@app.post("/api/download")
def api_download(body: DownloadRequest) -> dict:
    """创建服务端下载任务（模式①：落盘后通过 /api/files 取回）。"""
    url = body.url.strip()
    format_id = body.format_id.strip()
    is_vip = body.vip_token == "demo-vip"

    # 与前端 VIP 门禁双校验，防止直接调 API 绕过
    if format_requires_vip(format_id, body.height) and not is_vip:
        raise HTTPException(
            status_code=403,
            detail=f"超过免费清晰度上限（{FREE_MAX_HEIGHT}p），请开通演示会员后重试",
        )

    try:
        task = create_task(url, format_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"无法开始下载：{exc}") from exc

    return {"ok": True, "task": task_to_dict(task)}


@app.post("/api/direct")
def api_direct(body: DirectRequest) -> dict:
    """解析单流直链（模式②：不落盘）。需合并音视频的 format 会失败。"""
    url = body.url.strip()
    format_id = body.format_id.strip()
    is_vip = body.vip_token == "demo-vip"

    if format_requires_vip(format_id, body.height) and not is_vip:
        raise HTTPException(
            status_code=403,
            detail=f"超过免费清晰度上限（{FREE_MAX_HEIGHT}p），请开通演示会员后重试",
        )

    try:
        data = resolve_direct_url(url, format_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": data}


@app.post("/api/subtitles/download")
def api_subtitle_download(body: SubtitleDownloadRequest) -> FileResponse:
    """按语言下载字幕文件，响应为附件流。"""
    url = body.url.strip()
    lang = body.lang.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入有效链接")

    outdir = DOWNLOAD_DIR / f"sub-{uuid.uuid4().hex}"
    try:
        path = download_subtitle(url, lang, outdir, automatic=body.automatic)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"字幕下载失败：{exc}") from exc

    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/octet-stream",
    )


@app.post("/api/summarize")
def api_summarize(body: SummarizeRequest) -> dict:
    """创建 AI 视频总结后台任务，立即返回 task_id 供前端轮询。"""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入有效链接")

    _require_ai_vip(body.vip_token)

    try:
        task = create_summary_task(
            url,
            lang=body.lang,
            automatic=body.automatic,
            title=body.title,
            transcript=body.transcript,
            subtitle_text=body.subtitle_text,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"创建总结任务失败：{exc}") from exc

    return {"ok": True, "task_id": task.id}


@app.get("/api/summarize/status/{task_id}")
def api_summarize_status(task_id: str) -> dict:
    """查询总结任务状态与进度（前端轮询）。"""
    task = get_summary_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {
        "ok": True,
        "task": {
            "id": task.id,
            "status": task.status.value,
            "progress": task.progress,
            "message": task.message,
            "error": task.error,
            "data": task.result,
        },
    }


def _sse_pack(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _summary_task_payload(task) -> dict:
    return {
        "id": task.id,
        "status": task.status.value,
        "progress": task.progress,
        "message": task.message,
        "error": task.error,
        "data": task.result,
    }


@app.get("/api/summarize/stream/{task_id}")
async def api_summarize_stream(task_id: str):
    """SSE：推送总结任务进度，直至 done / error。"""
    task = get_summary_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    async def event_gen():
        last_key = None
        while True:
            current = get_summary_task(task_id)
            if not current:
                yield _sse_pack("error", {"error": "任务不存在或已过期"})
                return
            payload = _summary_task_payload(current)
            key = (payload["status"], round(payload["progress"], 1), payload["message"])
            if key != last_key:
                last_key = key
                yield _sse_pack("progress", {"ok": True, "task": payload})
            if current.status == SummaryStatus.DONE:
                yield _sse_pack("done", {"ok": True, "task": payload})
                return
            if current.status == SummaryStatus.ERROR:
                yield _sse_pack(
                    "error",
                    {"ok": False, "task": payload, "error": current.error},
                )
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/summarize/ask")
def api_summarize_ask(body: AskRequest) -> dict:
    """针对视频内容的 AI 问答（字幕优先；无 Key 时 Mock）。兼容旧客户端。"""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入有效链接")

    _require_ai_vip(body.vip_token)

    try:
        data = _summarizer.ask(
            url,
            body.question,
            lang=body.lang,
            automatic=body.automatic,
            title=body.title,
            transcript=body.transcript,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"问答失败：{exc}") from exc

    return {"ok": True, "data": data}


@app.post("/api/chat")
async def api_chat(body: AskRequest):
    """AI 问答 SSE：status / token / done / error。"""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入有效链接")

    _require_ai_vip(body.vip_token)

    def event_gen():
        for item in iter_ask_events(
            url,
            body.question,
            lang=body.lang,
            automatic=body.automatic,
            title=body.title,
            transcript=body.transcript,
        ):
            yield _sse_pack(item["event"], item["data"])

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/tasks/{task_id}")
def api_task(task_id: str) -> dict:
    """查询下载任务状态与进度（前端轮询）。"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return {"ok": True, "task": task_to_dict(task)}


@app.get("/api/embed")
def api_embed(
    url: str = Query(..., min_length=8, description="视频页 URL"),
    t: int = Query(default=0, ge=0, description="起始秒数"),
) -> dict:
    """解析页内嵌入播放地址（B 站会补全 cid）。"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请输入有效链接")
    data = resolve_player_embed(url, start_seconds=t)
    if not data:
        raise HTTPException(status_code=400, detail="暂不支持该链接的页内播放，请打开原视频")
    return {"ok": True, "data": data}


@app.get("/api/thumbnail")
def api_thumbnail(
    url: str = Query(..., min_length=8, description="原始封面 URL"),
    page: str | None = Query(default=None, description="视频页 URL，用于 Referer"),
) -> Response:
    """代理封面图：浏览器带本地 Referer 时部分 CDN（如 B 站）会 403。"""
    return fetch_thumbnail(url, page)


@app.get("/api/files/{task_id}")
def api_file(task_id: str) -> FileResponse:
    """任务完成后返回视频文件流，供浏览器保存。"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if task.status.value != "done" or not task.filepath:
        raise HTTPException(status_code=409, detail="文件尚未就绪")
    path = Path(task.filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已被清理，请重新下载")
    return FileResponse(
        path=path,
        filename=task.filename or path.name,
        media_type="application/octet-stream",
    )


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    """根路径提示：API 服务本身不托管 Vue 页面。"""
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{BRAND_NAME} API</title></head><body style='font-family:sans-serif;padding:2rem'>"
        f"<h1>{BRAND_NAME} / {BRAND_EN} API</h1>"
        "<p>前端请启动 Vue：<code>cd web && npm run dev</code> → "
        "<a href='http://127.0.0.1:5173'>http://127.0.0.1:5173</a></p>"
        "<p>接口文档：<a href='/docs'>/docs</a></p>"
        "</body></html>"
    )

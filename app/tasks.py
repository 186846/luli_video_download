"""
内存下载任务表 + 临时文件清理。

无数据库：进程内 dict 保存任务；daemon 线程定期按 TTL 删除 downloads/tmp。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from app.config import (
    DOWNLOAD_DIR,
    FILE_TTL_SECONDS,
    MAX_CONCURRENT_DOWNLOADS,
)
from app.downloader import download_video


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class DownloadTask:
    """单个下载任务的运行时状态（供 /api/tasks 轮询）。"""

    id: str
    url: str
    format_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    speed: str | None = None
    eta: str | None = None
    error: str | None = None
    filename: str | None = None
    filepath: Path | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


_lock = threading.Lock()
_tasks: dict[str, DownloadTask] = {}
_active_count = 0
_cleanup_started = False


def _ensure_cleanup_loop() -> None:
    """懒启动清理线程，避免模块 import 时就起后台任务。"""
    global _cleanup_started
    with _lock:
        if _cleanup_started:
            return
        _cleanup_started = True

    def loop() -> None:
        while True:
            time.sleep(60)
            cleanup_expired()

    t = threading.Thread(target=loop, daemon=True, name="tmp-cleanup")
    t.start()


def create_task(url: str, format_id: str) -> DownloadTask:
    """创建任务并在后台线程执行下载；超并发则抛 RuntimeError。"""
    _ensure_cleanup_loop()
    with _lock:
        running = sum(
            1
            for t in _tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        )
        if running >= MAX_CONCURRENT_DOWNLOADS:
            raise RuntimeError(
                f"当前下载任务已满（最多 {MAX_CONCURRENT_DOWNLOADS} 个），请稍后再试"
            )
        task = DownloadTask(id=uuid.uuid4().hex, url=url, format_id=format_id)
        _tasks[task.id] = task

    worker = threading.Thread(
        target=_run_task, args=(task.id,), daemon=True, name=f"dl-{task.id[:8]}"
    )
    worker.start()
    return task


def get_task(task_id: str) -> DownloadTask | None:
    with _lock:
        return _tasks.get(task_id)


def task_to_dict(task: DownloadTask) -> dict[str, Any]:
    """序列化为 API JSON。ready=True 时前端可请求 /api/files。"""
    return {
        "id": task.id,
        "status": task.status.value,
        "progress": round(task.progress, 2),
        "speed": task.speed,
        "eta": task.eta,
        "error": task.error,
        "filename": task.filename,
        "ready": task.status == TaskStatus.DONE and task.filepath is not None,
    }


def _run_task(task_id: str) -> None:
    """后台执行：挂 progress_hook 更新进度，结束写 filepath 或 error。"""
    global _active_count
    task = get_task(task_id)
    if not task:
        return

    with _lock:
        task.status = TaskStatus.RUNNING
        _active_count += 1

    outdir = DOWNLOAD_DIR / task_id
    try:

        def hook(d: dict[str, Any]) -> None:
            # yt-dlp progress_hooks 状态：downloading / finished / error
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes") or 0
                pct = (downloaded / total * 100) if total else 0.0
                speed = d.get("speed")
                eta = d.get("eta")
                with _lock:
                    t = _tasks.get(task_id)
                    if not t:
                        return
                    # 合并阶段前先顶到 99，真正完成再 100
                    t.progress = min(pct, 99.0)
                    if speed:
                        t.speed = _human_speed(speed)
                    if eta is not None:
                        t.eta = f"{int(eta)}s"
            elif status == "finished":
                with _lock:
                    t = _tasks.get(task_id)
                    if t:
                        t.progress = 99.0

        path = download_video(task.url, task.format_id, outdir, progress_hook=hook)
        with _lock:
            t = _tasks.get(task_id)
            if t:
                t.status = TaskStatus.DONE
                t.progress = 100.0
                t.filepath = path
                t.filename = path.name
                t.finished_at = time.time()
    except Exception as exc:  # noqa: BLE001 — 错误字符串直接给前端
        with _lock:
            t = _tasks.get(task_id)
            if t:
                t.status = TaskStatus.ERROR
                t.error = str(exc)
                t.finished_at = time.time()
    finally:
        with _lock:
            _active_count = max(0, _active_count - 1)


def _human_speed(bps: float) -> str:
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    value = float(bps)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} B/s"


def cleanup_expired() -> None:
    """删除超过 FILE_TTL_SECONDS 的任务记录及其临时目录。"""
    now = time.time()
    to_remove: list[str] = []
    with _lock:
        for tid, task in list(_tasks.items()):
            age_ref = task.finished_at or task.created_at
            if now - age_ref > FILE_TTL_SECONDS:
                to_remove.append(tid)

    for tid in to_remove:
        _remove_task(tid)


def _remove_task(task_id: str) -> None:
    with _lock:
        task = _tasks.pop(task_id, None)
    if not task:
        return
    folder = DOWNLOAD_DIR / task_id
    if folder.exists():
        for p in folder.rglob("*"):
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
        try:
            folder.rmdir()
        except OSError:
            pass
    elif task.filepath and task.filepath.exists():
        try:
            task.filepath.unlink()
        except OSError:
            pass


def mark_file_consumed(task_id: str) -> None:
    """可选：客户端取走文件后加速过期（预留）。"""
    task = get_task(task_id)
    if task:
        task.finished_at = time.time() - (FILE_TTL_SECONDS - 60)

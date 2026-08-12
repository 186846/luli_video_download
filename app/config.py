"""应用级配置：路径、免费档清晰度、并发与临时文件策略。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
# yt-dlp 下载产物与字幕临时文件目录（定时清理）
DOWNLOAD_DIR = BASE_DIR / "downloads" / "tmp"

# 免费档最高清晰度；超过则前端门禁 + 后端校验（登录 VIP；或 ALLOW_DEMO_VIP 时 demo-vip）
FREE_MAX_HEIGHT = 720

# 同时进行的下载任务上限，防止打满磁盘/带宽
MAX_CONCURRENT_DOWNLOADS = 2

# 临时文件存活时间（秒），超时由 tasks 后台线程回收
FILE_TTL_SECONDS = 15 * 60

# 单文件体积软上限（预留，当前主要用于配置说明）
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

BRAND_NAME = "速下"
BRAND_EN = "SpeedyDL"

# —— AI 视频总结（OpenAI 兼容；无 Key 则 Mock）——
AI_API_KEY = (os.getenv("SPEEDYDL_AI_API_KEY") or "").strip()
AI_BASE_URL = (os.getenv("SPEEDYDL_AI_BASE_URL") or "https://api.deepseek.com/v1").strip()
AI_MODEL = (os.getenv("SPEEDYDL_AI_MODEL") or "deepseek-chat").strip()
AI_REQUIRE_VIP = (os.getenv("SPEEDYDL_AI_REQUIRE_VIP") or "1").strip() not in (
    "0",
    "false",
    "False",
    "no",
)
AI_MAX_SUBTITLE_CHARS = int(os.getenv("SPEEDYDL_AI_MAX_SUBTITLE_CHARS") or "12000")

# —— B 站官方字幕（view + dm/view，对齐 NoteGPT）——
BILI_SUBS_ENABLED = (os.getenv("SPEEDYDL_BILI_SUBS_ENABLED") or "1").strip() not in (
    "0",
    "false",
    "False",
    "no",
)
# 可选：部分需登录字幕轨（need_login_subtitle）；B 站主路径已走 yt-dlp，通常无需配置
BILI_SESSDATA = (os.getenv("SPEEDYDL_BILI_SESSDATA") or "").strip()

# —— 账号 / Stripe 会员 ——
DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("SPEEDYDL_DB_PATH") or (DATA_DIR / "speedydl.db"))

ALLOW_DEMO_VIP = (os.getenv("SPEEDYDL_ALLOW_DEMO_VIP") or "0").strip() not in (
    "0",
    "false",
    "False",
    "no",
)

STRIPE_SECRET_KEY = (os.getenv("SPEEDYDL_STRIPE_SECRET_KEY") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("SPEEDYDL_STRIPE_WEBHOOK_SECRET") or "").strip()
STRIPE_PRICE_ID = (os.getenv("SPEEDYDL_STRIPE_PRICE_ID") or "").strip()
PUBLIC_BASE_URL = (
    os.getenv("SPEEDYDL_PUBLIC_BASE_URL") or "http://127.0.0.1:5173"
).rstrip("/")
API_PUBLIC_BASE_URL = (
    os.getenv("SPEEDYDL_API_PUBLIC_BASE_URL") or "http://127.0.0.1:8001"
).rstrip("/")

VIP_PRICE_CENTS = 990
VIP_CURRENCY = "usd"
VIP_PRODUCT_NAME = "速下永久会员"

# 免费登录用户每日 AI 总结次数；VIP 不限
FREE_AI_SUMMARIZE_DAILY = int(os.getenv("SPEEDYDL_FREE_AI_SUMMARIZE_DAILY") or "3")


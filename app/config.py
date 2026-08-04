"""应用级配置：路径、免费档清晰度、并发与临时文件策略。"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# yt-dlp 下载产物与字幕临时文件目录（定时清理）
DOWNLOAD_DIR = BASE_DIR / "downloads" / "tmp"

# 免费档最高清晰度；超过则前端门禁 + 后端校验，需 vip_token=demo-vip
FREE_MAX_HEIGHT = 720

# 同时进行的下载任务上限，防止打满磁盘/带宽
MAX_CONCURRENT_DOWNLOADS = 2

# 临时文件存活时间（秒），超时由 tasks 后台线程回收
FILE_TTL_SECONDS = 15 * 60

# 单文件体积软上限（预留，当前主要用于配置说明）
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

BRAND_NAME = "速下"
BRAND_EN = "SpeedyDL"

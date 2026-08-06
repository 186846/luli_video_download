# 速下 SpeedyDL

学习向「万能视频下载」：Vue 3 + Vite 前端 + FastAPI + [yt-dlp](https://github.com/yt-dlp/yt-dlp)。

> **仅供个人学习。请尊重版权与各平台条款，勿用于商业传播。**

## 文档（给后续扩展 / AI 参考）

| 文档 | 说明 |
|------|------|
| [docs/需求分析.md](docs/需求分析.md) | 背景、范围、阶段划分、阶段 3 验收标准 |
| [docs/方案设计.md](docs/方案设计.md) | 架构、模块职责、核心流程、扩展指引 |
| [docs/API.md](docs/API.md) | HTTP 接口契约与示例 |
| [docs/部署文档.md](docs/部署文档.md) | 开发联调、构建、Nginx/Caddy 同源反代与运维要点 |
| [docs/项目总结.md](docs/项目总结.md) | 主功能完成后的能力清单、决策与限制 |
| [docs/AI视频总结方案.md](docs/AI视频总结方案.md) | AI 总结 MVP 范围、流程、API 与验收 |
| [docs/竞品调研-AI视频总结.md](docs/竞品调研-AI视频总结.md) | BibiGPT / NoteGPT 调研与边界结论 |

## 架构

- **前端** `web/`：Vue 3 + Vite（`http://127.0.0.1:5173`，代理 `/api`）
- **后端** `app/`：FastAPI（`http://127.0.0.1:8000`，自带 `/docs`）
- **下载模式①**：服务端落盘后提供 `/api/files/{id}`
- **直链模式②**：`/api/direct` 返回单流直链（合并清晰度不可用）
- **字幕**：解析返回字幕列表，`/api/subtitles/download` 下载
- **AI 总结**：`/api/summarize`（字幕优先；无 Key 时 Mock）
- **无 CC 字幕**：弹幕兜底 → 元数据（不做默认语音转写，保证秒出）
- **历史**：浏览器 localStorage，最多 20 条

## 环境

- Python 3.11+
- Node.js 18+
- [ffmpeg](https://ffmpeg.org/) 已加入 PATH

AI 总结文本来源：B 站官方 CC/AI → yt-dlp → 用户粘贴/上传 → 弹幕 → 标题/简介（不做 Whisper / OCR）。

## 启动

### 1. 后端

```bash
cd d:\luli
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 前端（另开终端）

```bash
cd d:\luli\web
npm install
npm run dev
```

浏览器：**http://127.0.0.1:5173**

演示/准生产（构建前端 + 反代 `/api`）见 **[docs/部署文档.md](docs/部署文档.md)**。

## API

完整说明见 **[docs/API.md](docs/API.md)**。  
在线交互文档：后端启动后打开 http://127.0.0.1:8000/docs

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/parse` | 解析元数据 / 格式 / 字幕列表 |
| POST | `/api/download` | 服务端下载任务 |
| POST | `/api/direct` | 解析单流直链 |
| POST | `/api/subtitles/download` | 下载字幕文件 |
| POST | `/api/summarize` | AI 视频总结（无 Key 时 Mock）→ 前端跳转 `/summary` |
| POST | `/api/summarize/ask` | 针对视频内容问答 |
| GET | `/api/tasks/{id}` | 任务进度 |
| GET | `/api/files/{id}` | 取回已下载文件 |
| GET | `/api/thumbnail` | 封面代理 |

演示 VIP：`vip_token` 传 `demo-vip`（高清下载与 AI 总结默认门禁）。

## 测试

```bash
cd d:\luli
.\.venv\Scripts\python -m pytest -q
```

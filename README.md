# 速下 SpeedyDL

学习向「万能视频下载」：Vue 3 + Vite 前端 + FastAPI + [yt-dlp](https://github.com/yt-dlp/yt-dlp)。

> **仅供个人学习。请尊重版权与各平台条款，勿用于商业传播。**

**代码仓库**：[https://github.com/186846/luli_video_download](https://github.com/186846/luli_video_download)

## 文档（给后续扩展 / AI 参考）

| 文档 | 说明 |
|------|------|
| [docs/需求分析.md](docs/需求分析.md) | 背景、范围、阶段划分、阶段 3 验收标准 |
| [docs/方案设计.md](docs/方案设计.md) | 架构、模块职责、核心流程、扩展指引 |
| [docs/API.md](docs/API.md) | HTTP 接口契约与示例 |
| [docs/部署文档.md](docs/部署文档.md) | 开发联调、构建、Nginx/Caddy 同源反代与运维要点 |
| [docs/腾讯云部署.md](docs/腾讯云部署.md) | 腾讯云轻量 + 宝塔 LNMP + 域名 + HTTPS + Supervisor 线上部署 |
| [docs/SEO说明.md](docs/SEO说明.md) | 前端 SEO / GEO、换域名、站长平台与 AI 抽检清单 |
| [docs/GEO优化入门指南.md](docs/GEO优化入门指南.md) | 生成式引擎优化要点与本站已落地项 |
| [docs/项目总结.md](docs/项目总结.md) | 主功能完成后的能力清单、决策与限制 |
| [docs/AI视频总结方案.md](docs/AI视频总结方案.md) | AI 总结范围、流程、API 与验收 |
| [docs/思维导图增强方案.md](docs/思维导图增强方案.md) | 页内全屏与 PNG / FreeMind / OPML 导出 |
| [docs/Stripe会员接入.md](docs/Stripe会员接入.md) | 账号 + Stripe Checkout 配置与 CLI 本地测 Webhook |
| [docs/竞品调研-AI视频总结.md](docs/竞品调研-AI视频总结.md) | BibiGPT / NoteGPT 调研与边界结论 |

## 架构

- **前端** `web/`：Vue 3 + Vite（`http://127.0.0.1:5173`，代理 `/api`）；`api/` 分域、`components/` 区块化、`HomeView` 只做编排
- **后端** `app/`：FastAPI（本地默认 `http://127.0.0.1:8001`，自带 `/docs`）
- **布局**：解析结果 / 平台介绍在左，最近解析侧栏在右；定价、常见问题与关于填在左侧主栏
- **GEO**：`/llms.txt`、AI 爬虫 Allow、首页 `#faq`、FAQ/HowTo JSON-LD（详见 [SEO说明](docs/SEO说明.md)）
- **下载模式①**：服务端落盘后提供 `/api/files/{id}`
- **直链模式②**：`/api/direct` 返回单流直链（合并清晰度不可用）
- **字幕**：解析仍返回字幕轨（含 B 站官方 CC/AI）；首页不再单独下载，字幕/弹幕在总结页导出 TXT / SRT / VTT
- **AI 总结**：`/api/summarize` → `/summary`（摘要 · 字幕 · 弹幕 · 思维导图 · 问答）；左侧「视频简介」展示整体摘要与核心要点
- **思维导图**：页内全屏阅读；导出高清 PNG / FreeMind(`.mm`) / OPML / SVG（`.mm`/`opml` 可导入 XMind、幕布等继续编辑）
- **文本来源**：B 站官方 CC/AI → yt-dlp → 用户粘贴/上传 → 弹幕 → 标题/简介（不做 Whisper / OCR）
- **章节大纲**：按字幕时间轴 / 片长均分锚点，避免长视频章节挤在片头
- **历史**：浏览器 localStorage，最多 20 条
- **账号 / 会员**：邮箱密码登录（SQLite）；Stripe Checkout 一次性 $9.90 USD 开通永久 VIP（Webhook 履约）；详见 [Stripe会员接入](docs/Stripe会员接入.md)

## 环境

- Python 3.11+
- Node.js 18+
- [ffmpeg](https://ffmpeg.org/) 已加入 PATH

## 启动

### 1. 后端

```bash
cd d:\luli
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

> Windows 若本机 `8000` 被僵尸进程占用，请使用 **8001**（与 `web/vite.config.js` 代理一致）。

### 2. 前端（另开终端）

```bash
cd d:\luli\web
npm install
npm run dev
```

浏览器：**http://127.0.0.1:5173**

演示/准生产（构建前端 + 反代 `/api`）见 **[docs/部署文档.md](docs/部署文档.md)**。  
**腾讯云线上部署**见 **[docs/腾讯云部署.md](docs/腾讯云部署.md)**。

## API

完整说明见 **[docs/API.md](docs/API.md)**。  
在线交互文档：后端启动后打开 http://127.0.0.1:8001/docs

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/parse` | 解析元数据 / 格式 / 字幕列表 |
| POST | `/api/download` | 服务端下载任务 |
| POST | `/api/direct` | 解析单流直链 |
| POST | `/api/subtitles/download` | 下载字幕文件 |
| POST | `/api/summarize` | AI 视频总结（异步任务；无 Key 时 Mock） |
| GET | `/api/summarize/status/{id}` | 总结任务状态轮询 |
| GET | `/api/summarize/stream/{id}` | 总结进度 SSE |
| POST | `/api/summarize/ask` | 针对视频内容问答（同步） |
| POST | `/api/chat` | 针对视频内容问答（SSE） |
| GET | `/api/embed` | 页内播放参数 |
| GET | `/api/tasks/{id}` | 任务进度 |
| GET | `/api/files/{id}` | 取回已下载文件 |
| GET | `/api/thumbnail` | 封面代理 |

演示 VIP：`vip_token` 传 `demo-vip`（高清下载与 AI 总结默认门禁）。

## 测试

```bash
cd d:\luli
.\.venv\Scripts\python -m pytest -q
```

# 速下 SpeedyDL — AI 视频总结方案

> 关联：[竞品调研](./竞品调研-AI视频总结.md) · [API](./API.md) · [方案设计](./方案设计.md)  
> 范围：学习向总结详情页（摘要 · 字幕 · 弹幕 · 思维导图 · AI 问答）+ 导出 / 导图 / 左侧简介增强

---

## 1. 范围确认（已定）

| 项 | 决定 |
|----|------|
| 入口 | 首页结果卡点「AI 总结」→ **跳转 `/summary` 详情页**（首页不再提供独立「下载字幕」入口） |
| 详情 Tab | **摘要** · **字幕文本** · **弹幕列表** · **思维导图** · **AI 问答** |
| 左侧栏 | 播放器 + 标题；**视频简介**展示 AI **整体摘要** + **核心要点**（可滚动铺满剩余高度） |
| 字幕 / 弹幕 Tab | 轨信息、条数、**关键词搜索高亮**、**匹配导航**、复制、时间跳转；**导出下拉**：TXT / SRT / VTT |
| 摘要 Tab | 整体摘要 + 核心要点 + **章节时间戳跳转** + **导出 Markdown**；统计条（时长/章节/要点/字幕等） |
| 文本来源 | **B 站官方 CC/AI** → **yt-dlp** → **用户字幕** → **弹幕** → **元数据**（不做 Whisper / OCR） |
| 章节大纲 | **按字幕时间轴 / 片长均分锚点**；模型负责标题与摘要；长视频强制覆盖全片 |
| 后端模块 | `bilibili_subs` · `summarizer` · `embed`；总结结果附带 `description` / `uploader` |
| 推送 | 总结进度与问答均支持 **SSE**（`/api/summarize/stream` · `/api/chat`） |
| 模型 | OpenAI 兼容；无 Key 自动 Mock；**LLM JSON 解析容错**（解析失败降级兜底） |
| 门禁 | 演示 VIP（`vip_token=demo-vip`） |
| 思维导图 | NoteGPT 风格画布：`MindMapCanvas`（缩放 / 拖拽 / 折叠 / **页内全屏** / 导出 **PNG·FreeMind·OPML·SVG**）；详见 [思维导图增强方案](./思维导图增强方案.md) |

### 1.1 增强能力一览

| 能力 | 说明 | 改动位置 |
|------|------|----------|
| **章节时间戳跳转增强** | 章节点击跳转播放器后，可联动字幕/弹幕 Tab 高亮对应句并滚动到可视区 | `SummaryView.vue` seekTo |
| **字幕/弹幕搜索高亮** | 命中词 `<mark>` 高亮；↑/↓ 导航 + 计数 | `SummaryView.vue` highlightHtml / match-nav |
| **导出 Markdown / 字幕文件** | 摘要 `.md`；字幕/弹幕 **导出菜单**：`.txt` / `.srt` / `.vtt` | `exportFile.js` + SummaryView |
| **左侧视频简介** | 填入 AI 整体摘要 + 核心要点，替代平台 description 占位 | `SummaryView.vue` sum-intro |
| **思维导图增强** | 页内全屏 + PNG / `.mm` / OPML / SVG | `mindMapExport.js` · MindMapCanvas |

---

## 2. 流程

```mermaid
flowchart LR
  Home[首页解析结果] --> Click[点击AI总结]
  Click --> API[POST_api_summarize]
  API --> Page["/summary 详情页"]
  Page --> Side[左侧简介: 整体摘要+核心要点]
  Page --> T1[摘要要点章节]
  Page --> T2[字幕文本]
  Page --> T2b[弹幕列表]
  Page --> T3[思维导图树]
  Page --> T4[AI问答 ask]
  T1 -->|章节时间戳点击| Seek[seekTo 跳转播放器]
  T1 -->|导出| ExportMD[下载 .md]
  T2 -->|搜索 / 导出| SubOut[高亮导航 · TXT/SRT/VTT]
  T2b -->|搜索 / 导出| DmOut[高亮导航 · TXT/SRT/VTT]
  T3 -->|全屏 / 导出| MmOut[PNG · mm · OPML · SVG]
  T4 -->|提问 + 透传transcript| AskAPI["POST /api/summarize/ask"]
```

---

## 3. API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/summarize` | 摘要、要点、章节、`transcript`、`mind_map`（异步任务） |
| GET | `/api/summarize/stream/{task_id}` | SSE：总结进度 `progress` / `done` / `error` |
| POST | `/api/summarize/ask` | 针对视频内容提问（同步 JSON，兼容） |
| POST | `/api/chat` | 针对视频内容提问（SSE：`status` / `token` / `done` / `error`） |

总结响应关键字段：`summary` · `key_points` · `chapters` · `transcript[{start,text}]` · `mind_map{name,children[]}` · `description` · `uploader` · `mode` · `source`（可含 `danmaku_transcript`）

问答请求：`url` + `question` + `vip_token` + 可选 `lang` + 可选 `transcript[{start,text}]`

> **优化**：问答时前端传入已有 `transcript`，后端 `ask_about_video` 直接复用，跳过 `parse_video` + 字幕拉取，减少重复网络请求。

---

## 4. 前端

首页按区块拆分：`HomeView` 只保留状态与编排，UI 在 `components/`（Hero / VideoResult / HistoryPanel / Pricing 等）。API 按域拆到 `api/video` · `api/summarize` 等，经 `api/index` 统一导出。

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | `views/HomeView.vue` | 解析入口 + AI 总结编排（无独立字幕下载 UI） |
| `/summary` | `views/SummaryView.vue` | 五 Tab + 左侧简介 + 导出 / 跳转增强 |
| 思维导图 | `components/MindMapCanvas.vue` | 全屏 + 导出菜单 |
| 播放器工具 | `utils/embedPlayer.js` | 时间戳解析 + embed URL 构建 |
| **文本导出** | `utils/exportFile.js` | Markdown / TXT / SRT / VTT + `safeFilename` |
| **导图导出** | `utils/mindMapExport.js` | PNG / FreeMind `.mm` / OPML / SVG |

### 4.1 SummaryView 关键函数

| 函数 | 作用 |
|------|------|
| `seekTo(ts)` | 跳转播放器；在字幕/弹幕 Tab 时高亮对应句并滚动 |
| `highlightHtml(text, index)` | HTML 转义 + `<mark>` 高亮关键词，当前匹配项加 `.is-current` |
| `goPrevMatch` / `goNextMatch` | 匹配导航，循环切换 + `scrollIntoView` |
| `exportMarkdown` | 调用 `formatPlain()` 生成 Markdown，下载 `.md` |
| `exportTranscriptTxt` / `exportSrt` / `exportVtt` | 当前 Tab 时间轴列表导出对应格式 |

---

## 5. 后端容错

### 5.1 LLM JSON 解析容错

`_extract_json(content)` 两级策略：
1. 直接 `json.loads`（理想情况）
2. 提取第一个 `{` 到最后一个 `}` 之间的片段再解析（处理 LLM 在 JSON 前后加说明文字）

解析失败时 `_call_llm` 降级为结构化兜底（原始文本作 summary，空数组兜底要点/章节），不崩溃。

### 5.2 _chat_completion 网络异常容错

- `HTTPStatusError` → 友好 ValueError（含状态码 + 响应前 200 字）
- `RequestError` → 友好 ValueError（含异常信息）
- 返回结构异常 → 友好 ValueError

### 5.3 ask_about_video transcript 复用

前端传入 `transcript` 时跳过 `_resolve_context`，避免重复 `parse_video` + 字幕拉取。

---

## 6. 验收清单

### 6.1 基础五 Tab + 左侧简介

1. 演示会员 + 有字幕视频：点 AI 总结 → 进入详情页，五 Tab 可用
2. 左侧「视频简介」展示整体摘要与核心要点（与右侧摘要一致）
3. 无 Key：`mode=mock`，摘要/导图/问答均可演示
4. 字幕 / 弹幕 Tab 展示时间戳；可搜索
5. 思维导图：页内全屏 + 导出 PNG / `.mm` / OPML / SVG
6. AI 问答可发送问题并得到回答
7. 未开会员：403 / 前端提示开通
8. `pytest tests/test_summarize.py` 通过

### 6.2 导出与跳转

9. **章节跳转**：摘要 Tab 点击章节时间戳 → 播放器跳转；在字幕/弹幕 Tab 可联动高亮
10. **搜索高亮**：关键词标黄；↑/↓ 导航；`N/M` 计数
11. **导出 Markdown**：摘要 Tab → `{标题}.md`（标题/摘要/要点/章节）
12. **导出 TXT/SRT/VTT**：字幕或弹幕 Tab「导出」菜单下载对应文件

### 6.3 容错验证

13. **LLM 返回非 JSON**：`_call_llm` 不崩溃，降级为兜底结构
14. **LLM 返回带前缀文字的 JSON**：`_extract_json` 能提取出 JSON 对象
15. **问答透传 transcript**：后端不重复 `parse_video`，直接用前端传入的字幕回答

### 6.4 双模式验收

16. **Mock 模式**：无 `SPEEDYDL_AI_API_KEY`，五 Tab + 导出 / 导图增强可用
17. **真实 LLM 模式**：配置 `SPEEDYDL_AI_API_KEY` 后用有字幕视频验证 LLM 总结 + 问答

---

## 7. 环境变量

```bash
SPEEDYDL_AI_API_KEY=sk-...
SPEEDYDL_AI_BASE_URL=https://api.deepseek.com/v1
SPEEDYDL_AI_MODEL=deepseek-chat
SPEEDYDL_AI_REQUIRE_VIP=1
SPEEDYDL_AI_MAX_SUBTITLE_CHARS=12000
```

---

## 8. 测试覆盖

`tests/test_summarize.py` 覆盖：

| 测试 | 说明 |
|------|------|
| `test_parse_subtitle_cues` | VTT 字幕解析 |
| `test_parse_srt_with_index` | SRT 字幕解析（带序号） |
| `test_subtitle_candidates_prefer_zh` | 字幕轨中文优先排序 |
| `test_chapters_from_cues_have_timestamps` | 章节时间戳生成 |
| `test_build_mind_map` | 思维导图树构建 |
| `test_mock_summary_structure` | Mock 总结结构完整性 |
| `test_mock_summary_metadata_fallback` | 无字幕 Mock 降级 |
| `test_ask_mock_without_key` | Mock 问答 |
| `test_summarize_requires_vip` | 总结 VIP 门禁 |
| `test_ask_requires_vip` | 问答 VIP 门禁 |
| `test_summarize_mock_with_vip` | VIP + Mock 完整流程 |
| `test_health_lists_summarize_and_ask` | 健康检查特性声明 |
| **`test_extract_json_direct`** | JSON 直接解析 |
| **`test_extract_json_with_prefix_text`** | 带前缀文字的 JSON 提取 |
| **`test_extract_json_with_code_fence`** | 纯 JSON 解析 |
| **`test_extract_json_invalid_raises`** | 无效内容抛 ValueError |
| **`test_call_llm_json_parse_fallback`** | LLM 非 JSON 降级兜底 |
| **`test_ask_with_transcript_skips_resolve_context`** | transcript 复用跳过解析 |
| **`test_ask_without_transcript_calls_resolve_context`** | 无 transcript 回退解析 |
| **`test_ask_endpoint_accepts_transcript`** | 路由透传 transcript |

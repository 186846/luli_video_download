<script setup>
/**
 * AI 总结详情页：可播原视频 · 摘要 · 字幕 · 思维导图 · AI 问答
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { streamChat, thumbnailUrl } from '../api/client'
import MindMapCanvas from '../components/MindMapCanvas.vue'
import { loadSummarySession, saveSummarySession } from '../composables/useSummarySession'
import { useVip } from '../composables/useVip'
import {
  buildEmbedUrlFromPlayer,
  formatTimestampForDisplay,
  parseTimestampToSeconds,
  resolveEmbedPlayer,
} from '../utils/embedPlayer'
import { downloadMarkdown, downloadSrt, downloadTxt, downloadVtt } from '../utils/exportFile'

const router = useRouter()
const { isVip } = useVip()

const data = ref(null)
// summary | subtitles(字幕文本) | transcript(弹幕列表) | mindmap | ask
const tab = ref('summary')
const question = ref('')
const asking = ref(false)
const askError = ref('')
const askStatus = ref('')
const chat = ref([]) // { role: 'user'|'assistant', text, warning?, streaming? }
const copied = ref(false)
const transcriptCopied = ref(false)
const transcriptFilter = ref('')
/** 字幕列表默认折叠阈值；超出后默认收起，需要手动「展开全部」查看完整内容 */
const TRANSCRIPT_COLLAPSED_LIMIT = 50
/** 字幕文本列表是否展开（仅在 transcript 数量超出阈值时才显示「展开全部」按钮） */
const transcriptExpanded = ref(false)
/** 弹幕源时默认显示完整列表；可手动切换到「AI 整理章节」视图 */
const useChapterView = ref(false)
function toggleTranscriptView() {
  useChapterView.value = !useChapterView.value
}
/** 切换字幕列表的展开/收起 */
function toggleTranscriptExpand() {
  transcriptExpanded.value = !transcriptExpanded.value
}
/** 播放器跳转秒数；变更时强制重建 iframe */
const seekSeconds = ref(0)
const playerKey = ref(0)
const playerInfo = ref(null) // 后端补全的 cid 等
const playerLoading = ref(false)
const playerError = ref('')
/** 字幕搜索匹配导航：当前匹配索引（在 filteredTranscript 中的位置） */
const currentMatchIndex = ref(0)

onMounted(async () => {
  const saved = loadSummarySession()
  if (!saved) {
    router.replace({ name: 'home' })
    return
  }
  data.value = saved
  playerInfo.value = saved.player || null
  // 默认进入有内容的文本标签：有平台 CC 进字幕文本，否则有弹幕进弹幕列表
  useChapterView.value = false
  if (saved.transcript?.length && saved.source === 'subtitles') {
    tab.value = 'subtitles'
  } else if (saved.danmaku_transcript?.length || (saved.is_danmaku && saved.transcript?.length)) {
    tab.value = 'transcript'
  } else if (saved.transcript?.length && saved.source !== 'danmaku') {
    tab.value = 'subtitles'
  }
  document.addEventListener('pointerdown', onExportDocPointer, true)
  // 若会话里没有带 cid 的 player，再向后端补一次
  if (saved.url && (!saved.player?.cid || !saved.player?.embed_url)) {
    await refreshPlayer(0)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onExportDocPointer, true)
  if (exportMsgTimer) clearTimeout(exportMsgTimer)
})

watch(tab, () => {
  exportOpen.value = false
})

// data 切换时同步 useChapterView（默认显示完整列表）
watch(
  () => [data.value?.is_danmaku, data.value?.chapters?.length],
  () => {
    useChapterView.value = false
  }
)

const thumbSrc = computed(() => {
  if (!data.value?.thumbnail) return ''
  return thumbnailUrl(data.value.thumbnail, data.value.url)
})

const embed = computed(() => {
  if (playerInfo.value) {
    return buildEmbedUrlFromPlayer(playerInfo.value, seekSeconds.value)
  }
  if (!data.value?.url) return null
  return resolveEmbedPlayer(data.value.url, {
    startSeconds: seekSeconds.value,
    extractor: data.value.extractor,
    cid: data.value.player?.cid,
  })
})

async function refreshPlayer(t = 0) {
  if (!data.value?.url) return
  playerLoading.value = true
  playerError.value = ''
  try {
    const qs = new URLSearchParams({
      url: data.value.url,
      t: String(Math.max(0, Math.floor(t || 0))),
    })
    const res = await fetch(`/api/embed?${qs.toString()}`)
    const json = await res.json().catch(() => ({}))
    if (!res.ok) {
      throw new Error(json.detail || '无法获取播放地址')
    }
    playerInfo.value = json.data
    // 写回会话，避免刷新丢失 cid
    saveSummarySession({
      ...data.value,
      player: json.data,
    })
    data.value = { ...data.value, player: json.data }
  } catch (err) {
    playerError.value = err.message || String(err)
  } finally {
    playerLoading.value = false
  }
}

const sourceLabel = computed(() => {
  const src = data.value?.source
  if (src === 'subtitles') return '基于字幕'
  if (src === 'user') return '基于用户字幕'
  if (src === 'danmaku') return '基于弹幕'
  return '基于元数据'
})

/** 左侧简介：展示 AI 整体摘要，铺满剩余空间 */
const sideIntro = computed(() => {
  const d = data.value
  if (!d) return ''
  return String(d.summary || '')
    .replace(/\s+/g, ' ')
    .trim()
})

const sideKeyPoints = computed(() => data.value?.key_points || [])

const sideMetaLine = computed(() => {
  const d = data.value
  if (!d) return ''
  const parts = []
  if (d.uploader) parts.push(d.uploader)
  const dur = formatDurationLabel(d.duration)
  if (dur && dur !== '—') parts.push(dur)
  if (d.extractor) parts.push(String(d.extractor))
  return parts.join(' · ')
})

/** true: 主 transcript 实为弹幕；平台字幕不算弹幕 */
const isDanmaku = computed(() => Boolean(data.value?.is_danmaku) && data.value?.source === 'danmaku')
/** 字幕文本：平台 CC / 用户粘贴 */
const hasSubtitles = computed(() => {
  const d = data.value
  if (!d?.transcript?.length) return false
  return ['subtitles', 'user'].includes(d.source)
})
/** 弹幕列表：独立字段优先，否则回退旧逻辑 */
const hasDanmaku = computed(() => {
  if (data.value?.danmaku_transcript?.length) return true
  return Boolean(data.value?.is_danmaku) && Boolean(data.value?.transcript?.length)
})
/** 字幕轨道徽标 */
const subtitleTrackLabel = computed(() => {
  const d = data.value
  if (!d?.transcript?.length) return ''
  if (d.source === 'user') return '用户字幕'
  if (!d?.lang || d.source !== 'subtitles') return ''
  const auto = d.automatic ? '自动' : '人工'
  return `${d.subtitle_name || d.lang} · ${auto}`
})
/** 字幕文本条目 */
const subtitleCount = computed(() => data.value?.transcript_count || data.value?.transcript?.length || 0)

const danmakuList = computed(() => {
  const d = data.value
  if (d?.danmaku_transcript?.length) return d.danmaku_transcript
  if (d?.is_danmaku && d?.transcript?.length) return d.transcript
  return []
})

const filteredTranscript = computed(() => {
  // 「字幕文本」Tab 仅展示平台 CC；弹幕源时该列表为空由 empty 态处理
  const list = hasSubtitles.value ? data.value?.transcript || [] : []
  const q = transcriptFilter.value.trim().toLowerCase()
  if (!q) return list
  return list.filter(
    (c) =>
      (c.text || '').toLowerCase().includes(q) ||
      (c.start || '').includes(q),
  )
})

const filteredDanmaku = computed(() => {
  const list = danmakuList.value
  const q = transcriptFilter.value.trim().toLowerCase()
  if (!q) return list
  return list.filter(
    (c) =>
      (c.text || '').toLowerCase().includes(q) ||
      (c.start || '').includes(q),
  )
})

/**
 * 真正渲染到 DOM 的字幕列表：
 *   - 搜索时：始终渲染全部匹配项，方便匹配定位
 *   - 非搜索时：未展开时只取前 TRANSCRIPT_COLLAPSED_LIMIT 条，模拟截图中的折叠效果
 */
const displayTranscript = computed(() => {
  const list = filteredTranscript.value
  if (transcriptFilter.value.trim()) return list
  if (transcriptExpanded.value || list.length <= TRANSCRIPT_COLLAPSED_LIMIT) {
    return list
  }
  return list.slice(0, TRANSCRIPT_COLLAPSED_LIMIT)
})

/** 是否需要展示「展开全部 / 收起」按钮（仅当字幕超过阈值且不在搜索状态） */
const showTranscriptExpandToggle = computed(() => {
  if (transcriptFilter.value.trim()) return false
  return (data.value?.transcript?.length || 0) > TRANSCRIPT_COLLAPSED_LIMIT
})

/** 匹配总数（仅在搜索时计算；字幕 Tab / 弹幕 Tab 各自过滤） */
const matchCount = computed(() => {
  if (!transcriptFilter.value.trim()) return 0
  if (tab.value === 'transcript') return filteredDanmaku.value.length
  return filteredTranscript.value.length
})

/**
 * 搜索高亮：将文本中命中关键词用 <mark> 包裹，先转义再插入标签防 XSS。
 * 当前匹配项额外加 .is-current 类，用于区分颜色。
 */
function highlightHtml(text, index) {
  const raw = String(text || '')
  // 1. 先 HTML 转义，防止注入
  const escaped = raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  const q = transcriptFilter.value.trim()
  if (!q) return escaped
  // 2. 转义关键词中的正则特殊字符
  const safeQ = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  try {
    const re = new RegExp(`(${safeQ})`, 'gi')
    const cls = index === currentMatchIndex.value ? 'mark-match is-current' : 'mark-match'
    return escaped.replace(re, `<mark class="${cls}">$1</mark>`)
  } catch {
    return escaped
  }
}

const activeCueIndex = computed(() => {
  const list = filteredTranscript.value
  if (!list.length) return -1
  // 搜索模式下，高亮当前匹配项
  if (transcriptFilter.value.trim()) {
    const idx = Math.min(currentMatchIndex.value, list.length - 1)
    return idx >= 0 ? idx : -1
  }
  // 非搜索模式：按播放进度高亮
  const t = seekSeconds.value
  let best = -1
  for (let i = 0; i < list.length; i++) {
    const sec = parseTimestampToSeconds(list[i].start)
    if (sec <= t) best = i
    else break
  }
  return best
})

/** 滚动当前匹配项到可视区域（定位当前激活的文本面板） */
function scrollMatchIntoView() {
  nextTick(() => {
    const panel = document.querySelector(
      `.sum-panel[data-panel="${tab.value === 'transcript' ? 'transcript' : 'subtitles'}"]`,
    )
    const list = panel?.querySelector('.transcript-list')
    if (!list) return
    const items = list.querySelectorAll('li')
    const target = items[currentMatchIndex.value]
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
}

function goPrevMatch() {
  if (!matchCount.value) return
  currentMatchIndex.value =
    (currentMatchIndex.value - 1 + matchCount.value) % matchCount.value
  scrollMatchIntoView()
}

function goNextMatch() {
  if (!matchCount.value) return
  currentMatchIndex.value = (currentMatchIndex.value + 1) % matchCount.value
  scrollMatchIntoView()
}

/** 搜索框输入时重置匹配索引到第一条 */
function onTranscriptSearchInput() {
  currentMatchIndex.value = 0
}

function goHome() {
  router.push({ name: 'home' })
}

function formatChapterTime(ts) {
  const s = formatTimestampForDisplay(ts)
  return s || '--:--'
}

function seekTo(ts) {
  let sec = parseTimestampToSeconds(ts)
  const dur = Number(data.value?.duration)
  if (Number.isFinite(dur) && dur > 0) {
    sec = Math.min(sec, Math.max(0, Math.floor(dur) - 1))
  }
  seekSeconds.value = Math.max(0, sec)
  playerKey.value += 1
  // 字幕文本 / 弹幕列表 Tab 时同步高亮并滚动到对应句；不要强制切 Tab
  if (tab.value === 'subtitles' || tab.value === 'transcript') {
    transcriptFilter.value = ''
    currentMatchIndex.value = 0
    nextTick(() => {
      // 两个文本面板各自带 transcript-list，按当前激活标签的 data-panel 定位对应列表
      const panel = document.querySelector(
        `.sum-panel[data-panel="${tab.value}"]`,
      )
      const list = panel?.querySelector('.transcript-list')
      if (!list) return
      const items = list.querySelectorAll('li')
      const t = seekSeconds.value
      const allCues = data.value?.transcript || []
      let best = -1
      for (let i = 0; i < allCues.length; i++) {
        const cueSec = parseTimestampToSeconds(allCues[i].start)
        if (cueSec <= t) best = i
        else break
      }
      if (best >= 0 && items[best]) {
        items[best].scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    })
  }
}

function formatPlain() {
  const d = data.value
  if (!d) return ''
  const lines = []
  if (d.title) lines.push(`# ${d.title}`, '')
  lines.push('## 整体摘要', d.summary || '', '')
  if (d.key_points?.length) {
    lines.push('## 核心要点')
    d.key_points.forEach((p) => lines.push(`- ${p}`))
    lines.push('')
  }
  if (d.chapters?.length) {
    lines.push('## 章节大纲')
    d.chapters.forEach((c) => {
      lines.push(`- ${c.start || '--:--'} ${c.title || ''}${c.summary ? `：${c.summary}` : ''}`)
    })
  }
  return lines.join('\n').trim()
}

function formatTranscriptPlain() {
  const list = data.value?.transcript || []
  return list.map((c) => `[${c.start || '--:--'}] ${c.text || ''}`).join('\n')
}

async function copyAll() {
  try {
    await navigator.clipboard.writeText(formatPlain())
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1600)
  } catch {
    /* ignore */
  }
}

async function copyTranscript() {
  const text = formatTranscriptPlain()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    transcriptCopied.value = true
    setTimeout(() => {
      transcriptCopied.value = false
    }, 1600)
  } catch {
    /* ignore */
  }
}

const exportedMd = ref(false)
const exportOpen = ref(false)
const exportMsg = ref('')
let exportMsgTimer = null

function flashExportMsg(msg) {
  exportMsg.value = msg
  if (exportMsgTimer) clearTimeout(exportMsgTimer)
  exportMsgTimer = setTimeout(() => {
    exportMsg.value = ''
    exportMsgTimer = null
  }, 1800)
}

function flashExport(flag) {
  flag.value = true
  setTimeout(() => {
    flag.value = false
  }, 1600)
}

/** 当前 Tab 对应的可导出时间轴列表 */
function activeExportCues() {
  if (tab.value === 'transcript') return danmakuList.value
  return data.value?.transcript || []
}

function formatCuesPlain(list) {
  return (list || []).map((c) => `[${c.start || '--:--'}] ${c.text || ''}`).join('\n')
}

function exportMarkdown() {
  const d = data.value
  if (!d) return
  downloadMarkdown(d.title || 'AI总结', formatPlain())
  flashExport(exportedMd)
}

function runCueExport(fmt) {
  exportOpen.value = false
  const list = activeExportCues()
  if (!list.length) {
    flashExportMsg('暂无可导出内容')
    return
  }
  const title = data.value?.title || 'AI总结'
  if (fmt === 'txt') {
    const suffix = tab.value === 'transcript' ? '弹幕' : '字幕'
    downloadTxt(title, formatCuesPlain(list), suffix)
    flashExportMsg(`已导出 ${suffix} TXT`)
    return
  }
  if (fmt === 'srt') {
    downloadSrt(title, list)
    flashExportMsg('已导出 SRT')
    return
  }
  if (fmt === 'vtt') {
    downloadVtt(title, list)
    flashExportMsg('已导出 VTT')
  }
}

function onExportDocPointer(e) {
  if (!exportOpen.value) return
  if (e.target?.closest?.('.sum-export')) return
  exportOpen.value = false
}

async function onAsk() {
  const q = question.value.trim()
  if (!q || !data.value?.ask || asking.value) return
  if (!isVip.value) {
    askError.value = '请先在首页开通演示会员'
    return
  }
  asking.value = true
  askError.value = ''
  askStatus.value = '正在连接…'
  chat.value.push({ role: 'user', text: q })
  question.value = ''
  const assistantIdx = chat.value.length
  chat.value.push({
    role: 'assistant',
    text: '',
    warning: null,
    streaming: true,
  })
  await nextTick()

  try {
    await streamChat(
      {
        ...data.value.ask,
        question: q,
        transcript: data.value.transcript || null,
      },
      {
        onStatus(msg) {
          askStatus.value = msg || '生成中…'
        },
        onToken(text) {
          const row = chat.value[assistantIdx]
          if (!row) return
          chat.value[assistantIdx] = {
            ...row,
            text: (row.text || '') + text,
            streaming: true,
          }
        },
        onDone(payload) {
          const row = chat.value[assistantIdx] || {}
          chat.value[assistantIdx] = {
            ...row,
            role: 'assistant',
            text: payload?.answer || row.text || '（无回答）',
            warning: payload?.warning || null,
            mode: payload?.mode,
            streaming: false,
          }
          askStatus.value = ''
        },
        onError(msg) {
          askError.value = msg || '问答失败'
          const row = chat.value[assistantIdx] || {}
          chat.value[assistantIdx] = {
            ...row,
            role: 'assistant',
            text: row.text || `回答失败：${askError.value}`,
            streaming: false,
          }
          askStatus.value = ''
        },
      },
    )
  } catch (err) {
    askError.value = err.message || String(err)
    const row = chat.value[assistantIdx]
    if (row) {
      row.text = row.text || `回答失败：${askError.value}`
      row.streaming = false
    }
    askStatus.value = ''
  } finally {
    asking.value = false
  }
}

const presets = [
  '这个视频的核心结论是什么？',
  '列出 3 个最重要的知识点',
  '适合什么样的学习者观看？',
]

const TIMELINE_COLORS = [
  '#4B8BFF',
  '#34B36F',
  '#F59E0B',
  '#A855F7',
  '#F43F5E',
  '#14B8A6',
  '#6366F1',
  '#EAB308',
]

function formatDurationLabel(sec) {
  const n = Number(sec)
  if (!Number.isFinite(n) || n <= 0) return '—'
  const h = Math.floor(n / 3600)
  const m = Math.floor((n % 3600) / 60)
  const s = Math.floor(n % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

/** 摘要页顶部数据卡 */
const overviewStats = computed(() => {
  const d = data.value
  if (!d) return []
  const cueN = Number(d.transcript_count) || d.transcript?.length || 0
  const dmN = danmakuList.value.length
  const mindN = d.mind_map?.children?.length || 0
  return [
    { key: 'dur', label: '片长', value: formatDurationLabel(d.duration) },
    { key: 'ch', label: '章节', value: String(d.chapters?.length || 0) },
    { key: 'kp', label: '要点', value: String(d.key_points?.length || 0) },
    {
      key: 'txt',
      label: hasSubtitles.value ? '字幕' : dmN ? '弹幕' : '文本',
      value: String(hasSubtitles.value ? cueN : dmN || cueN || 0),
    },
    { key: 'mm', label: '导图分支', value: String(mindN) },
  ]
})

/** 章节时间轴分段（宽度按时间占比） */
const chapterSegments = computed(() => {
  const chapters = data.value?.chapters || []
  if (!chapters.length) return []
  const starts = chapters.map((c) => parseTimestampToSeconds(c.start))
  let total = Number(data.value?.duration) || 0
  const lastStart = starts[starts.length - 1] || 0
  if (!(total > lastStart)) total = Math.max(lastStart + 45, 60)

  return chapters.map((c, i) => {
    const start = starts[i] || 0
    const end = i + 1 < starts.length ? starts[i + 1] : total
    const span = Math.max((end || total) - start, 1)
    return {
      index: i,
      title: c.title || `章节 ${i + 1}`,
      start: c.start,
      pct: Math.max(2.5, (span / total) * 100),
      color: TIMELINE_COLORS[i % TIMELINE_COLORS.length],
    }
  })
})
</script>

<template>
  <div class="sum-page">
    <header class="sum-top">
      <button type="button" class="btn btn-ghost btn-sm" @click="goHome">← 返回下载</button>
      <div class="sum-brand">速下 · AI 总结</div>
      <button type="button" class="btn btn-outline btn-sm" :disabled="!data" @click="copyAll">
        {{ copied ? '已复制' : '复制摘要' }}
      </button>
    </header>

    <div v-if="data" class="sum-body">
      <aside class="sum-hero">
        <div class="sum-player">
          <iframe
            v-if="embed && !playerLoading"
            :key="playerKey"
            class="sum-player__frame"
            :src="embed.embedUrl"
            :title="data.title || '视频播放'"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowfullscreen
            referrerpolicy="no-referrer-when-downgrade"
          />
          <div v-if="playerLoading" class="sum-player__overlay" aria-live="polite">
            <span class="sum-player__spinner" aria-hidden="true" />
            <p>正在加载播放器…</p>
          </div>
          <div v-else-if="playerError && !embed" class="sum-player__overlay is-error">
            <p>{{ playerError }}</p>
            <button type="button" class="btn btn-primary btn-sm" @click="refreshPlayer(seekSeconds)">
              重试
            </button>
          </div>
          <template v-else-if="!embed">
            <img
              v-if="thumbSrc"
              class="sum-player__poster"
              :src="thumbSrc"
              :alt="data.title || '封面'"
              referrerpolicy="no-referrer"
            />
            <div v-else class="sum-thumb--empty" />
            <div class="sum-player__fallback">
              <p>当前平台暂不支持页内播放</p>
              <a v-if="data.url" class="btn btn-primary btn-sm" :href="data.url" target="_blank" rel="noopener">
                打开原视频
              </a>
            </div>
          </template>
        </div>
        <p v-if="playerError && embed" class="summary-error sum-player-error">{{ playerError }}</p>
        <p v-if="embed && seekSeconds > 0" class="summary-hint">
          已跳转到 {{ formatChapterTime(seekSeconds) }}
        </p>
        <h1 class="sum-title">{{ data.title || '未命名视频' }}</h1>
        <div class="sum-badges">
          <span class="summary-badge">{{ data.mode === 'llm' ? 'LLM' : 'Mock' }}</span>
          <span class="summary-badge summary-badge--muted">
            {{ sourceLabel }}
          </span>
          <span v-if="embed" class="summary-badge summary-badge--muted">{{ embed.provider }}</span>
        </div>
        <p v-if="data.warning" class="summary-warn">{{ data.warning }}</p>

        <div class="sum-intro">
          <div class="sum-intro__top">
            <div class="sum-intro__label">视频简介</div>
            <p v-if="sideMetaLine" class="sum-intro__meta">{{ sideMetaLine }}</p>
          </div>
          <div class="sum-intro__body">
            <p class="sum-intro__text">
              {{ sideIntro || '暂无 AI 摘要' }}
            </p>
            <div v-if="sideKeyPoints.length" class="sum-intro__section">
              <div class="sum-intro__label">核心要点</div>
              <ol class="sum-intro__points">
                <li v-for="(p, i) in sideKeyPoints" :key="i">{{ p }}</li>
              </ol>
            </div>
          </div>
          <div class="sum-intro__foot">
            <a
              v-if="data.url"
              class="sum-link"
              :href="data.url"
              target="_blank"
              rel="noopener"
            >打开原视频</a>
            <button
              type="button"
              class="btn btn-ghost btn-sm"
              @click="tab = 'summary'"
            >
              查看完整摘要
            </button>
          </div>
        </div>
      </aside>

      <section class="sum-main">
        <nav class="sum-tabs" aria-label="总结视图">
          <button
            type="button"
            :class="{ active: tab === 'summary' }"
            @click="tab = 'summary'"
          >
            总结摘要
          </button>
          <button
            type="button"
            :class="{ active: tab === 'subtitles' }"
            @click="tab = 'subtitles'"
          >
            字幕文本
            <small v-if="hasSubtitles">({{ subtitleCount }})</small>
          </button>
          <button
            type="button"
            :class="{ active: tab === 'transcript' }"
            @click="tab = 'transcript'"
          >
            弹幕列表
            <small v-if="hasDanmaku">({{ danmakuList.length }})</small>
          </button>
          <button
            type="button"
            :class="{ active: tab === 'mindmap' }"
            @click="tab = 'mindmap'"
          >
            思维导图
          </button>
          <button type="button" :class="{ active: tab === 'ask' }" @click="tab = 'ask'">
            AI 问答
          </button>
        </nav>

        <div v-show="tab === 'summary'" class="sum-panel sum-panel--summary">
          <div class="sum-stats" aria-label="内容概览">
            <div v-for="s in overviewStats" :key="s.key" class="sum-stat">
              <span class="sum-stat__value">{{ s.value }}</span>
              <span class="sum-stat__label">{{ s.label }}</span>
            </div>
          </div>

          <section class="sum-block">
            <h2>整体摘要</h2>
            <p class="summary-text">{{ data.summary }}</p>
          </section>

          <section v-if="data.key_points?.length" class="sum-block">
            <h2>核心要点</h2>
            <ol class="sum-points-compact">
              <li v-for="(p, i) in data.key_points" :key="i">{{ p }}</li>
            </ol>
          </section>

          <section v-if="chapterSegments.length" class="sum-block">
            <h2>
              章节大纲
              <small v-if="embed">点击色块或时间可跳转</small>
            </h2>
            <div
              class="sum-timeline"
              role="img"
              :aria-label="`共 ${chapterSegments.length} 个章节的时间分布`"
            >
              <div class="sum-timeline__bar">
                <button
                  v-for="seg in chapterSegments"
                  :key="seg.index"
                  type="button"
                  class="sum-timeline__seg"
                  :class="{ 'is-clickable': Boolean(embed) }"
                  :style="{ width: seg.pct + '%', background: seg.color }"
                  :title="`${formatChapterTime(seg.start)} ${seg.title}`"
                  :disabled="!embed"
                  @click="embed && seekTo(seg.start)"
                >
                  <span class="sum-timeline__seg-label">{{ seg.index + 1 }}</span>
                </button>
              </div>
            </div>
            <ul class="summary-chapters">
              <li v-for="(c, i) in data.chapters" :key="i">
                <button
                  v-if="embed"
                  type="button"
                  class="chapter-time chapter-time--btn"
                  @click="seekTo(c.start)"
                >
                  {{ formatChapterTime(c.start) }}
                </button>
                <span v-else class="chapter-time">{{ formatChapterTime(c.start) }}</span>
                <span class="chapter-body">
                  <strong>
                    <span
                      class="chapter-dot"
                      :style="{ background: TIMELINE_COLORS[i % TIMELINE_COLORS.length] }"
                      aria-hidden="true"
                    />
                    {{ c.title }}
                  </strong>
                  <span v-if="c.summary">{{ c.summary }}</span>
                </span>
              </li>
            </ul>
          </section>

          <div class="export-row">
            <button
              type="button"
              class="btn btn-outline btn-sm"
              @click="exportMarkdown"
            >
              {{ exportedMd ? '已导出' : '导出 Markdown' }}
            </button>
          </div>
        </div>

        <!-- ============ 字幕文本：视频自带 CC 字幕（语言文字） ============ -->
        <div
          v-show="tab === 'subtitles'"
          data-panel="subtitles"
          class="sum-panel sum-panel--fill"
        >
          <!-- 有平台字幕时 -->
          <template v-if="hasSubtitles">
            <div class="sum-toolbar">
              <input
                v-model="transcriptFilter"
                type="search"
                class="sum-search"
                placeholder="搜索字幕内容或时间…"
                @input="onTranscriptSearchInput"
              />
              <div v-if="matchCount" class="match-nav">
                <button
                  type="button"
                  class="btn btn-ghost btn-sm match-nav__btn"
                  :disabled="matchCount <= 1"
                  @click="goPrevMatch"
                  aria-label="上一个匹配"
                >
                  ↑
                </button>
                <span class="match-nav__count">
                  {{ currentMatchIndex + 1 }}/{{ matchCount }}
                </span>
                <button
                  type="button"
                  class="btn btn-ghost btn-sm match-nav__btn"
                  :disabled="matchCount <= 1"
                  @click="goNextMatch"
                  aria-label="下一个匹配"
                >
                  ↓
                </button>
              </div>
              <span
                v-if="subtitleTrackLabel"
                class="summary-badge summary-badge--muted transcript-meta__badge"
              >
                {{ subtitleTrackLabel }}
              </span>
              <button
                v-if="showTranscriptExpandToggle"
                type="button"
                class="transcript-expand-btn"
                @click="toggleTranscriptExpand"
              >
                {{ transcriptExpanded ? '收起' : '展开全部' }}
              </button>
              <button
                type="button"
                class="btn btn-ghost btn-sm"
                @click="copyTranscript"
              >
                {{ transcriptCopied ? '已复制' : '复制字幕' }}
              </button>
              <div class="sum-export">
                <button
                  type="button"
                  class="btn btn-primary btn-sm"
                  title="导出字幕"
                  aria-haspopup="menu"
                  :aria-expanded="exportOpen"
                  @click="exportOpen = !exportOpen"
                >
                  导出
                </button>
                <div v-if="exportOpen" class="sum-export-menu" role="menu">
                  <button type="button" role="menuitem" @click="runCueExport('txt')">
                    TXT 纯文本
                  </button>
                  <button type="button" role="menuitem" @click="runCueExport('srt')">
                    SRT 字幕
                  </button>
                  <button type="button" role="menuitem" @click="runCueExport('vtt')">
                    VTT 字幕
                  </button>
                </div>
              </div>
              <span v-if="exportMsg" class="sum-export-msg">{{ exportMsg }}</span>
            </div>

            <div class="transcript-meta">
              <span class="summary-hint">
                共 {{ subtitleCount }} 条字幕 · 点击时间可跳转播放
              </span>
            </div>

            <ul
              v-if="filteredTranscript.length"
              class="transcript-list"
              :class="{ 'transcript-list--collapsed': showTranscriptExpandToggle && !transcriptExpanded && !transcriptFilter }"
            >
              <li
                v-for="(c, i) in displayTranscript"
                :key="i"
                :class="{ 'is-active': i === activeCueIndex }"
              >
                <button
                  v-if="embed"
                  type="button"
                  class="chapter-time chapter-time--btn"
                  @click="seekTo(c.start)"
                >
                  {{ formatChapterTime(c.start) }}
                </button>
                <span v-else class="chapter-time">{{ formatChapterTime(c.start) }}</span>
                <span class="transcript-text" v-html="highlightHtml(c.text, i)"></span>
              </li>
            </ul>
            <p v-else class="summary-hint">无匹配字幕</p>
            <p
              v-if="filteredTranscript.length && showTranscriptExpandToggle && !transcriptExpanded && !transcriptFilter"
              class="summary-hint transcript-fold-hint"
            >
              已展示前 {{ displayTranscript.length }} / {{ subtitleCount }} 条字幕，
              <button type="button" class="link-btn" @click="toggleTranscriptExpand">展开全部</button>
              以查看完整内容
            </p>
          </template>

          <!-- 无平台字幕（可能是弹幕源或无任何文本） -->
          <div v-else class="transcript-empty">
            <p class="summary-hint">
              {{
                isDanmaku || hasDanmaku
                  ? '该视频未提供平台字幕。总结已用弹幕完成——请到「弹幕列表」查看；也可回首页粘贴字幕后重试。'
                  : data.available_real_subtitles > 0
                    ? '平台有字幕轨，但本次未能成功拉取文本。可回首页换字幕语言后重试「AI 总结」。'
                    : data.available_danmaku > 0
                      ? '该视频未提供平台字幕。请查看「弹幕列表」，或回首页粘贴字幕。'
                      : '该视频没有平台字幕也没有可用弹幕。请回首页粘贴字幕后重试。'
              }}
            </p>
          </div>
        </div>

        <!-- ============ 弹幕列表：B 站等平台的实时评论 ============ -->
        <div
          v-show="tab === 'transcript'"
          data-panel="transcript"
          class="sum-panel sum-panel--fill"
        >
          <!-- 有弹幕时 -->
          <template v-if="hasDanmaku">
            <div class="sum-toolbar">
              <input
                v-model="transcriptFilter"
                type="search"
                class="sum-search"
                placeholder="搜索弹幕内容或时间…"
                @input="onTranscriptSearchInput"
              />
              <div v-if="matchCount && !useChapterView" class="match-nav">
                <button
                  type="button"
                  class="btn btn-ghost btn-sm match-nav__btn"
                  :disabled="matchCount <= 1"
                  @click="goPrevMatch"
                  aria-label="上一个匹配"
                >
                  ↑
                </button>
                <span class="match-nav__count">
                  {{ currentMatchIndex + 1 }}/{{ matchCount }}
                </span>
                <button
                  type="button"
                  class="btn btn-ghost btn-sm match-nav__btn"
                  :disabled="matchCount <= 1"
                  @click="goNextMatch"
                  aria-label="下一个匹配"
                >
                  ↓
                </button>
              </div>
              <!-- 弹幕源时：切换 AI 整理章节 / 原始弹幕 -->
              <button
                v-if="data.chapters?.length"
                type="button"
                class="btn btn-ghost btn-sm"
                @click="toggleTranscriptView"
              >
                {{ useChapterView ? '查看完整弹幕' : '查看 AI 整理' }}
              </button>
              <button
                type="button"
                class="btn btn-ghost btn-sm"
                @click="copyTranscript"
              >
                {{ transcriptCopied ? '已复制' : '复制弹幕' }}
              </button>
              <div class="sum-export">
                <button
                  type="button"
                  class="btn btn-primary btn-sm"
                  title="导出弹幕"
                  aria-haspopup="menu"
                  :aria-expanded="exportOpen"
                  @click="exportOpen = !exportOpen"
                >
                  导出
                </button>
                <div v-if="exportOpen" class="sum-export-menu" role="menu">
                  <button type="button" role="menuitem" @click="runCueExport('txt')">
                    TXT 纯文本
                  </button>
                  <button type="button" role="menuitem" @click="runCueExport('srt')">
                    SRT 字幕
                  </button>
                  <button type="button" role="menuitem" @click="runCueExport('vtt')">
                    VTT 字幕
                  </button>
                </div>
              </div>
              <span v-if="exportMsg" class="sum-export-msg">{{ exportMsg }}</span>
            </div>

            <!-- 弹幕源 + 有 AI 章节：默认显示 AI 整理 -->
            <template v-if="data.chapters?.length && useChapterView">
              <div class="transcript-meta">
                <span class="summary-badge summary-badge--muted">AI 整理章节</span>
                <span class="summary-hint">
                  共 {{ data.chapters.length }} 个章节 · 基于弹幕整理
                  · 点击时间可跳转播放
                </span>
              </div>
              <ul class="transcript-list">
                <li v-for="(c, i) in data.chapters" :key="i">
                  <button
                    v-if="embed"
                    type="button"
                    class="chapter-time chapter-time--btn"
                    @click="seekTo(c.start)"
                  >
                    {{ formatChapterTime(c.start) }}
                  </button>
                  <span v-else class="chapter-time">{{ formatChapterTime(c.start) }}</span>
                  <div class="transcript-chapter-body">
                    <strong v-if="c.title" class="transcript-chapter-title">{{ c.title }}</strong>
                    <span v-if="c.summary" class="transcript-chapter-summary">{{ c.summary }}</span>
                  </div>
                </li>
              </ul>
            </template>

            <!-- 原始弹幕列表 -->
            <template v-else>
              <div class="transcript-meta">
                <span class="summary-hint">
                  共 {{ danmakuList.length }} 条弹幕 · 点击时间可跳转播放
                </span>
              </div>
              <ul
                v-if="filteredDanmaku.length"
                class="transcript-list"
              >
                <li
                  v-for="(c, i) in filteredDanmaku"
                  :key="i"
                >
                  <button
                    v-if="embed"
                    type="button"
                    class="chapter-time chapter-time--btn"
                    @click="seekTo(c.start)"
                  >
                    {{ formatChapterTime(c.start) }}
                  </button>
                  <span v-else class="chapter-time">{{ formatChapterTime(c.start) }}</span>
                  <span class="transcript-text" v-html="highlightHtml(c.text, i)"></span>
                </li>
              </ul>
              <p v-else class="summary-hint">无匹配弹幕</p>
            </template>
          </template>

          <!-- 无弹幕数据时 -->
          <div v-else class="transcript-empty">
            <p class="summary-hint">
              {{
                hasSubtitles
                  ? '该视频以平台字幕为主，没有弹幕数据。请在「字幕文本」中查看视频内容。'
                  : '该视频没有可用弹幕。平台字幕请在「字幕文本」标签查看（若拉取成功）。'
              }}
            </p>
          </div>
        </div>

        <div
          v-show="tab === 'mindmap'"
          data-panel="mindmap"
          class="sum-panel sum-panel--fill sum-panel--mindmap"
        >
          <div v-if="data.mind_map" class="mindmap-shell">
            <MindMapCanvas :root="data.mind_map" />
          </div>
          <p v-else class="summary-hint">暂无导图数据</p>
        </div>

        <div v-show="tab === 'ask'" class="sum-panel sum-ask">
          <p class="summary-hint">基于本视频字幕/元数据提问（无 API Key 时为演示回答）</p>
          <div class="ask-presets">
            <button
              v-for="p in presets"
              :key="p"
              type="button"
              class="ask-chip"
              @click="question = p"
            >
              {{ p }}
            </button>
          </div>
          <div class="ask-thread">
            <div
              v-for="(m, i) in chat"
              :key="i"
              class="ask-bubble"
              :class="[
                m.role === 'user' ? 'is-user' : 'is-bot',
                { 'is-streaming': m.streaming },
              ]"
            >
              <p>
                {{ m.text }}
                <span v-if="m.streaming && !m.text" class="ask-typing">{{ askStatus || '…' }}</span>
                <span v-else-if="m.streaming" class="ask-cursor" aria-hidden="true">▍</span>
              </p>
              <span v-if="m.warning" class="summary-warn">{{ m.warning }}</span>
            </div>
            <p v-if="!chat.length" class="summary-hint">还没有对话，试着问一个问题吧</p>
          </div>
          <form class="ask-form" @submit.prevent="onAsk">
            <input
              v-model="question"
              type="text"
              maxlength="500"
              placeholder="针对视频内容提问…"
              :disabled="asking"
            />
            <button type="submit" class="btn btn-primary" :disabled="asking || !question.trim()">
              {{ asking ? (askStatus || '生成中…') : '发送' }}
            </button>
          </form>
          <p v-if="askError" class="summary-error">{{ askError }}</p>
        </div>
      </section>
    </div>
  </div>
</template>

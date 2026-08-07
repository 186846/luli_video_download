<script setup>
/**
 * 速下 SpeedyDL 单页应用。
 * 阶段 3 主路径：粘贴 URL → 解析 → 选清晰度 → 服务端下载 → 取文件。
 * UI 对齐参考站：Hero 胶囊输入 + 结果左右栏 + VIP 转化。
 */
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  fileUrl,
  getTask,
  parseVideo,
  resolveDirect,
  startDownload,
  startSummarize,
  streamSummaryStatus,
  thumbnailUrl,
} from '../api/client'
import { useHistory } from '../composables/useHistory'
import { formatBytes, useVip, VIP_TOKEN } from '../composables/useVip'
import { saveSummarySession } from '../composables/useSummarySession'

const router = useRouter()
const { isVip, setVip, toggleVipPrompt } = useVip()
const { history, addHistory, removeHistory, clearHistory } = useHistory()

const urlInput = ref('')
const parsing = ref(false)
const statusMsg = ref('')
const statusType = ref('') // '' | 'ok' | 'error'
const video = ref(null) // /api/parse 返回的 data
const selectedFormat = ref(null)
// select 用字符串 key 绑定，避免对象引用不相等导致选不中
const selectedSubKey = ref('')
const showVipModal = ref(false)
const progressVisible = ref(false)
const progress = ref(0)
const progressText = ref('')
const downloading = ref(false)
const directBusy = ref(false)
const directInfo = ref('')
const summarizing = ref(false)
const summaryError = ref('')
const summaryProgress = ref(0)
const summaryProgressText = ref('')
/** 用户粘贴的 SRT/VTT/纯文本；无平台 CC 时生效 */
const userSubtitleText = ref('')
const resultEl = ref(null)
const urlFieldEl = ref(null)

/** 下载进度轮询定时器 */
let pollTimer = null
/** 总结 SSE AbortController */
let summaryAbort = null

/** 封面走后端代理（Bilibili 等 CDN 会拦 localhost Referer） */
const thumbSrc = computed(() => {
  if (!video.value?.thumbnail) return ''
  return thumbnailUrl(
    video.value.thumbnail,
    video.value.webpage_url || video.value.original_url,
  )
})

/** 结果区是否展示「开通 VIP 解锁高清」提示条 */
const showVipGate = computed(() => {
  if (!video.value || isVip.value) return false
  return (video.value.formats || []).some((f) => f.vip_required)
})

const subtitles = computed(() => video.value?.subtitles || [])

/** 平台真实字幕轨（排除弹幕） */
const platformSubtitles = computed(() =>
  subtitles.value.filter((s) => {
    const lang = String(s.lang || '').toLowerCase()
    return lang !== 'danmaku' && lang !== 'dm' && !s.is_danmaku
  }),
)

/** 无平台 CC 时展示用户粘贴选项 */
const needSubtitleFallback = computed(() => platformSubtitles.value.length === 0)

/** 字幕选项稳定 key：自动/人工 + 语言码 */
function subKey(sub) {
  return `${sub.automatic ? 'a' : 'm'}:${sub.lang}`
}

const selectedSub = computed(() =>
  subtitles.value.find((s) => subKey(s) === selectedSubKey.value) || null,
)

/** 当前清晰度是否可走直链模式（合并音视频格式不行） */
const canDirectSelected = computed(() => {
  const fmt = selectedFormat.value
  if (!fmt) return false
  return fmt.can_direct !== false && !fmt.needs_merge && !String(fmt.format_id).includes('+')
})

function setStatus(msg, type = '') {
  statusMsg.value = msg
  statusType.value = type
}

function openVipModal() {
  showVipModal.value = true
}

function closeVipModal() {
  showVipModal.value = false
}

function confirmVip() {
  setVip(true)
  closeVipModal()
  setStatus('演示会员已开通，可选择 1080p+ 清晰度', 'ok')
}

function onHeaderVipClick() {
  if (toggleVipPrompt()) openVipModal()
}

/** 清晰度卡片主标题，贴近参考站「1080p 最佳 (视频+音频合并)」 */
function formatTitle(fmt) {
  if (!fmt) return ''
  if (fmt.needs_merge && fmt.height) {
    return `${fmt.height}p 最佳 (视频+音频合并)`
  }
  if (fmt.height && fmt.has_video && fmt.has_audio) {
    return `${fmt.height}p 最佳`
  }
  if (fmt.height && fmt.has_video) {
    return `${fmt.height}p`
  }
  if (!fmt.has_video && fmt.has_audio) {
    return '仅音频'
  }
  return fmt.label || fmt.format_id
}

/** 副标题：有体积显示体积，否则显示扩展名/音轨信息 */
function formatSub(fmt) {
  if (!fmt) return ''
  const size = formatBytes(fmt.filesize)
  if (size) return size
  const parts = []
  if (fmt.ext) parts.push(String(fmt.ext).toUpperCase())
  if (fmt.has_audio && fmt.has_video) parts.push('含音频')
  else if (fmt.has_audio) parts.push('音频')
  else if (fmt.has_video) parts.push('仅视频')
  if (fmt.vip_required) parts.push('VIP')
  return parts.join(' · ') || '点击选择'
}

function platformBadge(extractor) {
  const e = String(extractor || '').toLowerCase()
  if (e.includes('bili')) return 'BiliBili'
  if (e.includes('youtube')) return 'YouTube'
  if (e.includes('tiktok') || e.includes('douyin')) return '短视频'
  return extractor || '未知平台'
}

function formatViews(n) {
  if (n == null || n === '') return ''
  const num = Number(n)
  if (!Number.isFinite(num) || num < 0) return ''
  return num.toLocaleString('en-US')
}

function descriptionPreview(text) {
  if (!text) return ''
  const t = String(text).replace(/\s+/g, ' ').trim()
  return t.length > 120 ? `${t.slice(0, 120)}…` : t
}

/** 免费用户点选 VIP 清晰度时视为锁定 */
function isLocked(fmt) {
  return Boolean(fmt.vip_required && !isVip.value)
}

function selectFormat(fmt) {
  if (isLocked(fmt)) {
    openVipModal()
    return
  }
  selectedFormat.value = fmt
  directInfo.value = ''
}

/** 默认选第一个未锁定清晰度 */
function pickDefaultFormat(formats) {
  const first = formats.find((f) => !isLocked(f))
  selectedFormat.value = first || null
}

/** 字幕优先：真实字幕 > 弹幕；简体中文 > 其它中文 > 人工轨 > 第一条 */
function pickDefaultSub(list) {
  if (!list?.length) {
    selectedSubKey.value = ''
    return
  }
  const rank = (s) => {
    const lang = String(s.lang || '').toLowerCase().replace('_', '-')
    let zh = 2
    if (['zh-hans', 'zh-cn', 'zh'].includes(lang)) zh = 0
    else if (lang.startsWith('zh') || lang.startsWith('ai-zh')) zh = 1
    // 弹幕轨排在所有真实字幕之后：避免默认拉到弹幕而错过真实字幕
    const dm = s.is_danmaku ? 1 : 0
    return [dm, s.automatic ? 1 : 0, zh, lang]
  }
  const sorted = [...list].sort((a, b) => {
    const ra = rank(a)
    const rb = rank(b)
    for (let i = 0; i < ra.length; i++) {
      if (ra[i] < rb[i]) return -1
      if (ra[i] > rb[i]) return 1
    }
    return 0
  })
  selectedSubKey.value = subKey(sorted[0])
}

/** 执行解析并刷新结果区；成功后写入本地历史 */
async function runParse(url) {
  parsing.value = true
  setStatus('正在解析，请稍候…')
  directInfo.value = ''
  summaryError.value = ''
  try {
    const json = await parseVideo(url)
    video.value = json.data
    progressVisible.value = false
    progress.value = 0
    pickDefaultFormat(json.data.formats || [])
    pickDefaultSub(json.data.subtitles || [])
    addHistory({
      url: json.data.original_url || json.data.webpage_url || url,
      title: json.data.title,
      extractor: json.data.extractor,
      thumbnail: json.data.thumbnail,
    })
    setStatus('解析成功，请选择清晰度后下载', 'ok')
    await nextTick()
    resultEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } catch (err) {
    setStatus(err.message || String(err), 'error')
  } finally {
    parsing.value = false
  }
}

async function onParse(e) {
  e.preventDefault()
  const url = urlInput.value.trim()
  if (!url) return
  await runParse(url)
}

function reuseHistory(item) {
  urlInput.value = item.url
  runParse(item.url)
}

function resetResult() {
  video.value = null
  selectedFormat.value = null
  selectedSubKey.value = ''
  progressVisible.value = false
  progress.value = 0
  progressText.value = ''
  downloading.value = false
  directInfo.value = ''
  summaryError.value = ''
  userSubtitleText.value = ''
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  setStatus('')
  nextTick(() => urlFieldEl.value?.focus())
}

async function onUserSubtitleFile(ev) {
  const file = ev.target?.files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    userSubtitleText.value = text
    setStatus(`已载入字幕文件：${file.name}`, 'ok')
  } catch (err) {
    setStatus(err.message || '读取字幕文件失败', 'error')
  } finally {
    ev.target.value = ''
  }
}

function historyThumb(item) {
  if (!item.thumbnail) return ''
  return thumbnailUrl(item.thumbnail, item.url)
}

function formatTime(ts) {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ''
  }
}

/** 模式①：创建服务端任务并开始轮询进度 */
async function onDownload() {
  if (!video.value || !selectedFormat.value) return
  const fmt = selectedFormat.value
  if (isLocked(fmt)) {
    openVipModal()
    return
  }

  downloading.value = true
  progressVisible.value = true
  progress.value = 0
  progressText.value = '任务已创建…'

  try {
    const json = await startDownload({
      url: video.value.original_url || video.value.webpage_url,
      format_id: fmt.format_id,
      height: fmt.height || null,
      vip_token: isVip.value ? VIP_TOKEN : null,
    })
    pollTask(json.task.id)
  } catch (err) {
    progressText.value = err.message || String(err)
    downloading.value = false
  }
}

/** 模式②：复制单流直链（合并清晰度不可用） */
async function onDirect() {
  if (!video.value || !selectedFormat.value) return
  const fmt = selectedFormat.value
  if (isLocked(fmt)) {
    openVipModal()
    return
  }
  if (!canDirectSelected.value) {
    directInfo.value = '该清晰度需合并音轨，无法提供直链，请使用「下载到本地」'
    return
  }

  directBusy.value = true
  directInfo.value = '正在解析直链…'
  try {
    const json = await resolveDirect({
      url: video.value.original_url || video.value.webpage_url,
      format_id: fmt.format_id,
      height: fmt.height || null,
      vip_token: isVip.value ? VIP_TOKEN : null,
    })
    const link = json.data.url
    try {
      await navigator.clipboard.writeText(link)
      directInfo.value = `直链已复制。${json.data.note || ''}`
    } catch {
      directInfo.value = `直链：${link}（${json.data.note || '请手动复制'}）`
    }
  } catch (err) {
    directInfo.value = err.message || String(err)
  } finally {
    directBusy.value = false
  }
}

/** AI 总结：创建后台任务 + SSE 进度，完成后跳转详情页 */
async function onSummarize() {
  if (!video.value) return
  if (!isVip.value) {
    openVipModal()
    return
  }
  summarizing.value = true
  summaryError.value = ''
  summaryProgress.value = 0
  summaryProgressText.value = '正在创建总结任务…'
  if (summaryAbort) {
    summaryAbort.abort()
    summaryAbort = null
  }

  const sub = selectedSub.value
  const url = video.value.original_url || video.value.webpage_url

  try {
    const { task_id } = await startSummarize({
      url,
      lang: sub?.lang || null,
      automatic: sub ? Boolean(sub.automatic) : null,
      vip_token: VIP_TOKEN,
      title: video.value.title || null,
      subtitle_text: userSubtitleText.value.trim() || null,
    })
    setStatus('AI 总结任务已创建，正在处理…', 'ok')
    summaryAbort = new AbortController()

    await streamSummaryStatus(task_id, {
      signal: summaryAbort.signal,
      onProgress(task) {
        summaryProgress.value = Math.min(99, Number(task.progress) || 0)
        const msg = task.message || '处理中'
        summaryProgressText.value = `${msg}（${Math.round(summaryProgress.value)}%）`
        setStatus(`总结中：${msg}（${Math.round(summaryProgress.value)}%）`, 'ok')
      },
      onDone(task) {
        summarizing.value = false
        summaryProgress.value = 100
        summaryProgressText.value = '总结完成'
        summaryAbort = null
        saveSummarySession({
          ...task.data,
          thumbnail: task.data.thumbnail || video.value.thumbnail,
          extractor: video.value.extractor || null,
          description: task.data.description || video.value.description || null,
          uploader: task.data.uploader || video.value.uploader || null,
          video_id: video.value.id || null,
          ask: {
            url,
            lang: sub?.lang || null,
            automatic: sub ? Boolean(sub.automatic) : null,
            title: video.value.title || null,
            vip_token: VIP_TOKEN,
          },
        })
        setStatus(
          task.data?.mode === 'mock' ? '演示总结完成' : 'AI 总结完成',
          'ok',
        )
        router.push({ name: 'summary' })
      },
      onError(errMsg) {
        summarizing.value = false
        summaryAbort = null
        summaryError.value = errMsg || '总结失败'
        summaryProgressText.value = summaryError.value
        setStatus(summaryError.value, 'error')
      },
    })
  } catch (err) {
    if (err?.name === 'AbortError') return
    summarizing.value = false
    summaryAbort = null
    summaryError.value = err.message || String(err)
    summaryProgressText.value = summaryError.value
    setStatus(summaryError.value, 'error')
  }
}

/** 轮询 /api/tasks，完成后跳转 /api/files 触发浏览器保存 */
function pollTask(taskId) {
  if (pollTimer) clearInterval(pollTimer)

  const tick = async () => {
    try {
      const json = await getTask(taskId)
      const task = json.task
      progress.value = task.progress || 0
      if (task.status === 'running' || task.status === 'pending') {
        const parts = [`进度 ${Math.round(task.progress || 0)}%`]
        if (task.speed) parts.push(task.speed)
        if (task.eta) parts.push(`剩余 ${task.eta}`)
        progressText.value = parts.join(' · ')
        return
      }
      clearInterval(pollTimer)
      pollTimer = null
      if (task.status === 'error') {
        progressText.value = task.error || '下载失败'
        downloading.value = false
        return
      }
      if (task.status === 'done' && task.ready) {
        progress.value = 100
        progressText.value = '完成，正在触发浏览器下载…'
        window.location.href = fileUrl(taskId)
        downloading.value = false
        setTimeout(() => {
          progressText.value =
            '若未自动下载，请再点一次「下载到本地」或检查浏览器拦截。'
        }, 1200)
      }
    } catch (err) {
      clearInterval(pollTimer)
      pollTimer = null
      progressText.value = err.message || String(err)
      downloading.value = false
    }
  }

  tick()
  pollTimer = setInterval(tick, 800)
}

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (summaryAbort) {
    summaryAbort.abort()
    summaryAbort = null
  }
})
</script>

<template>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="/" aria-label="速下 SpeedyDL" @click.prevent="$router.push('/')">
        <span class="brand-mark" aria-hidden="true" />
        <span class="brand-text">速下 <small>SpeedyDL</small></span>
      </a>
      <nav class="nav">
        <a href="#download">下载</a>
        <a href="#history">历史</a>
        <a href="#pricing">定价</a>
        <a href="#about">关于</a>
      </nav>
      <button
        type="button"
        class="btn btn-ghost btn-sm"
        :class="{ 'is-vip': isVip }"
        @click="onHeaderVipClick"
      >
        {{ isVip ? '演示会员已开通' : '演示会员' }}
      </button>
    </div>
  </header>

  <main>
    <section class="hero" id="download">
      <h1>万能视频下载，<span class="accent">一键保存</span></h1>
      <p class="hero-sub">粘贴链接 · 选清晰度 · 保存到本地。手机也能用。仅供个人学习。</p>
      <form class="url-bar" autocomplete="off" @submit="onParse">
        <div class="url-field">
          <svg class="url-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path
              fill="currentColor"
              d="M3.9 12a5 5 0 0 1 5-5h4v2h-4a3 3 0 0 0 0 6h4v2h-4a5 5 0 0 1-5-5m7-1h6v2h-6zm4.1-4h-4v2h4a5 5 0 0 1 0 10h-4v2h4a7 7 0 0 0 0-14"
            />
          </svg>
          <input
            ref="urlFieldEl"
            v-model="urlInput"
            type="url"
            name="url"
            placeholder="粘贴视频链接，例如 https://www.bilibili.com/video/..."
            required
            enterkeyhint="go"
          />
        </div>
        <button type="submit" class="btn btn-primary" :disabled="parsing">
          {{ parsing ? '解析中…' : '解析' }}
        </button>
      </form>
      <p
        v-if="statusMsg"
        class="hero-hint"
        :class="{ 'is-error': statusType === 'error', 'is-ok': statusType === 'ok' }"
      >
        {{ statusMsg }}
      </p>
    </section>

    <section v-if="video" id="video-result" ref="resultEl" class="result">
      <div class="result-sheet">
        <!-- 顶部：封面 + 标题/元信息 -->
        <div class="result-head">
          <div class="result-thumb">
            <img
              v-if="thumbSrc"
              :src="thumbSrc"
              :alt="video.title || '封面'"
              referrerpolicy="no-referrer"
            />
            <div v-else class="result-thumb--empty" aria-hidden="true" />
            <span v-if="video.duration_string" class="result-duration">{{ video.duration_string }}</span>
          </div>
          <div class="result-info">
            <h2 class="result-title">{{ video.title || '未命名视频' }}</h2>
            <div class="result-meta">
              <span v-if="video.uploader" class="meta-chip meta-uploader">
                <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                  <path
                    fill="currentColor"
                    d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4m0 2c-4.42 0-8 1.79-8 4v1h16v-1c0-2.21-3.58-4-8-4"
                  />
                </svg>
                {{ video.uploader }}
              </span>
              <span v-if="video.extractor" class="meta-badge">{{ platformBadge(video.extractor) }}</span>
              <span v-if="formatViews(video.view_count)" class="meta-chip meta-views">
                <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                  <path
                    fill="currentColor"
                    d="M12 5c-7 0-10 7-10 7s3 7 10 7 10-7 10-7-3-7-10-7m0 12a5 5 0 1 1 5-5 5 5 0 0 1-5 5m0-8a3 3 0 1 0 3 3 3 3 0 0 0-3-3"
                  />
                </svg>
                {{ formatViews(video.view_count) }}
              </span>
            </div>
            <p v-if="descriptionPreview(video.description)" class="result-desc">
              {{ descriptionPreview(video.description) }}
            </p>
            <p v-else class="result-desc result-desc--muted">解析成功，请选择清晰度后下载到本地。</p>
          </div>
        </div>

        <!-- 清晰度网格 -->
        <div class="formats-block">
          <h3 class="formats-heading">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path
                fill="currentColor"
                d="M3 17v2h6v-2zm0-6v2h12v-2zm0-6v2h18V5zm10 12v2h8v-2zm4-6v2h4v-2z"
              />
            </svg>
            选择清晰度和格式
          </h3>
          <div class="format-grid" role="listbox" aria-label="清晰度">
            <button
              v-for="fmt in video.formats"
              :key="fmt.format_id + (fmt.label || '')"
              type="button"
              class="format-card"
              :class="{
                'is-active':
                  selectedFormat?.format_id === fmt.format_id &&
                  selectedFormat?.label === fmt.label,
                'is-locked': isLocked(fmt),
              }"
              role="option"
              :aria-selected="
                selectedFormat?.format_id === fmt.format_id &&
                selectedFormat?.label === fmt.label
              "
              @click="selectFormat(fmt)"
            >
              <span class="format-card__icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="18" height="18">
                  <path
                    fill="currentColor"
                    d="M18 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2m-8 13-1.5-2L6 18V6h12v12l-4-5.5z"
                  />
                </svg>
              </span>
              <span class="format-card__text">
                <span class="format-card__title">{{ formatTitle(fmt) }}</span>
                <span class="format-card__sub">{{ formatSub(fmt) }}</span>
              </span>
            </button>
          </div>
        </div>

        <div v-if="showVipGate" class="vip-gate">
          <div class="vip-gate-inner">
            <p>1080p 及以上为会员清晰度</p>
            <button type="button" class="btn btn-primary" @click="openVipModal">
              开通演示会员解锁
            </button>
          </div>
        </div>

        <div v-if="needSubtitleFallback" class="user-sub-box">
          <label class="sub-label" for="user-sub-text">无平台字幕时的兜底</label>
          <p class="summary-hint">
            可粘贴或上传 SRT / VTT / 纯文本；无字幕时将尝试弹幕或元数据总结
          </p>
          <textarea
            id="user-sub-text"
            v-model="userSubtitleText"
            class="user-sub-textarea"
            rows="4"
            placeholder="粘贴字幕内容，例如：&#10;00:01:00 --> 00:01:05&#10;这是一句旁白"
          />
          <div class="user-sub-actions">
            <label class="user-sub-file btn btn-outline btn-sm">
              上传字幕文件
              <input
                type="file"
                accept=".srt,.vtt,.txt,text/plain,text/vtt"
                hidden
                @change="onUserSubtitleFile"
              />
            </label>
          </div>
        </div>

        <div class="summary-row">
          <button
            type="button"
            class="btn btn-outline"
            :disabled="summarizing"
            @click="onSummarize"
          >
            {{ summarizing ? '总结中…' : isVip ? 'AI 总结' : 'AI 总结（需演示会员）' }}
          </button>
          <span class="summary-hint">将打开总结详情页：摘要 · 字幕 · 思维导图 · AI 问答</span>
        </div>
        <div v-if="summarizing || summaryError" class="progress-wrap summary-progress">
          <div class="progress-bar">
            <div
              class="progress-fill"
              :class="{ 'is-error': Boolean(summaryError) && !summarizing }"
              :style="{ width: (summaryError && !summarizing ? 100 : summaryProgress) + '%' }"
            />
          </div>
          <p class="progress-text">
            {{ summaryError && !summarizing ? summaryError : summaryProgressText || '准备中…' }}
          </p>
        </div>
        <p v-else-if="summaryError" class="summary-error">{{ summaryError }}</p>

        <div v-if="progressVisible" class="progress-wrap">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: progress + '%' }" />
          </div>
          <p class="progress-text">{{ progressText }}</p>
        </div>
        <p v-if="directInfo" class="direct-hint">{{ directInfo }}</p>

        <!-- 底部操作：主按钮 + 已选提示 -->
        <div class="result-footer">
          <button
            type="button"
            class="btn-download"
            :disabled="!selectedFormat || downloading"
            @click="onDownload"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path
                fill="currentColor"
                d="M5 20h14v-2H5v2zm7-18v10.17l3.59-3.58L17 10l-5 5-5-5 1.41-1.41L11 12.17V2h2z"
              />
            </svg>
            {{ downloading ? '下载中…' : '立即下载' }}
          </button>
          <p class="result-selected">
            <template v-if="selectedFormat">
              已选择: {{ formatTitle(selectedFormat) }}
            </template>
            <template v-else>请选择清晰度</template>
          </p>
          <div class="result-secondary">
            <button
              type="button"
              class="btn btn-outline btn-sm"
              :disabled="!selectedFormat || directBusy || downloading"
              @click="onDirect"
            >
              {{ directBusy ? '解析直链…' : '复制直链' }}
            </button>
            <button type="button" class="btn btn-ghost btn-sm" @click="resetResult">
              换个链接
            </button>
          </div>
        </div>
      </div>
    </section>

    <section v-show="!video" class="section platforms" id="platforms-section">
      <h2 class="section-title">支持主流平台</h2>
      <p class="section-sub">站在 yt-dlp 肩膀上，覆盖海量站点（以公开可访问内容为准）</p>
      <div class="card-grid">
        <article class="card platform-card">
          <div class="card-visual card-visual--bili" aria-hidden="true">
            <span class="card-visual__glow" />
            <span class="card-visual__ring" />
            <svg class="card-icon" viewBox="0 0 64 64" fill="none">
              <rect x="8" y="18" width="48" height="32" rx="8" fill="#fff" fill-opacity="0.95" />
              <path d="M20 14l6 6M44 14l-6 6" stroke="#fff" stroke-width="3.5" stroke-linecap="round" />
              <circle cx="26" cy="34" r="4" fill="#00A1D6" />
              <circle cx="38" cy="34" r="4" fill="#00A1D6" />
              <path d="M24 42h16" stroke="#00A1D6" stroke-width="3" stroke-linecap="round" />
            </svg>
          </div>
          <h3>哔哩哔哩</h3>
          <p class="card-tags">学习 · UP主 · 公开稿件</p>
        </article>
        <article class="card platform-card">
          <div class="card-visual card-visual--yt" aria-hidden="true">
            <span class="card-visual__glow" />
            <span class="card-visual__ring" />
            <svg class="card-icon" viewBox="0 0 64 64" fill="none">
              <rect x="6" y="16" width="52" height="32" rx="12" fill="#fff" fill-opacity="0.96" />
              <path d="M28 26v12l12-6-12-6z" fill="#FF0000" />
            </svg>
          </div>
          <h3>YouTube</h3>
          <p class="card-tags">国际 · 高清 · 公开视频</p>
        </article>
        <article class="card platform-card">
          <div class="card-visual card-visual--dy" aria-hidden="true">
            <span class="card-visual__glow" />
            <span class="card-visual__ring" />
            <svg class="card-icon" viewBox="0 0 64 64" fill="none">
              <rect x="20" y="8" width="24" height="48" rx="6" fill="#fff" fill-opacity="0.95" />
              <rect x="24" y="14" width="16" height="28" rx="2" fill="#111" />
              <circle cx="32" cy="48" r="2.5" fill="#111" />
              <path
                d="M34 22c2 0 4-1.5 4-4M34 22v10a4 4 0 11-2-3.5"
                stroke="#25F4EE"
                stroke-width="2.2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                d="M34 22c2 0 4-1.5 4-4M34 22v10a4 4 0 11-2-3.5"
                stroke="#FE2C55"
                stroke-width="2.2"
                stroke-linecap="round"
                stroke-linejoin="round"
                transform="translate(1.2 0.8)"
                opacity="0.85"
              />
            </svg>
          </div>
          <h3>短视频</h3>
          <p class="card-tags">抖音 / TikTok · 无水印尝试</p>
        </article>
        <article class="card platform-card">
          <div class="card-visual card-visual--more" aria-hidden="true">
            <span class="card-visual__glow" />
            <span class="card-visual__ring" />
            <svg class="card-icon card-icon--wide" viewBox="0 0 72 64" fill="none">
              <circle cx="36" cy="32" r="18" stroke="#fff" stroke-opacity="0.35" stroke-width="2" />
              <circle cx="36" cy="32" r="8" fill="#fff" fill-opacity="0.95" />
              <circle cx="18" cy="18" r="4" fill="#fff" fill-opacity="0.9" />
              <circle cx="54" cy="16" r="3.5" fill="#fff" fill-opacity="0.85" />
              <circle cx="56" cy="42" r="4.5" fill="#fff" fill-opacity="0.9" />
              <circle cx="16" cy="44" r="3" fill="#fff" fill-opacity="0.8" />
              <path
                d="M22 20l10 8M50 18l-10 10M52 40l-10-6M20 42l12-6"
                stroke="#fff"
                stroke-opacity="0.55"
                stroke-width="1.6"
              />
              <text
                x="36"
                y="36"
                text-anchor="middle"
                fill="#1777FF"
                font-size="9"
                font-weight="800"
                font-family="Sora, sans-serif"
              >1k+</text>
            </svg>
          </div>
          <h3>更多站点</h3>
          <p class="card-tags">yt-dlp · 持续更新</p>
        </article>
      </div>
    </section>

    <section class="section history" id="history">
      <div class="section-head">
        <div>
          <h2 class="section-title">最近解析</h2>
          <p class="section-sub">保存在本机浏览器，最多 20 条</p>
        </div>
        <button
          v-if="history.length"
          type="button"
          class="btn btn-outline btn-sm"
          @click="clearHistory"
        >
          清空
        </button>
      </div>
      <div v-if="!history.length" class="history-empty">暂无记录，解析视频后会出现在这里</div>
      <ul v-else class="history-list">
        <li v-for="item in history" :key="item.url + item.at" class="history-item">
          <button type="button" class="history-main" @click="reuseHistory(item)">
            <img
              v-if="historyThumb(item)"
              class="history-thumb"
              :src="historyThumb(item)"
              alt=""
              referrerpolicy="no-referrer"
            />
            <span v-else class="history-thumb history-thumb--empty" />
            <span class="history-meta">
              <span class="history-title">{{ item.title }}</span>
              <span class="history-sub">{{ item.extractor || '未知平台' }} · {{ formatTime(item.at) }}</span>
            </span>
          </button>
          <button
            type="button"
            class="btn btn-ghost btn-sm history-del"
            aria-label="删除"
            @click="removeHistory(item.url)"
          >
            删除
          </button>
        </li>
      </ul>
    </section>

    <section class="section pricing" id="pricing">
      <h2 class="section-title">简单定价</h2>
      <p class="section-sub">学习演示 · 不接真实支付 · 本地一键解锁体验会员权益</p>
      <div class="pricing-grid">
        <article class="price-card">
          <h3>免费</h3>
          <p class="price"><span>¥0</span></p>
          <ul>
            <li>解析公开视频</li>
            <li>最高 720p</li>
            <li>单视频下载 / 直链</li>
          </ul>
          <button type="button" class="btn btn-outline" disabled>当前方案</button>
        </article>
        <article class="price-card price-card--vip">
          <div class="price-badge">推荐</div>
          <h3>演示会员</h3>
          <p class="price"><span class="old">¥99</span> <span class="now">¥0 演示</span></p>
          <ul>
            <li>1080p / 更高清晰度</li>
            <li>批量下载（占位）</li>
            <li>AI 能力优先体验</li>
          </ul>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="isVip"
            @click="openVipModal"
          >
            {{ isVip ? '已开通演示会员' : '立即开通（演示）' }}
          </button>
        </article>
      </div>
    </section>

    <section class="section about" id="about">
      <h2 class="section-title">关于与声明</h2>
      <div class="about-box">
        <p>
          <strong>速下 SpeedyDL</strong> 是学习项目：后端基于开源
          <a href="https://github.com/yt-dlp/yt-dlp" target="_blank" rel="noopener">yt-dlp</a>，不修改其上游源码。前端为 Vue 3 + Vite。
        </p>
        <p>
          请尊重版权与各平台服务条款。勿下载未授权内容，勿用于商业传播。账号封禁等风险请自行评估，建议仅用公开、可合法保存的素材练习。
        </p>
      </div>
    </section>
  </main>

  <footer class="site-footer">
    <p>© SpeedyDL · 仅供个人学习 · 请尊重版权</p>
  </footer>

  <Teleport to="body">
    <div
      v-if="showVipModal"
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="vip-modal-title"
      @click.self="closeVipModal"
    >
      <div class="modal-card">
        <h3 id="vip-modal-title">开通演示会员</h3>
        <p>
          这是<strong>学习演示</strong>，不会产生真实扣款。开通后本地记住会员状态，可解锁 1080p+ 清晰度。
        </p>
        <div class="modal-actions">
          <button type="button" class="btn btn-outline" @click="closeVipModal">取消</button>
          <button type="button" class="btn btn-primary" @click="confirmVip">确认开通</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
/**
 * 首页：组装 Header / Hero / 结果 / 平台 / 定价 / 历史等区块。
 * 业务状态留在本页；展示拆到 components/。
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
} from '../api'
import { useHistory } from '../composables/useHistory'
import { useVip, VIP_TOKEN } from '../composables/useVip'
import { saveSummarySession } from '../composables/useSummarySession'
import AppHeader from '../components/AppHeader.vue'
import AppFooter from '../components/AppFooter.vue'
import HeroSection from '../components/HeroSection.vue'
import VideoResult from '../components/VideoResult.vue'
import PlatformSection from '../components/PlatformSection.vue'
import PricingSection from '../components/PricingSection.vue'
import AboutSection from '../components/AboutSection.vue'
import FaqSection from '../components/FaqSection.vue'
import HistoryPanel from '../components/HistoryPanel.vue'
import AuthModal from '../components/AuthModal.vue'

const router = useRouter()
const { isVip, setVip, toggleVipPrompt } = useVip()
const { history, addHistory, removeHistory, clearHistory } = useHistory()

const urlInput = ref('')
const parsing = ref(false)
const statusMsg = ref('')
const statusType = ref('')
const video = ref(null)
const selectedFormat = ref(null)
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
const userSubtitleText = ref('')
const resultEl = ref(null)
const heroEl = ref(null)

let pollTimer = null
let summaryAbort = null

const thumbSrc = computed(() => {
  if (!video.value?.thumbnail) return ''
  return thumbnailUrl(
    video.value.thumbnail,
    video.value.webpage_url || video.value.original_url,
  )
})

const showVipGate = computed(() => {
  if (!video.value || isVip.value) return false
  return (video.value.formats || []).some((f) => f.vip_required)
})

const subtitles = computed(() => video.value?.subtitles || [])

const platformSubtitles = computed(() =>
  subtitles.value.filter((s) => {
    const lang = String(s.lang || '').toLowerCase()
    return lang !== 'danmaku' && lang !== 'dm' && !s.is_danmaku
  }),
)

const needSubtitleFallback = computed(() => platformSubtitles.value.length === 0)

function subKey(sub) {
  return `${sub.automatic ? 'a' : 'm'}:${sub.lang}`
}

const selectedSub = computed(
  () => subtitles.value.find((s) => subKey(s) === selectedSubKey.value) || null,
)

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

function pickDefaultFormat(formats) {
  const first = formats.find((f) => !isLocked(f))
  selectedFormat.value = first || null
}

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
    const el = resultEl.value?.$el
    el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  } catch (err) {
    setStatus(err.message || String(err), 'error')
  } finally {
    parsing.value = false
  }
}

async function onParse(e) {
  e?.preventDefault?.()
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
  nextTick(() => heroEl.value?.focus?.())
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
        setStatus(task.data?.mode === 'mock' ? '演示总结完成' : 'AI 总结完成', 'ok')
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
  <AppHeader :is-vip="isVip" @vip-click="onHeaderVipClick" />

  <main>
    <HeroSection
      ref="heroEl"
      v-model="urlInput"
      :parsing="parsing"
      :status-msg="statusMsg"
      :status-type="statusType"
      @parse="onParse"
    />

    <div class="workspace">
      <div class="workspace-main">
        <VideoResult
          v-if="video"
          ref="resultEl"
          v-model:user-subtitle-text="userSubtitleText"
          :video="video"
          :thumb-src="thumbSrc"
          :selected-format="selectedFormat"
          :is-vip="isVip"
          :show-vip-gate="showVipGate"
          :need-subtitle-fallback="needSubtitleFallback"
          :summarizing="summarizing"
          :summary-error="summaryError"
          :summary-progress="summaryProgress"
          :summary-progress-text="summaryProgressText"
          :progress-visible="progressVisible"
          :progress="progress"
          :progress-text="progressText"
          :direct-info="directInfo"
          :downloading="downloading"
          :direct-busy="directBusy"
          @select-format="selectFormat"
          @open-vip="openVipModal"
          @summarize="onSummarize"
          @download="onDownload"
          @direct="onDirect"
          @reset="resetResult"
          @subtitle-file="onUserSubtitleFile"
        />

        <PlatformSection v-show="!video" />
        <PricingSection :is-vip="isVip" @open-vip="openVipModal" />
        <FaqSection />
        <AboutSection />
      </div>

      <HistoryPanel
        :history="history"
        @reuse="reuseHistory"
        @remove="removeHistory"
        @clear="clearHistory"
      />
    </div>
  </main>

  <AppFooter />
  <AuthModal :open="showVipModal" @close="closeVipModal" @confirm="confirmVip" />
</template>

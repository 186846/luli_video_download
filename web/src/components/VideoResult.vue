<script setup>
import { computed } from 'vue'
import { formatBytes } from '../composables/useVip'

const props = defineProps({
  video: { type: Object, required: true },
  thumbSrc: { type: String, default: '' },
  selectedFormat: { type: Object, default: null },
  isVip: { type: Boolean, default: false },
  showVipGate: { type: Boolean, default: false },
  needSubtitleFallback: { type: Boolean, default: false },
  summarizing: { type: Boolean, default: false },
  summaryError: { type: String, default: '' },
  summaryProgress: { type: Number, default: 0 },
  summaryProgressText: { type: String, default: '' },
  progressVisible: { type: Boolean, default: false },
  progress: { type: Number, default: 0 },
  progressText: { type: String, default: '' },
  directInfo: { type: String, default: '' },
  downloading: { type: Boolean, default: false },
  directBusy: { type: Boolean, default: false },
})

const userSubtitleText = defineModel('userSubtitleText', { type: String, default: '' })

const emit = defineEmits([
  'select-format',
  'open-vip',
  'summarize',
  'download',
  'direct',
  'reset',
  'subtitle-file',
])

const canDirectSelected = computed(() => {
  const fmt = props.selectedFormat
  if (!fmt) return false
  return fmt.can_direct !== false && !fmt.needs_merge && !String(fmt.format_id).includes('+')
})

function formatTitle(fmt) {
  if (!fmt) return ''
  if (fmt.needs_merge && fmt.height) return `${fmt.height}p 最佳 (视频+音频合并)`
  if (fmt.height && fmt.has_video && fmt.has_audio) return `${fmt.height}p 最佳`
  if (fmt.height && fmt.has_video) return `${fmt.height}p`
  if (!fmt.has_video && fmt.has_audio) return '仅音频'
  return fmt.label || fmt.format_id
}

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

function isLocked(fmt) {
  return Boolean(fmt.vip_required && !props.isVip)
}
</script>

<template>
  <section id="video-result" class="result">
    <div class="result-sheet">
      <div class="result-head">
        <div class="result-thumb">
          <img
            v-if="thumbSrc"
            :src="thumbSrc"
            :alt="video.title ? `${video.title} 视频封面` : '视频封面'"
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
            @click="emit('select-format', fmt)"
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
          <button type="button" class="btn btn-primary" @click="emit('open-vip')">
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
              @change="emit('subtitle-file', $event)"
            />
          </label>
        </div>
      </div>

      <div class="summary-row">
        <button
          type="button"
          class="btn btn-outline"
          :disabled="summarizing"
          @click="emit('summarize')"
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

      <div class="result-footer">
        <button
          type="button"
          class="btn-download"
          :disabled="!selectedFormat || downloading"
          @click="emit('download')"
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
            :disabled="!selectedFormat || directBusy || downloading || !canDirectSelected"
            @click="emit('direct')"
          >
            {{ directBusy ? '解析直链…' : '复制直链' }}
          </button>
          <button type="button" class="btn btn-ghost btn-sm" @click="emit('reset')">
            换个链接
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

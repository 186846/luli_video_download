<script setup>
import { thumbnailUrl } from '../api/video'

defineProps({
  history: { type: Array, default: () => [] },
})

const emit = defineEmits(['reuse', 'remove', 'clear'])

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
</script>

<template>
  <aside class="history-panel" id="history">
    <div class="history-panel__head">
      <div>
        <h2 class="history-panel__title">最近解析</h2>
        <p class="history-panel__sub">本机保存，最多 20 条</p>
      </div>
      <button
        v-if="history.length"
        type="button"
        class="btn btn-outline btn-sm"
        @click="emit('clear')"
      >
        清空
      </button>
    </div>
    <div v-if="!history.length" class="history-empty">暂无记录，解析后出现在这里</div>
    <ul v-else class="history-list">
      <li v-for="item in history" :key="item.url + item.at" class="history-item">
        <button type="button" class="history-main" @click="emit('reuse', item)">
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
          @click="emit('remove', item.url)"
        >
          删除
        </button>
      </li>
    </ul>
  </aside>
</template>

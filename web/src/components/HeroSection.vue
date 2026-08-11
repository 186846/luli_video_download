<script setup>
import { ref } from 'vue'

defineProps({
  modelValue: { type: String, default: '' },
  parsing: { type: Boolean, default: false },
  statusMsg: { type: String, default: '' },
  statusType: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'parse'])
const urlFieldEl = ref(null)

function focus() {
  urlFieldEl.value?.focus()
}

defineExpose({ focus })
</script>

<template>
  <section class="hero" id="download" aria-labelledby="hero-heading">
    <h1 id="hero-heading">万能视频下载，<span class="accent">一键保存</span></h1>
    <p class="hero-sub">粘贴链接 · 选清晰度 · 保存到本地。手机也能用。仅供个人学习。</p>
    <form class="url-bar" autocomplete="off" @submit.prevent="emit('parse', $event)">
      <div class="url-field">
        <svg class="url-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path
            fill="currentColor"
            d="M3.9 12a5 5 0 0 1 5-5h4v2h-4a3 3 0 0 0 0 6h4v2h-4a5 5 0 0 1-5-5m7-1h6v2h-6zm4.1-4h-4v2h4a5 5 0 0 1 0 10h-4v2h4a7 7 0 0 0 0-14"
          />
        </svg>
        <input
          ref="urlFieldEl"
          :value="modelValue"
          type="url"
          name="url"
          placeholder="粘贴视频链接，例如 https://www.bilibili.com/video/..."
          required
          enterkeyhint="go"
          @input="emit('update:modelValue', $event.target.value)"
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
</template>

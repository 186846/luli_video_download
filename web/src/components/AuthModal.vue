<script setup>
import { computed, ref, watch } from 'vue'
import { VIP_PRICE_USD } from '../api/payment'

const props = defineProps({
  open: { type: Boolean, default: false },
  isLoggedIn: { type: Boolean, default: false },
  isVip: { type: Boolean, default: false },
  email: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  /** login | upgrade — 未登录强调登录；用尽配额强调升级 */
  intent: { type: String, default: 'upgrade' },
  quotaHint: { type: String, default: '' },
})

const emit = defineEmits(['close', 'login', 'register', 'checkout', 'logout'])

const mode = ref('login') // login | register
const emailInput = ref('')
const passwordInput = ref('')

watch(
  () => props.open,
  (v) => {
    if (v) {
      mode.value = 'login'
      emailInput.value = props.email || ''
      passwordInput.value = ''
    }
  },
)

const title = computed(() => {
  if (props.isVip) return '会员已开通'
  if (props.isLoggedIn) {
    return props.intent === 'upgrade' ? '升级永久会员' : '开通永久会员'
  }
  return props.intent === 'login'
    ? mode.value === 'register'
      ? '注册账号'
      : '请先登录'
    : mode.value === 'register'
      ? '注册账号'
      : '登录账号'
})

function submitAuth() {
  const email = emailInput.value.trim()
  const password = passwordInput.value
  if (mode.value === 'register') emit('register', { email, password })
  else emit('login', { email, password })
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="vip-modal-title"
      @click.self="emit('close')"
    >
      <div class="modal-card">
        <h3 id="vip-modal-title">{{ title }}</h3>

        <template v-if="isVip">
          <p>您已是永久会员，可使用 1080p+ 与 AI 总结。</p>
          <p v-if="email" class="modal-meta">当前账号：{{ email }}</p>
          <div class="modal-actions">
            <button type="button" class="btn btn-outline" @click="emit('logout')">退出登录</button>
            <button type="button" class="btn btn-primary" @click="emit('close')">关闭</button>
          </div>
        </template>

        <template v-else-if="isLoggedIn">
          <p v-if="quotaHint" class="modal-quota">{{ quotaHint }}</p>
          <p>
            一次性支付 <strong>${{ VIP_PRICE_USD }} USD</strong>，开通永久会员后 AI 总结不限次数，并解锁 1080p+。
            将跳转至 Stripe 安全支付页。
          </p>
          <p v-if="email" class="modal-meta">当前账号：{{ email }}</p>
          <p v-if="error" class="modal-error">{{ error }}</p>
          <div class="modal-actions">
            <button type="button" class="btn btn-outline" :disabled="busy" @click="emit('close')">
              取消
            </button>
            <button
              type="button"
              class="btn btn-primary"
              :disabled="busy"
              @click="emit('checkout')"
            >
              {{ busy ? '跳转中…' : `去支付 $${VIP_PRICE_USD}` }}
            </button>
          </div>
        </template>

        <template v-else>
          <p>
            {{
              intent === 'login'
                ? '使用 AI 总结请先登录。免费账号每天可总结 3 次，会员不限次数。'
                : '请先登录或注册。免费账号每天 3 次 AI 总结，会员无限。'
            }}
          </p>
          <div class="modal-tabs" role="tablist">
            <button
              type="button"
              class="modal-tab"
              :class="{ active: mode === 'login' }"
              @click="mode = 'login'"
            >
              登录
            </button>
            <button
              type="button"
              class="modal-tab"
              :class="{ active: mode === 'register' }"
              @click="mode = 'register'"
            >
              注册
            </button>
          </div>
          <form class="modal-form" @submit.prevent="submitAuth">
            <label>
              邮箱
              <input
                v-model="emailInput"
                type="email"
                autocomplete="email"
                required
                placeholder="you@example.com"
              />
            </label>
            <label>
              密码
              <input
                v-model="passwordInput"
                type="password"
                autocomplete="current-password"
                required
                minlength="8"
                placeholder="至少 8 位"
              />
            </label>
            <p v-if="error" class="modal-error">{{ error }}</p>
            <div class="modal-actions">
              <button type="button" class="btn btn-outline" :disabled="busy" @click="emit('close')">
                取消
              </button>
              <button type="submit" class="btn btn-primary" :disabled="busy">
                {{ busy ? '请稍候…' : mode === 'register' ? '注册' : '登录' }}
              </button>
            </div>
          </form>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-meta {
  font-size: 0.9rem;
  opacity: 0.8;
}
.modal-quota {
  color: #b45309;
  font-size: 0.95rem;
  margin: 0 0 0.5rem;
}
.modal-error {
  color: #c0392b;
  font-size: 0.9rem;
  margin: 0.5rem 0 0;
}
.modal-tabs {
  display: flex;
  gap: 0.5rem;
  margin: 0.75rem 0;
}
.modal-tab {
  flex: 1;
  border: 1px solid rgba(0, 0, 0, 0.12);
  background: transparent;
  padding: 0.4rem 0.6rem;
  border-radius: 8px;
  cursor: pointer;
}
.modal-tab.active {
  border-color: var(--accent, #2a6df4);
  color: var(--accent, #2a6df4);
  font-weight: 600;
}
.modal-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.modal-form label {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  font-size: 0.9rem;
}
.modal-form input {
  padding: 0.55rem 0.7rem;
  border-radius: 8px;
  border: 1px solid rgba(0, 0, 0, 0.15);
  font: inherit;
}
</style>

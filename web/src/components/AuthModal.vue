<script setup>
import { computed, nextTick, ref, watch } from 'vue'
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
const showPassword = ref(false)
const emailEl = ref(null)

watch(
  () => props.open,
  async (v) => {
    if (v) {
      mode.value = 'login'
      emailInput.value = props.email || ''
      passwordInput.value = ''
      showPassword.value = false
      await nextTick()
      emailEl.value?.focus?.()
    }
  },
)

const title = computed(() => {
  if (props.isVip) return '会员已开通'
  if (props.isLoggedIn) {
    return props.intent === 'upgrade' ? '升级永久会员' : '开通永久会员'
  }
  return mode.value === 'register' ? '创建账号' : '欢迎回来'
})

const subtitle = computed(() => {
  if (props.isVip) return '高清下载与 AI 总结已全部解锁'
  if (props.isLoggedIn) {
    return props.quotaHint
      || `一次性 $${VIP_PRICE_USD}，解锁 1080p+ 与不限次数 AI 总结`
  }
  if (props.intent === 'login') {
    return mode.value === 'register'
      ? '注册后每天可免费 AI 总结 3 次'
      : '登录后使用 AI 总结，免费额度每天 3 次'
  }
  return mode.value === 'register'
    ? '免费账号每天 3 次 AI 总结，会员不限次数'
    : '登录账号以开通会员或使用免费额度'
})

function switchMode(next) {
  mode.value = next
  showPassword.value = false
}

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
      <div class="modal-card auth-modal" @keydown.esc.prevent="emit('close')">
        <button type="button" class="auth-close" aria-label="关闭" @click="emit('close')">
          <span aria-hidden="true">×</span>
        </button>

        <div class="auth-head">
          <div class="auth-brand" aria-hidden="true">
            <span class="auth-brand-mark" />
          </div>
          <h3 id="vip-modal-title">{{ title }}</h3>
          <p class="auth-sub">{{ subtitle }}</p>
        </div>

        <!-- 已是 VIP -->
        <template v-if="isVip">
          <div class="auth-panel">
            <div class="auth-account" v-if="email">
              <span class="auth-account-label">当前账号</span>
              <span class="auth-account-value">{{ email }}</span>
            </div>
            <ul class="auth-perks">
              <li>1080p 及以上清晰度</li>
              <li>AI 总结不限次数</li>
              <li>永久会员权益</li>
            </ul>
          </div>
          <div class="modal-actions auth-actions">
            <button type="button" class="btn btn-outline" @click="emit('logout')">退出登录</button>
            <button type="button" class="btn btn-primary" @click="emit('close')">继续使用</button>
          </div>
        </template>

        <!-- 已登录未 VIP：升级 -->
        <template v-else-if="isLoggedIn">
          <div class="auth-panel">
            <div v-if="quotaHint" class="auth-banner auth-banner--warn" role="status">
              {{ quotaHint }}
            </div>
            <div class="auth-price">
              <span class="auth-price-amount">${{ VIP_PRICE_USD }}</span>
              <span class="auth-price-unit">USD · 一次性</span>
            </div>
            <ul class="auth-perks">
              <li>解锁 1080p / 更高清晰度</li>
              <li>AI 总结与问答不限次数</li>
              <li>跳转 Stripe 安全支付</li>
            </ul>
            <div class="auth-account" v-if="email">
              <span class="auth-account-label">支付账号</span>
              <span class="auth-account-value">{{ email }}</span>
            </div>
            <p v-if="error" class="modal-error" role="alert">{{ error }}</p>
          </div>
          <div class="modal-actions auth-actions">
            <button type="button" class="btn btn-outline" :disabled="busy" @click="emit('close')">
              稍后再说
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

        <!-- 未登录：登录 / 注册 -->
        <template v-else>
          <div class="auth-seg" role="tablist" aria-label="登录或注册">
            <button
              type="button"
              role="tab"
              class="auth-seg-btn"
              :class="{ active: mode === 'login' }"
              :aria-selected="mode === 'login'"
              @click="switchMode('login')"
            >
              登录
            </button>
            <button
              type="button"
              role="tab"
              class="auth-seg-btn"
              :class="{ active: mode === 'register' }"
              :aria-selected="mode === 'register'"
              @click="switchMode('register')"
            >
              注册
            </button>
          </div>

          <form class="modal-form auth-form" @submit.prevent="submitAuth">
            <label class="auth-field">
              <span class="auth-label">邮箱</span>
              <input
                ref="emailEl"
                v-model="emailInput"
                class="auth-input"
                type="email"
                autocomplete="email"
                required
                placeholder="name@example.com"
                :disabled="busy"
              />
            </label>
            <label class="auth-field">
              <span class="auth-label">密码</span>
              <div class="auth-input-wrap">
                <input
                  v-model="passwordInput"
                  class="auth-input"
                  :type="showPassword ? 'text' : 'password'"
                  :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
                  required
                  minlength="8"
                  :placeholder="mode === 'register' ? '至少 8 位字符' : '输入密码'"
                  :disabled="busy"
                />
                <button
                  type="button"
                  class="auth-eye"
                  :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                  @click="showPassword = !showPassword"
                >
                  {{ showPassword ? '隐藏' : '显示' }}
                </button>
              </div>
            </label>

            <p v-if="mode === 'register'" class="auth-hint">
              注册即表示你将使用本站学习演示功能，请遵守版权与平台条款。
            </p>

            <p v-if="error" class="modal-error" role="alert">{{ error }}</p>

            <button type="submit" class="btn btn-primary auth-submit" :disabled="busy">
              {{ busy ? '请稍候…' : mode === 'register' ? '创建账号' : '登录' }}
            </button>
          </form>

          <p class="auth-switch">
            <template v-if="mode === 'login'">
              还没有账号？
              <button type="button" class="auth-link" @click="switchMode('register')">去注册</button>
            </template>
            <template v-else>
              已有账号？
              <button type="button" class="auth-link" @click="switchMode('login')">去登录</button>
            </template>
          </p>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.auth-modal {
  position: relative;
  max-width: 440px;
  padding: 1.75rem 1.6rem 1.5rem;
  border: 1px solid var(--border, #e8eaed);
  background:
    linear-gradient(180deg, rgba(23, 119, 255, 0.06) 0%, transparent 42%),
    #fff;
  animation: authPop 0.22s ease both;
}

.auth-close {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--muted-foreground, #64748b);
  font-size: 1.4rem;
  line-height: 1;
  cursor: pointer;
}

.auth-close:hover {
  background: var(--muted, #f0f1f2);
  color: var(--foreground, #0f172a);
}

.auth-head {
  text-align: center;
  margin-bottom: 1.25rem;
  padding-right: 0.5rem;
}

.auth-brand {
  display: flex;
  justify-content: center;
  margin-bottom: 0.75rem;
}

.auth-brand-mark {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 12px;
  background: linear-gradient(135deg, #1777ff 0%, #0d66e8 100%);
  box-shadow: 0 8px 20px rgba(23, 119, 255, 0.28);
}

.auth-head h3 {
  margin: 0 0 0.35rem;
  font-family: var(--font-display, 'Sora', sans-serif);
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--foreground, #0f172a);
}

.auth-sub {
  margin: 0 !important;
  color: var(--muted-foreground, #64748b) !important;
  font-size: 0.9rem !important;
  line-height: 1.5;
}

.auth-panel {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  margin-bottom: 1.25rem;
}

.auth-banner {
  margin: 0;
  padding: 0.65rem 0.8rem;
  border-radius: 10px;
  font-size: 0.88rem;
  line-height: 1.45;
}

.auth-banner--warn {
  background: #fff7ed;
  color: #9a3412;
  border: 1px solid #fed7aa;
}

.auth-price {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  justify-content: center;
  padding: 0.35rem 0;
}

.auth-price-amount {
  font-family: var(--font-display, 'Sora', sans-serif);
  font-size: 2rem;
  font-weight: 700;
  color: var(--primary, #1777ff);
  letter-spacing: -0.03em;
}

.auth-price-unit {
  color: var(--muted-foreground, #64748b);
  font-size: 0.9rem;
}

.auth-perks {
  margin: 0;
  padding: 0.75rem 1rem;
  list-style: none;
  border-radius: 12px;
  background: var(--primary-soft, rgba(23, 119, 255, 0.08));
}

.auth-perks li {
  position: relative;
  padding: 0.28rem 0 0.28rem 1.15rem;
  font-size: 0.9rem;
  color: #334155;
}

.auth-perks li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.7em;
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: var(--primary, #1777ff);
}

.auth-account {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.65rem 0.8rem;
  border-radius: 10px;
  background: var(--muted, #f0f1f2);
}

.auth-account-label {
  font-size: 0.75rem;
  color: var(--muted-foreground, #64748b);
}

.auth-account-value {
  font-size: 0.92rem;
  font-weight: 600;
  word-break: break-all;
}

.auth-seg {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.25rem;
  padding: 0.25rem;
  margin-bottom: 1.1rem;
  border-radius: 12px;
  background: var(--muted, #f0f1f2);
}

.auth-seg-btn {
  border: none;
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
  background: transparent;
  color: var(--muted-foreground, #64748b);
  font: inherit;
  font-weight: 600;
  font-size: 0.92rem;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}

.auth-seg-btn.active {
  background: #fff;
  color: var(--primary, #1777ff);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
}

.auth-seg-btn:hover:not(.active) {
  color: var(--foreground, #0f172a);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.auth-field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.auth-label {
  font-size: 0.82rem;
  font-weight: 600;
  color: #334155;
}

.auth-input-wrap {
  position: relative;
}

.auth-input {
  width: 100%;
  padding: 0.7rem 0.85rem;
  border: 1px solid var(--border, #e8eaed);
  border-radius: 10px;
  background: #fff;
  font: inherit;
  font-size: 0.95rem;
  color: var(--foreground, #0f172a);
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.auth-input-wrap .auth-input {
  padding-right: 3.4rem;
}

.auth-input:focus {
  border-color: var(--primary, #1777ff);
  box-shadow: 0 0 0 3px var(--primary-soft, rgba(23, 119, 255, 0.08));
}

.auth-input:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.auth-eye {
  position: absolute;
  right: 0.35rem;
  top: 50%;
  transform: translateY(-50%);
  border: none;
  background: transparent;
  color: var(--primary, #1777ff);
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.35rem 0.5rem;
  cursor: pointer;
  border-radius: 6px;
}

.auth-eye:hover {
  background: var(--primary-soft, rgba(23, 119, 255, 0.08));
}

.auth-hint {
  margin: 0 !important;
  font-size: 0.78rem !important;
  color: var(--muted-foreground, #64748b) !important;
  line-height: 1.45;
}

.auth-submit {
  width: 100%;
  margin-top: 0.15rem;
  padding-top: 0.75rem;
  padding-bottom: 0.75rem;
  font-weight: 650;
}

.auth-actions {
  margin-top: 0.25rem;
}

.auth-actions .btn {
  min-width: 6.5rem;
}

.auth-switch {
  margin: 1rem 0 0 !important;
  text-align: center;
  font-size: 0.88rem !important;
  color: var(--muted-foreground, #64748b) !important;
}

.auth-link {
  border: none;
  background: none;
  padding: 0;
  color: var(--primary, #1777ff);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.auth-link:hover {
  text-decoration: underline;
}

.modal-error {
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
  font-size: 0.88rem;
  margin: 0 !important;
}

@keyframes authPop {
  from {
    opacity: 0;
    transform: translateY(10px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (max-width: 480px) {
  .auth-modal {
    padding: 1.4rem 1.15rem 1.25rem;
  }

  .auth-actions {
    flex-direction: column-reverse;
  }

  .auth-actions .btn {
    width: 100%;
  }
}
</style>

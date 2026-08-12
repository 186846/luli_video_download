/**
 * 登录态与会员 / AI 配额（服务端 /api/auth/me 为准）。
 */
import { computed, ref } from 'vue'
import { fetchMe, login as apiLogin, logout as apiLogout, register as apiRegister } from '../api/auth'
import { createCheckout, getBillingSessionStatus } from '../api/payment'

const user = ref(null)
const loading = ref(false)
const ready = ref(false)
let hydratePromise = null

export function useAuth() {
  const isLoggedIn = computed(() => Boolean(user.value))
  const isVip = computed(() => Boolean(user.value?.is_vip))
  const email = computed(() => user.value?.email || '')
  const aiRemaining = computed(() => {
    if (!user.value) return 0
    if (user.value.is_vip) return null
    const v = user.value.ai_summarize_remaining
    return typeof v === 'number' ? v : 0
  })
  const aiDailyLimit = computed(
    () => user.value?.ai_summarize_daily_limit ?? 3,
  )
  const canSummarize = computed(() => {
    if (!user.value) return false
    if (user.value.is_vip) return true
    return (aiRemaining.value ?? 0) > 0
  })

  function applyUser(u) {
    user.value = u || null
  }

  async function hydrate() {
    if (hydratePromise) return hydratePromise
    hydratePromise = (async () => {
      loading.value = true
      try {
        const json = await fetchMe()
        applyUser(json.user)
      } catch {
        applyUser(null)
      } finally {
        loading.value = false
        ready.value = true
        hydratePromise = null
      }
    })()
    return hydratePromise
  }

  async function register(emailAddr, password) {
    const json = await apiRegister(emailAddr, password)
    applyUser(json.user)
    ready.value = true
    return json.user
  }

  async function login(emailAddr, password) {
    const json = await apiLogin(emailAddr, password)
    applyUser(json.user)
    ready.value = true
    return json.user
  }

  async function logout() {
    try {
      await apiLogout()
    } finally {
      applyUser(null)
    }
  }

  async function refreshMe() {
    const json = await fetchMe()
    applyUser(json.user)
    return user.value
  }

  function applyQuotaFromResponse(quota) {
    if (!user.value || !quota) return
    user.value = {
      ...user.value,
      is_vip: quota.is_vip ?? user.value.is_vip,
      ai_summarize_remaining: quota.remaining,
      ai_summarize_used_today: quota.used,
      ai_summarize_daily_limit: quota.daily_limit ?? user.value.ai_summarize_daily_limit,
    }
  }

  /** 跳转 Stripe Checkout；未登录抛错由 UI 处理 */
  async function startCheckout() {
    const data = await createCheckout()
    if (!data?.url) throw new Error('未获得支付链接')
    window.location.href = data.url
  }

  /**
   * 支付成功回跳：轮询会员状态（Webhook 可能略晚于页面回跳）。
   */
  async function pollVipAfterBilling(sessionId, { attempts = 15, intervalMs = 800 } = {}) {
    for (let i = 0; i < attempts; i++) {
      try {
        if (sessionId) {
          const st = await getBillingSessionStatus(sessionId)
          if (st.user) applyUser(st.user)
          if (st.user?.is_vip) return true
        } else {
          const me = await refreshMe()
          if (me?.is_vip) return true
        }
      } catch {
        /* 继续重试 */
      }
      await new Promise((r) => setTimeout(r, intervalMs))
    }
    await refreshMe()
    return Boolean(user.value?.is_vip)
  }

  return {
    user,
    loading,
    ready,
    isLoggedIn,
    isVip,
    email,
    aiRemaining,
    aiDailyLimit,
    canSummarize,
    hydrate,
    register,
    login,
    logout,
    refreshMe,
    applyQuotaFromResponse,
    startCheckout,
    pollVipAfterBilling,
  }
}

/** 文件大小格式化（字节 → 可读字符串） */
export function formatBytes(n) {
  if (!n || n <= 0) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

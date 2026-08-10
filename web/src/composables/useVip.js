/**
 * 演示会员状态（非真实支付）。
 * 仅写 localStorage；请求高清时由前端附带 vip_token，后端再校验。
 */
import { computed, ref } from 'vue'
import { VIP_TOKEN } from '../api/auth'

export { VIP_TOKEN }

const VIP_KEY = 'speedydl_vip'
const vipFlag = ref(localStorage.getItem(VIP_KEY) === '1')

export function useVip() {
  const isVip = computed(() => vipFlag.value)

  function setVip(on) {
    if (on) localStorage.setItem(VIP_KEY, '1')
    else localStorage.removeItem(VIP_KEY)
    vipFlag.value = on
  }

  /** 已开通则询问是否关闭；未开通返回 true 表示应弹出开通框 */
  function toggleVipPrompt() {
    if (isVip.value) {
      if (confirm('关闭演示会员？将恢复免费清晰度限制。')) setVip(false)
      return false
    }
    return true
  }

  return { isVip, setVip, toggleVipPrompt }
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

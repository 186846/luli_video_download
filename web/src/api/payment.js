/**
 * Stripe 会员购买 API。
 */
import { request } from './http'

export const VIP_PRICE_USD = '9.90'

/** 创建 Checkout，返回 { url, session_id, order_id } */
export async function createCheckout() {
  const json = await request('/api/billing/checkout', {
    method: 'POST',
    body: '{}',
  })
  return json.data
}

/** 支付回跳后查询会话（不以本接口开通 VIP） */
export function getBillingSessionStatus(sessionId) {
  return request(
    `/api/billing/session-status?session_id=${encodeURIComponent(sessionId)}`,
  )
}

export function membershipPlan() {
  return {
    id: 'lifetime-vip',
    name: '永久会员',
    priceUsd: VIP_PRICE_USD,
    note: '一次性付款，解锁 1080p+ 与 AI 总结',
  }
}

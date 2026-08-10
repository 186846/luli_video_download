/**
 * 演示会员开通（非真实支付）。
 * 实际状态写入见 composables/useVip.js。
 */
import { VIP_TOKEN } from './auth'

/** 开通演示会员后可附带的令牌说明 */
export function demoMembershipPlan() {
  return {
    id: 'demo-vip',
    name: '演示会员',
    price: 0,
    token: VIP_TOKEN,
    note: '学习演示，无真实扣款',
  }
}

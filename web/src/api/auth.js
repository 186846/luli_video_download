/**
 * 演示会员「鉴权」令牌（非真实账号体系）。
 * 高清下载 / AI 总结请求体附带 vip_token，由后端校验。
 */
export const VIP_TOKEN = 'demo-vip'

export function vipPayload(isVip) {
  return isVip ? VIP_TOKEN : null
}

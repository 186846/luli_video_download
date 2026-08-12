/**
 * 账号鉴权 API（Cookie 会话）。
 */
import { request } from './http'

/** @deprecated 仅当后端 SPEEDYDL_ALLOW_DEMO_VIP=1 时有效 */
export const VIP_TOKEN = 'demo-vip'

export function vipPayload(isVip) {
  return isVip ? VIP_TOKEN : null
}

export function register(email, password) {
  return request('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function login(email, password) {
  return request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function logout() {
  return request('/api/auth/logout', { method: 'POST', body: '{}' })
}

export function fetchMe() {
  return request('/api/auth/me')
}

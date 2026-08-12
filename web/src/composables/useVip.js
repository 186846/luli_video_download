/**
 * 兼容层：旧代码可继续从 useVip 取 formatBytes；会员状态请用 useAuth。
 */
export { formatBytes, useAuth as useVip } from './useAuth'

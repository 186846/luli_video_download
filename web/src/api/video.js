import { request } from './http'

/** 解析视频元数据 / 格式 / 字幕列表 */
export function parseVideo(url) {
  return request('/api/parse', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

/** 创建服务端下载任务（模式①） */
export function startDownload(payload) {
  return request('/api/download', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 解析单流直链（模式②，合并清晰度会失败） */
export function resolveDirect(payload) {
  return request('/api/direct', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 轮询下载进度 */
export function getTask(taskId) {
  return request(`/api/tasks/${taskId}`)
}

/** 封面走后端代理，避免 CDN 防盗链 */
export function thumbnailUrl(thumb, pageUrl) {
  if (!thumb) return ''
  const params = new URLSearchParams({ url: thumb })
  if (pageUrl) params.set('page', pageUrl)
  return `/api/thumbnail?${params.toString()}`
}

/** 任务完成后的文件下载地址 */
export function fileUrl(taskId) {
  return `/api/files/${taskId}`
}

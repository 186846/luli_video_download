/**
 * 后端 API 封装。
 * 开发环境走 Vite proxy：浏览器请求 /api/* → http://127.0.0.1:8000
 */

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  const json = await res.json().catch(() => ({}))
  if (!res.ok) {
    // FastAPI 错误体通常是 { detail: string | ValidationError[] }
    const detail = json.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
          : '请求失败'
    throw new Error(msg)
  }
  return json
}

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

/**
 * 字幕接口返回文件流（非 JSON），需用 blob + a[download] 触发保存。
 */
export async function downloadSubtitleFile(payload) {
  const res = await fetch('/api/subtitles/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const json = await res.json().catch(() => ({}))
    throw new Error(typeof json.detail === 'string' ? json.detail : '字幕下载失败')
  }
  const blob = await res.blob()
  const disp = res.headers.get('content-disposition') || ''
  const match = /filename\*?=(?:UTF-8''|")?([^\";]+)/i.exec(disp)
  const filename = match
    ? decodeURIComponent(match[1].replace(/"/g, ''))
    : `subtitle.${payload.lang || 'vtt'}`
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(a.href)
}

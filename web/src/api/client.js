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

/** 解析 SSE 文本块为事件列表 */
function parseSseChunk(buffer) {
  const events = []
  const parts = buffer.split('\n\n')
  const rest = parts.pop() || ''
  for (const part of parts) {
    if (!part.trim()) continue
    let event = 'message'
    const dataLines = []
    for (const line of part.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    if (!dataLines.length) continue
    try {
      events.push({ event, data: JSON.parse(dataLines.join('\n')) })
    } catch {
      events.push({ event, data: { raw: dataLines.join('\n') } })
    }
  }
  return { events, rest }
}

/**
 * 读取 SSE 响应流并回调。
 * @returns {Promise<void>}
 */
async function consumeSse(res, { onEvent, signal } = {}) {
  if (!res.ok) {
    const json = await res.json().catch(() => ({}))
    const detail = json.detail
    throw new Error(typeof detail === 'string' ? detail : 'SSE 请求失败')
  }
  if (!res.body) throw new Error('浏览器不支持流式响应')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    if (signal?.aborted) {
      try {
        await reader.cancel()
      } catch {
        /* ignore */
      }
      throw new DOMException('Aborted', 'AbortError')
    }
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { events, rest } = parseSseChunk(buffer)
    buffer = rest
    for (const ev of events) {
      if (onEvent) onEvent(ev.event, ev.data)
    }
  }
  if (buffer.trim()) {
    const { events } = parseSseChunk(`${buffer}\n\n`)
    for (const ev of events) {
      if (onEvent) onEvent(ev.event, ev.data)
    }
  }
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

/** 创建 AI 视频总结后台任务，返回 { task_id } */
export function startSummarize(payload) {
  return request('/api/summarize', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 查询总结任务状态与进度（轮询兜底） */
export function getSummaryStatus(taskId) {
  return request(`/api/summarize/status/${taskId}`)
}

/**
 * SSE 订阅总结进度。
 * onProgress(task) / onDone(task) / onError(errMsg, task?)
 */
export async function streamSummaryStatus(taskId, { onProgress, onDone, onError, signal } = {}) {
  const res = await fetch(`/api/summarize/stream/${taskId}`, { signal })
  let finished = false
  await consumeSse(res, {
    signal,
    onEvent(event, data) {
      if (event === 'progress' && data?.task) {
        onProgress?.(data.task)
      } else if (event === 'done' && data?.task) {
        finished = true
        onDone?.(data.task)
      } else if (event === 'error') {
        finished = true
        onError?.(data?.error || data?.task?.error || '总结失败', data?.task)
      }
    },
  })
  if (!finished) onError?.('总结流意外结束')
}

/** 针对视频内容的 AI 问答（同步 JSON，兼容） */
export function askAboutVideo(payload) {
  return request('/api/summarize/ask', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/**
 * SSE 问答（/api/chat）。
 * onStatus(msg) / onToken(text) / onDone(data) / onError(msg)
 */
export async function streamChat(payload, { onStatus, onToken, onDone, onError, signal } = {}) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  let finished = false
  await consumeSse(res, {
    signal,
    onEvent(event, data) {
      if (event === 'status') {
        onStatus?.(data?.message || '')
      } else if (event === 'token') {
        onToken?.(data?.text || '')
      } else if (event === 'done') {
        finished = true
        onDone?.(data)
      } else if (event === 'error') {
        finished = true
        onError?.(data?.error || '问答失败')
      }
    },
  })
  if (!finished) onError?.('问答流意外结束')
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

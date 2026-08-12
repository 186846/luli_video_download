/**
 * 通用 HTTP / SSE 工具。业务接口见 video.js / summarize.js。
 * credentials: 'include' 以携带登录 Cookie。
 */

export async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  if (options.body != null && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  const res = await fetch(path, {
    credentials: 'include',
    ...options,
    headers,
  })
  const json = await res.json().catch(() => ({}))
  if (!res.ok) {
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
export function parseSseChunk(buffer) {
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
export async function consumeSse(res, { onEvent, signal } = {}) {
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

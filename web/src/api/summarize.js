import { consumeSse, request } from './http'

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
  const res = await fetch(`/api/summarize/stream/${taskId}`, {
    credentials: 'include',
    signal,
  })
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
    credentials: 'include',
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

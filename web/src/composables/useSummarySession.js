/** sessionStorage 暂存 AI 总结详情，供 /summary 页读取 */
const KEY = 'speedydl_ai_summary'

export function saveSummarySession(data) {
  sessionStorage.setItem(KEY, JSON.stringify(data))
}

export function loadSummarySession() {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function clearSummarySession() {
  sessionStorage.removeItem(KEY)
}

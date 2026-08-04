/**
 * 解析历史（仅浏览器 localStorage，最多 MAX_ITEMS 条）。
 * 用于阶段 5 体验；不落服务端，换设备不会同步。
 */
import { ref } from 'vue'

const HISTORY_KEY = 'speedydl_history'
const MAX_ITEMS = 20

function read() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    const list = raw ? JSON.parse(raw) : []
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function write(list) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, MAX_ITEMS)))
}

export function useHistory() {
  const history = ref(read())

  function refresh() {
    history.value = read()
  }

  /** 解析成功后写入；同 URL 提到最前 */
  function addHistory(item) {
    if (!item?.url) return
    const next = [
      {
        url: item.url,
        title: item.title || item.url,
        extractor: item.extractor || '',
        thumbnail: item.thumbnail || '',
        at: Date.now(),
      },
      ...read().filter((h) => h.url !== item.url),
    ].slice(0, MAX_ITEMS)
    write(next)
    history.value = next
  }

  function removeHistory(url) {
    const next = read().filter((h) => h.url !== url)
    write(next)
    history.value = next
  }

  function clearHistory() {
    localStorage.removeItem(HISTORY_KEY)
    history.value = []
  }

  return { history, refresh, addHistory, removeHistory, clearHistory }
}

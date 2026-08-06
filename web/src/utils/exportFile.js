/**
 * 文件下载工具：用 Blob + URL.createObjectURL + a[download] 触发浏览器下载。
 */

/**
 * 将文件名做安全处理：去除非法字符，限制长度。
 * @param {string} name 原始文件名（不含扩展名）
 * @param {string} ext 扩展名（不含点，如 'md'、'txt'）
 * @returns {string} 安全的文件名
 */
export function safeFilename(name, ext) {
  const base = String(name || 'video-summary')
    .replace(/[\\/:*?"<>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80) || 'video-summary'
  return `${base}.${ext}`
}

/**
 * 触发浏览器下载文本内容为文件。
 * @param {string} filename 文件名（含扩展名）
 * @param {string} content 文本内容
 * @param {string} mime MIME 类型，默认 text/plain
 */
export function downloadTextFile(filename, content, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // 延迟回收，避免某些浏览器下载未完成就 revoke
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * 下载 Markdown 文件。
 * @param {string} title 视频标题（用于生成文件名）
 * @param {string} content Markdown 内容
 */
export function downloadMarkdown(title, content) {
  downloadTextFile(safeFilename(title, 'md'), content, 'text/markdown;charset=utf-8')
}

/**
 * 下载纯文本文件。
 * @param {string} title 视频标题（用于生成文件名）
 * @param {string} content 文本内容
 * @param {string} suffix 文件名后缀（如 '字幕'），生成 {title}-{suffix}.txt
 */
export function downloadTxt(title, content, suffix = '') {
  const base = String(title || 'video-summary')
    .replace(/[\\/:*?"<>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80) || 'video-summary'
  const name = suffix ? `${base}-${suffix}.txt` : `${base}.txt`
  downloadTextFile(name, content, 'text/plain;charset=utf-8')
}

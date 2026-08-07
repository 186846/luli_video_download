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

/** 时间戳 → 秒；支持 mm:ss / hh:mm:ss / 带小数 */
export function timestampToSeconds(raw) {
  const s = String(raw || '').trim().replace(',', '.')
  if (!s) return 0
  const parts = s.split(':')
  try {
    if (parts.length === 3) {
      return Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2])
    }
    if (parts.length === 2) {
      return Number(parts[0]) * 60 + Number(parts[1])
    }
    return Number(parts[0]) || 0
  } catch {
    return 0
  }
}

/** 秒 → SRT 时间 HH:MM:SS,mmm */
export function formatSrtTime(sec) {
  const t = Math.max(0, Number(sec) || 0)
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = Math.floor(t % 60)
  const ms = Math.round((t - Math.floor(t)) * 1000)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms).padStart(3, '0')}`
}

/** 秒 → VTT 时间 HH:MM:SS.mmm */
export function formatVttTime(sec) {
  return formatSrtTime(sec).replace(',', '.')
}

/**
 * 为每条字幕补全 end（秒）：优先 cue.end → 下一条 start → start+3s
 * @param {Array<{start?: string, end?: string, text?: string}>} cues
 */
export function resolveCueRanges(cues) {
  const list = Array.isArray(cues) ? cues : []
  return list
    .map((c, i) => {
      const start = timestampToSeconds(c?.start)
      let end =
        c?.end != null && String(c.end).trim() !== ''
          ? timestampToSeconds(c.end)
          : null
      if (end == null || !(end > start)) {
        const next = list[i + 1]
        const nextStart = next ? timestampToSeconds(next.start) : null
        if (nextStart != null && nextStart > start) end = nextStart
        else end = start + 3
      }
      return {
        start,
        end,
        text: String(c?.text || '').replace(/\r\n/g, '\n').trim(),
      }
    })
    .filter((c) => c.text)
}

/** transcript → 标准 SRT 文本 */
export function toSrt(cues) {
  const ranges = resolveCueRanges(cues)
  if (!ranges.length) return ''
  return (
    ranges
      .map(
        (c, i) =>
          `${i + 1}\n${formatSrtTime(c.start)} --> ${formatSrtTime(c.end)}\n${c.text}\n`,
      )
      .join('\n')
      .trimEnd() + '\n'
  )
}

/** transcript → 标准 WebVTT 文本 */
export function toVtt(cues) {
  const ranges = resolveCueRanges(cues)
  if (!ranges.length) return 'WEBVTT\n'
  const body = ranges
    .map((c) => `${formatVttTime(c.start)} --> ${formatVttTime(c.end)}\n${c.text}\n`)
    .join('\n')
  return `WEBVTT\n\n${body}`.trimEnd() + '\n'
}

/** 下载 SRT 字幕文件 */
export function downloadSrt(title, cues) {
  downloadTextFile(
    safeFilename(title || 'subtitles', 'srt'),
    toSrt(cues),
    'application/x-subrip;charset=utf-8',
  )
}

/** 下载 VTT 字幕文件 */
export function downloadVtt(title, cues) {
  downloadTextFile(
    safeFilename(title || 'subtitles', 'vtt'),
    toVtt(cues),
    'text/vtt;charset=utf-8',
  )
}

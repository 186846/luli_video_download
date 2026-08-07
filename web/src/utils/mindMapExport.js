/**
 * 思维导图导出：FreeMind (.mm) / OPML / SVG 字符串 / PNG 光栅化。
 * 输入约定与后端一致：{ name, children[] } 递归树。
 */

import { downloadTextFile, safeFilename } from './exportFile.js'

/** XML 属性转义 */
export function escapeXmlAttr(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

/** 规范化节点，保证 name / children */
export function normalizeNode(node, fallback = '未命名') {
  if (node == null || typeof node !== 'object') {
    return { name: fallback, children: [] }
  }
  const name = String(node.name ?? '').trim() || fallback
  const kids = Array.isArray(node.children) ? node.children : []
  return {
    name,
    children: kids.map((c, i) =>
      typeof c === 'string'
        ? { name: c.trim() || `分支${i + 1}`, children: [] }
        : normalizeNode(c, `分支${i + 1}`),
    ),
  }
}

function freeMindNodeXml(node, indent) {
  const pad = '  '.repeat(indent)
  const kids = node.children || []
  const text = escapeXmlAttr(node.name)
  if (!kids.length) {
    return `${pad}<node TEXT="${text}"/>\n`
  }
  let out = `${pad}<node TEXT="${text}">\n`
  for (const c of kids) out += freeMindNodeXml(c, indent + 1)
  out += `${pad}</node>\n`
  return out
}

/**
 * 转为 FreeMind 1.0.1 XML（可被 XMind / 幕布 / 亿图等导入编辑）。
 */
export function toFreeMindXml(root) {
  const tree = normalizeNode(root, '视频大纲')
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<map version="1.0.1">\n` +
    freeMindNodeXml(tree, 1) +
    `</map>\n`
  )
}

function opmlOutlineXml(node, indent) {
  const pad = '  '.repeat(indent)
  const kids = node.children || []
  const text = escapeXmlAttr(node.name)
  if (!kids.length) {
    return `${pad}<outline text="${text}"/>\n`
  }
  let out = `${pad}<outline text="${text}">\n`
  for (const c of kids) out += opmlOutlineXml(c, indent + 1)
  out += `${pad}</outline>\n`
  return out
}

/**
 * 转为 OPML 2.0（可被 XMind / 幕布 / MindNode 等导入编辑）。
 */
export function toOpmlXml(root) {
  const tree = normalizeNode(root, '视频大纲')
  const title = escapeXmlAttr(tree.name)
  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<opml version="2.0">\n` +
    `  <head>\n` +
    `    <title>${title}</title>\n` +
    `  </head>\n` +
    `  <body>\n` +
    opmlOutlineXml(tree, 2) +
    `  </body>\n` +
    `</opml>\n`
  )
}

export function downloadFreeMind(root) {
  const tree = normalizeNode(root, '视频大纲')
  downloadTextFile(
    safeFilename(tree.name, 'mm'),
    toFreeMindXml(tree),
    'application/x-freemind',
  )
}

export function downloadOpml(root) {
  const tree = normalizeNode(root, '视频大纲')
  downloadTextFile(
    safeFilename(tree.name, 'opml'),
    toOpmlXml(tree),
    'text/x-opml+xml;charset=utf-8',
  )
}

/**
 * 触发 Blob 下载（图片 / SVG 等二进制或文本）。
 */
export function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1200)
}

/**
 * SVG 字符串 → PNG Blob（默认 2x 高清）。
 * @param {string} svgText 完整 SVG 文档
 * @param {{ width: number, height: number, scale?: number }} size
 */
export function svgToPngBlob(svgText, { width, height, scale = 2 }) {
  const w = Math.max(1, Math.ceil(width))
  const h = Math.max(1, Math.ceil(height))
  const s = Math.max(1, Number(scale) || 2)

  return new Promise((resolve, reject) => {
    const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const img = new Image()
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = Math.round(w * s)
        canvas.height = Math.round(h * s)
        const ctx = canvas.getContext('2d')
        if (!ctx) {
          URL.revokeObjectURL(url)
          reject(new Error('Canvas 不可用'))
          return
        }
        ctx.fillStyle = '#f7f8fa'
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        ctx.setTransform(s, 0, 0, s, 0, 0)
        ctx.drawImage(img, 0, 0, w, h)
        canvas.toBlob(
          (png) => {
            URL.revokeObjectURL(url)
            if (!png) reject(new Error('PNG 生成失败'))
            else resolve(png)
          },
          'image/png',
        )
      } catch (err) {
        URL.revokeObjectURL(url)
        reject(err)
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('SVG 加载失败，无法导出 PNG'))
    }
    img.src = url
  })
}

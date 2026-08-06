/**
 * 页内播放：优先用后端 /api/embed（B 站带 cid）；本地也可拼 YouTube。
 */

export function parseTimestampToSeconds(ts) {
  if (ts == null || ts === '') return 0
  if (typeof ts === 'number' && Number.isFinite(ts)) return Math.max(0, Math.floor(ts))
  const raw = String(ts).trim()
  const parts = raw.split(':').map((p) => Number(p))
  if (parts.some((n) => Number.isNaN(n))) return 0
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + Math.floor(parts[2])
  if (parts.length === 2) return parts[0] * 60 + Math.floor(parts[1])
  if (parts.length === 1) return Math.floor(parts[0])
  return 0
}

/** 把任意形式的 start 规范化为 mm:ss 或 hh:mm:ss 字符串用于展示。
 *  接受：数字 / '6' / '6.5' / '6s' / '00:06' / '1:02:03' 等。
 *  无法解析时返回空串。
 */
export function formatTimestampForDisplay(ts) {
  if (ts == null) return ''
  if (typeof ts === 'number' && Number.isFinite(ts)) {
    const sec = Math.max(0, Math.floor(ts))
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    const s = sec % 60
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  let s = String(ts).trim()
  if (!s) return ''
  // 去掉尾部 's' / '秒'
  s = s.replace(/(秒|[sS])$/, '').trim()
  // mm:ss 或 hh:mm:ss
  const m = s.match(/^(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?$/)
  if (m) {
    if (m[3] != null) return `${Number(m[1])}:${m[2].padStart(2, '0')}:${m[3].padStart(2, '0')}`
    return `${m[1].padStart(2, '0')}:${m[2].padStart(2, '0')}`
  }
  // 纯数字 / 浮点 → 当作秒
  const num = Number(s)
  if (Number.isFinite(num) && num >= 0) {
    return formatTimestampForDisplay(num)
  }
  return ''
}

/** 用已有 player 信息（含 cid）拼带跳转的嵌入地址 */
export function buildEmbedUrlFromPlayer(player, startSeconds = 0) {
  if (!player) return null
  const t = Math.max(0, Math.floor(startSeconds || 0))
  const provider = player.provider || player.Provider

  if (provider === 'bilibili') {
    const params = new URLSearchParams({
      page: '1',
      high_quality: '1',
      danmaku: '0',
      autoplay: t > 0 ? '1' : '0',
      as_wide: '1',
    })
    if (player.bvid) params.set('bvid', player.bvid)
    if (player.aid) params.set('aid', String(player.aid))
    if (player.cid) params.set('cid', String(player.cid))
    if (t > 0) params.set('t', String(t))
    return {
      provider: 'bilibili',
      embedUrl: `https://player.bilibili.com/player.html?${params.toString()}`,
    }
  }

  if (provider === 'youtube') {
    const id = player.video_id
    if (!id) {
      const raw = player.embed_url || player.embedUrl || ''
      const m = raw.match(/embed\/([^?&/]+)/)
      if (!m) return null
      const params = new URLSearchParams({ rel: '0', modestbranding: '1' })
      if (t > 0) params.set('start', String(t))
      return { provider: 'youtube', embedUrl: `https://www.youtube.com/embed/${m[1]}?${params}` }
    }
    const params = new URLSearchParams({ rel: '0', modestbranding: '1' })
    if (t > 0) params.set('start', String(t))
    return {
      provider: 'youtube',
      embedUrl: `https://www.youtube.com/embed/${id}?${params.toString()}`,
    }
  }

  const base = player.embed_url || player.embedUrl
  if (!base) return null
  return { provider: provider || 'unknown', embedUrl: base }
}

/** 前端轻量兜底（无 cid）；优先仍应用后端 player */
export function resolveEmbedPlayer(pageUrl, opts = {}) {
  const url = (pageUrl || '').trim()
  if (!url) return null
  const startSeconds = Math.max(0, Math.floor(opts.startSeconds || 0))

  if (/bilibili\.com|b23\.tv/i.test(url) || String(opts.extractor || '').toLowerCase().includes('bili')) {
    const bv = url.match(/BV[\w]+/i)?.[0]
    const aid = url.match(/\/av(\d+)/i)?.[1]
    if (!bv && !aid) return null
    const params = new URLSearchParams({
      page: '1',
      high_quality: '1',
      danmaku: '0',
      autoplay: '0',
      as_wide: '1',
    })
    if (bv) params.set('bvid', bv)
    if (aid) params.set('aid', aid)
    if (opts.cid) params.set('cid', String(opts.cid))
    if (startSeconds > 0) params.set('t', String(startSeconds))
    return {
      provider: 'bilibili',
      embedUrl: `https://player.bilibili.com/player.html?${params.toString()}`,
    }
  }

  try {
    const u = new URL(url)
    let id = null
    if (u.hostname.includes('youtu.be')) id = u.pathname.replace(/^\//, '').split('/')[0]
    else if (u.hostname.includes('youtube.com')) {
      id = u.searchParams.get('v')
      if (!id && u.pathname.startsWith('/shorts/')) id = u.pathname.split('/')[2]
    }
    if (id) {
      const params = new URLSearchParams({ rel: '0', modestbranding: '1' })
      if (startSeconds > 0) params.set('start', String(startSeconds))
      return {
        provider: 'youtube',
        embedUrl: `https://www.youtube.com/embed/${id}?${params.toString()}`,
      }
    }
  } catch {
    /* ignore */
  }
  return null
}

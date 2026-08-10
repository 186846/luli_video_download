/**
 * 轻量 SEO head 更新（无第三方依赖）。
 * 用于路由切换与总结页动态标题，不改业务逻辑。
 */

const SITE_ORIGIN = 'https://saveany.cc'

const HOME_SEO = {
  title: '万能视频下载与AI总结 - 速下 SpeedyDL | 粘贴链接一键保存',
  description:
    '速下 SpeedyDL 支持粘贴链接一键解析下载公开视频，覆盖 B 站、YouTube 等主流平台，并提供 AI 视频总结、字幕导出与思维导图。免费使用，仅供个人学习，请尊重版权。',
  keywords:
    '万能视频下载,AI视频总结,视频下载,B站视频下载,YouTube下载,视频解析,字幕导出,思维导图,速下,SpeedyDL',
  robots: 'index, follow',
  canonicalPath: '/',
  ogType: 'website',
}

const SUMMARY_DEFAULT_SEO = {
  title: 'AI视频总结 - 速下 SpeedyDL | 摘要字幕思维导图',
  description:
    '速下 SpeedyDL 的 AI 视频总结页：查看摘要、字幕、弹幕整理与思维导图，支持导出。仅供个人学习。',
  keywords: 'AI视频总结,视频摘要,字幕导出,思维导图,速下,SpeedyDL',
  robots: 'noindex, follow',
  canonicalPath: '/summary',
  ogType: 'website',
}

function ensureMeta(attr, key, content) {
  if (content == null || content === '') return
  let el = document.head.querySelector(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function ensureLink(rel, href) {
  if (!href) return
  let el = document.head.querySelector(`link[rel="${rel}"]`)
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}

function absoluteUrl(path) {
  if (!path) return SITE_ORIGIN + '/'
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  return SITE_ORIGIN + (path.startsWith('/') ? path : `/${path}`)
}

/**
 * @param {Partial<typeof HOME_SEO> & { image?: string }} seo
 */
export function applySeo(seo = {}) {
  const title = seo.title ?? HOME_SEO.title
  const description = seo.description ?? HOME_SEO.description
  const keywords = seo.keywords ?? HOME_SEO.keywords
  const robots = seo.robots ?? HOME_SEO.robots
  const canonical = absoluteUrl(seo.canonicalPath ?? HOME_SEO.canonicalPath)
  const image = absoluteUrl(seo.image ?? '/og-image.png')
  const ogType = seo.ogType ?? HOME_SEO.ogType
  const ogTitle = seo.ogTitle ?? title
  const ogDescription = seo.ogDescription ?? description

  document.title = title

  ensureMeta('name', 'description', description)
  ensureMeta('name', 'keywords', keywords)
  ensureMeta('name', 'robots', robots)

  ensureMeta('property', 'og:title', ogTitle)
  ensureMeta('property', 'og:description', ogDescription)
  ensureMeta('property', 'og:image', image)
  ensureMeta('property', 'og:type', ogType)
  ensureMeta('property', 'og:url', canonical)
  ensureMeta('property', 'og:locale', 'zh_CN')
  ensureMeta('property', 'og:site_name', '速下 SpeedyDL')

  ensureMeta('name', 'twitter:card', 'summary_large_image')
  ensureMeta('name', 'twitter:title', ogTitle)
  ensureMeta('name', 'twitter:description', ogDescription)
  ensureMeta('name', 'twitter:image', image)

  ensureMeta('itemprop', 'name', ogTitle)
  ensureMeta('itemprop', 'description', ogDescription)
  ensureMeta('itemprop', 'image', image)

  ensureLink('canonical', canonical)
}

export function seoFromRoute(route) {
  const base = route.meta?.seo
  if (!base) {
    applySeo(HOME_SEO)
    return
  }
  applySeo(base)
}

export { HOME_SEO, SUMMARY_DEFAULT_SEO, SITE_ORIGIN }

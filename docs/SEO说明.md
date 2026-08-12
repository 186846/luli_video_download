# 速下 SpeedyDL — SEO 说明



> 关联：[鱼厂 SEO 优化工作流](./鱼厂%20SEO%20优化工作流.md) · [GEO 优化入门指南](./GEO优化入门指南.md) · [部署文档](./部署文档.md)  

> 代码仓库：[https://github.com/186846/luli_video_download](https://github.com/186846/luli_video_download)



当前为 **Vue SPA 基础档 SEO + GEO 扩展**（无 SSR）。占位正式域名为 **`https://saveany.cc`**。



## 1. 已落地能力



| 项 | 位置 |

|----|------|

| 首页 TDK / OG / Twitter / robots / canonical | `web/index.html` |

| `theme-color` / `color-scheme` | `web/index.html` |

| Schema.org itemprop | `web/index.html` |

| JSON-LD（WebApplication + Organization + FAQPage + HowTo） | `web/index.html` |

| `noscript` 静态正文兜底（结论先行 + FAQ + 步骤） | `web/index.html` |

| 路由级动态 head | `web/src/composables/useSeo.js` + `web/src/router/index.js` |

| `/summary` | `noindex, follow`（不进 sitemap） |

| `robots.txt`（含 AI 爬虫显式 Allow） / `sitemap.xml` | `web/public/` |

| `llms.txt`（给 LLM / Agent 的站点说明） | `web/public/llms.txt` |

| 首页可见「常见问题」 | `web/src/components/FaqSection.vue`（`#faq`） |

| 分享图 / Apple 图标 / favicon | `web/public/og-image.png`、`apple-touch-icon.png`、`favicon.svg` |

| Footer 关键词内链 + FAQ / llms.txt | `web/src/components/AppFooter.vue` |

| 语义化区块（H1/H2、aria-labelledby、nav aria-label、封面 alt） | `HeroSection` / 各 Section / `AppHeader` / `HistoryPanel` 等 |



## 2. 换正式域名（全局替换）



将下列文件中的 **`https://saveany.cc`** 替换为真实域名（勿漏尾部路径一致性）：



1. `web/index.html`（canonical、og:url、og:image、twitter:image、itemprop、JSON-LD、noscript 内链等）

2. `web/public/robots.txt`（`Sitemap:` 行）

3. `web/public/sitemap.xml`（所有 `<loc>`）

4. `web/public/llms.txt`（正文中的全部绝对 URL）

5. `web/src/composables/useSeo.js`（常量 `SITE_ORIGIN`）



替换后重新 `npm run build` 并部署 `web/dist`。



## 3. 资源路径约定



| 资源 | URL |

|------|-----|

| OG 分享图（1200×630） | `/og-image.png` |

| Apple Touch Icon（180×180） | `/apple-touch-icon.png` |

| Favicon | `/favicon.svg` |

| Sitemap | `/sitemap.xml` |

| Robots | `/robots.txt` |

| LLM 说明 | `/llms.txt` |

| 常见问题锚点 | `/#faq` |



## 4. 上线后提交搜索引擎（人工）



站点可公网访问后，将 `https://你的域名/sitemap.xml` 提交到：



- [Google Search Console](https://search.google.com/search-console)

- [百度搜索资源平台](https://ziyuan.baidu.com/)

- [Bing Webmaster Tools](https://www.bing.com/webmasters)

- [360 搜索资源平台](https://zhanzhang.so.com/) 及其他需要的国内站长平台



可用 [Google Rich Results Test](https://search.google.com/test/rich-results) 校验 FAQ / HowTo / WebApplication 结构化数据。



## 5. GEO 检验（人工）



公网可访问后，用下列问题分别问 ChatGPT、Gemini、Perplexity，记录是否提到「速下 / SpeedyDL / saveany.cc」：



1. 有没有免费的在线视频下载工具，还支持 AI 总结？

2. B 站 / YouTube 公开视频怎么下载到本地学习用？

3. 什么工具可以根据字幕做视频摘要和思维导图？



站内给 AI 的权威摘要入口：`https://你的域名/llms.txt`。



## 6. 已知局限



- 纯 SPA：百度等对 JS 渲染支持有限；`noscript` + `llms.txt` 提供可读正文，深度收录仍可能需要预渲染 / SSR。

- `/summary` 依赖本地会话，故意不收录，避免薄内容与重复页。

- `keywords` meta 对 Google 权重极低，主要为国内引擎与站内约定保留。

- 站外权威外链、知乎/媒体曝光属运营动作，不在本仓库代码范围内。



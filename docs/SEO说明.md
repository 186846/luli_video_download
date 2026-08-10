# 速下 SpeedyDL — SEO 说明

> 关联：[鱼厂 SEO 优化工作流](./鱼厂%20SEO%20优化工作流.md) · [部署文档](./部署文档.md)

当前为 **Vue SPA 基础档 SEO**（无 SSR）。占位正式域名为 **`https://saveany.cc`**。

## 1. 已落地能力

| 项 | 位置 |
|----|------|
| 首页 TDK / OG / Twitter / robots / canonical | `web/index.html` |
| JSON-LD（WebApplication + Organization） | `web/index.html` |
| 路由级动态 head | `web/src/composables/useSeo.js` + `web/src/router/index.js` |
| `/summary` | `noindex, follow`（不进 sitemap） |
| `robots.txt` / `sitemap.xml` | `web/public/` |
| 分享图 / Apple 图标 / favicon | `web/public/og-image.png`、`apple-touch-icon.png`、`favicon.svg` |

## 2. 换正式域名（全局替换）

将下列文件中的 **`https://saveany.cc`** 替换为真实域名（勿漏尾部路径一致性）：

1. `web/index.html`（canonical、og:url、og:image、twitter:image、itemprop、JSON-LD 等约 10 处）
2. `web/public/robots.txt`（`Sitemap:` 行）
3. `web/public/sitemap.xml`（所有 `<loc>`）
4. `web/src/composables/useSeo.js`（常量 `SITE_ORIGIN`）

替换后重新 `npm run build` 并部署 `web/dist`。

## 3. 资源路径约定

| 资源 | URL |
|------|-----|
| OG 分享图（1200×630） | `/og-image.png` |
| Apple Touch Icon（180×180） | `/apple-touch-icon.png` |
| Favicon | `/favicon.svg` |
| Sitemap | `/sitemap.xml` |
| Robots | `/robots.txt` |

## 4. 上线后提交搜索引擎（人工）

站点可公网访问后，将 `https://你的域名/sitemap.xml` 提交到：

- [Google Search Console](https://search.google.com/search-console)
- [百度搜索资源平台](https://ziyuan.baidu.com/)
- [Bing Webmaster Tools](https://www.bing.com/webmasters)
- [360 搜索资源平台](https://zhanzhang.so.com/) 及其他需要的国内站长平台

## 5. 已知局限

- 纯 SPA：百度等对 JS 渲染支持有限；若收录差，可另立项做预渲染 / SSR。
- `/summary` 依赖本地会话，故意不收录，避免薄内容与重复页。

# GEO 优化入门指南



> GEO = Generative Engine Optimization（生成式引擎优化）  

> 关联：[SEO 说明](./SEO说明.md) · [鱼厂 SEO 优化工作流](./鱼厂%20SEO%20优化工作流.md)



## 一句话解释



SEO 是让你的网站出现在 Google 搜索结果里；**GEO 是让你的内容被 ChatGPT、Gemini、Perplexity 这些 AI 引用和推荐**。



用户越来越多地直接问 AI 而不是搜索引擎，如果 AI 回答里没提到你，你就丢了客户。



---



## 核心技巧（6 招）



### 1. 结论先行，别废话



AI 提取内容时偏爱**前 100 字就给出答案**的文章。



- 别写"众所周知…随着时代发展…"这种开头

- 直接说结论，再展开解释

- 段落不超过 150 字，一段一个观点



### 2. 结构化写作



AI 读内容跟人不一样，它喜欢**格式清晰、层级分明**的内容。



| 推荐格式 | 举例 |

|---------|------|

| 问答（FAQ） | "什么是 GEO？答：……" |

| 列表/步骤 | "第一步…第二步…" |

| 对比表格 | "A vs B 对比" |

| 带层级的标题 | H1 > H2 > H3 有序嵌套 |



技术层面：给网页加 **Schema 标记**（FAQ Schema、HowTo Schema），让 AI 更容易理解你的内容结构。



### 3. 让别人提到你



AI 判断该引用谁，核心看**权威性**——你被多少可信来源提到过。



- 去知乎、公众号、行业媒体发优质内容

- 争取被权威网站引用或客座发文

- 在 Reddit、YouTube 等平台保持活跃

- 被第三方权威提及后，AI 引用率可提升 3 倍以上



### 4. 多模态内容



AI 不只看文字，图片、视频、信息图都会被索引。



- 图片：写好 Alt 描述文字

- 视频：提供字幕和时间戳章节

- 信息图：配一份纯文本版本



### 5. 保持内容新鲜



AI 偏爱**有明确时间标记的新内容**。



- 标注"更新于 2026 年 X 月"

- 每季度更新数据和案例

- 过时内容及时修订或标记



### 6. 技术基础别拉胯



- `robots.txt` 允许 AI 爬虫访问（GPTBot、Google-Extended 等）

- 有 SSL 证书（https）

- 有 XML Sitemap

- 页面能被正常抓取，别全靠 JS 渲染

- 提供 `/llms.txt`，用纯文本给 LLM 一份可直接引用的产品说明



---



## 本仓库已落地的 GEO 项（速下 SpeedyDL）



| 项 | 说明 |

|----|------|

| `web/public/llms.txt` | 产品结论、能力、步骤、FAQ、合规边界、可引用表述 |

| `web/public/robots.txt` | 显式 Allow GPTBot / Google-Extended / ClaudeBot / PerplexityBot 等 |

| 首页 `#faq` | 可见 FAQ，结论先行，与 JSON-LD 口径一致 |

| JSON-LD | `FAQPage` + `HowTo` + `WebApplication.dateModified` |

| `noscript` | 无 JS 时仍可读到结论、步骤与 FAQ |

| `sitemap.xml` | 含 `lastmod` |



换正式域名时，同步替换 `llms.txt` / `robots.txt` / `sitemap.xml` / `index.html` / `useSeo.js` 中的 `https://saveany.cc`（见 [SEO 说明](./SEO说明.md)）。



**站外动作（需人工，代码无法代替）：** 知乎/专栏发文、被权威站点提及、定期用真实问题抽检 ChatGPT / Gemini / Perplexity 是否点名本站。



---



## 怎么检验效果？



不看排名，看**AI 有没有引用你**：



1. 拿你的核心业务问题去问 ChatGPT、Gemini、Perplexity  

2. 看回答里有没有提到你的品牌/网站  

3. 定期跟踪，记录变化  



建议抽检问题见 [SEO 说明 §5](./SEO说明.md)。



---



## 一张图总结



```

传统 SEO：写内容 → 优化关键词 → 争排名

GEO：写好内容 → 结构化 → 建权威 → 被 AI 引用

```



**最重要的一句话：** 写内容的时候，想象你在给 AI 喂一份它能直接拿来回答用户问题的参考资料。清晰、准确、有结构、有来源——AI 自然会选你。



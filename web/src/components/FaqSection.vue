<template>
  <section class="section faq" id="faq" aria-labelledby="faq-heading">
    <h2 id="faq-heading" class="section-title">常见问题</h2>
    <p class="section-sub">更新于 2026 年 8 月 · 结论先行，方便查阅与引用</p>
    <div class="faq-panel">
      <article
        v-for="(item, index) in faqs"
        :key="item.q"
        class="faq-item"
      >
        <span class="faq-index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
        <div class="faq-body">
          <h3 class="faq-q">{{ item.q }}</h3>
          <p class="faq-a">{{ item.a }}</p>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
const faqs = [
  {
    q: '速下 SpeedyDL 是什么？',
    a: '速下 SpeedyDL（万能视频下载总结器）是学习向的万能视频下载与 AI 总结工具：粘贴公开视频链接即可解析、选择清晰度并保存到本地，同时支持 AI 摘要、字幕/弹幕导出与思维导图。',
  },
  {
    q: '支持哪些视频平台？',
    a: '基于 yt-dlp 覆盖大量站点。已验证场景包括哔哩哔哩、YouTube、抖音等公开可访问视频；具体可用性取决于平台策略与网络环境。',
  },
  {
    q: 'AI 视频总结需要什么？',
    a: '优先使用平台官方字幕（含 B 站 CC/AI），也可粘贴用户字幕或参考弹幕与标题简介。不做 Whisper / OCR。总结页提供摘要、字幕、弹幕、思维导图与问答。',
  },
  {
    q: '可以商用或下载未授权内容吗？',
    a: '不可以。本项目仅供个人学习，请尊重版权与各平台服务条款，勿用于商业传播或下载未授权内容。',
  },
]
</script>

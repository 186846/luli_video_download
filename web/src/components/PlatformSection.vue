<template>
  <section class="section platforms" id="platforms-section">
    <h2 class="section-title">支持主流平台</h2>
    <p class="section-sub">站在 yt-dlp 肩膀上，覆盖海量站点（以公开可访问内容为准）</p>
    <div class="card-grid">
      <article class="card platform-card">
        <div class="card-visual card-visual--bili" aria-hidden="true">
          <span class="card-visual__glow" />
          <span class="card-visual__ring" />
          <svg class="card-icon" viewBox="0 0 64 64" fill="none">
            <rect x="8" y="18" width="48" height="32" rx="8" fill="#fff" fill-opacity="0.95" />
            <path d="M20 14l6 6M44 14l-6 6" stroke="#fff" stroke-width="3.5" stroke-linecap="round" />
            <circle cx="26" cy="34" r="4" fill="#00A1D6" />
            <circle cx="38" cy="34" r="4" fill="#00A1D6" />
            <path d="M24 42h16" stroke="#00A1D6" stroke-width="3" stroke-linecap="round" />
          </svg>
        </div>
        <h3>哔哩哔哩</h3>
        <p class="card-tags">学习 · UP主 · 公开稿件</p>
      </article>
      <article class="card platform-card">
        <div class="card-visual card-visual--yt" aria-hidden="true">
          <span class="card-visual__glow" />
          <span class="card-visual__ring" />
          <svg class="card-icon" viewBox="0 0 64 64" fill="none">
            <rect x="6" y="16" width="52" height="32" rx="12" fill="#fff" fill-opacity="0.96" />
            <path d="M28 26v12l12-6-12-6z" fill="#FF0000" />
          </svg>
        </div>
        <h3>YouTube</h3>
        <p class="card-tags">国际 · 高清 · 公开视频</p>
      </article>
      <article class="card platform-card">
        <div class="card-visual card-visual--dy" aria-hidden="true">
          <span class="card-visual__glow" />
          <span class="card-visual__ring" />
          <svg class="card-icon" viewBox="0 0 64 64" fill="none">
            <rect x="20" y="8" width="24" height="48" rx="6" fill="#fff" fill-opacity="0.95" />
            <rect x="24" y="14" width="16" height="28" rx="2" fill="#111" />
            <circle cx="32" cy="48" r="2.5" fill="#111" />
            <path
              d="M34 22c2 0 4-1.5 4-4M34 22v10a4 4 0 11-2-3.5"
              stroke="#25F4EE"
              stroke-width="2.2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              d="M34 22c2 0 4-1.5 4-4M34 22v10a4 4 0 11-2-3.5"
              stroke="#FE2C55"
              stroke-width="2.2"
              stroke-linecap="round"
              stroke-linejoin="round"
              transform="translate(1.2 0.8)"
              opacity="0.85"
            />
          </svg>
        </div>
        <h3>短视频</h3>
        <p class="card-tags">抖音 / TikTok · 无水印尝试</p>
      </article>
      <article class="card platform-card">
        <div class="card-visual card-visual--more" aria-hidden="true">
          <span class="card-visual__glow" />
          <span class="card-visual__ring" />
          <svg class="card-icon card-icon--wide" viewBox="0 0 72 64" fill="none">
            <circle cx="36" cy="32" r="18" stroke="#fff" stroke-opacity="0.35" stroke-width="2" />
            <circle cx="36" cy="32" r="8" fill="#fff" fill-opacity="0.95" />
            <circle cx="18" cy="18" r="4" fill="#fff" fill-opacity="0.9" />
            <circle cx="54" cy="16" r="3.5" fill="#fff" fill-opacity="0.85" />
            <circle cx="56" cy="42" r="4.5" fill="#fff" fill-opacity="0.9" />
            <circle cx="16" cy="44" r="3" fill="#fff" fill-opacity="0.8" />
            <path
              d="M22 20l10 8M50 18l-10 10M52 40l-10-6M20 42l12-6"
              stroke="#fff"
              stroke-opacity="0.55"
              stroke-width="1.6"
            />
            <text
              x="36"
              y="36"
              text-anchor="middle"
              fill="#1777FF"
              font-size="9"
              font-weight="800"
              font-family="Sora, sans-serif"
            >1k+</text>
          </svg>
        </div>
        <h3>更多站点</h3>
        <p class="card-tags">yt-dlp · 持续更新</p>
      </article>
    </div>
  </section>
</template>

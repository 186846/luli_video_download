<script setup>
defineProps({
  isVip: { type: Boolean, default: false },
})

const emit = defineEmits(['open-vip'])
</script>

<template>
  <section class="section pricing" id="pricing" aria-labelledby="pricing-heading">
    <h2 id="pricing-heading" class="section-title">简单定价</h2>
    <p class="section-sub">学习演示 · 不接真实支付 · 本地一键解锁体验会员权益</p>
    <div class="pricing-grid">
      <article class="price-card">
        <h3>免费</h3>
        <p class="price"><span>¥0</span></p>
        <ul>
          <li>解析公开视频</li>
          <li>最高 720p</li>
          <li>单视频下载 / 直链</li>
        </ul>
        <button type="button" class="btn btn-outline" disabled>当前方案</button>
      </article>
      <article class="price-card price-card--vip">
        <div class="price-badge">推荐</div>
        <h3>演示会员</h3>
        <p class="price"><span class="old">¥99</span> <span class="now">¥0 演示</span></p>
        <ul>
          <li>1080p / 更高清晰度</li>
          <li>批量下载（占位）</li>
          <li>AI 能力优先体验</li>
        </ul>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="isVip"
          @click="emit('open-vip')"
        >
          {{ isVip ? '已开通演示会员' : '立即开通（演示）' }}
        </button>
      </article>
    </div>
  </section>
</template>

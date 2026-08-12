<script setup>
import { VIP_PRICE_USD } from '../api/payment'

defineProps({
  isVip: { type: Boolean, default: false },
})

const emit = defineEmits(['open-vip'])
</script>

<template>
  <section class="section pricing" id="pricing" aria-labelledby="pricing-heading">
    <h2 id="pricing-heading" class="section-title">简单定价</h2>
    <p class="section-sub">
      登录后免费每天 3 次 AI 总结；永久会员不限次数，并解锁 1080p+（Stripe 一次性 $9.90）
    </p>
    <div class="pricing-grid">
      <article class="price-card">
        <h3>免费</h3>
        <p class="price"><span>$0</span></p>
        <ul>
          <li>解析公开视频</li>
          <li>最高 720p</li>
          <li>AI 总结每天 3 次（需登录）</li>
        </ul>
        <button type="button" class="btn btn-outline" disabled>当前方案</button>
      </article>
      <article class="price-card price-card--vip">
        <div class="price-badge">推荐</div>
        <h3>永久会员</h3>
        <p class="price"><span class="now">${{ VIP_PRICE_USD }} USD</span></p>
        <ul>
          <li>1080p / 更高清晰度</li>
          <li>AI 总结不限次数</li>
          <li>一次付费，账号长期有效</li>
        </ul>
        <button
          type="button"
          class="btn btn-primary"
          :disabled="isVip"
          @click="emit('open-vip')"
        >
          {{ isVip ? '已开通永久会员' : `立即开通 $${VIP_PRICE_USD}` }}
        </button>
      </article>
    </div>
  </section>
</template>

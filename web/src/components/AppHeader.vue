<script setup>
defineProps({
  isVip: { type: Boolean, default: false },
  isLoggedIn: { type: Boolean, default: false },
  email: { type: String, default: '' },
})

const emit = defineEmits(['vip-click', 'account-click'])
</script>

<template>
  <header class="site-header">
    <div class="header-inner">
      <a
        class="brand"
        href="/"
        title="速下 SpeedyDL - 万能视频下载与AI总结"
        aria-label="速下 SpeedyDL 首页"
        @click.prevent="$router.push('/')"
      >
        <span class="brand-mark" aria-hidden="true" />
        <span class="brand-text">速下 <small>SpeedyDL</small></span>
      </a>
      <nav class="nav" aria-label="主导航">
        <a href="#download">下载</a>
        <a href="#history">历史</a>
        <a href="#pricing">定价</a>
        <a href="#about">关于</a>
      </nav>
      <div class="header-actions">
        <button
          v-if="isLoggedIn"
          type="button"
          class="btn btn-ghost btn-sm"
          :title="email"
          @click="emit('account-click')"
        >
          {{ isVip ? '会员' : '账号' }}
        </button>
        <button
          type="button"
          class="btn btn-ghost btn-sm"
          :class="{ 'is-vip': isVip }"
          @click="emit('vip-click')"
        >
          {{ isVip ? '永久会员' : '开通会员' }}
        </button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.header-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
</style>

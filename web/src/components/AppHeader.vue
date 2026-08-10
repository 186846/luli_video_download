<script setup>
defineProps({
  isVip: { type: Boolean, default: false },
})

const emit = defineEmits(['vip-click'])
</script>

<template>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="/" aria-label="速下 SpeedyDL" @click.prevent="$router.push('/')">
        <span class="brand-mark" aria-hidden="true" />
        <span class="brand-text">速下 <small>SpeedyDL</small></span>
      </a>
      <nav class="nav">
        <a href="#download">下载</a>
        <a href="#history">历史</a>
        <a href="#pricing">定价</a>
        <a href="#about">关于</a>
      </nav>
      <button
        type="button"
        class="btn btn-ghost btn-sm"
        :class="{ 'is-vip': isVip }"
        @click="emit('vip-click')"
      >
        {{ isVip ? '演示会员已开通' : '演示会员' }}
      </button>
    </div>
  </header>
</template>

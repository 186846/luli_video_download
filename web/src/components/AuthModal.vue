<script setup>
defineProps({
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'confirm'])
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="vip-modal-title"
      @click.self="emit('close')"
    >
      <div class="modal-card">
        <h3 id="vip-modal-title">开通演示会员</h3>
        <p>
          这是<strong>学习演示</strong>，不会产生真实扣款。开通后本地记住会员状态，可解锁 1080p+ 清晰度。
        </p>
        <div class="modal-actions">
          <button type="button" class="btn btn-outline" @click="emit('close')">取消</button>
          <button type="button" class="btn btn-primary" @click="emit('confirm')">确认开通</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

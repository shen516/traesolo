<template>
  <div class="state-block" :class="`state-${type}`">
    <span v-if="icon" class="state-icon">{{ icon }}</span>
    <span class="state-text">
      <slot>{{ text }}</slot>
    </span>
    <button
      v-if="type === 'error' && retryText"
      type="button"
      class="btn btn-sm state-retry"
      @click="$emit('retry')"
    >{{ retryText }}</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  /** loading | empty | error */
  type: { type: String, required: true },
  text: { type: String, default: '' },
  retryText: { type: String, default: '' },
})

defineEmits(['retry'])

const icon = computed(() => ({
  loading: '⏳',
  empty: '📭',
  error: '⚠️',
}[props.type] || ''))
</script>

<style scoped>
.state-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: 40px var(--space-md);
  border-radius: var(--radius-md);
  border: 1px dashed var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-muted);
  font-size: var(--font-md);
}

.state-block.state-error {
  color: var(--color-red);
  border-color: rgba(var(--color-red-rgb), 0.4);
}

.state-icon {
  font-size: 20px;
}

.state-loading .state-icon {
  animation: state-spin 1s linear infinite;
}

@keyframes state-spin {
  to { transform: rotate(360deg); }
}
</style>

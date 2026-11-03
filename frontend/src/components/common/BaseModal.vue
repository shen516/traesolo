<template>
  <Teleport to="body">
    <Transition name="base-modal">
      <div
        v-if="modelValue"
        class="base-modal-overlay"
        @click.self="onOverlayClick"
      >
        <div class="base-modal" :style="{ width, maxWidth }">
          <div class="base-modal-header">
            <slot name="header" :title="title">
              <h3 class="base-modal-title">{{ title }}</h3>
            </slot>
            <button
              v-if="closable"
              type="button"
              class="base-modal-close"
              @click="close"
            >✕</button>
          </div>
          <div class="base-modal-body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="base-modal-footer">
            <slot name="footer" :close="close" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
const props = defineProps({
  modelValue: { type: Boolean, required: true },
  title: { type: String, default: '' },
  width: { type: String, default: '520px' },
  maxWidth: { type: String, default: 'calc(100vw - 48px)' },
  closable: { type: Boolean, default: true },
  /** 点击遮罩是否可关闭 */
  closeOnOverlay: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue', 'close'])

function close() {
  if (!props.closable) return
  emit('update:modelValue', false)
  emit('close')
}

function onOverlayClick() {
  if (props.closeOnOverlay) close()
}
</script>

<style scoped>
.base-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal, 1000);
  padding: var(--space-lg);
}

.base-modal {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 64px);
  overflow: hidden;
}

.base-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--border-color);
}

.base-modal-header > :first-child:not(.base-modal-close) {
  flex: 1;
  min-width: 0;
}

.base-modal-title {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--text-primary);
}

.base-modal-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: var(--font-md);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: var(--transition);
}

.base-modal-close:hover {
  color: var(--color-red);
  background: rgba(var(--color-red-rgb), 0.1);
}

.base-modal-body {
  padding: var(--space-lg);
  overflow-y: auto;
}

.base-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--border-color);
}

/* 过渡动画 */
.base-modal-enter-active,
.base-modal-leave-active {
  transition: opacity 0.2s ease;
}
.base-modal-enter-active .base-modal,
.base-modal-leave-active .base-modal {
  transition: transform 0.2s ease;
}
.base-modal-enter-from,
.base-modal-leave-to {
  opacity: 0;
}
.base-modal-enter-from .base-modal,
.base-modal-leave-to .base-modal {
  transform: translateY(-12px) scale(0.98);
}
</style>

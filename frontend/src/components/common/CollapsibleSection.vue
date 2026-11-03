<template>
  <div class="collapsible-section card">
    <button type="button" class="collapsible-header" @click="expanded = !expanded">
      <h2 class="collapsible-title">{{ title }}</h2>
      <span class="collapsible-sub" v-if="subtitle">{{ subtitle }}</span>
      <span class="collapsible-arrow" :class="{ open: expanded }">▾</span>
    </button>
    <div v-show="expanded" class="collapsible-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  defaultOpen: { type: Boolean, default: false },
})

const expanded = ref(props.defaultOpen)
</script>

<style scoped>
.collapsible-section {
  padding: 0;
  overflow: hidden;
}

.collapsible-header {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 16px 20px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.collapsible-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.collapsible-sub {
  flex: 1;
  font-size: 12px;
  color: var(--text-muted);
}

.collapsible-arrow {
  font-size: 14px;
  color: var(--text-muted);
  transition: transform 0.2s;
}

.collapsible-arrow.open {
  transform: rotate(180deg);
}

.collapsible-body {
  padding: 0 20px 20px;
}
</style>

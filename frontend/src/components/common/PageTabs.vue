<template>
  <div class="page-tabs">
    <template v-for="tab in tabs" :key="tab.key">
      <router-link
        v-if="routeBase"
        :to="tabRoute(tab.key)"
        class="page-tab"
        :class="{ active: modelValue === tab.key }"
      >
        {{ tab.label }}
        <span v-if="tab.badge" class="tab-badge">{{ tab.badge }}</span>
      </router-link>
      <button
        v-else
        type="button"
        class="page-tab"
        :class="{ active: modelValue === tab.key }"
        @click="$emit('update:modelValue', tab.key)"
      >
        {{ tab.label }}
        <span v-if="tab.badge" class="tab-badge">{{ tab.badge }}</span>
      </button>
    </template>
  </div>
</template>

<script setup>
const props = defineProps({
  tabs: { type: Array, required: true },
  modelValue: { type: String, required: true },
  routeBase: { type: String, default: '' },
})

defineEmits(['update:modelValue'])

function tabRoute(key) {
  const base = props.routeBase.replace(/\/$/, '')
  return `${base}/${key}`
}
</script>

<style scoped>
.page-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  margin-bottom: 16px;
  background: var(--bg-secondary, rgba(0, 0, 0, 0.2));
  border-radius: 10px;
  border: 1px solid var(--border-color);
  flex-wrap: wrap;
}

.page-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  text-decoration: none;
}

.page-tab:hover {
  color: var(--text-primary);
  background: var(--bg-hover, rgba(255, 255, 255, 0.04));
}

.page-tab.active {
  background: var(--bg-active, rgba(59, 130, 246, 0.15));
  color: var(--accent-blue, #3b82f6);
}

.tab-badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--accent-red, #ef4444);
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}
</style>

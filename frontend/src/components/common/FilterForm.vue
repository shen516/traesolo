<template>
  <div class="filter-form card">
    <slot />
    <div v-if="showActions" class="filter-actions">
      <slot name="actions">
        <button type="button" class="btn btn-primary" @click="$emit('search')">{{ searchText }}</button>
        <button type="button" class="btn" @click="$emit('reset')">{{ resetText }}</button>
      </slot>
    </div>
  </div>
</template>

<script setup>
defineProps({
  showActions: { type: Boolean, default: true },
  searchText: { type: String, default: '查询' },
  resetText: { type: String, default: '重置' },
})

defineEmits(['search', 'reset'])
</script>

<style scoped>
.filter-form {
  display: flex;
  align-items: flex-end;
  gap: var(--space-md);
  flex-wrap: wrap;
  padding: var(--space-md) var(--space-lg);
}

.filter-form > :deep(.form-group),
.filter-form > :deep(.filter-item) {
  min-width: 140px;
}

.filter-actions {
  display: flex;
  gap: var(--space-sm);
  margin-left: auto;
}
</style>

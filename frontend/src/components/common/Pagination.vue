<template>
  <div v-if="totalPages > 1" class="pagination-bar">
    <span class="pagination-info">
      共 {{ total }} 条 · 第 {{ page }}/{{ totalPages }} 页
    </span>
    <div class="pagination-btns">
      <button
        class="page-btn"
        :disabled="page <= 1"
        @click="change(page - 1)"
      >‹</button>
      <button
        v-for="p in visiblePages"
        :key="p"
        class="page-btn"
        :class="{ active: p === page }"
        @click="change(p)"
      >{{ p }}</button>
      <button
        class="page-btn"
        :disabled="page >= totalPages"
        @click="change(page + 1)"
      >›</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  page: { type: Number, required: true },
  pageSize: { type: Number, default: 20 },
  total: { type: Number, required: true },
})

const emit = defineEmits(['change'])

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

const visiblePages = computed(() => {
  const pages = []
  const maxVisible = 5
  let start = Math.max(1, props.page - Math.floor(maxVisible / 2))
  let end = Math.min(totalPages.value, start + maxVisible - 1)
  if (end - start + 1 < maxVisible) {
    start = Math.max(1, end - maxVisible + 1)
  }
  for (let i = start; i <= end; i++) {
    pages.push(i)
  }
  return pages
})

function change(p) {
  if (p >= 1 && p <= totalPages.value && p !== props.page) {
    emit('change', p)
  }
}
</script>

<style scoped>
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.pagination-info {
  font-size: var(--font-sm);
  color: var(--text-muted);
}

.pagination-btns {
  display: flex;
  gap: var(--space-xs);
  flex-wrap: wrap;
}

.page-btn {
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: var(--font-sm);
  cursor: pointer;
  transition: var(--transition);
}

.page-btn:hover:not(:disabled) {
  border-color: var(--color-blue);
  color: var(--color-blue);
}

.page-btn.active {
  background: var(--bg-hover);
  border-color: var(--color-blue);
  color: var(--color-blue);
  font-weight: 700;
}

.page-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>

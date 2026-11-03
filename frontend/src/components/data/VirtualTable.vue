<template>
  <div
    ref="containerRef"
    class="virtual-table-wrap"
    :style="{ maxHeight: height + 'px' }"
    @scroll="onScroll"
  >
    <div class="virtual-table-head-wrap">
      <table class="data-table virtual-table">
        <thead>
          <slot name="head" />
        </thead>
      </table>
    </div>
    <div class="virtual-table-body-scroller" :style="{ height: bodyHeight + 'px' }">
      <div :style="{ height: totalHeight + 'px', position: 'relative' }">
        <table
          class="data-table virtual-table virtual-table-body"
          :style="{ transform: `translateY(${offsetY}px)` }"
        >
          <tbody>
            <tr
              v-for="(row, i) in visibleItems"
              :key="resolveKey(row, startIndex + i)"
            >
              <slot name="row" :row="row" :index="startIndex + i" />
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div v-if="!items.length" class="virtual-empty">
      <slot name="empty">暂无数据</slot>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  rowHeight: { type: Number, default: 44 },
  height: { type: Number, default: 360 },
  rowKey: { type: [String, Function], default: 'id' },
  overscan: { type: Number, default: 6 },
})

const containerRef = ref(null)
const scrollTop = ref(0)
const headHeight = ref(40)

const bodyHeight = computed(() => Math.max(120, props.height - headHeight.value))
const totalHeight = computed(() => props.items.length * props.rowHeight)
const startIndex = computed(() => {
  const idx = Math.floor(scrollTop.value / props.rowHeight)
  return Math.max(0, idx - props.overscan)
})
const endIndex = computed(() => {
  const visible = Math.ceil(bodyHeight.value / props.rowHeight) + props.overscan * 2
  return Math.min(props.items.length, startIndex.value + visible)
})
const visibleItems = computed(() => props.items.slice(startIndex.value, endIndex.value))
const offsetY = computed(() => startIndex.value * props.rowHeight)

function onScroll(e) {
  scrollTop.value = e.target.scrollTop
}

function resolveKey(row, index) {
  if (typeof props.rowKey === 'function') return props.rowKey(row, index)
  return row?.[props.rowKey] ?? index
}

function measureHead() {
  nextTick(() => {
    const head = containerRef.value?.querySelector('.virtual-table-head-wrap thead')
    if (head) headHeight.value = head.offsetHeight || 40
  })
}

watch(() => props.items.length, measureHead)
onMounted(measureHead)
onBeforeUnmount(() => {})
</script>

<style scoped>
.virtual-table-wrap {
  overflow-y: auto;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-secondary, rgba(0, 0, 0, 0.15));
}

.virtual-table-head-wrap {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--bg-secondary, #142847);
}

.virtual-table {
  width: 100%;
  border-collapse: collapse;
}

.virtual-table-head-wrap .virtual-table {
  margin-bottom: 0;
}

.virtual-table-body-scroller {
  overflow: hidden;
}

.virtual-table th,
.virtual-table td {
  padding: 10px 12px;
  text-align: left;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color);
}

.virtual-table th {
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
}

.virtual-empty {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}
</style>

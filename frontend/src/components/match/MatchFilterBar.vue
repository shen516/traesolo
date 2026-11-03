<template>
  <div class="filter-bar card">
    <div class="filter-main">
      <div class="filter-section">
        <span class="filter-label">联赛</span>
        <select
          :value="league"
          class="filter-select"
          @change="onLeagueChange"
        >
          <option value="all">{{ followedOnly ? '关注的联赛' : '全部联赛' }}</option>
          <option v-for="item in leagues" :key="item.id" :value="item.id">
            {{ item.icon }} {{ item.name }}
          </option>
        </select>
      </div>
      <label class="filter-check">
        <input
          type="checkbox"
          :checked="followedOnly"
          @change="onFollowedOnlyChange"
        />
        仅关注
      </label>
      <label v-if="followedOnly" class="filter-check">
        <input
          type="checkbox"
          :checked="followsStore.includeChildren"
          @change="onIncludeChildrenChange"
        />
        含下级
      </label>

      <div class="filter-section">
        <span class="filter-label">日期</span>
        <input
          v-if="dateMode === 'input'"
          :value="date"
          type="date"
          class="date-input"
          :min="dateMin"
          @change="onDateInput"
        />
        <select
          v-else
          :value="date"
          class="date-select"
          @change="onDateSelect"
        >
          <option value="all">全部日期</option>
          <option v-for="d in availableDates" :key="d" :value="d">{{ d }}</option>
        </select>
        <button
          v-if="dateMode === 'input' && date"
          type="button"
          class="date-clear"
          @click="$emit('clear-date')"
        >全部</button>
      </div>

      <div class="filter-section search-section">
        <span class="filter-label">球队</span>
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input
            :value="keyword"
            class="search-input"
            placeholder="搜索球队名称..."
            @input="onKeywordInput"
            @keyup.enter="$emit('change')"
          />
        </div>
      </div>

      <button type="button" class="btn btn-sm filter-toggle" @click="$emit('update:expanded', !expanded)">
        {{ expanded ? '收起筛选' : '更多筛选' }}
      </button>

      <div class="filter-density">
        <button
          type="button"
          class="density-btn"
          :class="{ active: density === 'compact' }"
          @click="$emit('update:density', 'compact')"
        >紧凑</button>
        <button
          type="button"
          class="density-btn"
          :class="{ active: density === 'full' }"
          @click="$emit('update:density', 'full')"
        >详细</button>
      </div>
    </div>

    <div v-show="expanded" class="filter-extra">
      <div class="filter-section">
        <span class="filter-label">类型</span>
        <select :value="category" class="filter-select" @change="onCategoryChange">
          <option value="all">全部类型</option>
          <option v-for="cat in categories" :key="cat" :value="cat">
            {{ categoryLabel(cat) }}
          </option>
        </select>
      </div>

      <div class="filter-section">
        <span class="filter-label">国家</span>
        <select :value="country" class="filter-select" @change="onCountryChange">
          <option value="all">全部国家</option>
          <option v-for="c in countries" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
    </div>

    <div v-if="$slots.result" class="filter-result">
      <slot name="result" />
    </div>
  </div>
</template>

<script setup>
import { useFollowsStore } from '@/stores/follows'

const followsStore = useFollowsStore()

defineProps({
  league: { type: String, default: 'all' },
  date: { type: String, default: '' },
  keyword: { type: String, default: '' },
  expanded: { type: Boolean, default: false },
  density: { type: String, default: 'compact' },
  category: { type: String, default: 'all' },
  country: { type: String, default: 'all' },
  leagues: { type: Array, default: () => [] },
  countries: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
  categoryLabel: { type: Function, default: (c) => c },
  dateMode: { type: String, default: 'input' },
  dateMin: { type: String, default: '' },
  availableDates: { type: Array, default: () => [] },
  followedOnly: { type: Boolean, default: false },
})

const emit = defineEmits([
  'update:league', 'update:date', 'update:keyword', 'update:expanded',
  'update:density', 'update:category', 'update:country', 'update:followedOnly',
  'change', 'category-change', 'country-change', 'clear-date',
])

function onLeagueChange(e) {
  emit('update:league', e.target.value)
  emit('change')
}

function onFollowedOnlyChange(e) {
  emit('update:followedOnly', e.target.checked)
  emit('update:league', 'all')
  emit('change')
}

async function onIncludeChildrenChange(e) {
  await followsStore.setIncludeChildren(e.target.checked)
  emit('change')
}

function onDateInput(e) {
  emit('update:date', e.target.value)
  emit('change')
}

function onDateSelect(e) {
  emit('update:date', e.target.value)
  emit('change')
}

function onKeywordInput(e) {
  emit('update:keyword', e.target.value)
}

function onCategoryChange(e) {
  emit('update:category', e.target.value)
  emit('category-change')
}

function onCountryChange(e) {
  emit('update:country', e.target.value)
  emit('country-change')
}
</script>

<style scoped>
.filter-bar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
}

.filter-main,
.filter-extra {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}

.filter-extra {
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.filter-toggle { margin-left: auto; }

.filter-density {
  display: flex;
  gap: 4px;
  padding: 2px;
  background: var(--bg-primary);
  border-radius: 6px;
  border: 1px solid var(--border-color);
}

.density-btn {
  padding: 4px 10px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
}

.density-btn.active {
  background: var(--bg-active, rgba(59, 130, 246, 0.15));
  color: var(--accent-blue, #3b82f6);
}

.filter-section {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
}

.filter-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}

.filter-select,
.date-select {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 6px 12px;
  color: var(--text-primary);
  font-size: 12px;
  outline: none;
  height: 30px;
  cursor: pointer;
  min-width: 120px;
}

.filter-select:focus,
.date-select:focus { border-color: var(--color-blue); }

.date-input {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 6px 12px;
  color: var(--text-primary);
  font-size: 12px;
  height: 30px;
}

.date-clear {
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 0 10px;
  height: 30px;
}

.search-input {
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
  outline: none;
  width: 140px;
}

.filter-result {
  font-size: 12px;
  color: var(--text-muted);
  padding-top: 4px;
}

:deep(.result-count) {
  color: var(--color-gold);
  font-weight: 700;
}
</style>

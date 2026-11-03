<template>
  <div v-if="visible" class="drawer-overlay" @click.self="close">
    <aside class="drawer-panel card">
      <div class="drawer-header">
        <div class="drawer-title">
          <MediaImg
            v-if="parentLeague"
            :src="parentLeague.logo"
            :fallback="parentLeague.icon || '⚽'"
            size="sm"
            :alt="parentLeague.name"
          />
          <div>
            <h3>{{ parentLeague?.name || '子联赛' }}</h3>
            <span class="drawer-subtitle">子联赛列表 · 共 {{ total }} 个</span>
          </div>
        </div>
        <button class="close-btn" @click="close">×</button>
      </div>

      <div v-if="loading" class="drawer-loading">
        <span class="spinner"></span>
        <span>加载中...</span>
      </div>

      <div v-else-if="error" class="drawer-error">
        <span>{{ error }}</span>
        <button class="link-btn" @click="fetchChildren">重试</button>
      </div>

      <div v-else class="drawer-body">
        <table class="data-table">
          <thead>
            <tr>
              <th>联赛</th>
              <th>级别</th>
              <th>球队</th>
              <th>赛事</th>
              <th v-if="manageMode">状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="league in children" :key="league.id">
              <td>
                <div class="league-cell">
                  <MediaImg :src="league.logo" :fallback="league.icon || '⚽'" size="sm" :alt="league.name" />
                  <span>{{ league.name }}</span>
                </div>
              </td>
              <td>{{ levelName(league.level) }}</td>
              <td>{{ league.teams_count || 0 }}</td>
              <td>{{ league.matches_count || 0 }}</td>
              <td v-if="manageMode">
                <span class="tag" :class="league.is_active ? 'tag-low' : 'tag-high'">
                  {{ league.is_active ? '启用' : '禁用' }}
                </span>
              </td>
              <td>
                <button
                  class="link-btn"
                  :class="{ followed: isFollowed(league.id) }"
                  @click="toggleFollow(league)"
                >{{ isFollowed(league.id) ? '已关注' : '关注' }}</button>
                <button class="link-btn" @click="$emit('detail', league)">详情</button>
                <template v-if="manageMode">
                  <button class="link-btn" @click="$emit('edit', league)">编辑</button>
                  <button class="link-btn" @click="$emit('toggle', league)">
                    {{ league.is_active ? '禁用' : '启用' }}
                  </button>
                </template>
              </td>
            </tr>
            <tr v-if="children.length === 0">
              <td :colspan="manageMode ? 6 : 5" class="empty-row">暂无子联赛</td>
            </tr>
          </tbody>
        </table>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { leagueApi } from '@/api'
import { useFollowsStore } from '@/stores/follows'

const followsStore = useFollowsStore()
const isFollowed = (id) => followsStore.isFollowed(id)

const props = defineProps({
  visible: { type: Boolean, default: false },
  parentLeague: { type: Object, default: null },
  manageMode: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'detail', 'edit', 'toggle'])

const loading = ref(false)
const error = ref(null)
const children = ref([])
const total = ref(0)

async function toggleFollow(league) {
  if (!league?.id) return
  try {
    await followsStore.toggle(league.id, league)
  } catch (e) {
    error.value = e?.message || '关注操作失败'
  }
}

function levelName(level) {
  if (level === 1) return '顶级'
  if (level === 2) return '次级'
  if (level === 3) return '三级'
  return '未知'
}

function close() {
  emit('close')
}

async function fetchChildren() {
  if (!props.parentLeague?.id) return
  loading.value = true
  error.value = null
  try {
    const res = await leagueApi.getChildren(props.parentLeague.id)
    children.value = res.leagues || []
    total.value = res.total || 0
  } catch (e) {
    error.value = e?.message || '加载子联赛失败'
    children.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.visible, props.parentLeague?.id],
  ([vis]) => {
    if (vis && props.parentLeague?.id) fetchChildren()
  },
  { immediate: true }
)

defineExpose({ fetchChildren })
</script>

<style scoped>
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 1100;
  display: flex;
  justify-content: flex-end;
}

.drawer-panel {
  width: min(560px, 92vw);
  height: 100%;
  border-radius: 0;
  display: flex;
  flex-direction: column;
  animation: slideIn 0.25s ease;
}

@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-color);
}

.drawer-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.drawer-title h3 {
  margin: 0 0 4px;
  font-size: 18px;
  color: var(--text-primary);
}

.drawer-subtitle {
  font-size: 12px;
  color: var(--text-muted);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 28px;
  cursor: pointer;
  line-height: 1;
}

.close-btn:hover { color: var(--text-primary); }

.drawer-loading,
.drawer-error {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 24px;
  color: var(--text-secondary);
  font-size: 14px;
}

.drawer-body {
  flex: 1;
  overflow: auto;
  padding: 16px 24px 24px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 10px 8px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.data-table th {
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 12px;
}

.league-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.empty-row {
  text-align: center;
  color: var(--text-muted);
  padding: 24px 0 !important;
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-blue);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
}

.link-btn:hover { text-decoration: underline; }
.link-btn.followed { color: var(--color-gold); }

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(var(--color-blue-rgb), 0.3);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>

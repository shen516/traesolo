<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">联赛管理</h1>
      <p class="page-subtitle">管理联赛的启用/禁用状态，定时任务仅采集启用的联赛数据</p>
    </div>

    <StateBlock v-if="loading" type="loading" text="数据加载中..." />

    <StateBlock
      v-else-if="error"
      type="error"
      :text="error"
      retry-text="重试"
      @retry="fetchLeagues"
    />

    <div class="overview-grid">
      <div class="overview-card card" v-for="s in statsCards" :key="s.label">
        <div class="overview-icon" :style="{ background: s.bg, color: s.color }">{{ s.icon }}</div>
        <div class="overview-info">
          <div class="overview-value" :style="{ color: s.color }">{{ s.value }}</div>
          <div class="overview-label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2 class="card-title">联赛列表</h2>
        <div class="card-actions">
          <button class="refresh-btn" @click="fetchLeagues" :disabled="loading">
            <span v-if="loading" class="btn-spinner"></span>
            刷新
          </button>
          <button class="btn btn-sm" @click="runBackfillParents" :disabled="backfilling">
            {{ backfilling ? '回填中...' : '回填父子关系' }}
          </button>
          <button class="btn btn-primary btn-sm" @click="openCreateDialog">+ 新增联赛</button>
        </div>
      </div>

      <FilterForm @search="onFilterChange" @reset="resetFilters">
        <div class="form-group">
          <label>关键词</label>
          <input
            v-model="filters.keyword"
            placeholder="联赛名称"
            @keyup.enter="onFilterChange"
            class="form-input"
          />
        </div>
        <div class="form-group">
          <label>赛事类型</label>
          <select v-model="filters.category" class="form-select" @change="onFilterChange">
            <option :value="null">全部</option>
            <option value="international">国际赛事</option>
            <option value="europe">欧洲赛事</option>
            <option value="america">美洲赛事</option>
            <option value="asia">亚洲赛事</option>
            <option value="africa">非洲赛事</option>
          </select>
        </div>
        <div class="form-group">
          <label>国家</label>
          <select v-model="filters.country" class="form-select" @change="onFilterChange">
            <option :value="null">全部</option>
            <option v-for="c in countries" :key="c.country" :value="c.country">
              {{ c.flag }} {{ c.country }}
            </option>
          </select>
        </div>
        <div class="form-group">
          <label>状态</label>
          <select v-model="filters.is_active" class="form-select" @change="onFilterChange">
            <option :value="null">全部</option>
            <option :value="true">启用</option>
            <option :value="false">禁用</option>
          </select>
        </div>
        <label class="filter-check">
          <input type="checkbox" :checked="filters.level === 1" @change="toggleTopLevel" />
          仅顶级联赛
        </label>
      </FilterForm>

      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>图标</th>
              <th>联赛名称</th>
              <th>赛事类型</th>
              <th>国家</th>
              <th>球队数</th>
              <th>赛事数</th>
              <th>子联赛</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="league in leagues" :key="league.id">
              <td>
                <MediaImg :src="league.logo" :fallback="league.icon || '⚽'" size="sm" :alt="league.name" />
              </td>
              <td>
                <div class="name-cell">
                  <span>{{ league.name }}</span>
                  <span class="tag tag-mid">{{ league.id }}</span>
                </div>
              </td>
              <td><span class="tag tag-mid">{{ getCategoryName(league.category) }}</span></td>
              <td>{{ league.flag || '' }} {{ league.country || '-' }}</td>
              <td>{{ league.teams_count || 0 }}</td>
              <td>{{ league.matches_count || 0 }}</td>
              <td>
                <button
                  v-if="league.children_count > 0"
                  class="link-btn"
                  @click="openChildrenDrawer(league)"
                >{{ league.children_count }} 个</button>
                <span v-else class="text-muted">-</span>
              </td>
              <td>
                <span class="tag" :class="league.is_active ? 'tag-low' : 'tag-high'">
                  {{ league.is_active ? '启用' : '禁用' }}
                </span>
              </td>
              <td>
                <button
                  v-if="league.children_count > 0"
                  class="link-btn"
                  @click="openChildrenDrawer(league)"
                >子联赛</button>
                <button class="link-btn" @click="openEditDialog(league)">编辑</button>
                <button class="link-btn" @click="toggleActive(league)">
                  {{ league.is_active ? '禁用' : '启用' }}
                </button>
                <button class="link-btn link-danger" @click="deleteLeague(league)">删除</button>
              </td>
            </tr>
            <tr v-if="leagues.length === 0">
              <td colspan="9" class="empty-row">暂无联赛数据</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="total > 0" class="list-footer">
        <Pagination
          :page="currentPage"
          :page-size="pageSize"
          :total="total"
          @change="goToPage"
        />
        <select v-model="pageSize" class="page-size-select" @change="fetchLeagues">
          <option :value="10">10条/页</option>
          <option :value="20">20条/页</option>
          <option :value="50">50条/页</option>
          <option :value="100">100条/页</option>
        </select>
      </div>
    </div>

    <BaseModal
      v-model="leagueDialogVisible"
      :title="editMode ? '编辑联赛' : '新增联赛'"
      width="620px"
    >
      <div class="form-grid">
        <div class="form-group">
          <label><span class="required">*</span>联赛ID</label>
          <input v-model="leagueForm.id" :disabled="editMode" placeholder="例如：EPL" />
        </div>
        <div class="form-group">
          <label><span class="required">*</span>联赛名称</label>
          <input v-model="leagueForm.name" placeholder="例如：英超联赛" />
        </div>
        <div class="form-group">
          <label>图标（emoji）</label>
          <input v-model="leagueForm.icon" placeholder="例如：🏴" />
        </div>
        <div class="form-group">
          <label>赛事类型</label>
          <select v-model="leagueForm.category">
            <option value="international">国际赛事</option>
            <option value="europe">欧洲赛事</option>
            <option value="america">美洲赛事</option>
            <option value="asia">亚洲赛事</option>
            <option value="africa">非洲赛事</option>
          </select>
        </div>
        <div class="form-group">
          <label>国家</label>
          <input v-model="leagueForm.country" placeholder="例如：英格兰" />
        </div>
        <div class="form-group">
          <label>国旗（emoji）</label>
          <input v-model="leagueForm.flag" placeholder="例如：🏴" />
        </div>
        <div class="form-group">
          <label>地区</label>
          <select v-model="leagueForm.region">
            <option value="欧洲">欧洲</option>
            <option value="亚洲">亚洲</option>
            <option value="美洲">美洲</option>
            <option value="非洲">非洲</option>
            <option value="国际">国际</option>
          </select>
        </div>
        <div class="form-group">
          <label>级别</label>
          <select v-model="leagueForm.level">
            <option :value="1">顶级联赛</option>
            <option :value="2">次级联赛</option>
            <option :value="3">三级联赛</option>
          </select>
        </div>
        <div class="form-group" v-if="leagueForm.level > 1">
          <label>上级联赛</label>
          <select v-model="leagueForm.parent_id">
            <option :value="null">自动推断</option>
            <option v-for="p in rootLeagues" :key="p.id" :value="p.id">
              {{ p.country ? p.country + ' · ' : '' }}{{ p.name }}
            </option>
          </select>
        </div>
        <div class="form-group">
          <label>平均进球数</label>
          <input v-model.number="leagueForm.avg_goals" type="number" step="0.1" placeholder="2.7" />
        </div>
        <div class="form-group" v-if="editMode">
          <label>启用状态</label>
          <select v-model="leagueForm.is_active">
            <option :value="true">启用</option>
            <option :value="false">禁用</option>
          </select>
        </div>
      </div>
      <template #footer>
        <button class="btn" @click="leagueDialogVisible = false">取消</button>
        <button class="btn btn-primary" @click="saveLeague" :disabled="saving">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </template>
    </BaseModal>

    <LeagueChildrenDrawer
      ref="childrenDrawerRef"
      :visible="childrenDrawerVisible"
      :parent-league="childrenParent"
      manage-mode
      @close="childrenDrawerVisible = false"
      @edit="onChildEdit"
      @toggle="onChildToggle"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { leagueApi } from '@/api'
import LeagueChildrenDrawer from '@/components/league/LeagueChildrenDrawer.vue'
import Pagination from '@/components/common/Pagination.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import BaseModal from '@/components/common/BaseModal.vue'
import FilterForm from '@/components/common/FilterForm.vue'

const loading = ref(false)
const saving = ref(false)
const backfilling = ref(false)
const error = ref(null)

const leagues = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const allCountries = ref([])

const countries = computed(() => {
  if (!filters.category || filters.category === 'international') {
    return allCountries.value
  }
  return allCountries.value
})

const filters = reactive({
  keyword: '',
  category: null,
  country: null,
  is_active: null,
  level: 1,
})

const rootLeagues = ref([])
const childrenDrawerVisible = ref(false)
const childrenParent = ref(null)
const childrenDrawerRef = ref(null)

const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

const categoryNames = {
  international: '国际赛事',
  europe: '欧洲赛事',
  america: '美洲赛事',
  asia: '亚洲赛事',
  africa: '非洲赛事'
}

function getCategoryName(category) {
  return categoryNames[category] || category || '-'
}

const statsCards = computed(() => {
  const totalLeagues = total.value
  const active = leagues.value.filter(l => l.is_active).length
  const disabled = leagues.value.length - active
  const europe = leagues.value.filter(l => l.category === 'europe').length
  const asia = leagues.value.filter(l => l.category === 'asia').length
  return [
    { label: '总联赛数', value: totalLeagues, icon: '⚽', color: 'var(--color-blue)', bg: 'rgba(var(--color-blue-rgb), 0.12)' },
    { label: '已启用', value: active, icon: '✅', color: 'var(--color-green)', bg: 'rgba(var(--color-green-rgb), 0.12)' },
    { label: '已禁用', value: disabled, icon: '⛔', color: 'var(--color-red)', bg: 'rgba(var(--color-red-rgb), 0.12)' },
    { label: '欧洲赛事', value: europe, icon: '🇪🇺', color: 'var(--color-gold)', bg: 'rgba(var(--color-gold-rgb), 0.12)' },
    { label: '亚洲赛事', value: asia, icon: '🌏', color: 'var(--color-orange)', bg: 'rgba(var(--color-orange-rgb), 0.12)' }
  ]
})

const leagueDialogVisible = ref(false)
const editMode = ref(false)
const currentLeague = ref(null)
const leagueForm = reactive({
  id: '',
  name: '',
  icon: '',
  category: 'international',
  country: '',
  flag: '',
  region: '欧洲',
  level: 1,
  parent_id: null,
  avg_goals: 2.7,
  is_active: true
})

async function runBackfillParents() {
  if (!confirm('将根据联赛名称与国家推断 parent_id，补齐父子关系。是否继续？')) return
  backfilling.value = true
  error.value = null
  try {
    const res = await leagueApi.backfillParents()
    await fetchLeagues()
    await fetchRootLeagues()
    alert(`回填完成，更新 ${res.updated ?? 0} 条联赛`)
  } catch (e) {
    error.value = e?.message || '回填失败'
  } finally {
    backfilling.value = false
  }
}

async function fetchRootLeagues() {
  try {
    const res = await leagueApi.getRoots()
    rootLeagues.value = res.leagues || []
  } catch (e) {
    console.error('Failed to fetch root leagues:', e)
  }
}

function openChildrenDrawer(league) {
  childrenParent.value = league
  childrenDrawerVisible.value = true
}

function onChildEdit(league) {
  childrenDrawerVisible.value = false
  openEditDialog(league)
}

async function onChildToggle(league) {
  await toggleActive(league)
  await fetchLeagues()
  childrenParent.value = leagues.value.find(l => l.id === childrenParent.value?.id) || childrenParent.value
  childrenDrawerRef.value?.fetchChildren()
}

async function fetchLeagues() {
  loading.value = true
  error.value = null
  try {
    const res = await leagueApi.getList({
      page: currentPage.value,
      page_size: pageSize.value,
      ...filters
    })
    leagues.value = res.leagues || []
    total.value = res.total || 0
  } catch (e) {
    error.value = e?.message || '数据加载失败'
  } finally {
    loading.value = false
  }
}

async function fetchCountries() {
  try {
    const res = await leagueApi.getCountries()
    allCountries.value = res.countries || []
  } catch (e) {
    console.error('Failed to fetch countries:', e)
  }
}

function onFilterChange() {
  currentPage.value = 1
  fetchLeagues()
}

function toggleTopLevel(e) {
  filters.level = e.target.checked ? 1 : null
  onFilterChange()
}

function resetFilters() {
  filters.keyword = ''
  filters.category = null
  filters.country = null
  filters.is_active = null
  filters.level = 1
  currentPage.value = 1
  fetchLeagues()
}

function goToPage(page) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    fetchLeagues()
  }
}

function openCreateDialog() {
  editMode.value = false
  currentLeague.value = null
  Object.assign(leagueForm, {
    id: '',
    name: '',
    icon: '',
    category: 'international',
    country: '',
    flag: '',
    region: '欧洲',
    level: 1,
    parent_id: null,
    avg_goals: 2.7,
    is_active: true
  })
  leagueDialogVisible.value = true
}

function openEditDialog(league) {
  editMode.value = true
  currentLeague.value = league
  Object.assign(leagueForm, {
    id: league.id,
    name: league.name,
    icon: league.icon || '',
    category: league.category || 'international',
    country: league.country || '',
    flag: league.flag || '',
    region: league.region || '欧洲',
    level: league.level || 1,
    parent_id: league.parent_id || null,
    avg_goals: league.avg_goals || 2.7,
    is_active: league.is_active !== false
  })
  leagueDialogVisible.value = true
}

async function saveLeague() {
  if (!leagueForm.id || !leagueForm.name) {
    error.value = '联赛ID和名称不能为空'
    return
  }

  saving.value = true
  error.value = null
  try {
    const data = {
      id: leagueForm.id,
      name: leagueForm.name,
      icon: leagueForm.icon || null,
      category: leagueForm.category,
      country: leagueForm.country || null,
      flag: leagueForm.flag || null,
      region: leagueForm.region,
      level: leagueForm.level,
      parent_id: leagueForm.level > 1 ? leagueForm.parent_id : null,
      avg_goals: leagueForm.avg_goals,
      is_active: leagueForm.is_active
    }
    if (editMode.value) {
      await leagueApi.update(leagueForm.id, data)
    } else {
      await leagueApi.create(data)
    }
    leagueDialogVisible.value = false
    await fetchLeagues()
  } catch (e) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function toggleActive(league) {
  const action = league.is_active ? '禁用' : '启用'
  if (!confirm(`确认${action}联赛 "${league.name}" 吗？`)) return
  try {
    await leagueApi.toggleActive(league.id)
    await fetchLeagues()
  } catch (e) {
    error.value = e?.message || `${action}失败`
  }
}

async function deleteLeague(league) {
  if (!confirm(`确认删除联赛 "${league.name}" 吗？此操作不可恢复！`)) return
  try {
    await leagueApi.delete(league.id)
    await fetchLeagues()
  } catch (e) {
    error.value = e?.message || '删除失败'
  }
}

onMounted(() => {
  fetchLeagues()
  fetchCountries()
  fetchRootLeagues()
})
</script>

<style scoped>
.page-container {
  height: 100%;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header { margin-bottom: 4px; }
.page-title { font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }
.page-subtitle { font-size: 13px; color: var(--text-muted); }

.overview-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}
.overview-card { display: flex; align-items: center; gap: 14px; }
.overview-icon {
  width: 44px; height: 44px; border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; flex-shrink: 0;
}
.overview-info { display: flex; flex-direction: column; }
.overview-value { font-size: 20px; font-weight: 700; line-height: 1.2; }
.overview-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

.card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px;
}
.card-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.card-actions { display: flex; align-items: center; gap: 12px; }

.refresh-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: transparent;
  color: var(--text-secondary); font-size: 13px; cursor: pointer;
  transition: var(--transition);
}
.refresh-btn:hover:not(:disabled) {
  border-color: var(--color-blue); color: var(--color-blue);
}
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(var(--color-blue-rgb), 0.3);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.filter-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.text-muted {
  color: var(--text-muted);
  font-size: 12px;
}

.table-wrapper { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th, .data-table td {
  padding: 10px 12px; text-align: left;
  border-bottom: 1px solid var(--border-color);
}
.data-table th {
  background: var(--bg-secondary); color: var(--text-secondary);
  font-weight: 600; font-size: 12px;
  position: sticky; top: 0; z-index: 1;
}
.data-table tbody tr:hover { background: var(--bg-hover); }
.empty-row { text-align: center; color: var(--text-muted); padding: 24px 0 !important; }

.link-btn {
  background: none; border: none; color: var(--color-blue);
  cursor: pointer; font-size: 12px; padding: 2px 6px;
  margin-right: 4px; transition: var(--transition);
}
.link-btn:hover { text-decoration: underline; }
.link-danger { color: var(--color-red); }

.form-grid {
  display: grid; grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; color: var(--text-secondary); }
.required { color: var(--color-red); margin-right: 2px; }
.form-group input,
.form-group select {
  padding: 8px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-primary); font-size: 14px;
}
.form-group input:focus,
.form-group select:focus { outline: none; border-color: var(--color-blue); }
.form-group input:disabled { opacity: 0.5; cursor: not-allowed; }

.list-footer {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 12px; padding: 16px 0;
}
.page-size-select {
  padding: 6px 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-primary); font-size: 12px; cursor: pointer;
}
</style>

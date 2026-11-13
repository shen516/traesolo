<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">我的模拟投注</h1>
      <p class="page-subtitle">仅作学习与研究，模拟数据，不构成投注建议，不接入真实资金</p>
    </div>

    <!-- 加载 / 错误 / 空态 -->
    <div v-if="loading" class="state-banner loading-banner">
      <span class="spinner"></span>
      <span>数据加载中...</span>
    </div>
    <div v-if="error" class="state-banner error-banner">
      <span>⚠️ {{ error }}</span>
      <button class="retry-btn" @click="loadAll()">重试</button>
    </div>

    <!-- 统计卡 -->
    <div class="overview-grid">
      <div class="overview-card card" v-for="s in statCards" :key="s.label">
        <div class="overview-icon" :style="{ background: s.bg, color: s.color }">{{ s.icon }}</div>
        <div class="overview-info">
          <div class="overview-value" :style="{ color: s.color }">{{ s.value }}</div>
          <div class="overview-label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2 class="card-title">投注记录</h2>
        <div class="card-actions">
          <select v-model="filterStatus" class="filter-select" @change="reloadList">
            <option value="">全部状态</option>
            <option value="pending">待开赛</option>
            <option value="won">已中</option>
            <option value="lost">未中</option>
            <option value="void">作废</option>
          </select>
          <select v-model="filterPlayType" class="filter-select" @change="reloadList">
            <option value="">全部玩法</option>
            <option value="spf">胜平负</option>
            <option value="nspf">让球胜平负</option>
            <option value="bf">比分</option>
            <option value="tg">总进球</option>
            <option value="hspf">半场胜平负</option>
          </select>
          <input v-model="filterDateFrom" type="date" class="filter-input" title="创建日期起" @change="reloadList" />
          <span class="date-sep">至</span>
          <input v-model="filterDateTo" type="date" class="filter-input" title="创建日期止" @change="reloadList" />
          <button class="btn btn-sm btn-outline" @click="clearDateFilter">清除日期</button>
        </div>
      </div>

      <div v-if="!bets.length && !loading" class="empty-hint">
        <p>暂无模拟投注</p>
        <router-link to="/simulation" class="btn btn-sm btn-primary">去模拟预测</router-link>
      </div>

      <div v-else class="bet-table-wrap">
        <table class="bet-table">
          <thead>
            <tr>
              <th>场次</th>
              <th>玩法</th>
              <th>选项</th>
              <th>下单 SP</th>
              <th>金额</th>
              <th>状态</th>
              <th>派奖</th>
              <th>结算时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in groupedBets" :key="g.key">
              <tr v-for="(b, li) in g.legs" :key="b.id">
                <td>
                  <div class="bet-match">{{ b.match_name || b.match_no || b.match_id }}</div>
                  <div class="bet-meta">
                    <span v-if="g.isParlay" class="parlay-badge">串关 {{ li + 1 }}/{{ g.legs.length }}</span>
                    <span v-if="li === 0 && g.isParlay"> 组合 {{ g.key.slice(3, 9) }}</span>
                    <span v-else>{{ b.match_no || b.match_id }}</span>
                  </div>
                </td>
                <td><span class="tag tag-low">{{ playLabel(b.play_type) }}</span></td>
                <td class="bet-selection">{{ selectionLabel(b) }}</td>
                <td>{{ fmt(b.sp_at_create) }}</td>
                <td>
                  <template v-if="li === 0">{{ groupStake(g) }}</template>
                </td>
                <td>
                  <template v-if="g.isParlay && li === 0">
                    <span class="tag" :class="statusTagClass(groupStatus(g))">{{ statusLabel(groupStatus(g)) }}</span>
                  </template>
                  <template v-else-if="!g.isParlay">
                    <span class="tag" :class="statusTagClass(b.status)">{{ statusLabel(b.status) }}</span>
                  </template>
                </td>
                <td :class="groupStatus(g) === 'won' ? 'pos' : 'muted'">
                  <template v-if="g.isParlay && li === 0">{{ groupPayout(g) }}</template>
                  <template v-else-if="!g.isParlay">{{ b.status === 'won' ? fmt(b.payout) + ' 元' : '—' }}</template>
                </td>
                <td class="muted">
                  <template v-if="g.isParlay && li === 0">{{ g.legs.find((l) => l.settled_at)?.settled_at || '—' }}</template>
                  <template v-else-if="!g.isParlay">{{ b.settled_at || '—' }}</template>
                </td>
                <td>
                  <template v-if="g.isParlay">
                    <span v-if="li === 0" class="muted">整组结算</span>
                  </template>
                  <template v-else>
                    <button
                      v-if="canWrite && b.status === 'pending'"
                      class="btn btn-sm btn-outline danger"
                      @click="confirmVoid(b)"
                    >作废</button>
                    <span v-else class="muted">{{ canWrite ? '—' : '只读' }}</span>
                  </template>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- B2 上拉加载：触底加载更多（保留分页组件兜底） -->
      <div ref="loadSentinel" class="load-sentinel">
        <span v-if="loadingMore" class="spinner"></span>
        <span v-if="loadingMore">加载更多...</span>
        <span v-else-if="hasMore" class="muted">上拉加载更多</span>
        <span v-else class="muted">已加载全部</span>
      </div>

      <div class="bet-pagination" v-if="totalPages > 1">
        <span class="page-info">第 {{ page }} / {{ totalPages }} 页 · 共 {{ total }} 条</span>
        <div class="page-buttons">
          <button class="btn btn-sm" :disabled="page <= 1" @click="prevPage">上一页</button>
          <button class="btn btn-sm" :disabled="page >= totalPages" @click="nextPage">下一页</button>
        </div>
      </div>
    </div>

    <!-- B1 作废确认弹窗 -->
    <div v-if="voidTarget" class="modal-mask" @click.self="voidTarget = null">
      <div class="modal">
        <h3 class="modal-title">确认作废</h3>
        <p class="modal-text">确定作废这张模拟投注单？作废后该选项可重新提交，作废仅限开赛前整单操作。</p>
        <div class="modal-meta">
          {{ voidTarget.match_name || voidTarget.match_no }} · {{ selectionLabel(voidTarget) }}
        </div>
        <div class="modal-actions">
          <button class="btn btn-sm btn-outline" @click="voidTarget = null">取消</button>
          <button class="btn btn-sm danger" :disabled="voiding" @click="doVoid">
            {{ voiding ? '作废中...' : '确认作废' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { simulationBetApi } from '@/api'
import { hasAnyPermission } from '@/utils/permissions'

const CACHE_KEY = 'sim_bets_cache_v1'
const loading = ref(false)
const error = ref('')
const bets = ref([])
const stats = ref({ total_stake: 0, total_payout: 0, profit: 0, settled: 0, won: 0, hit_rate: null })
const page = ref(1)
const pageSize = 20
const total = ref(0)
const filterStatus = ref('')
const filterPlayType = ref('')
const filterDateFrom = ref('')
const filterDateTo = ref('')

// B1 作废
const canWrite = hasAnyPermission('model:manage')
const voidTarget = ref(null)
const voiding = ref(false)

// B2 上拉加载
const loadingMore = ref(false)
const loadSentinel = ref(null)
let observer = null
const hasMore = computed(() => page.value < totalPages.value)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// 串关组合分组：is_parlay=1 的行按 combination_id 聚合为一组卡片；
// 单关行（is_parlay=0 或空）保持单行。
const groupedBets = computed(() => {
  const groups = []
  const byCid = new Map()
  for (const b of bets.value) {
    if (b.is_parlay && b.combination_id) {
      if (!byCid.has(b.combination_id)) {
        byCid.set(b.combination_id, { key: b.combination_id, isParlay: true, legs: [] })
        groups.push(byCid.get(b.combination_id))
      }
      byCid.get(b.combination_id).legs.push(b)
    } else {
      groups.push({ key: 'single_' + b.id, isParlay: false, legs: [b] })
    }
  }
  return groups
})

// 组合整体状态：取组合内任一非 pending 行状态；全 pending 则 pending。
function groupStatus(g) {
  const settled = g.legs.find((l) => l.status !== 'pending')
  return settled ? settled.status : 'pending'
}
// 组合单注金额（首腿）与整体派奖（取非零）
function groupStake(g) {
  const b = g.legs[0]
  return b ? `${fmt(b.stake)} 元 × ${b.multiple}` : '—'
}
function groupPayout(g) {
  const s = groupStatus(g)
  if (s !== 'won') return '—'
  const b = g.legs.find((l) => l.payout > 0) || g.legs[0]
  return b ? fmt(b.payout) + ' 元' : '—'
}
const statCards = computed(() => [
  {
    icon: '💰', label: '累计模拟投注金额', value: fmt(stats.value.total_stake) + ' 元',
    bg: 'rgba(56,189,248,0.15)', color: '#38bdf8',
  },
  {
    icon: '🏆', label: '累计模拟派奖', value: fmt(stats.value.total_payout) + ' 元',
    bg: 'rgba(52,211,153,0.15)', color: '#34d399',
  },
  {
    icon: '📊', label: '累计模拟盈亏', value: fmt(stats.value.profit) + ' 元',
    bg: stats.value.profit >= 0 ? 'rgba(52,211,153,0.15)' : 'rgba(239,68,68,0.15)',
    color: stats.value.profit >= 0 ? '#34d399' : '#ef4444',
  },
  {
    icon: '🎯', label: '命中率', value: stats.value.hit_rate != null ? (stats.value.hit_rate * 100).toFixed(1) + '%' : '—',
    bg: 'rgba(251,191,36,0.15)', color: '#fbbf24',
  },
])

function fmt(v) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : v
}
function playLabel(p) {
  return { spf: '胜平负', nspf: '让球胜平负', bf: '比分', tg: '总进球', hspf: '半场胜平负' }[p] || p
}
function statusLabel(s) {
  return { pending: '待开赛', won: '已中', lost: '未中', void: '作废' }[s] || s
}
function statusTagClass(s) {
  return { pending: 'tag-low', won: 'tag-high', lost: 'tag-muted', void: 'tag-muted' }[s] || 'tag-low'
}
function selectionLabel(b) {
  if (b.play_type === 'spf') return { win: '主胜', draw: '平', lose: '客胜' }[b.selection] || b.selection
  if (b.play_type === 'nspf') return { win: '让胜', draw: '让平', lose: '让负' }[b.selection] || b.selection
  if (b.play_type === 'tg') return '总进球 ' + b.selection
  if (b.play_type === 'hspf') return '半场 ' + ({ win: '主胜', draw: '平', lose: '客胜' }[b.selection] || b.selection)
  return b.selection
}

async function loadStats() {
  try {
    stats.value = await simulationBetApi.stats()
  } catch (_) { /* 统计失败不阻塞列表 */ }
}

async function loadList() {
  loading.value = true
  error.value = ''
  try {
    const params = { page: page.value, page_size: pageSize }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterPlayType.value) params.play_type = filterPlayType.value
    if (filterDateFrom.value) params.date_from = filterDateFrom.value
    if (filterDateTo.value) params.date_to = filterDateTo.value
    const res = await simulationBetApi.list(params)
    bets.value = res?.items || []
    total.value = res?.pagination?.total || 0
    saveCache()
  } catch (e) {
    // 网络失败回退本地缓存（离线可看历史记录）
    const cached = loadCache()
    if (cached && cached.items.length) {
      bets.value = cached.items
      total.value = cached.total || cached.items.length
      error.value = '网络异常，已展示本地缓存（可能不是最新）'
    } else {
      error.value = e?.message || '加载失败'
    }
  } finally {
    loading.value = false
  }
}

function saveCache() {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ items: bets.value, total: total.value, ts: Date.now() }))
  } catch (_) { /* 隐私模式忽略 */ }
}
function loadCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch (_) {
    return null
  }
}
function clearDateFilter() {
  filterDateFrom.value = ''
  filterDateTo.value = ''
  reloadList()
}

async function loadAll() {
  await Promise.all([loadStats(), loadList()])
}
function reloadList() {
  page.value = 1
  loadList()
}
function prevPage() {
  if (page.value > 1) { page.value--; loadList() }
}
function nextPage() {
  if (page.value < totalPages.value) { page.value++; loadList() }
}

// B1 作废
function confirmVoid(b) {
  voidTarget.value = b
}
async function doVoid() {
  if (!voidTarget.value) return
  if (!canWrite) {
    error.value = '仅管理角色可作废投注单，当前为只读权限'
    voidTarget.value = null
    return
  }
  voiding.value = true
  try {
    await simulationBetApi.voidBet(voidTarget.value.id)
    voidTarget.value = null
    // 刷新当前页与统计（作废后列表状态变化）
    await Promise.all([loadStats(), loadList()])
  } catch (e) {
    error.value = e?.message || '作废失败'
  } finally {
    voiding.value = false
  }
}

// B2 上拉加载：触底加载下一页
async function loadMore() {
  if (loadingMore.value || !hasMore.value || loading.value) return
  loadingMore.value = true
  page.value++
  try {
    const params = { page: page.value, page_size: pageSize }
    if (filterStatus.value) params.status = filterStatus.value
    if (filterPlayType.value) params.play_type = filterPlayType.value
    if (filterDateFrom.value) params.date_from = filterDateFrom.value
    if (filterDateTo.value) params.date_to = filterDateTo.value
    const res = await simulationBetApi.list(params)
    const more = res?.items || []
    // 去重（防重复分页追加）
    const seen = new Set(bets.value.map((b) => b.id))
    bets.value = [...bets.value, ...more.filter((b) => !seen.has(b.id))]
    total.value = res?.pagination?.total || total.value
    saveCache()
  } catch (e) {
    error.value = e?.message || '加载更多失败'
    page.value--
  } finally {
    loadingMore.value = false
  }
}

function setupObserver() {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0]?.isIntersecting) loadMore()
    },
    { rootMargin: '120px' },
  )
  if (loadSentinel.value) observer.observe(loadSentinel.value)
}

onMounted(() => {
  loadAll()
  setupObserver()
})
onBeforeUnmount(() => {
  if (observer) observer.disconnect()
})
</script>

<style scoped>
.filter-select {
  background: var(--bg-card, #121826);
  color: var(--text-secondary, #b6bdd0);
  border: 1px solid var(--border-color, #232b3b);
  border-radius: var(--radius-sm, 8px);
  padding: 6px 10px;
  font-size: 13px;
}
.filter-input {
  background: var(--bg-card, #121826);
  color: var(--text-secondary, #b6bdd0);
  border: 1px solid var(--border-color, #232b3b);
  border-radius: var(--radius-sm, 8px);
  padding: 6px 10px;
  font-size: 13px;
}
.date-sep { color: var(--text-muted, #8b93a7); font-size: 13px; }
.card-actions { flex-wrap: wrap; gap: 8px; }
.bet-table-wrap { overflow-x: auto; }
.bet-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.bet-table th, .bet-table td {
  padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border-color, #232b3b);
  white-space: nowrap;
}
.bet-table th { color: var(--text-muted, #8b93a7); font-weight: 500; font-size: 12px; }
.bet-table td { color: var(--text-secondary, #b6bdd0); }
.bet-match { color: var(--text-primary, #e5e9f0); font-weight: 600; }
.bet-meta { color: var(--text-muted, #8b93a7); font-size: 12px; }
.bet-selection { color: var(--text-primary, #e5e9f0); font-weight: 600; }
.pos { color: var(--color-green, #34d399); }
.muted { color: var(--text-muted, #8b93a7); }
.tag-high { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.tag-muted { background: rgba(139, 147, 167, 0.15); color: #8b93a7; }
.bet-pagination {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0 0; gap: 12px;
}
.page-info { color: var(--text-muted, #8b93a7); font-size: 13px; }
.page-buttons { display: flex; gap: 8px; }
.empty-hint { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 40px 0; color: var(--text-muted, #8b93a7); }
.btn-outline.danger { color: #ef4444; border-color: rgba(239, 68, 68, 0.5); }
.btn-outline.danger:hover { background: rgba(239, 68, 68, 0.1); }
.btn.danger { background: #ef4444; border-color: #ef4444; color: #fff; }
.btn.danger:hover { background: #dc2626; }
.btn.danger:disabled { opacity: 0.6; }
.load-sentinel {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 14px 0 4px; min-height: 24px; color: var(--text-muted, #8b93a7); font-size: 12px;
}
.modal-mask {
  position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); z-index: 1000;
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.modal {
  background: var(--bg-card, #121826); border: 1px solid var(--border-color, #232b3b);
  border-radius: 12px; padding: 20px; max-width: 400px; width: 100%; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
}
.modal-title { font-size: 16px; font-weight: 600; color: var(--text-primary, #e5e9f0); margin-bottom: 10px; }
.modal-text { font-size: 13px; color: var(--text-secondary, #b6bdd0); line-height: 1.6; margin-bottom: 10px; }
.modal-meta { font-size: 12px; color: var(--text-muted, #8b93a7); background: rgba(139, 147, 167, 0.1); border-radius: 6px; padding: 8px 10px; margin-bottom: 16px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; }
</style>

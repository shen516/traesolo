<template>
  <div class="jingcai-live-page">
    <div class="page-head card">
      <div class="page-head-main">
        <h1 class="page-title">竞彩比分</h1>
        <p class="page-sub">
          采集自 live.500.com/jczq.php「竞彩比分」列表；比分/亚盘盘口（平手、球半等）/状态/SP 随采集回写，仅供分析，不构成投注建议。
        </p>
      </div>
      <div class="page-head-actions">
        <button
          v-if="canRefresh"
          class="btn btn-outline"
          :disabled="refreshing"
          @click="refreshLive"
        >{{ refreshing ? '刷新中...' : '立即刷新' }}</button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar card">
      <div class="filter-section">
        <span class="filter-label">状态</span>
        <select :value="statusFilter" class="filter-select" @change="onStatusChange">
          <option value="">全部</option>
          <option value="upcoming">未开赛</option>
          <option value="live">进行中</option>
          <option value="finished">已完赛</option>
        </select>
      </div>
      <div class="filter-section">
        <span class="filter-label">日期</span>
        <input :value="selectedDate" type="date" class="date-input" @change="onDateChange" />
        <button v-if="selectedDate" type="button" class="date-clear" @click="clearDate">全部</button>
      </div>
      <div class="filter-section">
        <span class="filter-label">联赛</span>
        <input
          v-model="leagueKeyword"
          class="search-input league-input"
          :placeholder="followedOnly ? '输入关注的联赛' : '输入联赛名称'"
          @keyup.enter="onFilterChange"
        />
      </div>
      <label class="filter-check">
        <input type="checkbox" v-model="followedOnly" @change="onFilterChange" />
        仅关注
      </label>
      <label v-if="followedOnly" class="filter-check">
        <input type="checkbox" :checked="followsStore.includeChildren" @change="onIncludeChildrenChange" />
        含下级
      </label>
      <div class="filter-section search-section">
        <span class="filter-label">球队</span>
        <input v-model="searchKeyword" class="search-input" placeholder="搜索球队..." @keyup.enter="onFilterChange" />
      </div>
      <button class="btn btn-sm btn-primary" @click="onFilterChange">查询</button>
      <span class="result-hint">共 <b>{{ total }}</b> 场</span>
    </div>

    <StateBlock v-if="loading" type="loading" text="数据加载中..." />
    <StateBlock v-else-if="errorMsg" type="error" :text="errorMsg" retry-text="重新加载" @retry="loadData" />
    <StateBlock v-else-if="!matches.length" type="empty" text="暂无竞彩比分数据">
      <div class="state-extra">
        可点击「立即刷新」，或到定时任务页启用「竞彩比分列表采集」
      </div>
    </StateBlock>

    <div v-else class="table-card card">
      <div class="table-wrap">
        <table class="live-table">
          <colgroup>
            <col class="col-no" />
            <col class="col-league" />
            <col class="col-round" />
            <col class="col-time" />
            <col class="col-status" />
            <col class="col-team" />
            <col class="col-score" />
            <col class="col-team" />
            <col class="col-half" />
            <col class="col-odd" />
            <col class="col-odd" />
            <col class="col-odd" />
            <col class="col-rq" />
            <col class="col-act" />
          </colgroup>
          <thead>
            <tr>
              <th>场次</th>
              <th>赛事</th>
              <th>轮次</th>
              <th>比赛时间</th>
              <th>状态</th>
              <th>主队</th>
              <th>比分</th>
              <th>客队</th>
              <th>半场</th>
              <th>胜</th>
              <th>平</th>
              <th>负</th>
              <th>让球</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(m, idx) in matches"
              :key="m.id"
              class="match-row"
              :class="{ alt: idx % 2 === 1 }"
              @click="goDetail(m.id)"
            >
              <td class="col-no">{{ m.matchNo || m.round || '-' }}</td>
              <td class="col-league">
                <span class="league-badge" :style="leagueBadgeStyle(m)">{{ leagueName(m) }}</span>
              </td>
              <td class="col-round">{{ m.round || '-' }}</td>
              <td class="col-time">{{ kickoffText(m) }}</td>
              <td class="col-status">
                <span class="status-tag" :class="`status-${m.status}`">{{ statusText(m.status) }}</span>
              </td>
              <td class="col-team">{{ teamName(m, 'home') }}</td>
              <td class="col-score">
                <span v-if="m.status === 'finished'" class="score-cell score-finished">
                  <b>{{ m.homeGoals ?? 0 }}</b>
                  <span class="hc-line" v-if="m.handicapLine">{{ m.handicapLine }}</span>
                  <span v-else>:</span>
                  <b>{{ m.awayGoals ?? 0 }}</b>
                </span>
                <span v-else-if="m.status === 'live'" class="score-cell score-live">
                  <b>{{ m.homeGoals ?? 0 }}</b>
                  <span class="hc-line" v-if="m.handicapLine">{{ m.handicapLine }}</span>
                  <span v-else>:</span>
                  <b>{{ m.awayGoals ?? 0 }}</b>
                </span>
                <span v-else class="score-cell score-vs">
                  <template v-if="m.handicapLine">{{ m.handicapLine }}</template>
                  <template v-else>VS</template>
                </span>
              </td>
              <td class="col-team">{{ teamName(m, 'away') }}</td>
              <td class="col-half">{{ m.halfScore || '-' }}</td>
              <td class="col-odd">{{ fmtOdds(m.oddsSpfWin) }}</td>
              <td class="col-odd">{{ fmtOdds(m.oddsSpfDraw) }}</td>
              <td class="col-odd">{{ fmtOdds(m.oddsSpfLose) }}</td>
              <td class="col-rq">
                <span v-if="m.oddsNspfWin != null" class="rq-box">
                  <span class="hc" :class="handicapClass(m.handicap)">{{ formatHandicapDisplay(m.handicap) }}</span>
                  <span class="rq-odds">{{ fmtOdds(m.oddsNspfWin) }}/{{ fmtOdds(m.oddsNspfDraw) }}/{{ fmtOdds(m.oddsNspfLose) }}</span>
                </span>
                <span v-else class="muted">-</span>
              </td>
              <td class="col-act">
                <button type="button" class="link-btn" @click.stop="goDetail(m.id)">详情</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="totalPages > 1" class="pagination">
        <button class="btn btn-sm" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
        <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
        <button class="btn btn-sm" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { jingcaiApi, scheduleApi } from '@/api'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'
import { hasAnyPermission } from '@/utils/permissions'
import { adaptUpcomingMatch, unwrapList } from '@/utils/adapters'
import { fmtOdds, formatHandicap } from '@/utils/matchMeta'

const router = useRouter()
const userStore = useUserStore()
const followsStore = useFollowsStore()

const matches = ref([])
const loading = ref(false)
const refreshing = ref(false)
const errorMsg = ref('')
const total = ref(0)
const currentPage = ref(1)
const pageSize = 50
const leagueKeyword = ref('')
const selectedDate = ref('')
const searchKeyword = ref('')
const statusFilter = ref('')
const followedOnly = ref(!userStore.isAdmin)
let loadSeq = 0

const canRefresh = computed(() => hasAnyPermission('schedule:manage', 'match:manage'))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

const LEAGUE_COLORS = [
  '#137AAC', '#1F4E79', '#2E7D32', '#6A1B9A', '#C62828',
  '#EF6C00', '#00838F', '#455A64', '#5D4037', '#283593',
]

function leagueName(m) {
  return m.leagueInfo?.name || m.league || '-'
}

function leagueBadgeStyle(m) {
  const id = String(m.league || leagueName(m) || '')
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) >>> 0
  return { background: LEAGUE_COLORS[hash % LEAGUE_COLORS.length] }
}

function teamName(m, side) {
  const info = side === 'home' ? m.homeTeamInfo : m.awayTeamInfo
  return info?.short || info?.name || (side === 'home' ? m.homeTeam : m.awayTeam) || '-'
}

function kickoffText(m) {
  if (!m.date) return m.time || '-'
  const md = String(m.date).slice(5)
  return m.time ? `${md} ${m.time}` : md
}

function statusText(s) {
  return { upcoming: '未开赛', live: '进行中', finished: '已完赛' }[s] || s || '-'
}

function formatHandicapDisplay(hc) {
  const text = formatHandicap(hc)
  return text == null ? '-' : text
}

function handicapClass(hc) {
  const n = Number(hc)
  if (!Number.isFinite(n) || n === 0) return ''
  return n < 0 ? 'hc-neg' : 'hc-pos'
}

function adaptLiveMatch(raw) {
  const m = adaptUpcomingMatch(raw)
  m.homeGoals = raw.home_goals ?? raw.homeGoals ?? null
  m.awayGoals = raw.away_goals ?? raw.awayGoals ?? null
  m.result = raw.result ?? null
  m.halfScore = raw.half_score ?? raw.halfScore ?? null
  m.matchNo = raw.match_no ?? raw.matchNo ?? null
  m.source = raw.source ?? null
  m.handicapLine = raw.handicap_line ?? raw.handicapLine ?? null
  return m
}

function listParams() {
  const params = {
    page: currentPage.value,
    page_size: pageSize,
    view: 'summary',
  }
  if (followedOnly.value) params.league_ids = followsStore.queryIds.join(',')
  if (selectedDate.value) params.match_date = selectedDate.value
  if (searchKeyword.value.trim()) params.keyword = searchKeyword.value.trim()
  if (statusFilter.value) params.status = statusFilter.value
  return params
}

async function loadData() {
  const seq = ++loadSeq
  loading.value = true
  errorMsg.value = ''
  try {
    await followsStore.ensureLoaded()
    if (seq !== loadSeq) return
    if (followedOnly.value && !followsStore.ids.length) {
      matches.value = []
      total.value = 0
      return
    }
    const data = await jingcaiApi.getLive(listParams())
    if (seq !== loadSeq) return
    matches.value = unwrapList(data, 'matches').map(adaptLiveMatch)
    total.value = data?.pagination?.total ?? matches.value.length
  } catch (e) {
    if (seq !== loadSeq) return
    errorMsg.value = e?.response?.data?.detail || e.message || '加载失败'
    matches.value = []
    total.value = 0
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function onFilterChange() {
  currentPage.value = 1
  loadData()
}

function onStatusChange(e) {
  statusFilter.value = e.target.value
  onFilterChange()
}

function onDateChange(e) {
  selectedDate.value = String(e.target.value || '').slice(0, 10)
  onFilterChange()
}

function clearDate() {
  selectedDate.value = ''
  onFilterChange()
}

async function onIncludeChildrenChange(e) {
  await followsStore.setIncludeChildren(e.target.checked)
  onFilterChange()
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  currentPage.value = p
  loadData()
}

function goDetail(id) {
  router.push({ path: `/match/${id}`, query: { from: '/jingcai-live' } })
}

async function refreshLive() {
  if (!canRefresh.value) {
    errorMsg.value = '无采集权限，请联系管理员或到定时任务页执行「竞彩比分列表采集」'
    return
  }
  refreshing.value = true
  errorMsg.value = ''
  try {
    try {
      await scheduleApi.runLiveJingcaiNow()
    } catch {
      await jingcaiApi.refreshLive({ days_ahead: 1 })
    }
    await loadData()
  } catch (e) {
    errorMsg.value = e?.response?.data?.detail || e.message || '刷新失败'
  } finally {
    refreshing.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: center;
  margin-bottom: 16px;
}
.filter-section {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.filter-label {
  color: var(--text-muted);
  font-size: 12px;
}
.filter-select,
.date-input,
.search-input {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  outline: none;
}
.date-input {
  color-scheme: dark;
}
.date-clear {
  background: none;
  border: none;
  color: var(--color-blue);
  cursor: pointer;
  font-size: 12px;
}
.league-input {
  width: 160px;
}
.search-input {
  width: 180px;
}
.filter-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}
.result-hint {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 13px;
}
.result-hint b {
  color: var(--color-gold);
}

.table-card {
  overflow: hidden;
}
.table-wrap {
  overflow-x: auto;
}
.live-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
.live-table th {
  text-align: left;
  padding: 10px 12px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-color);
  font-weight: 500;
  white-space: nowrap;
}
.live-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: middle;
}
.match-row {
  cursor: pointer;
}
.match-row.alt {
  background: rgba(255, 255, 255, 0.02);
}
.match-row:hover {
  background: rgba(19, 122, 172, 0.08);
}

.col-no { width: 80px; color: var(--text-muted); }
.col-league { width: 80px; }
.col-round { width: 70px; color: var(--text-muted); }
.col-time { width: 110px; white-space: nowrap; }
.col-status { width: 70px; }
.col-team { min-width: 110px; }
.col-score { width: 110px; text-align: center; }
.col-half { width: 60px; color: var(--text-muted); }
.col-odd { width: 70px; text-align: center; font-family: Consolas, monospace; font-weight: 600; }
.col-rq { width: 130px; }
.col-act { width: 60px; }

.league-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  color: #fff;
  font-size: 0.78rem;
  line-height: 1.4;
}

.status-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.status-upcoming { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
.status-live { background: rgba(239, 68, 68, 0.15); color: #f87171; }
.status-finished { background: rgba(34, 197, 94, 0.15); color: #4ade80; }

.score-cell {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  white-space: nowrap;
}
.score-finished,
.score-live {
  font-family: Consolas, monospace;
  font-size: 15px;
  color: var(--color-gold);
  font-weight: 700;
}
.score-live { color: #f87171; }
.score-vs { color: var(--text-muted); font-size: 13px; }
.hc-line {
  font-size: 12px;
  font-weight: 600;
  color: #22c55e;
  font-family: inherit;
  margin: 0 2px;
}

.rq-box {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.rq-box .hc {
  font-weight: 700;
  font-family: Consolas, monospace;
}
.rq-box .hc.hc-neg { color: #22c55e; }
.rq-box .hc.hc-pos { color: #ef4444; }
.rq-odds {
  font-family: Consolas, monospace;
  font-weight: 600;
  color: var(--text-primary);
}
.muted { color: var(--text-muted); }

.link-btn {
  background: transparent;
  border: 0;
  color: var(--color-blue);
  font-size: 12px;
  cursor: pointer;
}
.link-btn:hover { text-decoration: underline; }

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 14px;
}
.page-info {
  color: var(--text-muted);
  font-size: 13px;
}
</style>

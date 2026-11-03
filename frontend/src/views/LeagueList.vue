<template>
  <div class="league-list">
    <div class="page-header card">
      <h1 class="page-title">联赛列表</h1>
      <p class="page-subtitle">浏览顶级联赛，点击查看子联赛与球队详情</p>
    </div>

    <StateBlock v-if="loading" type="loading" text="数据加载中..." />

    <template v-else>
      <div class="filter-bar card">
        <label class="filter-check">
          <input type="checkbox" v-model="onlyWithData" @change="onFilterChange" />
          仅显示已有球队或赛事的联赛
        </label>
        <label class="filter-check">
          <input type="checkbox" v-model="topLevelOnly" @change="onFilterChange" />
          仅顶级联赛
        </label>
        <label class="filter-check">
          <input type="checkbox" v-model="onlyFollowed" />
          仅已关注
        </label>
      </div>

      <div class="card table-card">
        <table class="data-table">
          <thead>
            <tr>
              <th>联赛</th>
              <th>国家</th>
              <th>球队数</th>
              <th>赛事数</th>
              <th>子联赛</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="league in displayLeagues" :key="league.id">
              <td>
                <div class="league-cell">
                  <MediaImg :src="league.logo" :fallback="leagueIcon(league.id)" img-class="league-icon" size="md" :alt="league.name" />
                  <div>
                    <span class="league-name">{{ league.name }}</span>
                    <span class="league-id">{{ league.id }}</span>
                  </div>
                </div>
              </td>
              <td>{{ league.country || '-' }}</td>
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
                <button
                  v-if="league.children_count > 0"
                  class="link-btn"
                  @click="openChildrenDrawer(league)"
                >子联赛</button>
                <button
                  class="follow-btn"
                  :class="{ active: isFollowed(league.id) }"
                  :disabled="followBusyId === league.id"
                  @click="toggleFollow(league)"
                >{{ isFollowed(league.id) ? '已关注' : '关注' }}</button>
                <button class="link-btn" @click="showLeague(league)">详情</button>
              </td>
            </tr>
            <tr v-if="displayLeagues.length === 0">
              <td colspan="6" class="empty-row">{{ onlyFollowed ? '尚未关注任何联赛' : '暂无联赛数据' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <p v-if="followError" class="follow-error">{{ followError }}</p>

    <Pagination
      v-if="!loading && !onlyFollowed && leagues.length > 0"
      :page="currentPage"
      :page-size="pageSize"
      :total="total"
      @change="goPage"
    />

    <LeagueChildrenDrawer
      :visible="childrenDrawerVisible"
      :parent-league="childrenParent"
      @close="childrenDrawerVisible = false"
      @detail="onChildDetail"
    />

    <BaseModal
      v-model="showModal"
      width="800px"
      :close-on-overlay="true"
      @close="closeModal"
    >
      <template #header>
        <div class="modal-title">
          <MediaImg :src="selectedLeague?.logo" :fallback="leagueIcon(selectedLeague?.id)" img-class="league-icon-large" size="lg" :alt="selectedLeague?.name" />
          <div>
            <h2>{{ selectedLeague?.name }}</h2>
            <span class="text-muted">{{ selectedLeague?.country }}</span>
          </div>
        </div>
        <div class="modal-actions">
          <button
            class="follow-btn"
            :class="{ active: isFollowed(selectedLeague?.id) }"
            :disabled="followBusyId === selectedLeague?.id"
            @click="toggleFollow(selectedLeague)"
          >{{ isFollowed(selectedLeague?.id) ? '已关注' : '关注' }}</button>
        </div>
      </template>
      <div v-if="enriching" class="loading-state">
        <span class="loading-spinner"></span>
        <span class="loading-text">正在采集该联赛的球队、赛事和图片...</span>
      </div>
      <div class="section">
        <h3 class="section-title">联赛球队（{{ leagueTeams.length }}）</h3>
        <div v-if="leagueTeams.length === 0" class="empty-hint">暂无球队数据</div>
        <div v-else class="teams-grid">
          <div
            v-for="team in leagueTeams"
            :key="team.id"
            class="team-item card"
            @click="goTeamDetail(team.id)"
          >
            <MediaImg :src="team.logo" fallback="⚽" img-class="team-logo" size="sm" :alt="team.name" />
            <div class="team-info">
              <span class="team-name">{{ team.name }}</span>
              <span class="team-short">{{ team.short_name }}</span>
            </div>
            <span class="team-arrow">→</span>
          </div>
        </div>
      </div>
      <div class="section">
        <h3 class="section-title">近期赛事（{{ leagueMatches.length }}）</h3>
        <div v-if="leagueMatches.length === 0" class="empty-hint">暂无赛事数据</div>
        <div v-else class="matches-list">
          <div
            v-for="match in leagueMatches"
            :key="match.id"
            class="match-item"
            @click="goMatchDetail(match.id)"
          >
            <span class="match-round">{{ match.round_name || match.round || '-' }}</span>
            <span class="match-home">{{ matchHome(match) }}</span>
            <span class="match-score">{{ matchScore(match) }}</span>
            <span class="match-away">{{ matchAway(match) }}</span>
            <span class="match-date">{{ match.match_date || match.date || '' }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <button
          v-if="selectedLeague"
          class="btn btn-primary"
          :disabled="enriching"
          @click="enrichSelected(true)"
        >{{ enriching ? '采集中...' : '采集球队/赛事/图片' }}</button>
        <button class="btn btn-secondary" @click="closeModal">关闭</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { leagueApi, teamApi, matchApi, scheduleApi } from '@/api'
import LeagueChildrenDrawer from '@/components/league/LeagueChildrenDrawer.vue'
import Pagination from '@/components/common/Pagination.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import BaseModal from '@/components/common/BaseModal.vue'
import { useFollowsStore } from '@/stores/follows'

const router = useRouter()
const followsStore = useFollowsStore()
const leagues = ref([])
const loading = ref(false)
const followBusyId = ref('')
const followError = ref('')
const onlyFollowed = ref(false)
const enriching = ref(false)
const showModal = ref(false)
const selectedLeague = ref(null)
const onlyWithData = ref(false)
const topLevelOnly = ref(true)
const childrenDrawerVisible = ref(false)
const childrenParent = ref(null)

const leagueTeams = ref([])
const leagueMatches = ref([])

const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const totalPages = ref(0)

const leagueIcons = {
  'EPL': '🏴󠁧󠁢󠁥󠁮󠁧󠁿',
  'BUNDES': '🇩🇪',
  'LALIGA': '🇪🇸',
  'LIGUE1': '🇫🇷',
  'SERIEA': '🇮🇹',
  'WC': '🏆',
  'CHAMPIONS': '⭐',
  'UCL': '⭐',
}

const leagueIcon = (id) => leagueIcons[id] || '⚽'

const displayLeagues = computed(() => {
  if (!onlyFollowed.value) return leagues.value
  return followsStore.leagues
})

const isFollowed = (id) => followsStore.isFollowed(id)

async function toggleFollow(league) {
  if (!league?.id || followBusyId.value) return
  followBusyId.value = league.id
  followError.value = ''
  try {
    await followsStore.toggle(league.id, league)
  } catch (e) {
    followError.value = e?.message || '操作失败'
  } finally {
    followBusyId.value = ''
  }
}

const matchHome = (m) => m.home_team?.name || m.home_team_name || m.home_team_id || m.homeTeam || '-'
const matchAway = (m) => m.away_team?.name || m.away_team_name || m.away_team_id || m.awayTeam || '-'
const matchScore = (m) => {
  if (m.status === 'finished' || (m.home_goals != null && m.away_goals != null && m.status !== 'upcoming')) {
    if (m.status === 'upcoming') return 'vs'
    return `${m.home_goals ?? 0} : ${m.away_goals ?? 0}`
  }
  return 'vs'
}

const goPage = (page) => {
  if (page >= 1 && page <= totalPages.value && page !== currentPage.value) {
    currentPage.value = page
    fetchData()
  }
}

const onFilterChange = () => {
  currentPage.value = 1
  fetchData()
}

function openChildrenDrawer(league) {
  childrenParent.value = league
  childrenDrawerVisible.value = true
}

function onChildDetail(league) {
  childrenDrawerVisible.value = false
  showLeague(league)
}

const loadLeagueExtras = async (leagueId) => {
  const [teamRes, matchRes] = await Promise.all([
    teamApi.getByLeague(leagueId).catch(() => ({ teams: [] })),
    matchApi.getByLeague(leagueId).catch(() => ({ matches: [] })),
  ])
  leagueTeams.value = teamRes?.teams || teamRes || []
  const rawMatches = matchRes?.matches || matchRes || []
  const list = Array.isArray(rawMatches) ? [...rawMatches] : []
  list.sort((a, b) => String(a.match_date || '').localeCompare(String(b.match_date || '')))
  const idx = list.findIndex(m => m.status !== 'finished')
  const start = Math.max(0, (idx < 0 ? Math.max(0, list.length - 30) : idx) - 4)
  leagueMatches.value = list.slice(start, start + 30)
}

const showLeague = async (league) => {
  selectedLeague.value = league
  showModal.value = true
  leagueTeams.value = []
  leagueMatches.value = []
  try {
    await loadLeagueExtras(league.id)
    const noTeams = !leagueTeams.value.length
    const noMatches = !leagueMatches.value.length
    const isCanonical = league.id && !String(league.id).startsWith('LS')
    if (isCanonical && (noTeams || noMatches)) {
      await enrichSelected(false)
    }
  } catch (e) {
    console.error('Failed to load league detail:', e)
  }
}

const enrichSelected = async (manual = true) => {
  if (!selectedLeague.value || enriching.value) return
  enriching.value = true
  try {
    await scheduleApi.enrichLeague(selectedLeague.value.id, manual, manual ? 2 : 0)
    await loadLeagueExtras(selectedLeague.value.id)
    const info = await leagueApi.getById(selectedLeague.value.id).catch(() => null)
    const idx = leagues.value.findIndex(l => l.id === selectedLeague.value.id)
    if (idx >= 0 && info) {
      leagues.value[idx] = { ...leagues.value[idx], ...info }
      selectedLeague.value = { ...selectedLeague.value, ...info }
    }
  } catch (e) {
    console.error('Failed to enrich league:', e)
  } finally {
    enriching.value = false
  }
}

const closeModal = () => {
  showModal.value = false
  selectedLeague.value = null
}

const goTeamDetail = (teamId) => {
  closeModal()
  router.push(`/team/${teamId}`)
}

const goMatchDetail = (matchId) => {
  closeModal()
  router.push(`/match/${matchId}`)
}

const fetchData = async () => {
  loading.value = true
  try {
    const leagueRes = await leagueApi.getAll({
      page: currentPage.value,
      page_size: pageSize.value,
      has_data: onlyWithData.value || undefined,
      level: topLevelOnly.value ? 1 : undefined,
    })
    leagues.value = leagueRes?.leagues || leagueRes || []
    total.value = leagueRes?.total || 0
    totalPages.value = leagueRes?.total_pages || 0
  } catch (e) {
    console.error('Failed to load data:', e)
  } finally {
    loading.value = false
  }
}

followsStore.ensureLoaded()
fetchData()
</script>

<style scoped>
.league-list {
  padding: 0;
}

.page-header {
  padding: 32px;
  margin-bottom: 24px;
}

.page-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px 0;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 14px 20px;
  margin-bottom: 20px;
}

.filter-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: var(--text-primary);
  cursor: pointer;
}

.table-card {
  padding: 0;
  overflow: hidden;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.data-table th,
.data-table td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.data-table th {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 12px;
}

.data-table tbody tr:hover {
  background: var(--bg-hover);
}

.league-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.league-name {
  display: block;
  font-weight: 600;
  color: var(--text-primary);
}

.league-id {
  font-size: 11px;
  color: var(--text-muted);
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-blue);
  cursor: pointer;
  font-size: 13px;
  padding: 2px 6px;
  margin-right: 4px;
}

.follow-btn {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
  margin-right: 8px;
}

.follow-btn:hover {
  border-color: var(--color-gold);
  color: var(--color-gold);
}

.follow-btn.active {
  background: rgba(212, 175, 55, 0.12);
  border-color: var(--color-gold);
  color: var(--color-gold);
}

.follow-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.follow-error {
  color: var(--color-red);
  font-size: 13px;
  margin: 0 0 12px;
}

.link-btn:hover {
  text-decoration: underline;
}

.text-muted {
  color: var(--text-muted);
}

.empty-row {
  text-align: center;
  color: var(--text-muted);
  padding: 32px 0 !important;
}




.modal-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.modal-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.league-icon-large {
  font-size: 56px;
}

.modal-title h2 {
  margin: 0 0 4px 0;
  font-size: 24px;
}




.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 16px 0;
}

.section + .section {
  margin-top: 28px;
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
  padding: 12px 0;
}

.matches-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.match-item {
  display: grid;
  grid-template-columns: 72px 1fr 72px 1fr 110px;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
}

.match-item:hover {
  background: var(--bg-hover);
}

.match-round,
.match-date {
  color: var(--text-muted);
  font-size: 12px;
}

.match-home,
.match-away {
  font-weight: 500;
  color: var(--text-primary);
}

.match-home {
  text-align: right;
}

.match-score {
  text-align: center;
  font-weight: 700;
}



.teams-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.team-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.team-item:hover {
  background: var(--bg-secondary);
}

.team-logo {
  font-size: 28px;
}

.team-info {
  flex: 1;
}

.team-name {
  display: block;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.team-short {
  font-size: 12px;
  color: var(--text-secondary);
}

.team-arrow {
  color: var(--text-muted);
  font-size: 18px;
}










.loading-state {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 40px;
  justify-content: center;
}

.loading-spinner,
.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(var(--color-blue-rgb), 0.3);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>

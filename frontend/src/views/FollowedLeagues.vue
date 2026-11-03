<template>
  <div class="followed-page">
    <div class="page-header card">
      <div>
        <h1 class="page-title">我的关注</h1>
        <p class="page-subtitle">只看已关注联赛的未赛、积分榜与射手榜</p>
      </div>
      <div class="header-actions">
        <label class="filter-check">
          <input type="checkbox" :checked="followsStore.includeChildren" @change="onIncludeChildren" />
          含下级联赛
        </label>
        <button class="btn btn-outline" @click="goLeagues">去联赛列表</button>
      </div>
    </div>

    <div v-if="loading" class="loading-state card">
      <span class="loading-spinner"></span>
      <span class="loading-text">数据加载中...</span>
    </div>

    <div v-else-if="errorMsg" class="empty-state card">
      <div class="empty-text">加载失败</div>
      <div class="empty-hint">{{ errorMsg }}</div>
      <button class="btn btn-primary" @click="loadData">重新加载</button>
    </div>

    <div v-else-if="!groups.length" class="empty-state card">
      <div class="empty-icon">⭐</div>
      <div class="empty-text">还没有关注联赛</div>
      <div class="empty-hint">关注后，这里会按联赛展示未赛与积分榜</div>
      <button class="btn btn-primary" @click="goLeagues">去关注联赛</button>
    </div>

    <section v-else class="league-groups">
      <article v-for="group in groups" :key="group.id" class="card league-group">
        <header class="group-header">
          <div class="group-title">
            <MediaImg :src="group.logo" :fallback="group.icon || '🏆'" size="sm" :alt="group.name" />
            <div>
              <h2>
                {{ group.name }}
                <span v-if="!group.isActive" class="inactive-tag">已停用</span>
              </h2>
              <span class="text-muted">{{ group.upcoming.length }} 场未赛</span>
            </div>
          </div>
          <div class="group-actions">
            <button class="link-btn" @click="toggleStandings(group.id)">
              {{ expanded[group.id] ? '收起积分榜' : '积分榜 / 射手' }}
            </button>
            <button class="follow-btn active" :disabled="busyId === group.id" @click="unfollow(group)">
              取消关注
            </button>
          </div>
        </header>

        <div v-if="!group.upcoming.length" class="empty-hint">该联赛暂无未赛</div>
        <div v-else class="match-list">
          <button
            v-for="match in group.upcoming"
            :key="match.id"
            type="button"
            class="match-row"
            @click="goMatch(match.id)"
          >
            <span class="match-date">{{ match.date }} {{ match.time }}</span>
            <span class="match-vs">
              {{ match.homeTeamInfo?.short || match.homeTeam }}
              <em>vs</em>
              {{ match.awayTeamInfo?.short || match.awayTeam }}
            </span>
            <span class="match-pred text-gold">
              {{ match.prediction?.hasPrediction ? match.prediction.mainScore : '未预测' }}
            </span>
          </button>
        </div>

        <div v-if="expanded[group.id]" class="board-wrap">
          <div class="board-col">
            <h3 class="board-title">积分榜 {{ group.seasonLabel }}</h3>
            <table v-if="group.standings.length" class="data-table">
              <thead>
                <tr>
                  <th>排名</th>
                  <th>球队</th>
                  <th>场</th>
                  <th>积分</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in group.standings" :key="row.team">
                  <td>{{ row.rank }}</td>
                  <td>{{ teamShort(row.team) }}</td>
                  <td>{{ row.played }}</td>
                  <td class="text-gold">{{ row.points }}</td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-hint">暂无积分榜</div>
          </div>
          <div class="board-col">
            <h3 class="board-title">射手榜 Top 5</h3>
            <ul v-if="group.scorers.length" class="scorer-list">
              <li v-for="scorer in group.scorers" :key="scorer.rank + scorer.name">
                <span class="scorer-rank">{{ scorer.rank || '-' }}</span>
                <span class="scorer-name">{{ scorer.name }}</span>
                <span class="text-gold">{{ scorer.goals }} 球</span>
              </li>
            </ul>
            <div v-else class="empty-hint">暂无射手榜</div>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup>
import { onActivated, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { followApi } from '@/api'
import { useFollowsStore } from '@/stores/follows'
import {
  adaptDashboardMatch,
  adaptStandings,
  adaptScorer,
  unwrapList,
} from '@/utils/adapters'
import { getTeamMap } from '@/utils/catalogCache'

const router = useRouter()
const followsStore = useFollowsStore()
const loading = ref(false)
const errorMsg = ref('')
const groups = ref([])
const busyId = ref('')
const expanded = reactive({})
const teams = ref({})

function teamShort(teamId) {
  return teams.value[teamId]?.short || teamId
}

function goLeagues() {
  router.push('/leagues')
}

function goMatch(id) {
  router.push(`/match/${id}`)
}

function toggleStandings(id) {
  expanded[id] = !expanded[id]
}

async function onIncludeChildren(e) {
  await followsStore.setIncludeChildren(e.target.checked)
  await loadData()
}

async function unfollow(group) {
  if (!group?.id || busyId.value) return
  busyId.value = group.id
  try {
    await followsStore.toggle(group.id, group)
    groups.value = groups.value.filter((item) => item.id !== group.id)
  } catch (e) {
    errorMsg.value = e?.message || '取消关注失败'
  } finally {
    busyId.value = ''
  }
}

function seasonLabel(raw) {
  if (!raw) return ''
  return String(raw).replace(/(\d{4})-(\d{4})/, (_, a, b) => `${a}-${String(b).slice(2)}`)
}

async function loadData() {
  loading.value = true
  errorMsg.value = ''
  try {
    await followsStore.ensureLoaded()
    const [summary, teamMap] = await Promise.all([
      followApi.summary({
        per_league_matches: 5,
        match_limit: 40,
        standings_limit: 8,
        scorers_limit: 5,
        include_children: followsStore.includeChildren,
      }),
      getTeamMap().catch(() => new Map()),
    ])
    const map = {}
    teamMap.forEach((t, id) => { map[id] = t })
    teams.value = map

    const matches = unwrapList(summary, 'matches').map(adaptDashboardMatch)
    const boards = summary?.boards || []
    const leagues = summary?.leagues || followsStore.leagues
    followsStore.applyPayload(summary)

    const childMap = summary?.child_map || followsStore.childMap || {}
    const includeChildren = followsStore.includeChildren
    groups.value = leagues.map((league) => {
      const board = boards.find((b) => b.league_id === league.id) || {}
      const childIds = new Set(childMap[league.id] || league.child_ids || [])
      return {
        id: league.id,
        name: league.name,
        logo: league.logo,
        icon: league.icon,
        isActive: league.is_active !== false,
        seasonLabel: seasonLabel(board.season),
        upcoming: matches.filter((m) => (
          m.league === league.id || (includeChildren && childIds.has(m.league))
        )),
        standings: (board.standings || []).map(adaptStandings),
        scorers: (board.scorers || []).slice(0, 5).map(adaptScorer),
      }
    })
  } catch (e) {
    errorMsg.value = e?.message || '加载失败'
    groups.value = []
  } finally {
    loading.value = false
  }
}

onActivated(() => {
  loadData()
})
</script>

<style scoped>
.followed-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 28px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.filter-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}

.inactive-tag {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
}

.page-title {
  margin: 0 0 6px;
  font-size: 24px;
  color: var(--text-primary);
}

.page-subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 56px 20px;
  text-align: center;
}

.loading-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--border-color);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-icon { font-size: 32px; }
.empty-text { font-size: 16px; color: var(--text-primary); }
.empty-hint { font-size: 13px; color: var(--text-muted); padding: 8px 0; }

.league-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.league-group { padding: 16px 20px 20px; }

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.group-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.group-title h2 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

.group-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.link-btn,
.follow-btn {
  background: none;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}

.follow-btn.active {
  border-color: var(--color-gold);
  color: var(--color-gold);
}

.match-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.match-row {
  display: grid;
  grid-template-columns: 140px 1fr auto;
  gap: 12px;
  align-items: center;
  width: 100%;
  text-align: left;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 10px 12px;
  color: var(--text-primary);
  cursor: pointer;
}

.match-row:hover { border-color: var(--color-blue); }
.match-date { font-size: 12px; color: var(--text-muted); }
.match-vs em {
  margin: 0 8px;
  font-style: normal;
  color: var(--text-muted);
}
.match-pred { font-size: 12px; font-weight: 600; }

.board-wrap {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 16px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.board-title {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-secondary);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.data-table th,
.data-table td {
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.scorer-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.scorer-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.scorer-rank {
  width: 20px;
  color: var(--color-gold);
  font-weight: 700;
}

@media (max-width: 800px) {
  .match-row,
  .board-wrap { grid-template-columns: 1fr; }
}
</style>

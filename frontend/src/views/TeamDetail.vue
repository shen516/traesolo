<template>
  <div class="team-detail">
    <div v-if="loading" class="loading-state card">
      <span class="loading-spinner"></span>
      <span class="loading-text">数据加载中...</span>
    </div>

    <template v-else>
      <div class="team-header card">
        <div class="team-header-left">
          <MediaImg :src="team.logo" fallback="⚽" img-class="team-logo-large" size="xl" :alt="team.name" />
          <div class="team-info">
            <h1 class="team-name">{{ team.name }}</h1>
            <span class="team-league">{{ leagueInfo?.name }} · {{ team.country }}</span>
          </div>
        </div>
        <div class="team-stats-row">
          <div class="team-stat">
            <span class="stat-value">{{ team.elo_rating }}</span>
            <span class="stat-label">ELO评分</span>
          </div>
          <div class="team-stat">
            <span class="stat-value">{{ team.attack_strength }}</span>
            <span class="stat-label">进攻能力</span>
          </div>
          <div class="team-stat">
            <span class="stat-value">{{ team.defense_strength }}</span>
            <span class="stat-label">防守能力</span>
          </div>
          <div class="team-stat">
            <span class="stat-value">{{ team.founded_year }}</span>
            <span class="stat-label">成立年份</span>
          </div>
        </div>
      </div>

      <div class="section section-two-col">
        <div class="card">
          <div class="section-header">
            <h2 class="section-title"><span class="section-bar"></span>球队阵容</h2>
            <span class="section-sub text-muted">{{ players.length }} 名球员</span>
            <button class="crawl-btn" :disabled="crawling" @click="crawlSquad(true)">
              {{ crawling ? '采集中...' : '采集阵容' }}
            </button>
          </div>
          <div class="position-tabs">
            <button
              v-for="tab in positionTabs"
              :key="tab.key"
              class="position-tab"
              :class="{ active: activePosition === tab.key }"
              @click="activePosition = tab.key"
            >{{ tab.label }}</button>
          </div>
          <table class="player-table">
            <thead>
              <tr>
                <th class="col-num">#</th>
                <th class="col-name">球员</th>
                <th class="col-position">位置</th>
                <th class="col-nation">国籍</th>
                <th class="col-goals">进球</th>
                <th class="col-assists">助攻</th>
                <th class="col-apps">出场</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="player in filteredPlayers" :key="player.id">
                <td class="col-num">{{ player.jersey_number || '-' }}</td>
                <td class="col-name">
                  <div class="player-name-cell">
                    <MediaImg :src="player.photo" fallback="👤" img-class="player-photo" size="sm" :alt="player.name" />
                    <div class="player-name-text">
                      <span class="player-name">{{ player.name }}</span>
                      <span class="player-short">{{ player.short_name }}</span>
                    </div>
                  </div>
                </td>
                <td class="col-position">
                  <span class="position-badge" :class="`pos-${player.position}`">{{ positionText(player.position) }}</span>
                </td>
                <td class="col-nation">{{ player.nationality }}</td>
                <td class="col-goals text-green">{{ player.goals }}</td>
                <td class="col-assists text-blue">{{ player.assists }}</td>
                <td class="col-apps">{{ player.appearances }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="card">
          <div class="section-header">
            <h2 class="section-title"><span class="section-bar"></span>射手榜</h2>
            <span class="section-sub text-muted">球队Top 5</span>
          </div>
          <ul class="scorer-list">
            <li
              v-for="(scorer, index) in topScorers"
              :key="scorer.id"
              class="scorer-item"
            >
              <span class="scorer-rank" :class="rankClass(index + 1)">{{ index + 1 }}</span>
              <div class="scorer-info">
                <span class="scorer-name">{{ scorer.name }}</span>
                <span class="scorer-position">{{ positionText(scorer.position) }}</span>
              </div>
              <span class="scorer-goals">{{ scorer.goals }}</span>
            </li>
          </ul>

          <div class="section-header mt-24">
            <h2 class="section-title"><span class="section-bar"></span>球员数据统计</h2>
          </div>
          <div class="stats-summary">
            <div class="stat-box">
              <span class="stat-box-value text-green">{{ totalGoals }}</span>
              <span class="stat-box-label">总进球</span>
            </div>
            <div class="stat-box">
              <span class="stat-box-value text-blue">{{ totalAssists }}</span>
              <span class="stat-box-label">总助攻</span>
            </div>
            <div class="stat-box">
              <span class="stat-box-value">{{ avgAge }}</span>
              <span class="stat-box-label">平均年龄</span>
            </div>
            <div class="stat-box">
              <span class="stat-box-value">{{ avgHeight }}cm</span>
              <span class="stat-box-label">平均身高</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { teamApi, playerApi, leagueApi, scheduleApi } from '@/api'

const route = useRoute()
const team = ref({})
const leagueInfo = ref(null)
const players = ref([])
const loading = ref(false)
const crawling = ref(false)
const activePosition = ref('all')

const positionTabs = [
  { key: 'all', label: '全部' },
  { key: 'GK', label: '门将' },
  { key: 'CB', label: '后卫' },
  { key: 'DM', label: '中场' },
  { key: 'AM', label: '进攻' },
  { key: 'ST', label: '前锋' },
]

const positionTextMap = {
  'GK': '门将',
  'CB': '中后卫',
  'RB': '右后卫',
  'LB': '左后卫',
  'DM': '后腰',
  'CM': '中场',
  'AM': '前腰',
  'RM': '右中场',
  'LM': '左中场',
  'RW': '右边锋',
  'LW': '左边锋',
  'ST': '前锋',
}

const positionText = (pos) => positionTextMap[pos] || pos

const filteredPlayers = computed(() => {
  if (activePosition.value === 'all') return players.value
  if (activePosition.value === 'CB') {
    return players.value.filter(p => ['CB', 'RB', 'LB'].includes(p.position))
  }
  if (activePosition.value === 'DM') {
    return players.value.filter(p => ['DM', 'CM', 'RM', 'LM'].includes(p.position))
  }
  if (activePosition.value === 'AM') {
    return players.value.filter(p => ['AM', 'RW', 'LW'].includes(p.position))
  }
  if (activePosition.value === 'ST') {
    return players.value.filter(p => p.position === 'ST')
  }
  return players.value.filter(p => p.position === activePosition.value)
})

const topScorers = computed(() => {
  return [...players.value].sort((a, b) => b.goals - a.goals).slice(0, 5)
})

const totalGoals = computed(() => players.value.reduce((sum, p) => sum + (p.goals || 0), 0))
const totalAssists = computed(() => players.value.reduce((sum, p) => sum + (p.assists || 0), 0))

const avgAge = computed(() => {
  const now = new Date()
  const validAges = players.value.filter(p => p.birth_date).map(p => {
    const birth = new Date(p.birth_date)
    return Math.floor((now - birth) / (365.25 * 24 * 60 * 60 * 1000))
  })
  if (validAges.length === 0) return '-'
  return Math.round(validAges.reduce((sum, age) => sum + age, 0) / validAges.length)
})

const avgHeight = computed(() => {
  const heights = players.value.filter(p => p.height).map(p => p.height)
  if (heights.length === 0) return '-'
  return Math.round(heights.reduce((sum, h) => sum + h, 0) / heights.length)
})

const rankClass = (rank) => {
  if (rank === 1) return 'rank-gold'
  if (rank === 2) return 'rank-silver'
  if (rank === 3) return 'rank-bronze'
  return ''
}

const fetchData = async () => {
  loading.value = true
  try {
    const teamId = route.params.id
    const [teamRes, playerRes, leagueRes] = await Promise.all([
      teamApi.getById(teamId),
      playerApi.getByTeam(teamId),
      leagueApi.getAll()
    ])
    team.value = teamRes
    players.value = playerRes?.players || playerRes || []
    const leagues = leagueRes?.leagues || leagueRes || []
    leagueInfo.value = leagues.find(l => l.id === team.value.league_id)
    if (players.value.length < 8) {
      await crawlSquad(false)
    }
  } catch (e) {
    console.error('Failed to load data:', e)
  } finally {
    loading.value = false
  }
}

const crawlSquad = async (manual = true) => {
  const teamId = route.params.id
  if (!teamId || crawling.value) return
  crawling.value = true
  try {
    await scheduleApi.runPlayerCrawl(null, teamId)
    const [playerRes, teamRes] = await Promise.all([
      playerApi.getByTeam(teamId),
      teamApi.getById(teamId)
    ])
    players.value = playerRes?.players || playerRes || []
    if (teamRes) team.value = teamRes
  } catch (e) {
    if (manual) console.error('Failed to crawl squad:', e)
  } finally {
    crawling.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.team-detail {
  padding: 0;
}

.team-header {
  padding: 32px;
  margin-bottom: 24px;
}

.team-header-left {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 24px;
}

.team-logo-large {
  font-size: 80px;
}

.team-info h1 {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--text-primary);
}

.team-league {
  font-size: 14px;
  color: var(--text-secondary);
}

.team-stats-row {
  display: flex;
  gap: 32px;
}

.team-stat {
  text-align: center;
}

.team-stat .stat-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.team-stat .stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.section {
  margin-bottom: 24px;
}

.section-two-col {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.section-bar {
  display: inline-block;
  width: 4px;
  height: 18px;
  background: linear-gradient(180deg, #ffd700, #ff8c00);
  border-radius: 2px;
  margin-right: 8px;
  vertical-align: middle;
}

.section-sub {
  font-size: 13px;
  margin-left: auto;
  margin-right: 12px;
}

.crawl-btn {
  padding: 6px 12px;
  background: linear-gradient(135deg, #0066cc, #004499);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.crawl-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.text-muted {
  color: var(--text-secondary);
}

.position-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.position-tab {
  padding: 8px 16px;
  border: 1px solid var(--border-color);
  border-radius: 20px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.position-tab:hover {
  border-color: var(--text-primary);
}

.position-tab.active {
  background: linear-gradient(135deg, #0066cc, #004499);
  color: #fff;
  border-color: var(--text-primary);
}

.player-table {
  width: 100%;
  border-collapse: collapse;
}

.player-table th,
.player-table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
}

.player-table th {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-secondary);
}

.col-num {
  width: 40px;
  font-weight: 600;
}

.col-name {
  width: 180px;
}

.col-position {
  width: 80px;
}

.col-nation {
  width: 80px;
}

.col-goals, .col-assists, .col-apps {
  width: 60px;
  text-align: center;
}

.player-name-cell {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
}

.player-name-text {
  display: flex;
  flex-direction: column;
}

.player-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.player-short {
  font-size: 12px;
  color: var(--text-secondary);
}

.position-badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.pos-GK { background: #e0f7fa; color: #00838f; }
.pos-CB, .pos-RB, .pos-LB { background: #e3f2fd; color: #1565c0; }
.pos-DM, .pos-CM, .pos-RM, .pos-LM { background: #f3e5f5; color: #7b1fa2; }
.pos-AM, .pos-RW, .pos-LW { background: #fff3e0; color: #e65100; }
.pos-ST { background: #ffebee; color: #c62828; }

.text-green { color: var(--color-green); }
.text-blue { color: var(--color-blue); }

.scorer-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.scorer-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-color);
}

.scorer-item:last-child {
  border-bottom: none;
}

.scorer-rank {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
}

.rank-gold { background: #ffd700; color: #fff; }
.rank-silver { background: #c0c0c0; color: #fff; }
.rank-bronze { background: #cd7f32; color: #fff; }

.scorer-info {
  flex: 1;
}

.scorer-name {
  display: block;
  font-size: 14px;
  font-weight: 500;
}

.scorer-position {
  font-size: 12px;
  color: var(--text-secondary);
}

.scorer-goals {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-red);
}

.mt-24 {
  margin-top: 24px;
}

.stats-summary {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.stat-box {
  background: var(--bg-secondary);
  padding: 20px;
  border-radius: 8px;
  text-align: center;
}

.stat-box-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-box-label {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
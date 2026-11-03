<template>
  <div class="table-card card">
    <div class="table-wrap">
      <!-- 在赛模式：单行 + 8 格赔率矩阵 -->
      <table v-if="mode === 'upcoming'" class="bet-table">
        <colgroup>
          <col class="col-no" />
          <col class="col-league" />
          <col class="col-time" />
          <col class="col-vs" />
          <col class="col-hc" />
          <col class="col-odd" />
          <col class="col-odd" />
          <col class="col-odd" />
          <col class="col-bet" />
          <col class="col-act" />
        </colgroup>
        <thead>
          <tr>
            <th>编号</th>
            <th>赛事</th>
            <th>开赛时间</th>
            <th>主队 VS 客队</th>
            <th>让球</th>
            <th>胜</th>
            <th>平</th>
            <th>负</th>
            <th>投注区</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody v-for="group in groups" :key="group.date">
          <tr class="date-row">
            <td colspan="10">
              <button type="button" class="date-toggle" @click="toggleDate(group.date)">
                <span class="caret" :class="{ collapsed: collapsedDates[group.date] }">▾</span>
                {{ group.label }}
                <span class="date-count">{{ group.items.length }} 场</span>
              </button>
            </td>
          </tr>
          <template v-if="!collapsedDates[group.date]">
            <template v-for="(m, idx) in group.items" :key="m.id">
              <tr
                class="match-row"
                :class="{ alt: idx % 2 === 1 }"
                @click="$emit('goDetail', m.id)"
              >
                <td class="col-no">{{ m.round || '-' }}</td>
                <td class="col-league">
                  <span class="league-badge" :style="leagueBadgeStyle(m)">{{ leagueName(m) }}</span>
                </td>
                <td class="col-time">
                  <div class="kickoff">
                    <span v-if="m.isSingle" class="single-flag" title="单关">单</span>
                    {{ kickoffText(m) }}
                  </div>
                </td>
                <td class="col-vs">
                  <div class="vs-line">
                    <span class="home">{{ teamName(m, 'home') }}</span>
                    <span class="vs">VS</span>
                    <span class="away">{{ teamName(m, 'away') }}</span>
                  </div>
                </td>
                <td colspan="4" class="cell-odds-wrap">
                  <div class="odds-grid">
                    <div class="o-hc">0</div>
                    <div class="o-sp">{{ oddText(m.oddsNspfWin, hasNspf(m)) }}</div>
                    <div class="o-sp">{{ oddText(m.oddsNspfDraw, hasNspf(m)) }}</div>
                    <div class="o-sp">{{ oddText(m.oddsNspfLose, hasNspf(m)) }}</div>
                    <div class="o-hc" :class="handicapClass(m.handicap)">
                      {{ formatHandicapDisplay(m.handicap) }}
                    </div>
                    <div class="o-sp">{{ oddText(m.oddsSpfWin, hasSpf(m)) }}</div>
                    <div class="o-sp">{{ oddText(m.oddsSpfDraw, hasSpf(m)) }}</div>
                    <div class="o-sp">{{ oddText(m.oddsSpfLose, hasSpf(m)) }}</div>
                  </div>
                </td>
                <td class="col-bet" @click.stop>
                  <button
                    type="button"
                    class="expand-btn"
                    :class="{ on: expanded[m.id] }"
                    @click="toggleExpand(m.id)"
                  >
                    {{ expanded[m.id] ? '收起投注' : '展开投注' }}
                  </button>
                </td>
                <td class="col-act" @click.stop>
                  <button type="button" class="link-btn" @click="$emit('goDetail', m.id)">详情</button>
                </td>
              </tr>
              <tr v-if="expanded[m.id]" class="bf-expand-row" :class="{ alt: idx % 2 === 1 }">
                <td colspan="10">
                  <BfPanel :match="m" :top3-scores="top3Scores" />
                </td>
              </tr>
            </template>
          </template>
        </tbody>
      </table>

      <!-- 历史模式：双行（不让球 / 让球）+ 比分列 -->
      <table v-else class="bet-table">
        <thead>
          <tr>
            <th class="col-no">编号</th>
            <th class="col-league">赛事</th>
            <th class="col-time">开赛时间</th>
            <th class="col-vs">主队 VS 客队</th>
            <th class="col-score">比分</th>
            <th class="col-hc">让球</th>
            <th class="col-odd">胜</th>
            <th class="col-odd">平</th>
            <th class="col-odd">负</th>
            <th class="col-bet">投注区</th>
            <th class="col-act">操作</th>
          </tr>
        </thead>
        <tbody v-for="group in groups" :key="group.date">
          <tr class="date-row">
            <td colspan="11">
              <button type="button" class="date-toggle" @click="toggleDate(group.date)">
                <span class="caret" :class="{ collapsed: collapsedDates[group.date] }">▾</span>
                {{ group.label }}
                <span class="date-count">{{ group.items.length }} 场</span>
              </button>
            </td>
          </tr>
          <template v-if="!collapsedDates[group.date]">
            <template v-for="(m, idx) in group.items" :key="m.id">
              <tr
                class="match-row nspf-row"
                :class="{ alt: idx % 2 === 1, miss: isMissingScore(m) }"
                @click="$emit('goDetail', m.id)"
              >
                <td class="col-no" rowspan="2">{{ m.round || '-' }}</td>
                <td class="col-league" rowspan="2">
                  <span class="league-badge" :style="leagueBadgeStyle(m)">{{ leagueName(m) }}</span>
                </td>
                <td class="col-time" rowspan="2">
                  <div class="kickoff">{{ kickoffText(m) }}</div>
                  <div class="status-mini">{{ statusText(m.status) }}</div>
                </td>
                <td class="col-vs" rowspan="2">
                  <div class="vs-line">
                    <span class="home">{{ teamName(m, 'home') }}</span>
                    <span class="vs">VS</span>
                    <span class="away">{{ teamName(m, 'away') }}</span>
                  </div>
                </td>
                <td class="col-score" rowspan="2">
                  <div class="score-show" :class="{ empty: isMissingScore(m) }">
                    <template v-if="!isMissingScore(m)">
                      <b>{{ m.homeGoals ?? 0 }}</b>
                      <span>:</span>
                      <b>{{ m.awayGoals ?? 0 }}</b>
                      <span class="result-tag">{{ resultText(m.result) }}</span>
                    </template>
                    <template v-else>待回写</template>
                  </div>
                </td>
                <td class="col-hc">
                  <span class="hc-box">
                    <span v-if="m.isSingle" class="single-flag" title="单关">单</span>
                    0
                  </span>
                </td>
                <td v-if="hasNspf(m)" class="col-odd">{{ fmtOdds(m.oddsNspfWin) }}</td>
                <td v-if="hasNspf(m)" class="col-odd">{{ fmtOdds(m.oddsNspfDraw) }}</td>
                <td v-if="hasNspf(m)" class="col-odd">{{ fmtOdds(m.oddsNspfLose) }}</td>
                <td v-if="!hasNspf(m)" class="col-odd unsold" colspan="3">未开售</td>
                <td class="col-bet" rowspan="2" @click.stop>
                  <button
                    type="button"
                    class="expand-btn"
                    :class="{ on: expanded[m.id] }"
                    @click="toggleExpand(m.id)"
                  >
                    {{ expanded[m.id] ? '收起投注' : '展开投注' }}
                  </button>
                </td>
                <td class="col-act" rowspan="2" @click.stop>
                  <button class="link-btn" @click="$emit('goDetail', m.id)">详情</button>
                </td>
              </tr>
              <tr
                class="match-row spf-row"
                :class="{ alt: idx % 2 === 1, miss: isMissingScore(m) }"
                @click="$emit('goDetail', m.id)"
              >
                <td class="col-hc">
                  <span class="hc-box" :class="handicapClass(m.handicap)">
                    {{ formatHandicapDisplay(m.handicap) }}
                  </span>
                </td>
                <td v-if="hasSpf(m)" class="col-odd">{{ fmtOdds(m.oddsSpfWin) }}</td>
                <td v-if="hasSpf(m)" class="col-odd">{{ fmtOdds(m.oddsSpfDraw) }}</td>
                <td v-if="hasSpf(m)" class="col-odd">{{ fmtOdds(m.oddsSpfLose) }}</td>
                <td v-if="!hasSpf(m)" class="col-odd unsold" colspan="3">未开售</td>
              </tr>
              <tr v-if="expanded[m.id]" class="bf-expand-row" :class="{ alt: idx % 2 === 1 }">
                <td colspan="11">
                  <BfPanel :match="m" :top3-scores="top3Scores" show-hit />
                </td>
              </tr>
            </template>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
/**
 * 竞彩比分共享表格：在赛（upcoming）/ 历史（history）两种模式。
 * 展开投注区由内部 BfPanel 子组件渲染（比分赔率 + 历史相似 Top3）。
 */
import { reactive } from 'vue'
import { fmtOdds, formatHandicap } from '@/utils/matchMeta'
import BfPanel from './BfPanel.vue'

const props = defineProps({
  /** upcoming | history */
  mode: { type: String, required: true },
  /** [{ date, label, items }] */
  groups: { type: Array, required: true },
  leagues: { type: Array, default: () => [] },
})

defineEmits(['goDetail'])

const collapsedDates = reactive({})
const expanded = reactive({})
const top3Scores = reactive({})

const LEAGUE_COLORS = [
  '#137AAC', '#1F4E79', '#2E7D32', '#6A1B9A', '#C62828',
  '#EF6C00', '#00838F', '#455A64', '#5D4037', '#283593',
]

function leagueName(m) {
  return m.leagueInfo?.name || props.leagues.find((l) => l.id === m.league)?.name || m.league || '-'
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

function resultText(r) {
  return { H: '主胜', A: '客胜', D: '平' }[r] || ''
}

function isMissingScore(m) {
  if (!m) return true
  if (m.status !== 'finished') return true
  if (m.result == null) return true
  if (m.homeGoals == null || m.awayGoals == null) return true
  return false
}

function hasNspf(m) {
  return [m.oddsNspfWin, m.oddsNspfDraw, m.oddsNspfLose].some((v) => v != null && v !== '')
}

function hasSpf(m) {
  return [m.oddsSpfWin, m.oddsSpfDraw, m.oddsSpfLose].some((v) => v != null && v !== '')
}

function oddText(v, ok) {
  if (!ok) return '-'
  return fmtOdds(v)
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

function toggleDate(date) {
  collapsedDates[date] = !collapsedDates[date]
}

function toggleExpand(id) {
  expanded[id] = !expanded[id]
}
</script>

<style scoped>
.table-wrap {
  overflow-x: auto;
}

.bet-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.bet-table th {
  text-align: left;
  padding: 10px 12px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-color);
  font-weight: 500;
  white-space: nowrap;
}

.bet-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  vertical-align: middle;
}

.date-row td {
  background: rgba(19, 122, 172, 0.12);
  padding: 6px 12px;
}

.date-toggle {
  background: none;
  border: none;
  color: var(--color-blue);
  cursor: pointer;
  font-size: 0.92rem;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
}

.caret {
  display: inline-block;
  transition: transform 0.15s ease;
}

.caret.collapsed {
  transform: rotate(-90deg);
}

.date-count {
  color: var(--text-muted);
  font-size: 0.8rem;
  margin-left: 4px;
}

.match-row {
  cursor: pointer;
}

.match-row.alt,
.bf-expand-row.alt {
  background: rgba(255, 255, 255, 0.02);
}

.match-row.miss {
  background: rgba(var(--color-orange-rgb), 0.06);
}

.match-row:hover {
  background: rgba(19, 122, 172, 0.08);
}

.col-no { width: 72px; color: var(--text-muted); }
.col-league { width: 72px; }
.col-time { width: 110px; white-space: nowrap; }
.col-vs { min-width: 200px; }
.col-score { width: 120px; }
.col-hc { width: 64px; height: 36px; }
.col-odd { width: 72px; }
.col-bet { width: 110px; }
.col-act { width: 72px; }

/* 在赛模式：8 格赔率矩阵 */
.cell-odds-wrap {
  padding: 0 !important;
  vertical-align: stretch;
}
.odds-grid {
  display: grid;
  grid-template-columns: 64px 72px 72px 72px;
  width: 100%;
  min-width: 280px;
}
.odds-grid .o-hc,
.odds-grid .o-sp {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  border-right: 1px solid rgba(255, 255, 255, 0.04);
  font-family: Consolas, monospace;
  font-weight: 600;
  box-sizing: border-box;
}
.odds-grid .o-hc {
  color: var(--text-primary);
  font-weight: 700;
}
.odds-grid .o-hc.hc-neg { color: #22c55e; }
.odds-grid .o-hc.hc-pos { color: #ef4444; }
.odds-grid .o-sp {
  color: var(--text-primary);
  background: rgba(0, 120, 200, 0.08);
}
.odds-grid > :nth-child(n + 5) {
  border-bottom: 0;
}

/* 历史模式：让球框 + 赔率单元格 */
.col-odd {
  height: 36px;
  font-family: Consolas, monospace;
  font-weight: 600;
  color: var(--text-primary);
  background: rgba(0, 120, 200, 0.08);
}
.col-odd.unsold {
  color: var(--text-muted);
  font-weight: 500;
}
.hc-box {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 36px;
  padding: 4px 8px;
  font-weight: 700;
  font-family: Consolas, monospace;
  color: var(--text-primary);
}
.hc-box.hc-neg,
.odds-grid .o-hc.hc-neg { color: #22c55e; }
.hc-box.hc-pos,
.odds-grid .o-hc.hc-pos { color: #ef4444; }

.league-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  color: #fff;
  font-size: 0.78rem;
  line-height: 1.4;
}

.kickoff {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.status-mini {
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
}

.single-flag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 3px;
  background: #c62828;
  color: #fff;
  font-size: 0.68rem;
  line-height: 1;
}
.nspf-row .single-flag {
  position: absolute;
  top: -6px;
  left: -2px;
  background: none;
  color: #ef4444;
  font-weight: 800;
}

.vs-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.vs {
  color: var(--text-muted);
  font-size: 0.8rem;
}

.score-show {
  font-family: Consolas, monospace;
  font-size: 16px;
  color: var(--color-gold);
  font-weight: 700;
}

.score-show.empty {
  color: var(--color-orange);
  font-size: 12px;
  font-weight: 600;
}

.score-show span {
  margin: 0 2px;
}

.result-tag {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.expand-btn {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  color: var(--color-blue);
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 0.82rem;
}

.expand-btn.on {
  border-color: var(--color-blue);
  background: rgba(19, 122, 172, 0.15);
}

.link-btn {
  display: block;
  width: 100%;
  margin: 2px 0;
  padding: 2px 4px;
  background: transparent;
  border: 0;
  color: var(--color-blue);
  font-size: 12px;
  cursor: pointer;
}

.link-btn:hover {
  text-decoration: underline;
}

.bf-expand-row td {
  padding: 8px 12px 14px;
  background: rgba(0, 0, 0, 0.18);
}
</style>

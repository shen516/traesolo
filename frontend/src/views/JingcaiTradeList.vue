<template>
  <div class="jingcai-trade-page">
    <div class="page-head card">
      <div class="page-head-main">
        <h1 class="page-title">竞彩足球列表</h1>
        <p class="page-sub">
          采集自 trade.500.com/jczq 全玩法（单关/胜平负/让球/混合过关/比分/进球数/半全场），仅供分析研究，不构成投注建议。
        </p>
      </div>
      <div class="page-head-actions">
        <button
          v-if="canManage"
          class="btn btn-outline"
          :disabled="busyAction"
          @click="doHistory"
        >{{ busyAction === 'history' ? '回补中...' : '历史回补' }}</button>
        <button
          v-if="canManage"
          class="btn btn-outline"
          :disabled="busyAction"
          @click="doVerify"
        >{{ busyAction === 'verify' ? '校验中...' : '赛果校验' }}</button>
        <button
          class="btn btn-outline"
          :disabled="busyAction"
          @click="openSummary"
        >汇总报表</button>
        <button
          class="btn btn-outline"
          :disabled="busyAction"
          @click="openSpChanges"
        >SP异动</button>
        <button
          class="btn btn-outline"
          :disabled="busyAction"
          @click="doExport"
        >导出CSV</button>
        <button
          v-if="canRefresh"
          class="btn btn-outline"
          :disabled="refreshing"
          @click="refresh"
        >{{ refreshing ? '刷新中...' : '立即刷新' }}</button>
      </div>
    </div>

    <!-- 玩法 tab -->
    <div class="play-tabs card">
      <button
        v-for="t in playTabs"
        :key="t.key"
        class="play-tab"
        :class="{ active: play === t.key }"
        @click="switchPlay(t.key)"
      >{{ t.label }}</button>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar card">
      <div class="filter-section">
        <span class="filter-label">销售日</span>
        <select :value="selectedDate" class="filter-select" @change="onDateChange">
          <option value="">全部</option>
          <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
      <div class="filter-section">
        <span class="filter-label">联赛</span>
        <input
          v-model="leagueKeyword"
          class="search-input"
          placeholder="输入联赛名称"
          @keyup.enter="onFilterChange"
        />
      </div>
      <button class="btn btn-sm btn-primary" @click="onFilterChange">查询</button>
      <span class="result-hint">共 <b>{{ matches.length }}</b> 场</span>
    </div>

    <StateBlock v-if="loading" type="loading" text="数据加载中..." />
    <StateBlock v-else-if="errorMsg" type="error" :text="errorMsg" retry-text="重新加载" @retry="loadData" />
    <StateBlock v-else-if="!matches.length" type="empty" :text="`暂无${currentTab.label}数据`">
      <div class="state-extra">
        可点击「立即刷新」，或到定时任务页启用「竞彩全玩法采集」
      </div>
    </StateBlock>

    <div v-else class="table-card card">
      <div class="table-wrap">
        <table class="trade-table">
          <thead>
            <tr>
              <th class="col-no">场次</th>
              <th class="col-league">赛事</th>
              <th class="col-team">主队</th>
              <th class="col-score">让球</th>
              <th class="col-team">客队</th>
              <th class="col-time">开赛</th>
              <th class="col-status">状态</th>
              <th class="col-play">投注选项（点击选号）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in matches" :key="m.process_id">
              <td class="col-no">{{ m.match_num || '-' }}</td>
              <td class="col-league">
                <span class="league-badge">{{ m.league_name || '-' }}</span>
              </td>
              <td class="col-team">{{ m.home_name || '-' }}</td>
              <td class="col-score">{{ handicapText(m.handicap) }}</td>
              <td class="col-team">{{ m.away_name || '-' }}</td>
              <td class="col-time">{{ kickoffText(m) }}</td>
              <td class="col-status">
                <span class="sale-badge" :class="'sale-' + (m.sale_status || 'open')">
                  {{ m.sale_status_label || '在售' }}
                </span>
                <span v-if="countdownText(m)" class="countdown">{{ countdownText(m) }}</span>
              </td>
              <td class="col-play">
                <div class="odds-groups">
                  <div v-for="grp in playGroups(m)" :key="grp.play" class="odds-group">
                    <span class="odds-group-label">{{ grp.label }}</span>
                    <div class="odds-btns">
                      <button
                        v-for="opt in grp.options"
                        :key="opt.value"
                        class="odds-btn"
                        :class="{ active: isSelected(m, grp.play, opt.value), disabled: m.closed }"
                        :disabled="m.closed"
                        @click="toggleSelect(m, grp.play, opt)"
                      >
                        <span class="opt-label">{{ opt.label }}</span>
                        <span class="opt-sp">{{ fmtOdds(opt.sp) }}</span>
                      </button>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 选号 / 奖金计算面板 -->
    <div class="bet-panel card">
      <div class="bet-summary">
        <div class="bet-summary-left">
          <span class="bet-count">已选 <b>{{ selectedMatchCount }}</b> 场 / <b>{{ selectedList.length }}</b> 个选项</span>
          <span v-if="calcResult" class="bet-meta">
            共 <b>{{ calcResult.bet_count }}</b> 注 · 金额 <b>¥{{ calcResult.total_amount }}</b>
            <template v-if="calcResult.ok">
              · 预计奖金 <b>¥{{ calcResult.min_amount }}</b> ~ <b>¥{{ calcResult.max_amount }}</b>
            </template>
          </span>
          <span v-else class="bet-meta hint">选择场次与玩法后点击「计算奖金」</span>
        </div>
        <div class="bet-summary-right">
          <select v-model="selectedPass" class="filter-select" :disabled="!selectedList.length">
            <option v-for="p in passTypeOptions" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
          <label class="times-label">
            倍数
            <input v-model.number="times" type="number" min="1" max="999" class="times-input" />
          </label>
          <button class="btn btn-sm btn-outline" :disabled="!selectedList.length" @click="clearAll">清空</button>
          <button
            class="btn btn-sm btn-primary"
            :disabled="!selectedList.length || calcLoading"
            @click="doCalculate"
          >{{ calcLoading ? '计算中...' : '计算奖金' }}</button>
          <button
            v-if="calcResult && calcResult.details && calcResult.details.length"
            class="btn btn-sm btn-outline"
            @click="showDetails = !showDetails"
          >{{ showDetails ? '收起明细' : '查看明细' }}</button>
        </div>
      </div>

      <div v-if="calcResult && !calcResult.ok && calcResult.reason" class="calc-error">
        {{ calcResult.reason }}
      </div>
      <div v-if="calcError" class="calc-error">{{ calcError }}</div>
      <div v-if="calcResult && calcResult.invalid && calcResult.invalid.length" class="calc-warn">
        {{ calcResult.invalid.length }} 个选项无效（SP 缺失或比赛过期），已排除
      </div>

      <!-- 已选清单 -->
      <div v-if="selectedList.length" class="selected-list">
        <span
          v-for="s in selectedList"
          :key="s.key"
          class="selected-chip"
          @click="removeSelected(s.key)"
        >
          {{ s.match_num }} {{ s.home_name }} vs {{ s.away_name }} · {{ PLAY_NAMES[s.play] }} {{ s.label }}
          <i class="chip-close">×</i>
        </span>
      </div>

      <!-- 奖金明细 -->
      <div v-if="showDetails && calcResult && calcResult.details" class="detail-list">
        <div v-if="calcResult.truncated" class="detail-hint">明细超过 200 注，仅展示前 200 注</div>
        <div v-for="(d, i) in calcResult.details" :key="i" class="detail-row">
          <span class="detail-idx">{{ i + 1 }}</span>
          <span class="detail-items">
            <template v-for="(it, j) in d.items" :key="j">
              <span class="detail-item">
                {{ it.home_name }} vs {{ it.away_name }} {{ PLAY_NAMES[it.play] }}{{ optionLabel(it.play, it.option) }}@{{ fmtOdds(it.sp) }}
              </span>
              <span v-if="j < d.items.length - 1" class="detail-sep">×</span>
            </template>
          </span>
          <span class="detail-pass">{{ d.pass_type === 'single' ? '单关' : d.pass_type.replace('x', '串') }}</span>
          <span class="detail-amount">¥{{ d.amount }}</span>
        </div>
      </div>

      <div class="bet-footnote">仅供学习研究与数据分析，不构成投注建议，请勿用于任何赌博行为。</div>
    </div>

    <!-- SP 异动弹窗 -->
    <div v-if="spOpen" class="modal-mask" @click.self="spOpen = false">
      <div class="modal-panel">
        <div class="modal-head">
          <h3>SP 异动监测</h3>
          <button class="modal-close" @click="spOpen = false">×</button>
        </div>
        <div class="modal-body">
          <div class="modal-filters">
            <label class="checkbox">
              <input v-model="spOnlyAlert" type="checkbox" @change="loadSpChanges" /> 只看告警（|涨跌幅| ≥ {{ spThreshold * 100 }}%）
            </label>
            <span v-if="spCount" class="modal-count">共 {{ spCount }} 条</span>
          </div>
          <div v-if="spLoading" class="modal-empty">加载中...</div>
          <div v-else-if="!spChanges.length" class="modal-empty">暂无 SP 异动记录（轮询触发后自动记录）</div>
          <table v-else class="sp-table">
            <thead>
              <tr>
                <th>场次</th><th>玩法</th><th>选项</th><th>原SP</th><th>新SP</th><th>涨跌</th><th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in spChanges" :key="c.id">
                <td class="sp-match">
                  <span class="sp-num">{{ c.match_num || '-' }}</span>
                  <span class="sp-teams">{{ c.home_name }} vs {{ c.away_name }}</span>
                </td>
                <td>{{ PLAY_NAMES[c.play] || c.play }}</td>
                <td>{{ optionLabel(c.play, c.option) }}</td>
                <td>{{ fmtOdds(c.old_sp) }}</td>
                <td>{{ fmtOdds(c.new_sp) }}</td>
                <td>
                  <span class="sp-pct" :class="c.alert ? 'sp-alert' : (c.change_pct >= 0 ? 'up' : 'down')">
                    {{ pctText(c.change_pct) }}
                  </span>
                  <span v-if="c.alert" class="sp-alert-tag">告警</span>
                </td>
                <td class="sp-time">{{ c.detected_at }}</td>
              </tr>
            </tbody>
          </table>
          <div class="modal-footnote">仅供分析研究，不构成投注建议。</div>
        </div>
      </div>
    </div>

    <!-- 汇总报表弹窗 -->
    <div v-if="summaryOpen" class="modal-mask" @click.self="summaryOpen = false">
      <div class="modal-panel">
        <div class="modal-head">
          <h3>汇总报表 · {{ summary?.process_date || '—' }}</h3>
          <button class="modal-close" @click="summaryOpen = false">×</button>
        </div>
        <div class="modal-body">
          <div v-if="summaryLoading" class="modal-empty">加载中...</div>
          <div v-else-if="!summary" class="modal-empty">暂无数据</div>
          <template v-else>
            <div class="summary-grid">
              <div class="summary-item">
                <span class="summary-num">{{ summary.total_matches }}</span>
                <span class="summary-label">总场次</span>
              </div>
              <div class="summary-item">
                <span class="summary-num">{{ summary.ended_matches }}</span>
                <span class="summary-label">已开赛/完赛</span>
              </div>
              <div class="summary-item">
                <span class="summary-num">{{ summary.ended_with_result }}</span>
                <span class="summary-label">有赛果</span>
              </div>
              <div class="summary-item">
                <span class="summary-num">{{ (summary.result_coverage * 100).toFixed(1) }}%</span>
                <span class="summary-label">赛果覆盖率</span>
              </div>
              <div class="summary-item">
                <span class="summary-num">{{ summary.kdg_matches }}</span>
                <span class="summary-label">可单关</span>
              </div>
              <div class="summary-item">
                <span class="summary-num">{{ summary.avg_handicap ?? '-' }}</span>
                <span class="summary-label">平均让球</span>
              </div>
            </div>

            <div class="summary-section">
              <h4>按玩法覆盖</h4>
              <div class="summary-rows">
                <div v-for="(cnt, pk) in summary.play_coverage" :key="pk" class="summary-row">
                  <span class="summary-key">{{ PLAY_NAMES[pk] || pk }}</span>
                  <span class="summary-bar-wrap"><span class="summary-bar" :style="{ width: barWidth(cnt, summary.total_matches) }"></span></span>
                  <span class="summary-val">{{ cnt }} 场</span>
                </div>
              </div>
            </div>

            <div class="summary-section">
              <h4>按销售状态</h4>
              <div class="summary-rows">
                <div v-for="(cnt, st) in summary.by_status" :key="st" class="summary-row">
                  <span class="summary-key">{{ st }}</span>
                  <span class="summary-bar-wrap"><span class="summary-bar" :style="{ width: barWidth(cnt, summary.total_matches) }"></span></span>
                  <span class="summary-val">{{ cnt }} 场</span>
                </div>
              </div>
            </div>

            <div v-if="summary.by_league?.length" class="summary-section">
              <h4>按联赛（Top 8）</h4>
              <div class="summary-rows">
                <div v-for="(item, i) in summary.by_league.slice(0, 8)" :key="i" class="summary-row">
                  <span class="summary-key">{{ item[0] }}</span>
                  <span class="summary-bar-wrap"><span class="summary-bar" :style="{ width: barWidth(item[1], summary.total_matches) }"></span></span>
                  <span class="summary-val">{{ item[1] }} 场</span>
                </div>
              </div>
            </div>
            <div class="modal-footnote">仅供分析研究，不构成投注建议。</div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { jingcaiTradeApi } from '@/api'
import { hasAnyPermission } from '@/utils/permissions'
import { fmtOdds, formatHandicap } from '@/utils/matchMeta'

const route = useRoute()
const router = useRouter()

// 玩法 tab（路由 /jingcai-trade/:play）
const playTabs = [
  { key: 'dg', label: '单关' },
  { key: 'spf', label: '胜平负/让球' },
  { key: 'hhgg', label: '混合过关' },
  { key: 'bf', label: '比分' },
  { key: 'jqs', label: '进球数' },
  { key: 'bqc', label: '半全场' },
]

const PLAY_NAMES = { spf: '胜平负', nspf: '让球', bf: '比分', jqs: '进球数', bqc: '半全场' }
const FULL_PLAYS = ['spf', 'nspf', 'bf', 'jqs', 'bqc']

// 与后端 PLAY_OPTION_ORDER 保持一致
const PLAY_OPTION_ORDER = {
  nspf: ['3', '1', '0'],
  spf: ['3', '1', '0'],
  bf: [
    '1:0', '2:0', '2:1', '3:0', '3:1', '3:2', '4:0', '4:1', '4:2', '5:0',
    '5:1', '5:2', '0:0', '1:1', '2:2', '3:3', '0:1', '0:2', '1:2', '0:3',
    '1:3', '2:3', '0:4', '1:4', '2:4', '0:5', '1:5', '2:5', '胜其它', '平其它', '负其它',
  ],
  jqs: ['0', '1', '2', '3', '4', '5', '6', '7'],
  bqc: ['3-3', '3-1', '3-0', '1-3', '1-1', '1-0', '0-3', '0-1', '0-0'],
}

const FALLBACK_PASS = [
  '2x1', '3x1', '3x3', '3x4', '4x1', '4x4', '4x5', '4x6', '4x11',
  '5x1', '5x5', '5x6', '5x10', '5x16', '5x20', '5x26',
  '6x1', '6x6', '6x7', '6x15', '6x22', '6x42', '6x57',
]

const play = ref(route.params.play || 'dg')
const matches = ref([])
const dates = ref([])
const selectedDate = ref('')
const leagueKeyword = ref('')
const loading = ref(false)
const refreshing = ref(false)
const errorMsg = ref('')

const selectedMap = ref({})
const selectedPass = ref('single')
const times = ref(1)
const passTypeKeys = ref(FALLBACK_PASS)
const calcLoading = ref(false)
const calcResult = ref(null)
const calcError = ref('')
const showDetails = ref(false)

const canRefresh = computed(() =>
  hasAnyPermission('jingcai:manage', 'schedule:manage')
)
const canManage = computed(() =>
  hasAnyPermission('jingcai:manage')
)
const currentTab = computed(() =>
  playTabs.find((t) => t.key === play.value) || playTabs[0]
)
const selectedList = computed(() =>
  Object.values(selectedMap.value).sort((a, b) => String(a.match_num).localeCompare(String(b.match_num)))
)
const selectedMatchCount = computed(() =>
  new Set(selectedList.value.map((s) => `${s.process_id}|${s.process_date}`)).size
)
const passTypeOptions = computed(() => {
  const n = selectedMatchCount.value
  const opts = []
  if (n >= 1) opts.push({ value: 'single', label: '单关' })
  for (const pt of passTypeKeys.value) {
    const m = parseInt(pt.split('x')[0], 10)
    if (m >= 2 && m <= n) opts.push({ value: pt, label: pt.replace('x', '串') })
  }
  return opts
})

watch(passTypeOptions, (opts) => {
  if (!opts.some((o) => o.value === selectedPass.value)) {
    selectedPass.value = opts.length ? opts[opts.length - 1].value : 'single'
  }
})

watch(
  () => route.params.play,
  (p) => {
    if (p && p !== play.value) {
      play.value = p
      loadData()
    }
  }
)

function switchPlay(key) {
  if (key === play.value) return
  router.push({ path: `/jingcai-trade/${key}` })
}

function optionLabel(p, v) {
  if (p === 'spf' || p === 'nspf') return { 3: '胜', 1: '平', 0: '负' }[v] || v
  if (p === 'jqs') return v === '7' ? '7+' : v
  if (p === 'bqc') {
    const map = { 3: '胜', 1: '平', 0: '负' }
    const [h, f] = String(v).split('-')
    return `${map[h] || h}${map[f] || f}`
  }
  return v
}

function activePlays() {
  if (play.value === 'dg' || play.value === 'hhgg') return FULL_PLAYS
  if (play.value === 'spf') return ['spf', 'nspf']
  return [play.value]
}

function playGroups(m) {
  const groups = []
  for (const p of activePlays()) {
    const odds = m.odds?.[p]
    if (!odds) continue
    const order = PLAY_OPTION_ORDER[p] || Object.keys(odds)
    const options = order
      .filter((v) => odds[v] != null)
      .map((v) => ({ value: v, label: optionLabel(p, v), sp: odds[v] }))
    if (options.length) groups.push({ play: p, label: PLAY_NAMES[p] || p, options })
  }
  return groups
}

function selKey(m, p, v) {
  return `${m.process_id}|${m.process_date}|${p}|${v}`
}

function isSelected(m, p, v) {
  return !!selectedMap.value[selKey(m, p, v)]
}

function toggleSelect(m, p, opt) {
  const key = selKey(m, p, opt.value)
  const next = { ...selectedMap.value }
  if (next[key]) {
    delete next[key]
  } else {
    next[key] = {
      key,
      process_id: m.process_id,
      process_date: m.process_date,
      play: p,
      option: opt.value,
      sp: opt.sp,
      label: opt.label,
      match_num: m.match_num,
      home_name: m.home_name,
      away_name: m.away_name,
    }
  }
  selectedMap.value = next
  calcResult.value = null
  calcError.value = ''
}

function removeSelected(key) {
  const next = { ...selectedMap.value }
  delete next[key]
  selectedMap.value = next
  calcResult.value = null
}

function clearAll() {
  selectedMap.value = {}
  calcResult.value = null
  calcError.value = ''
  showDetails.value = false
}

function handicapText(hc) {
  const t = formatHandicap(hc)
  return t == null || t === '' ? '-' : t
}

function kickoffText(m) {
  if (!m.match_date) return m.match_time || '-'
  const md = String(m.match_date).slice(5)
  return m.match_time ? `${md} ${m.match_time}` : md
}

async function loadData(silent = false) {
  if (!silent) {
    loading.value = true
  }
  errorMsg.value = ''
  try {
    const params = { play: play.value }
    if (selectedDate.value) params.process_date = selectedDate.value
    if (leagueKeyword.value) params.league_name = leagueKeyword.value
    const res = await jingcaiTradeApi.getMatches(params)
    matches.value = res.matches || []
    dates.value = res.dates || []
  } catch (e) {
    if (!silent) errorMsg.value = e?.message || '加载失败'
  } finally {
    if (!silent) loading.value = false
  }
}

// ===== P3：销售时序倒计时 + 静默轮询 =====

const POLL_INTERVAL = 60_000 // 60 秒静默轮询列表
const nowTick = ref(Date.now())
let pollTimer = null

// 每 30 秒刷新一次倒计时（不重新请求数据）
const tickTimer = setInterval(() => {
  nowTick.value = Date.now()
}, 30_000)

function countdownText(m) {
  if (!m || m.closed) return ''
  // 读取 nowTick 以建立响应式依赖，使倒计时每 30 秒重算（Vue 在渲染时收集依赖）
  void nowTick.value
  const sec = m.remaining_seconds
  if (sec == null || sec <= 0) return ''
  const h = Math.floor(sec / 3600)
  const min = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  const pad = (n) => String(n).padStart(2, '0')
  if (h > 0) return `${h}:${pad(min)}:${pad(s)}`
  return `${min}:${pad(s)}`
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    // 静默轮询：有场次处于「在售/临场」且临近封盘时才拉取最新 SP
    if (matches.value.some((m) => !m.closed && m.sale_status !== 'ended')) {
      loadData(true)
    }
  }, POLL_INTERVAL)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadPassTypes() {
  try {
    const res = await jingcaiTradeApi.getPassTypes()
    if (res?.pass_types?.length) passTypeKeys.value = res.pass_types
  } catch (_e) {
    // 忽略，使用内置兜底列表
  }
}

async function doCalculate() {
  if (!selectedList.value.length) return
  calcLoading.value = true
  calcError.value = ''
  showDetails.value = false
  try {
    calcResult.value = await jingcaiTradeApi.calculate({
      selections: selectedList.value.map((s) => ({
        process_id: s.process_id,
        process_date: s.process_date,
        play: s.play,
        option: s.option,
      })),
      pass_types: [selectedPass.value],
      times: Math.max(1, Math.min(Number(times.value) || 1, 999)),
    })
  } catch (e) {
    calcError.value = e?.message || '计算失败'
    calcResult.value = null
  } finally {
    calcLoading.value = false
  }
}

async function refresh() {
  refreshing.value = true
  errorMsg.value = ''
  try {
    await jingcaiTradeApi.refresh()
    await loadData()
  } catch (e) {
    errorMsg.value = e?.message || '刷新失败'
  } finally {
    refreshing.value = false
  }
}

// ===== P4：历史回补 / 赛果校验 / 导出 / 报表 / SP 异动 =====

const busyAction = ref('')

function pctText(pct) {
  if (pct == null) return '-'
  const v = (pct * 100).toFixed(2)
  return `${v > 0 ? '+' : ''}${v}%`
}

function barWidth(val, total) {
  if (!total) return '0%'
  return `${Math.min(100, Math.round((val / total) * 100))}%`
}

async function doHistory() {
  busyAction.value = 'history'
  try {
    const res = await jingcaiTradeApi.history({ days_back: 30 })
    alert(`历史回补完成：新增 ${res?.saved_count ?? 0} 场，更新 ${res?.updated_count ?? 0} 场（${res?.days_back ?? 30} 天）`)
    await loadData()
  } catch (e) {
    alert('历史回补失败：' + (e?.message || '未知错误'))
  } finally {
    busyAction.value = ''
  }
}

async function doVerify() {
  busyAction.value = 'verify'
  try {
    const res = await jingcaiTradeApi.verify({ days_back: 30 })
    const mis = res?.mismatches?.length || 0
    alert(
      `赛果校验完成：检查 ${res?.checked ?? 0} 场，一致 ${res?.matched ?? 0}，` +
      `不一致 ${res?.mismatched ?? 0}，缺赛果 ${res?.missing ?? 0}` +
      (mis ? `（明细前 ${mis} 条见控制台）` : '')
    )
    if (mis) console.warn('[赛果校验] 不一致明细:', res.mismatches)
  } catch (e) {
    alert('赛果校验失败：' + (e?.message || '未知错误'))
  } finally {
    busyAction.value = ''
  }
}

async function doExport() {
  busyAction.value = 'export'
  try {
    const params = {}
    if (selectedDate.value) params.process_date = selectedDate.value
    // http.js 拦截器已把响应归一化为 response.data；blob 响应时 response.data 即 Blob 本身，
    // 因此这里直接使用返回值，不要再 .data 解包（否则得到 undefined → 导出空文件）。
    const blob = await jingcaiTradeApi.exportCsv(params)
    if (!blob || blob.size === 0) {
      alert('没有可导出的数据' + (selectedDate.value ? `（${selectedDate.value}）` : ''))
      return
    }
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `jingcai_trade_${selectedDate.value || 'latest'}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    alert(`导出成功：${a.download}（${blob.size} 字节）`)
  } catch (e) {
    alert('导出失败：' + (e?.message || '未知错误'))
  } finally {
    busyAction.value = ''
  }
}

// 汇总报表
const summaryOpen = ref(false)
const summaryLoading = ref(false)
const summary = ref(null)

async function openSummary() {
  summaryOpen.value = true
  summaryLoading.value = true
  summary.value = null
  try {
    const params = {}
    if (selectedDate.value) params.process_date = selectedDate.value
    summary.value = await jingcaiTradeApi.getSummary(params)
  } catch (e) {
    alert('汇总加载失败：' + (e?.message || '未知错误'))
  } finally {
    summaryLoading.value = false
  }
}

// SP 异动
const spOpen = ref(false)
const spLoading = ref(false)
const spChanges = ref([])
const spCount = ref(0)
const spThreshold = ref(0.2)
const spOnlyAlert = ref(false)

async function loadSpChanges() {
  spLoading.value = true
  try {
    const params = { limit: 100 }
    if (spOnlyAlert.value) params.only_alert = true
    const res = await jingcaiTradeApi.getSpChanges(params)
    spChanges.value = res?.changes || []
    spCount.value = res?.count || 0
    spThreshold.value = res?.threshold ?? 0.2
  } catch (e) {
    alert('SP 异动加载失败：' + (e?.message || '未知错误'))
  } finally {
    spLoading.value = false
  }
}

function openSpChanges() {
  spOpen.value = true
  loadSpChanges()
}

function onDateChange(e) {
  selectedDate.value = e.target.value
  loadData()
}

function onFilterChange() {
  loadData()
}

onMounted(() => {
  loadPassTypes()
  loadData()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
  clearInterval(tickTimer)
})
</script>

<style scoped>
.play-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.play-tab {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary, #666);
  padding: 6px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}
.play-tab:hover {
  background: rgba(0, 0, 0, 0.05);
}
.play-tab.active {
  background: var(--primary, #137aac);
  color: #fff;
}
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.filter-section {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-label {
  font-size: 13px;
  color: var(--text-secondary, #666);
}
.filter-select,
.search-input {
  padding: 6px 10px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  font-size: 13px;
}
.result-hint {
  font-size: 13px;
  color: var(--text-secondary, #666);
}
.table-card {
  overflow: hidden;
}
.table-wrap {
  overflow-x: auto;
}
.trade-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.trade-table th,
.trade-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-color, #eee);
  text-align: center;
  white-space: nowrap;
}
.trade-table th {
  background: var(--bg-secondary, #f7f8fa);
  color: var(--text-secondary, #666);
  font-weight: 600;
}
.col-no { width: 70px; }
.col-league { width: 110px; }
.col-team { width: 120px; }
.col-score { width: 70px; }
.col-time { width: 96px; }
.col-status { width: 110px; }
.col-play { text-align: left !important; white-space: normal !important; min-width: 420px; }
.league-badge {
  background: #137aac;
  color: #fff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

/* 销售状态徽标（P3 时序） */
.sale-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.4;
}
.sale-open { background: #e6f7ef; color: #0f8a56; }
.sale-closing { background: #fff7e6; color: #c47b00; }
.sale-closed { background: #fdecec; color: #c0392b; }
.sale-started { background: #eef2f7; color: #5a6b82; }
.sale-ended { background: #f0f0f0; color: #8a8a8a; }
.countdown {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #c47b00;
  font-variant-numeric: tabular-nums;
}

/* 赔率选号 */
.odds-groups {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.odds-group {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}
.odds-group-label {
  flex: 0 0 48px;
  font-size: 12px;
  color: #999;
  padding-top: 6px;
  text-align: right;
}
.odds-btns {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.odds-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 44px;
  padding: 3px 6px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 11px;
  line-height: 1.25;
  transition: all 0.15s;
}
.odds-btn:hover {
  border-color: #137aac;
}
.odds-btn .opt-sp {
  color: #137aac;
  font-family: 'Consolas', 'Menlo', monospace;
}
.odds-btn.active {
  background: #137aac;
  border-color: #137aac;
}
.odds-btn.active .opt-label,
.odds-btn.active .opt-sp {
  color: #fff;
}
.odds-btn.disabled,
.odds-btn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
  border-color: #e0e0e0;
}
.odds-btn.disabled:hover,
.odds-btn:disabled:hover {
  border-color: #e0e0e0;
}

/* 投注单面板 */
.bet-panel {
  position: sticky;
  bottom: 0;
  margin-top: 12px;
  z-index: 20;
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.08);
}
.bet-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.bet-summary-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bet-count {
  font-size: 14px;
}
.bet-meta {
  font-size: 13px;
  color: #137aac;
}
.bet-meta.hint {
  color: #999;
}
.bet-summary-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.times-label {
  font-size: 13px;
  color: var(--text-secondary, #666);
  display: flex;
  align-items: center;
  gap: 4px;
}
.times-input {
  width: 60px;
  padding: 5px 8px;
  border: 1px solid var(--border-color, #ddd);
  border-radius: 6px;
  font-size: 13px;
}
.calc-error {
  margin-top: 8px;
  color: #c62828;
  font-size: 13px;
}
.calc-warn {
  margin-top: 8px;
  color: #ef6c00;
  font-size: 13px;
}
.selected-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.selected-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #eef6fb;
  color: #137aac;
  border: 1px solid #cfe6f2;
  border-radius: 12px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}
.chip-close {
  font-style: normal;
  font-weight: 700;
}
.detail-list {
  margin-top: 10px;
  max-height: 260px;
  overflow-y: auto;
  border-top: 1px dashed var(--border-color, #eee);
  padding-top: 8px;
}
.detail-hint {
  font-size: 12px;
  color: #ef6c00;
  margin-bottom: 6px;
}
.detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px solid #f4f4f4;
}
.detail-idx {
  flex: 0 0 36px;
  color: #999;
}
.detail-items {
  flex: 1;
  min-width: 0;
}
.detail-item {
  color: #333;
}
.detail-sep {
  margin: 0 4px;
  color: #999;
}
.detail-pass {
  flex: 0 0 70px;
  color: #137aac;
}
.detail-amount {
  flex: 0 0 80px;
  text-align: right;
  color: #c62828;
  font-family: 'Consolas', 'Menlo', monospace;
}
.bet-footnote {
  margin-top: 8px;
  font-size: 12px;
  color: #b71c1c;
}

/* P4：弹窗 / SP 异动 / 汇总 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-panel {
  background: #fff;
  border-radius: 10px;
  width: 720px;
  max-width: 92vw;
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.18);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-color, #eee);
}
.modal-head h3 {
  margin: 0;
  font-size: 16px;
}
.modal-close {
  border: none;
  background: transparent;
  font-size: 20px;
  cursor: pointer;
  color: #999;
  line-height: 1;
}
.modal-body {
  padding: 14px 18px;
  overflow-y: auto;
}
.modal-empty {
  padding: 40px 0;
  text-align: center;
  color: #999;
  font-size: 13px;
}
.modal-filters {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 10px;
  font-size: 13px;
}
.checkbox {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.modal-count {
  color: var(--text-secondary, #666);
}
.modal-footnote {
  margin-top: 12px;
  font-size: 12px;
  color: #b71c1c;
}

/* SP 异动表 */
.sp-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.sp-table th,
.sp-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-color, #f0f0f0);
  text-align: left;
  white-space: nowrap;
}
.sp-table th {
  background: var(--bg-secondary, #f7f8fa);
  color: var(--text-secondary, #666);
}
.sp-match {
  display: flex;
  flex-direction: column;
}
.sp-num {
  font-size: 11px;
  color: #999;
}
.sp-teams {
  font-weight: 500;
}
.sp-pct {
  font-family: 'Consolas', 'Menlo', monospace;
}
.sp-pct.up { color: #c62828; }
.sp-pct.down { color: #0f8a56; }
.sp-pct.sp-alert {
  color: #fff;
  background: #c62828;
  padding: 1px 6px;
  border-radius: 4px;
}
.sp-alert-tag {
  margin-left: 4px;
  background: #c62828;
  color: #fff;
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
}
.sp-time {
  color: #999;
  font-size: 11px;
}

/* 汇总 */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.summary-item {
  background: var(--bg-secondary, #f7f8fa);
  border-radius: 8px;
  padding: 12px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.summary-num {
  font-size: 20px;
  font-weight: 700;
  color: #137aac;
  font-family: 'Consolas', 'Menlo', monospace;
}
.summary-label {
  font-size: 12px;
  color: var(--text-secondary, #666);
}
.summary-section {
  margin-bottom: 14px;
}
.summary-section h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-secondary, #666);
}
.summary-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.summary-key {
  flex: 0 0 90px;
  color: #333;
}
.summary-bar-wrap {
  flex: 1;
  height: 10px;
  background: var(--bg-secondary, #f0f2f5);
  border-radius: 5px;
  overflow: hidden;
}
.summary-bar {
  display: block;
  height: 100%;
  background: #137aac;
  border-radius: 5px;
}
.summary-val {
  flex: 0 0 56px;
  text-align: right;
  color: var(--text-secondary, #666);
}
</style>

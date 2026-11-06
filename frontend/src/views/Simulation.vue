<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">模拟预测</h1>
      <p class="page-subtitle">对已排期未来赛事做只读比分推演：概率对比 · 比分分布 · 奖金分析（不落库）</p>
    </div>

    <!-- 赛事选择 -->
    <div class="card selector-card">
      <div class="card-header">
        <h2 class="card-title">选择未来赛事</h2>
        <span class="card-sub">仅展示未开赛（upcoming）赛事</span>
      </div>
      <div class="filter-row">
        <select v-model="filters.leagueId" class="filter-select" @change="loadMatches(1)">
          <option value="">全部联赛</option>
          <option v-for="l in leagues" :key="l.id" :value="l.id">{{ l.name }}</option>
        </select>
        <input v-model="filters.matchDate" type="date" class="filter-input" @change="loadMatches(1)" />
        <input
          v-model="filters.keyword"
          class="filter-input keyword"
          placeholder="搜索球队 / 编号"
          @keyup.enter="loadMatches(1)"
        />
        <button class="btn btn-outline" @click="loadMatches(1)">查询</button>
      </div>

      <div v-if="matchesLoading" class="state-banner loading-banner">
        <span class="spinner"></span><span>赛事加载中...</span>
      </div>
      <div v-else-if="!matches.length" class="empty-hint">暂无未开赛赛事</div>
      <div v-else class="match-list">
        <div
          v-for="m in matches"
          :key="m.id"
          class="match-item"
          :class="{ active: selectedMatchId === m.id }"
          @click="selectedMatchId = m.id"
        >
          <input
            type="checkbox"
            class="batch-check"
            title="加入批量模拟 / 串关（最多 8 场）"
            :checked="batchIds.includes(m.id)"
            @click.stop
            @change="toggleBatch(m.id)"
          />
          <span class="match-no">{{ m.match_no || '—' }}</span>
          <span class="match-league">{{ (m.league && m.league.name) || m.league_id }}</span>
          <span class="match-teams">
            {{ teamName(m.home_team) }} <em>vs</em> {{ teamName(m.away_team) }}
          </span>
          <span class="match-time">{{ m.match_date }} {{ m.match_time }}</span>
          <span v-if="m.handicap != null" class="match-hc">让 {{ m.handicap }}</span>
        </div>
      </div>
      <div class="match-pagination" v-if="matchPages > 1">
        <span class="page-info">第 {{ matchPage }} / {{ matchPages }} 页 · 共 {{ matchTotal }} 场</span>
        <div class="page-buttons">
          <button class="btn btn-sm" :disabled="matchPage <= 1" @click="loadMatches(matchPage - 1)">上一页</button>
          <button class="btn btn-sm" :disabled="matchPage >= matchPages" @click="loadMatches(matchPage + 1)">下一页</button>
        </div>
      </div>
    </div>

    <!-- 高级选项（折叠） -->
    <div class="card">
      <div class="card-header clickable" @click="showAdvanced = !showAdvanced">
        <h2 class="card-title">高级选项（假设推演）</h2>
        <span class="card-sub">{{ showAdvanced ? '收起 ▲' : '展开 ▼' }}</span>
      </div>
      <div v-if="showAdvanced" class="advanced-grid">
        <div class="adv-group">
          <div class="adv-group-title">泊松 λ（留空=自动计算）</div>
          <label>主队 λ <input v-model.number="adv.lambdaHome" type="number" step="0.05" min="0.05" max="6" placeholder="自动" /></label>
          <label>客队 λ <input v-model.number="adv.lambdaAway" type="number" step="0.05" min="0.05" max="6" placeholder="自动" /></label>
          <label>xG 主队 λ <input v-model.number="adv.xgLambdaHome" type="number" step="0.05" min="0.05" max="6" placeholder="自动" /></label>
          <label>xG 客队 λ <input v-model.number="adv.xgLambdaAway" type="number" step="0.05" min="0.05" max="6" placeholder="自动" /></label>
        </div>
        <div class="adv-group">
          <div class="adv-group-title">融合权重（留空=联赛/全局权重）</div>
          <label>ELO <input v-model.number="adv.wElo" type="number" step="0.05" min="0" max="1" placeholder="默认" /></label>
          <label>泊松 <input v-model.number="adv.wPoisson" type="number" step="0.05" min="0" max="1" placeholder="默认" /></label>
          <label>xG <input v-model.number="adv.wXg" type="number" step="0.05" min="0" max="1" placeholder="默认" /></label>
          <label>蒙特卡洛 <input v-model.number="adv.wMc" type="number" step="0.05" min="0" max="1" placeholder="默认" /></label>
        </div>
        <div class="adv-group">
          <div class="adv-group-title">环境与联赛</div>
          <label>主场优势系数 <input v-model.number="adv.homeAdvantage" type="number" step="0.05" min="0.8" max="1.6" placeholder="默认" /></label>
          <label>联赛场均进球 <input v-model.number="adv.leagueAvgGoals" type="number" step="0.05" min="1.5" max="4.5" placeholder="默认" /></label>
          <label>天气
            <select v-model="adv.weather">
              <option value="">赛事默认</option>
              <option v-for="w in weatherOptions" :key="w" :value="w">{{ w }}</option>
            </select>
          </label>
          <label>草皮
            <select v-model="adv.pitch">
              <option value="">赛事默认</option>
              <option v-for="p in pitchOptions" :key="p" :value="p">{{ p }}</option>
            </select>
          </label>
        </div>
        <div class="adv-group">
          <div class="adv-group-title">模拟与奖金</div>
          <label>模拟次数 <input v-model.number="adv.simulations" type="number" step="1000" min="1000" max="50000" /></label>
          <label>随机种子 <input v-model.number="adv.seed" type="number" min="0" placeholder="留空随机" /></label>
          <label>SP 模式
            <select v-model="adv.spMode">
              <option value="auto">自动（真实优先）</option>
              <option value="real">仅真实 SP</option>
              <option value="synthetic">合成兜底</option>
            </select>
          </label>
          <label>让球数（留空=赛事让球）<input v-model.number="adv.handicap" type="number" step="1" min="-10" max="10" placeholder="赛事" /></label>
        </div>
        <div class="adv-actions">
          <button class="btn btn-outline btn-sm" @click="resetAdvanced">重置高级选项</button>
        </div>
      </div>
    </div>

    <!-- 运行 -->
    <div class="run-bar">
      <button
        class="btn btn-primary btn-lg"
        :disabled="!selectedMatchId || running || !!validationError"
        @click="runSimulation"
      >
        {{ running ? '模拟计算中...' : '运行模拟预测' }}
      </button>
      <button
        class="btn btn-outline btn-lg"
        :disabled="!selectedMatchId || running || sensRunning || !!validationError"
        @click="runSensitivity"
      >
        {{ sensRunning ? 'λ 扫描中...' : 'λ 敏感性分析' }}
      </button>
      <button
        class="btn btn-outline btn-lg"
        :disabled="batchIds.length < 2 || running || batchRunning || !!validationError"
        @click="runBatch"
      >
        {{ batchRunning ? '批量模拟中...' : `批量模拟 · ${batchIds.length}串1` }}
      </button>
      <span v-if="result" class="run-meta">
        耗时 {{ result.meta.elapsed_ms }} ms · {{ result.meta.simulations }} 次模拟
        <template v-if="result.meta.seed != null"> · 种子 {{ result.meta.seed }}</template>
        <template v-if="result.meta.cache_hit"> · 缓存命中</template>
      </span>
    </div>
    <div class="batch-hint" v-if="batchIds.length === 1">再勾选至少 1 场赛事即可运行批量模拟 / 串关（2~8 场）</div>

    <div v-if="validationError" class="state-banner error-banner">
      <span>⚠️ {{ validationError }}</span>
    </div>
    <div v-if="simError" class="state-banner error-banner">
      <span>⚠️ {{ simError }}</span>
    </div>
    <div v-if="result && result.meta.warnings && result.meta.warnings.length" class="state-banner warn-banner">
      <span v-for="(w, i) in result.meta.warnings" :key="i">⚠️ {{ w }}<br v-if="i < result.meta.warnings.length - 1" /></span>
    </div>

    <!-- 结果 -->
    <template v-if="result">
      <div class="card match-brief">
        <div class="brief-title">
          {{ result.match.league_name || result.match.league_id }} · {{ result.match.match_no }}
          · {{ result.match.match_date }} {{ result.match.match_time }}
        </div>
        <div class="brief-teams">
          <span class="team home">{{ result.home.name }}</span>
          <span class="vs">VS</span>
          <span class="team away">{{ result.away.name }}</span>
        </div>
        <div class="brief-params">
          <span>主队：攻 {{ fmt(result.home.attack) }} / 防 {{ fmt(result.home.defense) }} / ELO {{ result.home.elo }}</span>
          <span>客队：攻 {{ fmt(result.away.attack) }} / 防 {{ fmt(result.away.defense) }} / ELO {{ result.away.elo }}</span>
          <span>联赛场均 {{ fmt(result.league.avg_goals) }}</span>
        </div>
      </div>

      <div class="tabs">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="tab-btn"
          :class="{ active: activeTab === t.key }"
          @click="activeTab = t.key"
        >{{ t.label }}</button>
      </div>

      <!-- 概率对比 -->
      <div v-show="activeTab === 'probs'" class="card tab-panel">
        <div class="prob-compare">
          <div class="prob-row header">
            <span class="col-label"></span>
            <span>主胜</span><span>平局</span><span>客胜</span>
          </div>
          <div class="prob-row">
            <span class="col-label">基线</span>
            <span v-for="k in ['home_win_prob', 'draw_prob', 'away_win_prob']" :key="'b' + k">{{ pct(result.baseline[k]) }}</span>
          </div>
          <div class="prob-row">
            <span class="col-label">模拟</span>
            <span v-for="k in ['home_win_prob', 'draw_prob', 'away_win_prob']" :key="'s' + k">{{ pct(result.simulated[k]) }}</span>
          </div>
          <div class="prob-row delta" v-if="hasOverrides">
            <span class="col-label">变化</span>
            <span
              v-for="k in ['home_win_prob', 'draw_prob', 'away_win_prob']"
              :key="'d' + k"
              :class="deltaClass(result.delta[k])"
            >{{ signedPct(result.delta[k]) }}</span>
          </div>
        </div>
        <div class="lambda-row">
          <span>λ 主队：{{ fmt(result.simulated.lambda_home) }}
            <em v-if="hasOverrides" :class="deltaClass(result.delta.lambda_home)">（{{ signed(result.delta.lambda_home) }}）</em>
          </span>
          <span>λ 客队：{{ fmt(result.simulated.lambda_away) }}
            <em v-if="hasOverrides" :class="deltaClass(result.delta.lambda_away)">（{{ signed(result.delta.lambda_away) }}）</em>
          </span>
          <span>推荐比分：{{ result.simulated.main_score }}（备选：{{ (result.simulated.alt_scores || []).join('、') }}）</span>
        </div>
        <div ref="probChartRef" class="chart-box"></div>
      </div>

      <!-- 比分热力 -->
      <div v-show="activeTab === 'score'" class="card tab-panel">
        <div class="card-header">
          <h2 class="card-title">比分概率热力图</h2>
          <span class="card-sub">默认展示 0~5 球；颜色越深概率越高</span>
        </div>
        <div ref="heatChartRef" class="chart-box tall"></div>
        <div class="top-scores">
          <div class="top-score-item" v-for="t in (result.simulated.mc && result.simulated.mc.top_scores) || []" :key="t.score">
            <span class="score">{{ t.score.replace('-', ':') }}</span>
            <span class="score-prob">{{ pct(t.prob) }}</span>
          </div>
        </div>
      </div>

      <!-- 总进球 -->
      <div v-show="activeTab === 'goals'" class="card tab-panel">
        <div class="market-stats">
          <div class="stat-chip">大 2.5 球 <b>{{ pct(result.simulated.mc && result.simulated.mc.over_2_5_prob) }}</b></div>
          <div class="stat-chip">大 3.5 球 <b>{{ pct(result.simulated.mc && result.simulated.mc.over_3_5_prob) }}</b></div>
          <div class="stat-chip">双方进球 <b>{{ pct(result.simulated.mc && result.simulated.mc.btts_prob) }}</b></div>
          <div class="stat-chip">总进球均值 <b>{{ fmt(result.simulated.mc && result.simulated.mc.total_goals_avg) }}</b></div>
        </div>
        <div ref="goalChartRef" class="chart-box"></div>
      </div>

      <!-- 市场指标 -->
      <div v-show="activeTab === 'market'" class="card tab-panel">
        <table class="data-table">
          <thead>
            <tr><th>指标</th><th>模型概率</th><th>SP</th><th>隐含概率</th><th>EV（每2元）</th><th>价值</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in marketRows" :key="row.key" :class="{ 'value-row': row.value }">
              <td>{{ row.label }}</td>
              <td>{{ pct(row.prob) }}</td>
              <td>{{ row.sp != null ? fmt(row.sp) : '—' }}</td>
              <td>{{ row.implied != null ? pct(row.implied) : '—' }}</td>
              <td :class="row.ev > 0 ? 'pos' : 'neg'">{{ row.ev != null ? fmt(row.ev) : '—' }}</td>
              <td>{{ row.value ? '★ 价值' : '' }}</td>
            </tr>
          </tbody>
        </table>
        <p class="disclaimer">{{ result.prize.disclaimer }} · SP 来源：{{ spSourceText }}</p>
      </div>

      <!-- 模型分量 -->
      <div v-show="activeTab === 'components'" class="card tab-panel">
        <div class="component-grid">
          <div class="component-card" v-for="c in componentRows" :key="c.key">
            <div class="component-title">{{ c.label }} <span class="component-weight">权重 {{ pct(c.weight) }}</span></div>
            <div class="component-probs">
              <span>主胜 {{ pct(c.probs.home_win_prob) }}</span>
              <span>平 {{ pct(c.probs.draw_prob) }}</span>
              <span>客胜 {{ pct(c.probs.away_win_prob) }}</span>
            </div>
          </div>
        </div>
        <div class="weights-row">
          <span>生效权重来源：{{ result.simulated.weight_source }}</span>
          <span v-if="result.meta.applied_overrides.length">已应用覆盖：{{ result.meta.applied_overrides.join('、') }}</span>
        </div>
      </div>

      <!-- 奖金分析 -->
      <div v-show="activeTab === 'prize'" class="card tab-panel">
        <div class="prize-section" v-for="play in prizePlays" :key="play.key">
          <div class="prize-title">
            {{ play.label }}
            <span class="prize-src">SP 来源：{{ play.source }}</span>
            <span v-if="play.key === 'nspf'" class="prize-src">让球 {{ play.handicap >= 0 ? '+' : '' }}{{ play.handicap }}</span>
          </div>
          <table class="data-table compact">
            <thead>
              <tr><th>选项</th><th>模型概率</th><th>SP</th><th>单注奖金</th><th>EV</th><th>价值</th></tr>
            </thead>
            <tbody>
              <tr v-for="o in play.options" :key="o.key" :class="{ 'value-row': o.value }">
                <td>{{ o.label }}</td>
                <td>{{ pct(o.prob) }}</td>
                <td>{{ o.sp != null ? fmt(o.sp) : '—' }}</td>
                <td>{{ o.payout != null ? fmt(o.payout) + ' 元' : '—' }}</td>
                <td :class="o.ev > 0 ? 'pos' : 'neg'">{{ o.ev != null ? fmt(o.ev) : '—' }}</td>
                <td>{{ o.value ? '★' : '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="prize-section" v-if="bfTopValue.length">
          <div class="prize-title">比分 Top 价值选项</div>
          <div class="top-value-list">
            <div class="top-value-item" v-for="t in bfTopValue" :key="t.score">
              <span class="score">{{ t.score.replace(':', ':') }}</span>
              <span>SP {{ fmt(t.sp) }}</span>
              <span>概率 {{ pct(t.prob) }}</span>
              <span :class="t.ev > 0 ? 'pos' : 'neg'">EV {{ fmt(t.ev) }}</span>
            </div>
          </div>
        </div>
        <p class="disclaimer">{{ result.prize.disclaimer }}</p>
      </div>
    </template>

    <!-- λ 敏感性分析 -->
    <div v-if="sensResult" class="card">
      <div class="card-header">
        <h2 class="card-title">λ 敏感性分析</h2>
        <span class="card-sub">
          {{ sensResult.match.home_team }} vs {{ sensResult.match.away_team }} ·
          基准 λ 主 {{ fmt(sensResult.series.lambda_home.base) }} / 客 {{ fmt(sensResult.series.lambda_away.base) }} ·
          扫描 ±{{ sensResult.meta.range }}（步长 {{ sensResult.meta.step }}）
        </span>
      </div>
      <div ref="sensChartRef" class="chart-box"></div>
    </div>

    <!-- 批量模拟 / 串关 -->
    <div v-if="batchResult" class="card">
      <div class="card-header">
        <h2 class="card-title">批量模拟 · {{ batchResult.meta.succeeded }}/{{ batchResult.meta.requested }} 场成功</h2>
        <span class="card-sub">耗时 {{ batchResult.meta.elapsed_ms }} ms · 每场 {{ batchResult.meta.simulations }} 次模拟</span>
      </div>
      <div v-if="batchResult.errors.length" class="state-banner error-banner">
        <span v-for="(e, i) in batchResult.errors" :key="i">⚠️ {{ e.match_id }}：{{ e.detail }}<br v-if="i < batchResult.errors.length - 1" /></span>
      </div>
      <table class="data-table compact">
        <thead>
          <tr><th>赛事</th><th>主胜</th><th>平局</th><th>客胜</th><th>推荐比分</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in batchResult.results" :key="r.match.id">
            <td>{{ r.match.home_team.name }} vs {{ r.match.away_team.name }}</td>
            <td>{{ pct(r.simulated.home_win_prob) }}</td>
            <td>{{ pct(r.simulated.draw_prob) }}</td>
            <td>{{ pct(r.simulated.away_win_prob) }}</td>
            <td>{{ r.simulated.main_score }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="batchResult.parlay" class="parlay-block">
        <div class="prize-title">
          {{ batchResult.parlay.legs }}串1 串关奖金（胜平负全组合）
          <span class="prize-src">总组合 {{ batchResult.parlay.total_combos }} · 期望奖金 {{ fmt(batchResult.parlay.expected_payout) }} 元 · 期望 EV {{ fmt(batchResult.parlay.expected_ev) }} 元</span>
        </div>
        <table class="data-table compact">
          <thead>
            <tr><th>组合（概率前 10）</th><th>命中概率</th><th>单注奖金</th><th>EV</th></tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in batchResult.parlay.top_combos" :key="i" :class="{ 'value-row': c.ev > 0 }">
              <td>{{ c.picks.join(' / ') }}</td>
              <td>{{ pct(c.prob) }}</td>
              <td>{{ fmt(c.payout) }} 元</td>
              <td :class="c.ev > 0 ? 'pos' : 'neg'">{{ fmt(c.ev) }}</td>
            </tr>
          </tbody>
        </table>
        <p class="disclaimer">{{ batchResult.parlay.disclaimer }} · 串关单注上限 {{ batchResult.parlay.payout_cap.toLocaleString() }} 元</p>
      </div>
    </div>

    <!-- 模拟历史 -->
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">模拟历史（最近 {{ history.length }} 条）</h2>
        <span class="card-sub">勾选 2 条可并排对比概率与参数</span>
        <button class="btn btn-outline btn-sm" @click="loadHistory">刷新</button>
      </div>
      <div v-if="!history.length" class="empty-hint">暂无模拟记录</div>
      <table v-else class="data-table compact">
        <thead>
          <tr><th></th><th>时间</th><th>赛事</th><th>主胜/平/客胜</th><th>推荐比分</th><th>参数</th><th>耗时</th></tr>
        </thead>
        <tbody>
          <tr v-for="h in history" :key="h.id" :class="{ 'hist-selected': compareIds.includes(h.id) }">
            <td>
              <input
                type="checkbox"
                class="batch-check"
                :checked="compareIds.includes(h.id)"
                :disabled="!compareIds.includes(h.id) && compareIds.length >= 2"
                @change="toggleCompare(h.id)"
              />
            </td>
            <td>{{ h.created_at }}</td>
            <td>{{ h.match_name }}</td>
            <td>{{ pct(h.summary.home_win_prob) }} / {{ pct(h.summary.draw_prob) }} / {{ pct(h.summary.away_win_prob) }}</td>
            <td>{{ h.summary.main_score }}</td>
            <td class="hist-params">{{ histParamsText(h) }}</td>
            <td>{{ h.elapsed_ms }} ms</td>
          </tr>
        </tbody>
      </table>

      <div v-if="comparePair.length === 2" class="hist-compare">
        <h3 class="hist-compare-title">方案对比</h3>
        <div class="hist-compare-grid">
          <div v-for="(h, idx) in comparePair" :key="h.id" class="hist-compare-col">
            <div class="hist-compare-label">方案 {{ idx + 1 }} · {{ h.match_name }}</div>
            <div class="hist-compare-meta">{{ h.created_at }} · {{ histParamsText(h) }}</div>
            <table class="data-table compact">
              <tbody>
                <tr><td>主胜</td><td>{{ pct(h.summary.home_win_prob) }}</td></tr>
                <tr><td>平局</td><td>{{ pct(h.summary.draw_prob) }}</td></tr>
                <tr><td>客胜</td><td>{{ pct(h.summary.away_win_prob) }}</td></tr>
                <tr><td>推荐比分</td><td>{{ h.summary.main_score || '—' }}</td></tr>
                <tr><td>λ 主/客</td><td>{{ fmtLambda(h.summary.lambda_home) }} / {{ fmtLambda(h.summary.lambda_away) }}</td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <table class="data-table compact hist-diff-table">
          <thead>
            <tr><th>指标</th><th>方案1</th><th>方案2</th><th>差值 (2−1)</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in compareDiffRows" :key="row.key">
              <td>{{ row.label }}</td>
              <td>{{ row.a }}</td>
              <td>{{ row.b }}</td>
              <td :class="{ 'diff-pos': row.deltaNum > 0, 'diff-neg': row.deltaNum < 0 }">{{ row.delta }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import echarts from '@/utils/echarts'
import { CHART_COLORS, CHART_TOOLTIP, axisLabelStyle } from '@/utils/chartTheme'
import { matchApi, leagueApi, predictionApi } from '@/api'

const weatherOptions = ['晴', '多云', '阴', '小雨', '大雨', '雪']
const pitchOptions = ['优秀', '良好', '一般', '较差']

// ---------- 赛事选择 ----------
const leagues = ref([])
const matches = ref([])
const matchesLoading = ref(false)
const matchPage = ref(1)
const matchTotal = ref(0)
const matchPages = computed(() => Math.max(1, Math.ceil(matchTotal.value / 20)))
const selectedMatchId = ref('')
const filters = reactive({ leagueId: '', matchDate: '', keyword: '' })

async function loadLeagues() {
  try {
    const res = await leagueApi.getAll()
    leagues.value = res.leagues || res.items || []
  } catch {
    leagues.value = []
  }
}

async function loadMatches(page = 1) {
  matchesLoading.value = true
  try {
    const params = { page, page_size: 20, view: 'summary' }
    if (filters.leagueId) params.league_id = filters.leagueId
    if (filters.matchDate) params.match_date = filters.matchDate
    if (filters.keyword) params.keyword = filters.keyword
    const res = await matchApi.getUpcoming(params)
    matches.value = res.matches || []
    matchPage.value = res.pagination?.page || page
    matchTotal.value = res.pagination?.total || 0
  } catch {
    matches.value = []
    matchTotal.value = 0
  } finally {
    matchesLoading.value = false
  }
}

function teamName(t) {
  return (t && (t.name || t.short_name)) || '—'
}

// ---------- 批量模拟 / 串关 ----------
const batchIds = ref([])
const batchResult = ref(null)
const batchRunning = ref(false)

function toggleBatch(id) {
  const i = batchIds.value.indexOf(id)
  if (i >= 0) {
    batchIds.value.splice(i, 1)
  } else {
    if (batchIds.value.length >= 8) {
      simError.value = '批量模拟最多支持 8 场赛事'
      return
    }
    batchIds.value.push(id)
  }
}

async function runBatch() {
  if (batchIds.value.length < 2 || validationError.value) return
  batchRunning.value = true
  simError.value = ''
  try {
    const payload = {
      match_ids: [...batchIds.value],
      simulations: Math.min(adv.simulations || 5000, 20000),
      // 批量层面无手动 SP 输入，manual 归入 auto
      sp_mode: ['auto', 'real', 'synthetic'].includes(adv.spMode) ? adv.spMode : 'auto',
    }
    if (adv.seed != null && adv.seed !== '') payload.seed = adv.seed
    batchResult.value = await predictionApi.simulateBatch(payload)
    loadHistory()
  } catch (e) {
    simError.value = e.message || '批量模拟失败'
  } finally {
    batchRunning.value = false
  }
}

// ---------- 高级选项 ----------
const showAdvanced = ref(false)
const adv = reactive({
  lambdaHome: null, lambdaAway: null, xgLambdaHome: null, xgLambdaAway: null,
  wElo: null, wPoisson: null, wXg: null, wMc: null,
  homeAdvantage: null, leagueAvgGoals: null, weather: '', pitch: '',
  simulations: 10000, seed: null, spMode: 'auto', handicap: null,
})

function resetAdvanced() {
  Object.assign(adv, {
    lambdaHome: null, lambdaAway: null, xgLambdaHome: null, xgLambdaAway: null,
    wElo: null, wPoisson: null, wXg: null, wMc: null,
    homeAdvantage: null, leagueAvgGoals: null, weather: '', pitch: '',
    simulations: 10000, seed: null, spMode: 'auto', handicap: null,
  })
}

function buildOverrides() {
  const o = {}
  if (adv.lambdaHome != null && adv.lambdaHome !== '') o.lambda_home = adv.lambdaHome
  if (adv.lambdaAway != null && adv.lambdaAway !== '') o.lambda_away = adv.lambdaAway
  if (adv.xgLambdaHome != null && adv.xgLambdaHome !== '') o.xg_lambda_home = adv.xgLambdaHome
  if (adv.xgLambdaAway != null && adv.xgLambdaAway !== '') o.xg_lambda_away = adv.xgLambdaAway
  const weights = {}
  if (adv.wElo != null && adv.wElo !== '') weights.elo = adv.wElo
  if (adv.wPoisson != null && adv.wPoisson !== '') weights.poisson = adv.wPoisson
  if (adv.wXg != null && adv.wXg !== '') weights.xg = adv.wXg
  if (adv.wMc != null && adv.wMc !== '') weights.monte_carlo = adv.wMc
  if (Object.keys(weights).length) o.weights = weights
  if (adv.homeAdvantage != null && adv.homeAdvantage !== '') o.poisson_home_advantage = adv.homeAdvantage
  if (adv.leagueAvgGoals != null && adv.leagueAvgGoals !== '') o.league_avg_goals = adv.leagueAvgGoals
  if (adv.weather) o.weather = adv.weather
  if (adv.pitch) o.pitch_condition = adv.pitch
  if (adv.spMode && adv.spMode !== 'auto') o.sp_mode = adv.spMode
  if (adv.handicap != null && adv.handicap !== '') o.handicap = adv.handicap
  return Object.keys(o).length ? o : null
}

// ---------- 运行 ----------
const running = ref(false)
const simError = ref('')
const result = ref(null)
const activeTab = ref('probs')

// 前端预校验：与后端 SimulationRequest / SimulationOverrides 约束保持一致，
// 非法时禁用运行按钮，避免只看到 422 拼接文案。
function numOrNull(v) {
  return v == null || v === '' ? null : Number(v)
}

const validationError = computed(() => {
  const sims = numOrNull(adv.simulations)
  if (sims == null || !Number.isFinite(sims) || sims < 1000 || sims > 50000) {
    return '模拟次数须在 1000 ~ 50000 之间'
  }
  const seed = numOrNull(adv.seed)
  if (seed != null && (!Number.isInteger(seed) || seed < 0)) {
    return '随机种子须为不小于 0 的整数'
  }
  const lambdaFields = [
    ['lambdaHome', '主队 λ'], ['lambdaAway', '客队 λ'],
    ['xgLambdaHome', 'xG 主队 λ'], ['xgLambdaAway', 'xG 客队 λ'],
  ]
  for (const [key, label] of lambdaFields) {
    const v = numOrNull(adv[key])
    if (v != null && (!Number.isFinite(v) || v < 0.05 || v > 6)) {
      return `${label} 须在 0.05 ~ 6 之间`
    }
  }
  const weightFields = [['wElo', 'ELO'], ['wPoisson', '泊松'], ['wXg', 'xG'], ['wMc', '蒙特卡洛']]
  let weightSum = 0
  let hasWeight = false
  for (const [key, label] of weightFields) {
    const v = numOrNull(adv[key])
    if (v != null) {
      if (!Number.isFinite(v) || v < 0 || v > 1) return `融合权重 ${label} 须在 0 ~ 1 之间`
      weightSum += v
      hasWeight = true
    }
  }
  if (hasWeight && weightSum <= 0) return '融合权重之和必须大于 0'
  const ha = numOrNull(adv.homeAdvantage)
  if (ha != null && (!Number.isFinite(ha) || ha < 0.8 || ha > 1.6)) {
    return '主场优势系数须在 0.8 ~ 1.6 之间'
  }
  const lag = numOrNull(adv.leagueAvgGoals)
  if (lag != null && (!Number.isFinite(lag) || lag < 1.5 || lag > 4.5)) {
    return '联赛场均进球须在 1.5 ~ 4.5 之间'
  }
  const hc = numOrNull(adv.handicap)
  if (hc != null && (!Number.isInteger(hc) || hc < -10 || hc > 10)) {
    return '让球数须为 -10 ~ 10 的整数'
  }
  return ''
})
const tabs = [
  { key: 'probs', label: '概率对比' },
  { key: 'score', label: '比分热力' },
  { key: 'goals', label: '总进球' },
  { key: 'market', label: '市场指标' },
  { key: 'components', label: '模型分量' },
  { key: 'prize', label: '奖金分析' },
]

const hasOverrides = computed(() =>
  !!(result.value && result.value.meta.applied_overrides.length)
)

async function runSimulation() {
  if (!selectedMatchId.value || validationError.value) return
  running.value = true
  simError.value = ''
  try {
    const payload = {
      match_id: selectedMatchId.value,
      simulations: adv.simulations || 10000,
    }
    if (adv.seed != null && adv.seed !== '') payload.seed = adv.seed
    const overrides = buildOverrides()
    if (overrides) payload.overrides = overrides
    result.value = await predictionApi.simulate(payload)
    activeTab.value = 'probs'
    await nextTick()
    renderCharts()
    loadHistory()
  } catch (e) {
    simError.value = e.message || '模拟失败'
  } finally {
    running.value = false
  }
}

// ---------- λ 敏感性分析 ----------
const sensResult = ref(null)
const sensRunning = ref(false)
const sensChartRef = ref(null)
let sensChart = null

async function runSensitivity() {
  if (!selectedMatchId.value || validationError.value) return
  sensRunning.value = true
  simError.value = ''
  try {
    const payload = {
      match_id: selectedMatchId.value,
      simulations: Math.min(adv.simulations || 2000, 10000),
    }
    if (adv.seed != null && adv.seed !== '') payload.seed = adv.seed
    const overrides = buildOverrides()
    if (overrides) {
      // λ 扫描本身会覆盖 λ，去掉手动 λ 避免冲突；其余覆盖保留
      delete overrides.lambda_home
      delete overrides.lambda_away
      if (Object.keys(overrides).length) payload.overrides = overrides
    }
    sensResult.value = await predictionApi.simulateSensitivity(payload)
    await nextTick()
    renderSensChart()
  } catch (e) {
    simError.value = e.message || '敏感性分析失败'
  } finally {
    sensRunning.value = false
  }
}

function renderSensChart() {
  if (!sensChartRef.value || !sensResult.value) return
  if (!sensChart) sensChart = echarts.init(sensChartRef.value)
  const s = sensResult.value.series
  const mk = (points, key) => points.map((p) => +(p[key] * 100).toFixed(2))
  sensChart.setOption({
    tooltip: { trigger: 'axis', ...CHART_TOOLTIP, valueFormatter: (v) => v + '%' },
    legend: {},
    grid: { left: 40, right: 20, top: 36, bottom: 60 },
    xAxis: [
      {
        type: 'category', name: '主队 λ', position: 'bottom',
        data: s.lambda_home.points.map((p) => p.lambda.toFixed(2)),
        axisLabel: axisLabelStyle(),
      },
      {
        type: 'category', name: '客队 λ', position: 'top',
        data: s.lambda_away.points.map((p) => p.lambda.toFixed(2)),
        axisLabel: axisLabelStyle(), axisLine: { show: false }, axisTick: { show: false },
      },
    ],
    yAxis: { type: 'value', max: 100, axisLabel: { ...axisLabelStyle(), formatter: '{value}%' } },
    series: [
      { name: '主胜(主λ)', type: 'line', xAxisIndex: 0, data: mk(s.lambda_home.points, 'home_win_prob'), itemStyle: { color: CHART_COLORS.blue } },
      { name: '平局(主λ)', type: 'line', xAxisIndex: 0, data: mk(s.lambda_home.points, 'draw_prob'), itemStyle: { color: CHART_COLORS.textMuted } },
      { name: '客胜(主λ)', type: 'line', xAxisIndex: 0, data: mk(s.lambda_home.points, 'away_win_prob'), itemStyle: { color: CHART_COLORS.orange } },
      { name: '主胜(客λ)', type: 'line', xAxisIndex: 1, data: mk(s.lambda_away.points, 'home_win_prob'), lineStyle: { type: 'dashed' }, itemStyle: { color: CHART_COLORS.blue } },
      { name: '平局(客λ)', type: 'line', xAxisIndex: 1, data: mk(s.lambda_away.points, 'draw_prob'), lineStyle: { type: 'dashed' }, itemStyle: { color: CHART_COLORS.textMuted } },
      { name: '客胜(客λ)', type: 'line', xAxisIndex: 1, data: mk(s.lambda_away.points, 'away_win_prob'), lineStyle: { type: 'dashed' }, itemStyle: { color: CHART_COLORS.orange } },
    ],
  }, true)
}

// ---------- 模拟历史 ----------
const history = ref([])
const compareIds = ref([])

const comparePair = computed(() => {
  if (compareIds.value.length !== 2) return []
  return compareIds.value
    .map((id) => history.value.find((h) => h.id === id))
    .filter(Boolean)
})

const compareDiffRows = computed(() => {
  if (comparePair.value.length !== 2) return []
  const [a, b] = comparePair.value
  const sa = a.summary || {}
  const sb = b.summary || {}
  const mkProb = (label, key) => {
    const va = Number(sa[key] ?? 0)
    const vb = Number(sb[key] ?? 0)
    const d = vb - va
    return {
      key,
      label,
      a: pct(va),
      b: pct(vb),
      delta: `${d >= 0 ? '+' : ''}${(d * 100).toFixed(1)}%`,
      deltaNum: d,
    }
  }
  const rows = [
    mkProb('主胜', 'home_win_prob'),
    mkProb('平局', 'draw_prob'),
    mkProb('客胜', 'away_win_prob'),
  ]
  const la = Number(sa.lambda_home)
  const lb = Number(sb.lambda_home)
  if (Number.isFinite(la) && Number.isFinite(lb)) {
    const d = lb - la
    rows.push({
      key: 'lambda_home',
      label: 'λ 主队',
      a: fmtLambda(la),
      b: fmtLambda(lb),
      delta: `${d >= 0 ? '+' : ''}${d.toFixed(2)}`,
      deltaNum: d,
    })
  }
  const aa = Number(sa.lambda_away)
  const ab = Number(sb.lambda_away)
  if (Number.isFinite(aa) && Number.isFinite(ab)) {
    const d = ab - aa
    rows.push({
      key: 'lambda_away',
      label: 'λ 客队',
      a: fmtLambda(aa),
      b: fmtLambda(ab),
      delta: `${d >= 0 ? '+' : ''}${d.toFixed(2)}`,
      deltaNum: d,
    })
  }
  return rows
})

function toggleCompare(id) {
  const i = compareIds.value.indexOf(id)
  if (i >= 0) {
    compareIds.value.splice(i, 1)
    return
  }
  if (compareIds.value.length >= 2) return
  compareIds.value.push(id)
}

async function loadHistory() {
  try {
    const res = await predictionApi.simulateHistory({ limit: 20 })
    history.value = res.history || []
    compareIds.value = compareIds.value.filter((id) =>
      history.value.some((h) => h.id === id),
    )
  } catch {
    history.value = []
    compareIds.value = []
  }
}

function histParamsText(h) {
  const p = h.params || {}
  const parts = []
  if (p.lambda_home != null || p.lambda_away != null) {
    parts.push(`λ ${p.lambda_home ?? '自动'}/${p.lambda_away ?? '自动'}`)
  }
  if (p.weather) parts.push(p.weather)
  if (p.pitch_condition) parts.push('草皮' + p.pitch_condition)
  if (p.league_avg_goals != null) parts.push('场均' + p.league_avg_goals)
  if (p.weights) parts.push('自定义权重')
  if (h.seed != null) parts.push('种子' + h.seed)
  return parts.length ? parts.join(' · ') : '默认参数'
}

function fmtLambda(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : '—'
}

// ---------- 图表 ----------
const probChartRef = ref(null)
const heatChartRef = ref(null)
const goalChartRef = ref(null)
let probChart = null
let heatChart = null
let goalChart = null

function renderCharts() {
  renderProbChart()
  renderHeatChart()
  renderGoalChart()
}

function renderProbChart() {
  if (!probChartRef.value || !result.value) return
  if (!probChart) probChart = echarts.init(probChartRef.value)
  const cats = ['主胜', '平局', '客胜']
  const keys = ['home_win_prob', 'draw_prob', 'away_win_prob']
  const series = [{
    name: '基线', type: 'bar',
    data: keys.map((k) => +(result.value.baseline[k] * 100).toFixed(2)),
    itemStyle: { color: CHART_COLORS.textMuted },
  }]
  if (hasOverrides.value) {
    series.push({
      name: '模拟', type: 'bar',
      data: keys.map((k) => +(result.value.simulated[k] * 100).toFixed(2)),
      itemStyle: { color: CHART_COLORS.blue },
    })
  }
  probChart.setOption({
    tooltip: { trigger: 'axis', ...CHART_TOOLTIP, valueFormatter: (v) => v + '%' },
    legend: hasOverrides.value ? {} : { show: false },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: cats, axisLabel: axisLabelStyle() },
    yAxis: { type: 'value', max: 100, axisLabel: { ...axisLabelStyle(), formatter: '{value}%' } },
    series,
  }, true)
}

function renderHeatChart() {
  if (!heatChartRef.value || !result.value) return
  const mc = result.value.simulated.mc
  if (!mc || !mc.score_matrix) return
  if (!heatChart) heatChart = echarts.init(heatChartRef.value)
  const size = Math.min(6, mc.score_matrix_size)
  const data = []
  let maxP = 0
  for (let h = 0; h < size; h++) {
    for (let a = 0; a < size; a++) {
      const p = mc.score_matrix[h][a]
      if (p > maxP) maxP = p
      data.push([a, h, +(p * 100).toFixed(2)])
    }
  }
  heatChart.setOption({
    tooltip: {
      ...CHART_TOOLTIP,
      formatter: (p) => `主队 ${p.value[1]} : ${p.value[0]} 客队<br/>概率 ${p.value[2]}%`,
    },
    grid: { left: 60, right: 30, top: 30, bottom: 60 },
    xAxis: { type: 'category', name: '客队进球', data: Array.from({ length: size }, (_, i) => i), axisLabel: axisLabelStyle() },
    yAxis: { type: 'category', name: '主队进球', data: Array.from({ length: size }, (_, i) => i), axisLabel: axisLabelStyle() },
    visualMap: {
      min: 0, max: +(maxP * 100).toFixed(2), calculable: true, orient: 'horizontal',
      left: 'center', bottom: 0,
      inRange: { color: ['#12233d', '#1d4ed8', '#38bdf8', '#fbbf24'] },
      textStyle: { color: CHART_COLORS.textMuted },
    },
    series: [{ type: 'heatmap', data, label: { show: true, color: '#fff', fontSize: 10 } }],
  }, true)
}

function renderGoalChart() {
  if (!goalChartRef.value || !result.value) return
  const mc = result.value.simulated.mc
  if (!mc || !mc.goal_distribution) return
  if (!goalChart) goalChart = echarts.init(goalChartRef.value)
  const dist = mc.goal_distribution
  goalChart.setOption({
    tooltip: { trigger: 'axis', ...CHART_TOOLTIP, valueFormatter: (v) => v + '%' },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category',
      data: dist.map((d) => (d.goals >= 10 ? '10+' : String(d.goals))),
      axisLabel: axisLabelStyle(),
    },
    yAxis: { type: 'value', axisLabel: { ...axisLabelStyle(), formatter: '{value}%' } },
    series: [{
      type: 'bar',
      data: dist.map((d) => +(d.prob * 100).toFixed(2)),
      itemStyle: { color: CHART_COLORS.green },
    }],
  }, true)
}

function handleResize() {
  probChart && probChart.resize()
  heatChart && heatChart.resize()
  goalChart && goalChart.resize()
  sensChart && sensChart.resize()
}

watch(activeTab, async () => {
  await nextTick()
  handleResize()
})

// ---------- 派生数据 ----------
function pct(v) {
  return v == null ? '—' : (v * 100).toFixed(1) + '%'
}
function fmt(v) {
  return v == null ? '—' : Number(v).toFixed(2)
}
function signed(v) {
  return v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2)
}
function signedPct(v) {
  return v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + 'pp'
}
function deltaClass(v) {
  if (v == null || Math.abs(v) < 1e-9) return 'flat'
  return v > 0 ? 'pos' : 'neg'
}

const spSourceText = computed(() => {
  const s = result.value?.prize?.sp_source || {}
  const names = { real: '真实', snapshot: '快照', synthetic: '合成', manual: '手动' }
  return ['spf', 'nspf', 'bf', 'tg']
    .map((k) => `${k.toUpperCase()}=${names[s[k]] || s[k] || '—'}`)
    .join(' · ')
})

const marketRows = computed(() => {
  const prize = result.value?.prize
  if (!prize) return []
  const rows = []
  const labels = { win: '主胜', draw: '平局', lose: '客胜' }
  const spf = prize.spf || {}
  for (const k of ['win', 'draw', 'lose']) {
    rows.push({
      key: 'spf-' + k,
      label: '胜平负 · ' + labels[k],
      prob: spf.probs?.[k],
      sp: spf.sp?.[k],
      implied: spf.implied?.[k],
      ev: spf.ev?.[k],
      value: spf.value_flags?.[k],
    })
  }
  const nspf = prize.nspf || {}
  for (const k of ['win', 'draw', 'lose']) {
    rows.push({
      key: 'nspf-' + k,
      label: `让球(${nspf.handicap >= 0 ? '+' : ''}${nspf.handicap ?? 0}) · ` + labels[k],
      prob: nspf.probs?.[k],
      sp: nspf.sp?.[k],
      implied: nspf.implied?.[k],
      ev: nspf.ev?.[k],
      value: nspf.value_flags?.[k],
    })
  }
  const tg = prize.tg || {}
  for (const k of Object.keys(tg.probs || {})) {
    rows.push({
      key: 'tg-' + k,
      label: '总进球 ' + k,
      prob: tg.probs?.[k],
      sp: tg.sp?.[k],
      implied: tg.implied?.[k],
      ev: tg.ev?.[k],
      value: tg.value_flags?.[k],
    })
  }
  return rows
})

const componentRows = computed(() => {
  const sim = result.value?.simulated
  if (!sim || !sim.components) return []
  const labels = { poisson: '泊松', elo: 'ELO', xg: 'xG', monte_carlo: '蒙特卡洛' }
  return Object.keys(labels).map((k) => ({
    key: k,
    label: labels[k],
    weight: sim.weights_used?.[k] ?? 0,
    probs: sim.components[k] || {},
  }))
})

const prizePlays = computed(() => {
  const prize = result.value?.prize
  if (!prize) return []
  const names = { real: '真实', snapshot: '快照', synthetic: '合成', manual: '手动' }
  const labels = { win: '胜', draw: '平', lose: '负' }
  const plays = []
  for (const key of ['spf', 'nspf', 'tg']) {
    const block = prize[key]
    if (!block) continue
    const options = Object.keys(block.probs || {}).map((k) => ({
      key: k,
      label: key === 'tg' ? '总进球 ' + k : labels[k] || k,
      prob: block.probs[k],
      sp: block.sp?.[k],
      payout: block.payout?.[k],
      ev: block.ev?.[k],
      value: block.value_flags?.[k],
    }))
    plays.push({
      key,
      label: key === 'spf' ? '胜平负' : key === 'nspf' ? '让球胜平负' : '总进球',
      source: names[prize.sp_source?.[key]] || prize.sp_source?.[key] || '—',
      handicap: key === 'nspf' ? block.handicap : null,
      options,
    })
  }
  return plays
})

const bfTopValue = computed(() => result.value?.prize?.bf?.top_value || [])

// ---------- 生命周期 ----------
onMounted(() => {
  loadLeagues()
  loadMatches(1)
  loadHistory()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  probChart && probChart.dispose()
  heatChart && heatChart.dispose()
  goalChart && goalChart.dispose()
  sensChart && sensChart.dispose()
})
</script>

<style scoped>
.page-container { max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }
.page-header { margin-bottom: 20px; }
.page-title { font-size: 22px; font-weight: 700; color: var(--text-primary, #e5e9f0); }
.page-subtitle { margin-top: 4px; font-size: 13px; color: var(--text-muted, #8b93a7); }

.card {
  background: var(--card-bg, #141a26);
  border: 1px solid var(--border-color, #232b3b);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.card-header.clickable { cursor: pointer; user-select: none; }
.card-title { font-size: 15px; font-weight: 600; color: var(--text-primary, #e5e9f0); }
.card-sub { font-size: 12px; color: var(--text-muted, #8b93a7); }

.filter-row { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.filter-select, .filter-input {
  background: var(--input-bg, #0f1420);
  border: 1px solid var(--border-color, #232b3b);
  color: var(--text-primary, #e5e9f0);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13px;
}
.filter-input.keyword { flex: 1; min-width: 160px; }

.match-list { display: flex; flex-direction: column; gap: 6px; max-height: 320px; overflow-y: auto; }
.match-item {
  display: flex; align-items: center; gap: 12px;
  padding: 9px 12px; border-radius: 8px; cursor: pointer;
  border: 1px solid transparent;
  background: var(--input-bg, #0f1420);
  font-size: 13px; color: var(--text-secondary, #b6bdd0);
}
.match-item:hover { border-color: var(--border-color, #232b3b); }
.match-item.active { border-color: var(--primary, #3b82f6); background: rgba(59, 130, 246, 0.08); }
.match-no { color: var(--text-muted, #8b93a7); min-width: 64px; }
.batch-check { accent-color: var(--primary, #3b82f6); cursor: pointer; }
.batch-hint { margin: -8px 0 12px; font-size: 12px; color: var(--text-muted, #8b93a7); }
.hist-selected { background: rgba(59, 130, 246, 0.08); }
.hist-compare { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border-color, #232b3b); }
.hist-compare-title { font-size: 14px; margin: 0 0 12px; color: var(--text-primary, #e5e9f0); }
.hist-compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.hist-compare-col { background: var(--input-bg, #0f1420); border-radius: 8px; padding: 10px 12px; }
.hist-compare-label { font-size: 13px; font-weight: 600; color: var(--text-primary, #e5e9f0); }
.hist-compare-meta { font-size: 12px; color: var(--text-muted, #8b93a7); margin: 4px 0 8px; }
.hist-diff-table .diff-pos { color: var(--color-green, #22c55e); }
.hist-diff-table .diff-neg { color: var(--orange, #fb923c); }
@media (max-width: 720px) {
  .hist-compare-grid { grid-template-columns: 1fr; }
}
.match-league { color: var(--gold, #f59e0b); min-width: 72px; }
.match-teams { flex: 1; color: var(--text-primary, #e5e9f0); }
.match-teams em { font-style: normal; color: var(--text-muted, #8b93a7); margin: 0 6px; }
.match-time { color: var(--text-muted, #8b93a7); }
.match-hc { color: var(--orange, #fb923c); }

.match-pagination { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
.page-info { font-size: 12px; color: var(--text-muted, #8b93a7); }
.page-buttons { display: flex; gap: 8px; }

.advanced-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
.adv-group { display: flex; flex-direction: column; gap: 8px; }
.adv-group-title { font-size: 13px; font-weight: 600; color: var(--text-secondary, #b6bdd0); }
.adv-group label {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  font-size: 12px; color: var(--text-muted, #8b93a7);
}
.adv-group input, .adv-group select {
  width: 120px; background: var(--input-bg, #0f1420);
  border: 1px solid var(--border-color, #232b3b);
  color: var(--text-primary, #e5e9f0); border-radius: 6px; padding: 5px 8px; font-size: 12px;
}
.adv-actions { grid-column: 1 / -1; }

.run-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.run-meta { font-size: 12px; color: var(--text-muted, #8b93a7); }

.btn { border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--primary, #3b82f6); color: #fff; }
.btn-outline { background: transparent; border: 1px solid var(--border-color, #232b3b); color: var(--text-secondary, #b6bdd0); }
.btn-sm { padding: 5px 12px; font-size: 12px; }
.btn-lg { padding: 10px 28px; font-size: 14px; }

.state-banner { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; font-size: 13px; }
.loading-banner { background: rgba(59, 130, 246, 0.08); color: var(--text-secondary, #b6bdd0); }
.error-banner { background: rgba(239, 68, 68, 0.1); color: #f87171; }
.warn-banner { background: rgba(245, 158, 11, 0.1); color: #fbbf24; }
.spinner {
  width: 14px; height: 14px; border: 2px solid var(--border-color, #232b3b);
  border-top-color: var(--primary, #3b82f6); border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.empty-hint { padding: 24px; text-align: center; color: var(--text-muted, #8b93a7); font-size: 13px; }

.match-brief { text-align: center; }
.brief-title { font-size: 13px; color: var(--text-muted, #8b93a7); margin-bottom: 8px; }
.brief-teams { display: flex; justify-content: center; align-items: center; gap: 20px; font-size: 20px; font-weight: 700; }
.brief-teams .team.home { color: var(--blue, #60a5fa); }
.brief-teams .team.away { color: var(--orange, #fb923c); }
.brief-teams .vs { color: var(--text-muted, #8b93a7); font-size: 13px; }
.brief-params { display: flex; justify-content: center; gap: 24px; flex-wrap: wrap; margin-top: 8px; font-size: 12px; color: var(--text-muted, #8b93a7); }

.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.tab-btn {
  background: var(--input-bg, #0f1420); border: 1px solid var(--border-color, #232b3b);
  color: var(--text-secondary, #b6bdd0); border-radius: 8px; padding: 7px 14px;
  font-size: 13px; cursor: pointer;
}
.tab-btn.active { background: var(--primary, #3b82f6); border-color: var(--primary, #3b82f6); color: #fff; }
.tab-panel { min-height: 300px; }

.prob-compare { max-width: 560px; margin-bottom: 12px; }
.prob-row { display: grid; grid-template-columns: 80px repeat(3, 1fr); padding: 8px 0; border-bottom: 1px solid var(--border-color, #232b3b); font-size: 14px; }
.prob-row.header { font-size: 12px; color: var(--text-muted, #8b93a7); }
.prob-row.delta { font-weight: 600; }
.col-label { color: var(--text-muted, #8b93a7); font-size: 12px; }
.lambda-row { display: flex; gap: 24px; flex-wrap: wrap; font-size: 13px; color: var(--text-secondary, #b6bdd0); margin-bottom: 12px; }
.lambda-row em { font-style: normal; font-size: 12px; }

.pos { color: #34d399; }
.neg { color: #f87171; }
.flat { color: var(--text-muted, #8b93a7); }

.chart-box { width: 100%; height: 280px; }
.chart-box.tall { height: 380px; }

.top-scores { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
.top-score-item {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  background: var(--input-bg, #0f1420); border-radius: 8px; padding: 8px 14px;
}
.top-score-item .score { font-size: 16px; font-weight: 700; color: var(--text-primary, #e5e9f0); }
.top-score-item .score-prob { font-size: 12px; color: var(--text-muted, #8b93a7); }

.market-stats { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.stat-chip {
  background: var(--input-bg, #0f1420); border-radius: 8px; padding: 8px 14px;
  font-size: 13px; color: var(--text-secondary, #b6bdd0);
}
.stat-chip b { color: var(--text-primary, #e5e9f0); margin-left: 6px; }

.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th, .data-table td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border-color, #232b3b); }
.data-table th { color: var(--text-muted, #8b93a7); font-weight: 500; font-size: 12px; }
.data-table td { color: var(--text-secondary, #b6bdd0); }
.data-table.compact td, .data-table.compact th { padding: 6px 10px; }
.value-row { background: rgba(52, 211, 153, 0.06); }
.disclaimer { margin-top: 12px; font-size: 12px; color: var(--text-muted, #8b93a7); }

.component-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 12px; }
.component-card { background: var(--input-bg, #0f1420); border-radius: 10px; padding: 12px 14px; }
.component-title { font-size: 14px; font-weight: 600; color: var(--text-primary, #e5e9f0); margin-bottom: 8px; }
.component-weight { font-size: 12px; font-weight: 400; color: var(--text-muted, #8b93a7); margin-left: 8px; }
.component-probs { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-secondary, #b6bdd0); }
.weights-row { display: flex; gap: 24px; flex-wrap: wrap; font-size: 12px; color: var(--text-muted, #8b93a7); }

.prize-section { margin-bottom: 20px; }
.prize-title { font-size: 14px; font-weight: 600; color: var(--text-primary, #e5e9f0); margin-bottom: 8px; }
.prize-src { font-size: 12px; font-weight: 400; color: var(--text-muted, #8b93a7); margin-left: 10px; }
.top-value-list { display: flex; flex-direction: column; gap: 6px; }
.top-value-item {
  display: flex; gap: 16px; align-items: center;
  background: var(--input-bg, #0f1420); border-radius: 8px; padding: 8px 12px;
  font-size: 13px; color: var(--text-secondary, #b6bdd0);
}
.top-value-item .score { font-weight: 700; color: var(--text-primary, #e5e9f0); min-width: 48px; }

.parlay-block { margin-top: 16px; }
.hist-params { max-width: 260px; font-size: 12px; color: var(--text-muted, #8b93a7); }
</style>

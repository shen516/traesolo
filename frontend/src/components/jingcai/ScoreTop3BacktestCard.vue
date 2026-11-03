<template>
  <div class="card monitor-card" style="margin-top: 16px">
    <div class="card-header">
      <h2 class="card-title">比分 {{ topLabel }} 回测</h2>
      <span class="card-sub">历史相似盘口比分分布；滚动回测，每场只用开赛前已完赛样本</span>
      <div class="card-actions">
        <select v-model.number="days" class="monitor-select" @change="load">
          <option :value="30">近 30 天</option>
          <option :value="60">近 60 天</option>
          <option :value="90">近 90 天</option>
          <option :value="180">近 180 天</option>
        </select>
        <button class="refresh-btn" :disabled="loading" @click="load">
          {{ loading ? '回测中...' : '重新回测' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="quality-error" style="margin: 0 20px 12px">{{ error }}</div>

    <div v-if="report" class="monitor-body">
      <div class="monitor-kpis">
        <div class="monitor-kpi">
          <span class="qk-label">测试场次</span>
          <b>{{ report.test_size ?? 0 }}</b>
          <span class="qk-sub">样本库 {{ report.pool_size ?? 0 }} 场</span>
        </div>
        <div class="monitor-kpi">
          <span class="qk-label">不约束 {{ topLabel }}</span>
          <b>{{ pct(report.modes?.none?.top3) }}</b>
          <span class="qk-sub">先验基线 {{ pct(report.baselines?.prior?.top3) }}</span>
        </div>
        <div class="monitor-kpi">
          <span class="qk-label">真实方向 {{ topLabel }}</span>
          <b>{{ pct(report.modes?.oracle?.top3) }}</b>
          <span class="qk-sub">方向判断正确时的上限</span>
        </div>
        <div class="monitor-kpi">
          <span class="qk-label">平均相似样本当量</span>
          <b>{{ report.avg_effective_samples ?? '-' }}</b>
          <span class="qk-sub">≥ {{ report.params?.min_effective_samples }} 才用历史统计</span>
        </div>
      </div>

      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>方向来源 / 基线</th>
              <th>场次</th>
              <th>Top1</th>
              <th>{{ topLabel }}</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.label">
              <td>{{ row.label }}</td>
              <td>{{ row.stats?.n ?? 0 }}</td>
              <td>{{ pct(row.stats?.top1) }}</td>
              <td :class="{ better: row.better, worse: row.worse }">{{ pct(row.stats?.top3) }}</td>
              <td class="note">{{ row.note }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="report.direction_accuracy" class="bt-line">
        方向判断准确率：
        <template v-for="(label, key) in DIRECTION_SOURCES" :key="key">
          <span v-if="report.direction_accuracy[key]?.n" class="bt-seg">
            {{ label }} 胜平负 {{ pct(report.direction_accuracy[key].nspf) }}
            · 让球 {{ pct(report.direction_accuracy[key].spf) }}
            · 两者都对 {{ pct(report.direction_accuracy[key].both) }}
            （{{ report.direction_accuracy[key].n }} 场）
          </span>
        </template>
      </p>

      <div v-if="report.by_handicap?.length" class="table-wrapper" style="margin-top: 12px">
        <table class="data-table">
          <thead>
            <tr>
              <th>盘口</th>
              <th>场次</th>
              <th>不约束 {{ topLabel }}</th>
              <th>看盘倾向 {{ topLabel }}</th>
              <th>先验基线 {{ topLabel }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in report.by_handicap" :key="row.handicap">
              <td>{{ formatHandicap(row.handicap) ?? row.handicap }}</td>
              <td>{{ row.none?.n ?? 0 }}</td>
              <td>{{ pct(row.none?.top3) }}</td>
              <td>{{ pct(row.auto?.top3) }}</td>
              <td>{{ pct(row.prior?.top3) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <p class="bt-line">
        依据级别分布：
        <span v-for="(label, level) in LEVEL_LABELS" :key="level" class="bt-seg">
          {{ label }} {{ report.fallback_levels?.[level] ?? 0 }} 场
        </span>
      </p>
      <p class="bt-line muted">
        参数：推荐 {{ topLabel }} · k={{ report.params?.k }} · 带宽 {{ report.params?.bandwidth }} · 先验强度 α={{ report.params?.smoothing_alpha }}
        · 比分 SP 权重 {{ report.params?.bf_prior_weight ?? 0 }}
        · 模型 λ 权重 {{ report.params?.model_prior_weight ?? 0 }}
        · 回溯 {{ report.params?.lookback_days }} 天 · 生成于 {{ report.generated_at }}
      </p>
      <p class="bt-line muted">{{ report.disclaimer }}</p>
    </div>
    <p v-else-if="loading" class="empty-hint">回测计算中…</p>
    <p v-else-if="!error" class="empty-hint">切换到本页后自动回测</p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { matchApi } from '@/api'
import { formatHandicap } from '@/utils/matchMeta'

const props = defineProps({
  /** 父组件传入时优先；未传则根据路由 params.tab === 'monitor' 判断 */
  active: { type: Boolean, default: undefined },
})

const route = useRoute()
const isActive = computed(() => {
  if (props.active !== undefined) return props.active
  return route.params.tab === 'monitor'
})

const DIRECTION_SOURCES = { auto: '看盘倾向', model: '模型倾向' }
const LEVEL_LABELS = {
  0: '双玩法相似',
  1: '单玩法相似',
  2: '同盘口全部',
  3: '纯先验',
}

const days = ref(60)
const loading = ref(false)
const error = ref('')
const report = ref(null)
let loaded = false

const topLabel = computed(() => {
  const n = Number(report.value?.params?.recommend_count)
  return `Top${Number.isFinite(n) && n > 0 ? n : 3}`
})

const rows = computed(() => {
  const r = report.value
  if (!r) return []
  const noneTop3 = r.modes?.none?.top3
  const subsetNone = r.model_subset?.none?.top3
  const cmp = (v, base) => ({
    better: v != null && base != null && v > base + 0.005,
    worse: v != null && base != null && v < base - 0.005,
  })
  return [
    { label: '不约束（默认）', stats: r.modes?.none, note: '前端默认方式' },
    { label: '看盘倾向', stats: r.modes?.auto, note: '方向取看盘启发式', ...cmp(r.modes?.auto?.top3, noneTop3) },
    {
      label: '模型倾向',
      stats: r.modes?.model,
      note: `仅统计有赛前预测的场次；同批不约束 ${topLabel.value} ${pct(subsetNone)}`,
      ...cmp(r.modes?.model?.top3, subsetNone),
    },
    { label: '真实方向（上限）', stats: r.modes?.oracle, note: '胜平负与让球方向都判断正确时' },
    { label: '基线：市场泊松先验', stats: r.baselines?.prior, note: '不使用历史样本' },
    { label: '基线：先验 + 真实方向', stats: r.baselines?.prior_oracle, note: '对照“真实方向”行' },
    { label: '基线：看盘启发式比分', stats: r.baselines?.heuristic, note: '启发式写死的主推 + 备选比分' },
    {
      label: '子集：比分 SP 先验',
      stats: r.bf_subset?.bf_prior,
      note: `仅有完整赛前比分快照的场次；同批泊松先验 ${pct(r.bf_subset?.prior?.top3)}。高于同批才考虑把比分 SP 权重从 0 调高`,
      ...cmp(r.bf_subset?.bf_prior?.top3, r.bf_subset?.prior?.top3),
    },
    {
      label: '子集：模型 λ 先验',
      stats: r.model_lambda_subset?.model_prior,
      note: `仅有赛前 λ 的场次，不约束；同批当前结果 ${pct(r.model_lambda_subset?.none?.top3)}。高于同批才考虑把模型 λ 权重从 0 调高。模型方向按钮仍不开放`,
      ...cmp(r.model_lambda_subset?.model_prior?.top3, r.model_lambda_subset?.none?.top3),
    },
  ]
})

function pct(v) {
  const n = Number(v)
  return v != null && Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '-'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await matchApi.getJingcaiScoreTop3Backtest(days.value)
    loaded = true
  } catch (e) {
    error.value = e?.response?.data?.detail || e.message || '回测失败'
  } finally {
    loading.value = false
  }
}

watch(
  isActive,
  (active) => {
    if (active && !loaded && !loading.value) load()
  },
  { immediate: true },
)
</script>

<style scoped>
.quality-error {
  margin: 0 20px 12px;
  color: var(--color-red);
  font-size: 13px;
}
.monitor-select {
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.monitor-body {
  padding: 0 20px 16px;
}
.monitor-kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.monitor-kpi {
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.monitor-kpi b {
  font-size: 20px;
  color: var(--color-gold);
  font-weight: 600;
}
.monitor-kpi .qk-label {
  font-size: 12px;
  color: var(--text-secondary);
}
.monitor-kpi .qk-sub {
  font-size: 11px;
  color: var(--text-muted, var(--text-secondary));
}
.data-table td.better { color: var(--color-green); font-weight: 600; }
.data-table td.worse { color: var(--color-red); font-weight: 600; }
.data-table td.note { color: var(--text-muted); font-size: 12px; }
.bt-line {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.7;
}
.bt-line.muted { color: var(--text-muted); margin-top: 4px; }
.bt-seg { margin-right: 14px; white-space: nowrap; }
</style>

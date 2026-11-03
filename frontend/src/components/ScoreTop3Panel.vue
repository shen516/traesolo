<template>
  <div class="top3-panel">
    <div class="top3-head">
      <span class="top3-title">历史相似盘口比分分布 Top{{ recommendCount }}</span>
      <div class="dir-group">
        <span class="dir-label">胜平负</span>
        <button
          v-for="opt in NSPF_OPTIONS"
          :key="opt.value"
          type="button"
          class="dir-chip"
          :class="{ on: nspf === opt.value }"
          @click="nspf = opt.value"
        >{{ opt.label }}</button>
      </div>
      <div class="dir-group">
        <span class="dir-label">让球</span>
        <button
          v-for="opt in SPF_OPTIONS"
          :key="opt.value"
          type="button"
          class="dir-chip"
          :class="{ on: spf === opt.value }"
          @click="spf = opt.value"
        >{{ opt.label }}</button>
      </div>
    </div>

    <div v-if="loading" class="top3-hint">计算中...</div>
    <div v-else-if="error" class="top3-hint error">{{ error }}</div>
    <template v-else-if="data">
      <div v-if="!data.available" class="top3-hint">{{ data.reason || '暂无结果' }}</div>
      <template v-else>
        <div class="top3-tags">
          <div
            v-for="(t, i) in data.top3"
            :key="t.score"
            class="top3-tag"
            :class="{ hit: data.actual_score === t.score }"
          >
            <span class="rank">{{ i + 1 }}</span>
            <span class="score">{{ t.score }}</span>
            <span class="prob">{{ pct(t.prob) }}</span>
            <span class="hits" title="相似样本中该比分出现次数">样本 {{ t.sample_hits }}</span>
          </div>
          <UpgradeHint v-if="data.top3_locked" inline text="免费版仅展示第 1 个比分" />
        </div>
        <div class="top3-meta">
          <div>
            依据：{{ data.fallback_label }}；相似样本当量 {{ data.samples?.effective ?? 0 }}
            （同盘口 {{ data.samples?.same_handicap ?? 0 }} 场）
          </div>
          <div v-if="data.outcome_dist">
            相似样本赛果：主胜 {{ pct(data.outcome_dist.home) }} · 平 {{ pct(data.outcome_dist.draw) }}
            · 客胜 {{ pct(data.outcome_dist.away) }}
            <template v-if="data.handicap_dist">
              ｜ 让胜 {{ pct(data.handicap_dist.home) }} · 让平 {{ pct(data.handicap_dist.draw) }}
              · 让负 {{ pct(data.handicap_dist.away) }}
            </template>
          </div>
          <div v-if="constraintText">{{ constraintText }}</div>
          <div v-if="data.constraint?.relaxed?.length" class="warn">
            看盘倾向在该盘口下不兼容，已放宽{{ data.constraint.relaxed.map(relaxedLabel).join('、') }}约束
          </div>
          <div v-if="data.actual_score">
            实际比分 {{ data.actual_score }}
            <template v-if="data.hit != null"> · {{ data.hit ? `命中 Top${recommendCount}` : '未命中' }}</template>
          </div>
        </div>
      </template>
    </template>
    <div class="top3-disclaimer">{{ disclaimer }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { matchApi } from '@/api'
import UpgradeHint from '@/components/UpgradeHint.vue'

const props = defineProps({
  matchId: { type: String, required: true },
})
const emit = defineEmits(['update'])

const NSPF_OPTIONS = [
  { value: 'any', label: '不限' },
  { value: 'H', label: '胜' },
  { value: 'D', label: '平' },
  { value: 'A', label: '负' },
  { value: 'auto', label: '看盘倾向' },
]
const SPF_OPTIONS = [
  { value: 'any', label: '不限' },
  { value: 'H', label: '让胜' },
  { value: 'D', label: '让平' },
  { value: 'A', label: '让负' },
  { value: 'auto', label: '看盘倾向' },
]
const NSPF_LABEL = { H: '胜', D: '平', A: '负' }
const SPF_LABEL = { H: '让胜', D: '让平', A: '让负' }
const SOURCE_LABEL = { user: '手选', heuristic: '看盘倾向' }

const nspf = ref('any')
const spf = ref('any')
const loading = ref(false)
const error = ref('')
const data = ref(null)
const recommendCount = ref(3)
const disclaimer = ref('历史相似盘口比分分布仅供分析对照，不构成投注建议')

const constraintText = computed(() => {
  const c = data.value?.constraint
  if (!c || (!c.nspf && !c.spf)) return ''
  const parts = []
  if (c.nspf) parts.push(`${NSPF_LABEL[c.nspf]}（${SOURCE_LABEL[c.source?.nspf] || ''}）`)
  if (c.spf) parts.push(`${SPF_LABEL[c.spf]}（${SOURCE_LABEL[c.source?.spf] || ''}）`)
  return `方向约束：${parts.join(' + ')}，概率为该方向内的条件概率`
})

function pct(v) {
  const n = Number(v)
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '-'
}

function relaxedLabel(key) {
  return key === 'spf' ? '让球' : '胜平负'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await matchApi.getJingcaiScoreTop3(props.matchId, { nspf: nspf.value, spf: spf.value })
    data.value = (res?.items || [])[0] || null
    const n = Number(res?.recommend_count)
    recommendCount.value = Number.isFinite(n) && n > 0 ? n : (data.value?.top3?.length || 3)
    if (res?.disclaimer) disclaimer.value = res.disclaimer
    emit('update', data.value?.available ? data.value.top3.map((t) => t.score) : [])
  } catch (e) {
    data.value = null
    error.value = e?.response?.data?.detail || e.message || '加载失败'
    emit('update', [])
  } finally {
    loading.value = false
  }
}

watch([nspf, spf], load)
onMounted(load)
</script>

<style scoped>
.top3-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-sm, 6px);
  background: rgba(var(--color-blue-rgb), 0.04);
}
.top3-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
}
.top3-title {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--color-blue);
}
.dir-group {
  display: flex;
  align-items: center;
  gap: 4px;
}
.dir-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-right: 2px;
}
.dir-chip {
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
}
.dir-chip.on {
  border-color: var(--color-blue);
  color: var(--color-blue);
  background: rgba(var(--color-blue-rgb), 0.12);
}
.top3-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.top3-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
}
.top3-tag.hit {
  border-color: var(--color-green, #66bb6a);
}
.top3-tag .rank {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.top3-tag .score {
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.top3-tag .prob {
  color: var(--color-gold, #ffd54f);
  font-variant-numeric: tabular-nums;
  font-size: 0.85rem;
}
.top3-tag .hits {
  font-size: 0.7rem;
  color: var(--text-muted);
}
.top3-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.75rem;
  color: var(--text-secondary);
}
.top3-meta .warn {
  color: var(--color-gold, #ffd54f);
}
.top3-hint {
  font-size: 0.8rem;
  color: var(--text-muted);
}
.top3-hint.error {
  color: #ef9a9a;
}
.top3-disclaimer {
  font-size: 0.7rem;
  color: var(--text-muted);
}
</style>

<template>
  <div class="model-training-tab">
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">分联赛权重与超参</h2>
        <div class="card-actions">
          <span class="card-sub" v-if="leagueWeightSummary">
            权重优化 {{ leagueWeightSummary.optimized }} · 超参优化 {{ leagueWeightSummary.hyperOptimized }} · 回退 {{ leagueWeightSummary.fallback }} · 共 {{ leagueWeightRows.length }} 联赛
          </span>
          <button
            class="chip-btn"
            :class="{ active: showLeagueHyper }"
            @click="showLeagueHyper = !showLeagueHyper"
          >{{ showLeagueHyper ? '收起超参' : '展开超参' }}</button>
          <div class="league-filter">
            <button
              class="chip-btn"
              :class="{ active: leagueFilter === 'all' }"
              @click="leagueFilter = 'all'"
            >全部</button>
            <button
              class="chip-btn"
              :class="{ active: leagueFilter === 'optimized' }"
              @click="leagueFilter = 'optimized'"
            >已优化</button>
            <button
              class="chip-btn"
              :class="{ active: leagueFilter === 'fallback' }"
              @click="leagueFilter = 'fallback'"
            >回退全局</button>
          </div>
        </div>
      </div>
      <div v-if="globalWeightRow" class="global-weight-strip">
        <span class="strip-label">全局权重</span>
        <span class="weight-pill" v-for="p in globalWeightProp" :key="p.key" :style="{ '--wcolor': p.color }">
          {{ p.label }} {{ p.pct }}
        </span>
        <template v-if="globalHyperProp">
          <span class="strip-label" style="margin-left:12px">全局超参</span>
          <span class="weight-pill" v-for="p in globalHyperProp" :key="'hp-' + p.key" style="--wcolor: var(--color-gold)">
            {{ p.label }} {{ p.value }}
          </span>
        </template>
      </div>
      <div class="table-wrapper" v-if="filteredLeagueWeightRows.length">
        <VirtualTable
          :key="showLeagueHyper ? 'hyper' : 'basic'"
          :items="filteredLeagueWeightRows"
          row-key="id"
          :height="480"
          :row-height="52"
          class="league-weight-table"
        >
          <template #head>
            <tr>
              <th>联赛</th>
              <th>来源</th>
              <th>训练样本</th>
              <th>验证场次</th>
              <th>验证准确率</th>
              <th>权重 E/P/xG/MC</th>
              <template v-if="showLeagueHyper">
                <th title="权重 EMA 系数 α，越小越粘旧权重">平滑α</th>
                <th>ELO K</th>
                <th>ELO主场</th>
                <th>泊松主场</th>
              </template>
              <th>权重构成</th>
            </tr>
          </template>
          <template #row="{ row }">
            <td>
              <div class="league-cell">
                <span class="league-id">{{ row.id }}</span>
                <span class="league-name" v-if="row.name">{{ row.name }}</span>
              </div>
            </td>
            <td>
              <span class="tag" :class="leagueSourceTag(row.source)">{{ leagueSourceText(row.source) }}</span>
            </td>
            <td>{{ row.trainMatches ?? '-' }}</td>
            <td>{{ row.validationMatches ?? '-' }}</td>
            <td>
              <div class="acc-cell" v-if="row.accuracy != null">
                <div class="acc-bar">
                  <div
                    class="acc-fill"
                    :style="{ width: Math.min(100, row.accuracyPct) + '%', background: accuracyColor(row.accuracyPct) }"
                  ></div>
                </div>
                <span class="acc-text" :style="{ color: accuracyColor(row.accuracyPct) }">{{ formatAccuracy(row.accuracy) }}</span>
              </div>
              <span v-else class="text-muted">—</span>
            </td>
            <td class="weight-compact">
              {{ weightPct(row.weights.elo) }}/{{ weightPct(row.weights.poisson) }}/{{ weightPct(row.weights.xg) }}/{{ weightPct(row.weights.monte_carlo) }}
            </td>
            <template v-if="showLeagueHyper">
              <td>{{ formatSmoothAlpha(row.smoothAlpha) }}</td>
              <td>{{ row.hyperparams?.elo_k ?? '-' }}</td>
              <td>{{ row.hyperparams?.elo_home_advantage ?? '-' }}</td>
              <td>{{ formatPoissonHa(row.hyperparams?.poisson_home_advantage) }}</td>
            </template>
            <td>
              <div class="mini-stack">
                <span
                  v-for="seg in row.segments"
                  :key="seg.key"
                  class="mini-seg"
                  :style="{ width: seg.pct + '%', background: seg.color }"
                  :title="seg.label + ' ' + seg.pct + '%'"
                ></span>
              </div>
            </td>
          </template>
        </VirtualTable>
      </div>
      <div v-else class="empty-hint">暂无分联赛权重数据。完成一次训练后，将在此展示各联赛验证准确率与选用权重。</div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2 class="card-title">模型版本历史</h2>
        <span class="card-sub">共 {{ modelVersions.length }} 个版本 · 默认展示最近 {{ VERSION_PAGE_SIZE }} 条</span>
      </div>
      <div class="timeline">
        <div
          class="timeline-item"
          v-for="v in visibleModelVersions"
          :key="v.version"
          :class="{ current: v.status === 'current' }"
        >
          <div class="timeline-dot" :class="{ active: v.status === 'current' }"></div>
          <div class="timeline-content">
            <div class="timeline-top">
              <div class="timeline-version">
                <span class="version-number">{{ v.version }}</span>
                <span class="tag" :class="v.status === 'current' ? 'tag-info' : 'tag-mid'">
                  {{ v.status === 'current' ? '当前版本' : '历史版本' }}
                </span>
              </div>
              <span class="timeline-date">{{ v.date }}</span>
            </div>
            <p class="timeline-desc">{{ v.description }}</p>
            <div class="timeline-meta">
              <span class="meta-label">准确率</span>
              <span class="meta-value text-green">{{ v.accuracy }}%</span>
            </div>
          </div>
        </div>
        <div v-if="!modelVersions.length" class="empty-hint">暂无模型版本记录</div>
      </div>
      <div class="version-more" v-if="modelVersions.length > VERSION_PAGE_SIZE">
        <button
          v-if="versionVisibleCount < modelVersions.length"
          class="more-btn"
          @click="loadMoreVersions"
        >
          查看更多（还有 {{ modelVersions.length - versionVisibleCount }} 条）
        </button>
        <button v-else class="more-btn" @click="collapseVersions">收起</button>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2 class="card-title">训练数据与完善建议</h2>
        <div class="card-actions">
          <span class="card-sub" v-if="latestRecord?.id">
            训练 #{{ latestRecord.id }} · {{ formatDateTime(latestRecord.finished_at || latestRecord.started_at) }}
          </span>
          <span class="card-sub" v-else-if="latestRecord?.status === 'preview'">实时分析（尚未训练）</span>
          <button class="refresh-btn" @click="fetchLatestInsights()" :disabled="insightsLoading">刷新</button>
        </div>
      </div>
      <div v-if="insightsError" class="state-banner error-banner" style="margin-bottom: 12px;">
        <span>⚠️ {{ insightsError }}</span>
        <button class="retry-btn" @click="fetchLatestInsights()">重试</button>
      </div>
      <div v-if="latestRecord" class="snapshot-grid">
        <div class="snapshot-item" v-for="item in snapshotCards" :key="item.label">
          <div class="snapshot-value">{{ item.value }}</div>
          <div class="snapshot-label">{{ item.label }}</div>
        </div>
      </div>
      <div
        v-if="latestRecord && insightLeagueRows.length"
        class="insight-league-block"
      >
        <div class="insight-league-head">
          <h3 class="insight-league-title">本次训练 · 分联赛表现</h3>
          <span class="card-sub">按验证准确率排序 · 前 {{ Math.min(8, insightLeagueRows.length) }} 项</span>
        </div>
        <div class="insight-league-list">
          <div class="insight-league-row" v-for="row in insightLeagueRows.slice(0, 8)" :key="'ins-' + row.id">
            <div class="insight-league-left">
              <span class="league-id">{{ row.id }}</span>
              <span class="tag" :class="leagueSourceTag(row.source)">{{ leagueSourceText(row.source) }}</span>
            </div>
            <div class="insight-league-mid">
              <div class="acc-bar tall">
                <div
                  class="acc-fill"
                  :style="{ width: (row.accuracyPct || 0) + '%', background: accuracyColor(row.accuracyPct || 0) }"
                ></div>
              </div>
            </div>
            <div class="insight-league-right">
              <span class="acc-text" :style="{ color: accuracyColor(row.accuracyPct || 0) }">
                {{ row.accuracy != null ? formatAccuracy(row.accuracy) : '—' }}
              </span>
              <span class="weight-compact">
                {{ weightPct(row.weights.elo) }}/{{ weightPct(row.weights.poisson) }}/{{ weightPct(row.weights.xg) }}/{{ weightPct(row.weights.monte_carlo) }}
              </span>
            </div>
          </div>
        </div>
        <p class="weight-legend">权重顺序：ELO / 泊松 / xG / 蒙特卡洛</p>
      </div>
      <div v-if="latestRecord" class="suggest-list">
        <div
          class="suggest-item"
          v-for="(s, idx) in latestRecord.suggestions || []"
          :key="`${latestRecord.id || 'preview'}-${idx}-${s.title}`"
        >
          <div class="suggest-top">
            <span class="tag" :class="priorityTag(s.priority)">{{ priorityText(s.priority) }}</span>
            <span class="tag tag-info">{{ s.category }}</span>
            <span class="suggest-title">{{ s.title }}</span>
          </div>
          <p class="suggest-detail">{{ s.detail }}</p>
          <p class="suggest-action">建议：{{ s.action }}</p>
        </div>
        <div v-if="!(latestRecord.suggestions || []).length" class="empty-hint">暂无数据建议，请先执行一次训练。</div>
      </div>
      <div v-else-if="insightsLoading" class="empty-hint">加载中…</div>
      <div v-else class="empty-hint">暂无训练数据，请先执行一次训练或点击刷新。</div>
    </div>

    <div class="card">
      <div class="card-header">
        <h2 class="card-title">训练记录</h2>
        <div class="card-actions">
          <span class="card-sub">共 {{ recordTotal }} 次</span>
          <button class="refresh-btn" @click="fetchRecords" :disabled="recordsLoading">刷新记录</button>
        </div>
      </div>
      <div class="table-wrapper" v-if="trainingRecords.length">
        <VirtualTable
          :items="trainingRecords"
          row-key="id"
          :height="420"
          :row-height="48"
          class="training-records-table"
        >
          <template #head>
            <tr>
              <th>ID</th>
              <th>开始时间</th>
              <th>版本</th>
              <th>样本场次</th>
              <th>数据区间</th>
              <th>验证准确率</th>
              <th>耗时</th>
              <th>状态</th>
              <th>建议</th>
              <th>操作</th>
            </tr>
          </template>
          <template #row="{ row }">
            <td>{{ row.id }}</td>
            <td>{{ formatDateTime(row.started_at) }}</td>
            <td>{{ row.model_version || '-' }}</td>
            <td>{{ row.total_matches }}</td>
            <td>{{ formatRange(row.data_start, row.data_end) }}</td>
            <td>{{ formatAccuracy(row.accuracy) }}</td>
            <td>{{ formatDuration(row.duration_ms) }}</td>
            <td>
              <span class="tag" :class="statusTag(row.status)">{{ statusText(row.status) }}</span>
            </td>
            <td>
              <span v-if="row.high_priority_count" class="tag tag-high">高优 {{ row.high_priority_count }}</span>
              <span v-else class="tag tag-mid">{{ row.suggestion_count || 0 }} 条</span>
            </td>
            <td>
              <button class="link-btn" @click="openRecord(row.id)">查看结果</button>
            </td>
          </template>
        </VirtualTable>
      </div>
      <div v-else class="empty-hint">暂无训练记录，点击「开始训练」后会在此保存结果与建议</div>
      <Pagination
        :page="recordPage"
        :page-size="RECORD_PAGE_SIZE"
        :total="recordTotal"
        @change="changeRecordPage"
      />
    </div>

    <BaseModal
      v-model="showRecordModal"
      :title="recordDetail ? `训练记录 #${recordDetail.id}` : '训练记录'"
      width="920px"
    >
      <template v-if="recordDetail">
        <div class="detail-grid">
          <div class="detail-item">
            <span class="detail-label">状态</span>
            <span class="detail-value">
              <span class="tag" :class="statusTag(recordDetail.status)">{{ statusText(recordDetail.status) }}</span>
            </span>
          </div>
          <div class="detail-item">
            <span class="detail-label">模型版本</span>
            <span class="detail-value">{{ recordDetail.model_version || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">训练样本</span>
            <span class="detail-value">{{ recordDetail.total_matches }} 场</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">验证准确率</span>
            <span class="detail-value text-green">{{ formatAccuracy(recordDetail.accuracy) }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">数据区间</span>
            <span class="detail-value">{{ formatRange(recordDetail.data_start, recordDetail.data_end) }}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">耗时</span>
            <span class="detail-value">{{ formatDuration(recordDetail.duration_ms) }}</span>
          </div>
        </div>
        <p class="modal-tip">{{ recordDetail.message }}</p>

        <h4 class="detail-section-title">训练结果</h4>
        <div class="result-grid">
          <div class="result-card" v-if="recordDetail.results?.elo">
            <div class="result-name">ELO 评级</div>
            <div class="result-row"><span>训练球队</span><b>{{ recordDetail.results.elo.trained_teams }}</b></div>
            <div class="result-row"><span>平均评级</span><b>{{ recordDetail.results.elo.avg_rating }}</b></div>
            <div class="result-row"><span>最高球队</span><b>{{ recordDetail.results.elo.top_team }}（{{ recordDetail.results.elo.top_rating }}）</b></div>
          </div>
          <div class="result-card" v-if="recordDetail.results?.poisson">
            <div class="result-name">泊松模型</div>
            <div class="result-row"><span>训练球队</span><b>{{ recordDetail.results.poisson.trained_teams }}</b></div>
            <div class="result-row"><span>覆盖联赛</span><b>{{ recordDetail.results.poisson.leagues }}</b></div>
            <div class="result-row"><span>均攻 / 均防</span><b>{{ recordDetail.results.poisson.avg_attack }} / {{ recordDetail.results.poisson.avg_defense }}</b></div>
          </div>
          <div class="result-card" v-if="recordDetail.results?.xg">
            <div class="result-name">xG 模型</div>
            <div class="result-row"><span>训练球队</span><b>{{ recordDetail.results.xg.trained_teams }}</b></div>
            <div class="result-row"><span>有统计场次</span><b>{{ recordDetail.results.xg.matches_with_stats ?? '-' }}</b></div>
            <div class="result-row"><span>场均 xG</span><b>{{ recordDetail.results.xg.avg_xg_for ?? '-' }}</b></div>
          </div>
          <div class="result-card" v-if="recordDetail.results?.ensemble">
            <div class="result-name">融合模型</div>
            <div class="result-row"><span>验证场次</span><b>{{ recordDetail.results.ensemble.validation_matches }}</b></div>
            <div class="result-row"><span>验证准确率</span><b>{{ formatAccuracy(recordDetail.results.ensemble.validation_accuracy) }}</b></div>
            <div class="result-row" v-if="recordDetail.results.ensemble.evaluation">
              <span>Brier / ECE</span>
              <b>
                {{ Number(recordDetail.results.ensemble.evaluation.global_brier || 0).toFixed(4) }}
                /
                {{ Number(recordDetail.results.ensemble.evaluation.global_ece || 0).toFixed(4) }}
              </b>
            </div>
            <div class="result-row" v-if="recordDetail.results.ensemble.evaluation">
              <span>主指标 / WF折</span>
              <b>
                {{ recordDetail.results.ensemble.evaluation.primary_metric || 'brier' }}
                /
                {{ recordDetail.results.ensemble.evaluation.global_folds || recordDetail.results.ensemble.evaluation.walk_forward_folds || '-' }}
              </b>
            </div>
            <div class="result-row" v-if="recordDetail.results.ensemble.max_monte_carlo_weight != null">
              <span>MC 上限</span>
              <b>{{ recordDetail.results.ensemble.max_monte_carlo_weight }}</b>
            </div>
            <div class="result-row" v-if="recordDetail.results.ensemble.leagues_optimized != null">
              <span>分联赛优化</span>
              <b>{{ recordDetail.results.ensemble.leagues_optimized }} / 回退 {{ recordDetail.results.ensemble.leagues_fallback ?? 0 }}</b>
            </div>
            <div class="result-row" v-if="recordDetail.results.ensemble.weights">
              <span>全局权重</span>
              <b>
                ELO {{ weightPct(recordDetail.results.ensemble.weights.elo) }} /
                泊松 {{ weightPct(recordDetail.results.ensemble.weights.poisson) }} /
                xG {{ weightPct(recordDetail.results.ensemble.weights.xg) }} /
                MC {{ weightPct(recordDetail.results.ensemble.weights.monte_carlo) }}
              </b>
            </div>
            <p v-if="recordDetail.results.ensemble.message" class="suggest-detail">{{ recordDetail.results.ensemble.message }}</p>
          </div>
          <div class="empty-hint" v-if="!recordDetail.results || !Object.keys(recordDetail.results).length">本次没有写出模型结果（通常是缺少完赛数据）。</div>
        </div>

        <h4 class="detail-section-title" v-if="detailLeagueRows.length">分联赛权重与准确率</h4>
        <div class="table-wrapper" v-if="detailLeagueRows.length">
          <table class="data-table league-weight-table compact">
            <thead>
              <tr>
                <th>联赛</th>
                <th>来源</th>
                <th>样本</th>
                <th>验证</th>
                <th>准确率</th>
                <th>α</th>
                <th>权重 E/P/X/M</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in detailLeagueRows" :key="'d-' + row.id">
                <td>{{ row.id }}{{ row.name ? ' · ' + row.name : '' }}</td>
                <td><span class="tag" :class="leagueSourceTag(row.source)">{{ leagueSourceText(row.source) }}</span></td>
                <td>{{ row.trainMatches ?? '-' }}</td>
                <td>{{ row.validationMatches ?? '-' }}</td>
                <td :style="{ color: row.accuracy != null ? accuracyColor(row.accuracyPct) : undefined }">
                  {{ row.accuracy != null ? formatAccuracy(row.accuracy) : '—' }}
                </td>
                <td>{{ formatSmoothAlpha(row.smoothAlpha) }}</td>
                <td class="weight-compact">
                  {{ weightPct(row.weights.elo) }}/{{ weightPct(row.weights.poisson) }}/{{ weightPct(row.weights.xg) }}/{{ weightPct(row.weights.monte_carlo) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <h4 class="detail-section-title" v-if="leagueAvgRows.length">各联赛场均进球</h4>
        <div class="league-avg-list" v-if="leagueAvgRows.length">
          <span class="league-avg-chip" v-for="row in leagueAvgRows" :key="row.id">{{ row.id }} {{ row.avg }}</span>
        </div>

        <h4 class="detail-section-title">完善建议</h4>
        <div class="suggest-list compact">
          <div class="suggest-item" v-for="(s, idx) in recordDetail.suggestions || []" :key="idx">
            <div class="suggest-top">
              <span class="tag" :class="priorityTag(s.priority)">{{ priorityText(s.priority) }}</span>
              <span class="tag tag-info">{{ s.category }}</span>
              <span class="suggest-title">{{ s.title }}</span>
            </div>
            <p class="suggest-detail">{{ s.detail }}</p>
            <p class="suggest-action">建议：{{ s.action }}</p>
          </div>
        </div>
      </template>
      <template #footer="{ close }">
        <button class="btn" @click="close">关闭</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import VirtualTable from '@/components/data/VirtualTable.vue'
import BaseModal from '@/components/common/BaseModal.vue'
import Pagination from '@/components/common/Pagination.vue'
import { modelApi } from '@/api'
import {
  formatDateTime,
  formatRange,
  formatAccuracy,
  formatSmoothAlpha,
  formatPoissonHa,
  formatDuration,
  weightPct,
  accuracyColor,
  statusTag,
  statusText,
  priorityTag,
  priorityText,
  leagueSourceTag,
  leagueSourceText,
} from './modelFormatters'
import {
  WEIGHT_SEGMENT_META,
  buildLeagueRows,
  parseWeightsJson,
  normalizeByLeagueMap,
} from './modelLeagueWeights'
import {
  modelVersions,
  modelStatus,
  currentVersion,
  fetchModelVersions,
  dataEpoch,
  onTrainingDone,
} from './modelStore'

const RECORD_PAGE_SIZE = 10
const VERSION_PAGE_SIZE = 5

const showLeagueHyper = ref(localStorage.getItem('modelShowLeagueHyper') === '1')
const leagueFilter = ref(localStorage.getItem('modelLeagueFilter') || 'all')
const versionVisibleCount = ref(VERSION_PAGE_SIZE)

const trainingRecords = ref([])
const recordTotal = ref(0)
const recordPage = ref(1)
const recordsLoading = ref(false)
const insightsLoading = ref(false)
const insightsError = ref(null)
const latestRecord = ref(null)
const recordDetail = ref(null)

const showRecordModal = computed({
  get: () => recordDetail.value != null,
  set: (v) => { if (!v) recordDetail.value = null },
})

watch(showLeagueHyper, (v) => {
  localStorage.setItem('modelShowLeagueHyper', v ? '1' : '0')
})

watch(leagueFilter, (v) => {
  localStorage.setItem('modelLeagueFilter', v)
})

const visibleModelVersions = computed(() =>
  modelVersions.value.slice(0, versionVisibleCount.value)
)

function loadMoreVersions() {
  versionVisibleCount.value = Math.min(
    versionVisibleCount.value + VERSION_PAGE_SIZE,
    modelVersions.value.length
  )
}

function collapseVersions() {
  versionVisibleCount.value = VERSION_PAGE_SIZE
}

const snapshotCards = computed(() => {
  const snap = latestRecord.value?.snapshot || {}
  const acc = snap.validation_accuracy
  const accText = acc != null ? formatAccuracy(acc) : '-'
  const prevAcc = snap.prev_validation_accuracy
  const accTrend = prevAcc != null && acc != null
    ? `（较上次 ${formatAccuracy(prevAcc)}）`
    : ''
  return [
    { label: '本次训练样本', value: snap.training_sample ?? snap.finished_matches ?? '-' },
    { label: '验证准确率', value: acc != null ? accText + accTrend : '-' },
    { label: 'Brier（越低越好）', value: snap.validation_brier != null ? Number(snap.validation_brier).toFixed(4) : '-' },
    { label: '校准 ECE', value: snap.validation_ece != null ? Number(snap.validation_ece).toFixed(4) : '-' },
    { label: '主指标 / 折数', value: `${snap.eval_primary_metric || 'brier'} / ${snap.walk_forward_folds ?? '-'}` },
    { label: '时间衰减半衰期', value: snap.time_decay?.enabled ? `${snap.time_decay.half_life_days} 天` : (snap.time_decay ? '关闭' : '-') },
    { label: 'MC 权重上限', value: snap.max_monte_carlo_weight != null ? snap.max_monte_carlo_weight : '-' },
    { label: '分联赛优化', value: snap.leagues_optimized != null ? `${snap.leagues_optimized} / 回退 ${snap.leagues_fallback ?? 0}` : '-' },
    { label: '完赛场次', value: snap.finished_matches ?? '-' },
    { label: '球员逐场统计', value: snap.matches_with_player_stats ?? snap.player_match_stats ?? '-' },
  ]
})

const leagueAvgRows = computed(() => {
  const avg = recordDetail.value?.results?.poisson?.league_avg || {}
  return Object.entries(avg).map(([id, avgVal]) => ({ id, avg: avgVal }))
})

function pickByLeagueSource() {
  const candidates = [
    latestRecord.value?.results?.ensemble?.by_league,
    latestRecord.value?.snapshot?.by_league_weights,
    modelStatus.value?.by_league,
    parseWeightsJson(currentVersion.value?.weights_json)?.by_league,
    modelStatus.value?.league_weights,
  ]
  for (const c of candidates) {
    const n = normalizeByLeagueMap(c)
    if (Object.keys(n).length) return n
  }
  return {}
}

const leagueWeightRows = computed(() => buildLeagueRows(pickByLeagueSource()))

const filteredLeagueWeightRows = computed(() => {
  const rows = leagueWeightRows.value
  if (leagueFilter.value === 'optimized') {
    return rows.filter(r => r.source === 'league' || r.source === 'global_better' || r.source === 'league_blended')
  }
  if (leagueFilter.value === 'fallback') {
    return rows.filter(r => r.source === 'global_fallback' || r.source === 'runtime')
  }
  return rows
})

const leagueWeightSummary = computed(() => {
  const rows = leagueWeightRows.value
  if (!rows.length) return null
  return {
    optimized: rows.filter(r => r.source === 'league' || r.source === 'league_blended').length,
    hyperOptimized: rows.filter(r => r.hyperSource === 'league' || r.hyperSource === 'league_blended').length,
    fallback: rows.filter(r => r.source === 'global_fallback' || r.source === 'runtime').length,
  }
})

const globalWeightProp = computed(() => {
  const w = modelStatus.value?.weights
    || latestRecord.value?.results?.ensemble?.weights
    || parseWeightsJson(currentVersion.value?.weights_json)
  if (!w) return null
  return WEIGHT_SEGMENT_META.map(m => ({
    key: m.key,
    label: m.label,
    color: m.color,
    pct: weightPct(w[m.key] ?? w.global?.[m.key]),
  }))
})

const globalHyperProp = computed(() => {
  const hp = modelStatus.value?.hyperparams
    || latestRecord.value?.results?.ensemble?.hyperparams
    || parseWeightsJson(currentVersion.value?.weights_json)?.hyperparams
  if (!hp) return null
  return [
    { key: 'elo_k', label: 'ELO K', value: hp.elo_k },
    { key: 'elo_ha', label: 'ELO主场', value: hp.elo_home_advantage },
    { key: 'p_ha', label: '泊松主场', value: formatPoissonHa(hp.poisson_home_advantage) },
  ]
})

const globalWeightRow = computed(() => globalWeightProp.value)

const insightLeagueRows = computed(() => {
  const snap = latestRecord.value?.snapshot || {}
  const map = normalizeByLeagueMap(
    latestRecord.value?.results?.ensemble?.by_league || snap.by_league_weights
  )
  const rows = buildLeagueRows(map)
  return [...rows].sort((a, b) => (b.accuracyPct ?? -1) - (a.accuracyPct ?? -1))
})

const detailLeagueRows = computed(() => {
  const map = normalizeByLeagueMap(
    recordDetail.value?.results?.ensemble?.by_league
    || recordDetail.value?.snapshot?.by_league_weights
  )
  return buildLeagueRows(map)
})

async function fetchLatestInsights(recordId = null) {
  insightsLoading.value = true
  insightsError.value = null
  try {
    if (recordId) {
      latestRecord.value = await modelApi.getTrainingRecord(recordId)
      return
    }
    latestRecord.value = await modelApi.getLatestTrainingInsights()
  } catch (e) {
    console.error('加载训练洞察失败:', e)
    try {
      const res = await modelApi.getTrainingRecords({ page: 1, page_size: 1 })
      const first = res?.records?.[0]
      if (first?.id) {
        latestRecord.value = await modelApi.getTrainingRecord(first.id)
        return
      }
    } catch (fallbackErr) {
      console.error('训练记录兜底加载失败:', fallbackErr)
    }
    insightsError.value = e?.message || '加载训练数据与完善建议失败'
  } finally {
    insightsLoading.value = false
  }
}

async function fetchRecords() {
  recordsLoading.value = true
  try {
    const res = await modelApi.getTrainingRecords({ page: recordPage.value, page_size: RECORD_PAGE_SIZE })
    trainingRecords.value = res?.records || []
    recordTotal.value = res?.total || 0
  } catch (e) {
    console.error('加载训练记录失败:', e)
  } finally {
    recordsLoading.value = false
  }
  if (recordPage.value === 1) {
    await fetchLatestInsights()
  }
}

async function changeRecordPage(page) {
  recordPage.value = page
  await fetchRecords()
}

async function openRecord(id) {
  try {
    recordDetail.value = await modelApi.getTrainingRecord(id)
  } catch (e) {
    console.error('加载训练详情失败:', e)
  }
}

async function refreshTrainingData() {
  versionVisibleCount.value = VERSION_PAGE_SIZE
  if (!modelVersions.value.length) {
    try {
      await fetchModelVersions()
    } catch (e) {
      console.error('加载模型版本失败:', e)
    }
  }
  await fetchRecords()
}

let unsubTrainingDone = null

onMounted(async () => {
  unsubTrainingDone = onTrainingDone(() => fetchRecords())
  if (!modelVersions.value.length) {
    try {
      await fetchModelVersions()
    } catch (e) {
      console.error('加载模型版本失败:', e)
    }
  }
  await fetchRecords()
})

watch(dataEpoch, () => {
  refreshTrainingData()
})

onBeforeUnmount(() => {
  unsubTrainingDone?.()
})
</script>

<style scoped>
.model-training-tab {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.card-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.card-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
}

.refresh-btn:hover:not(:disabled) {
  border-color: var(--color-blue);
  color: var(--color-blue);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.version-more {
  display: flex;
  justify-content: center;
  padding: 8px 0 4px;
}

.more-btn {
  padding: 8px 20px;
  border-radius: var(--radius-sm);
  border: 1px dashed var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
}

.more-btn:hover {
  border-color: var(--color-blue);
  color: var(--color-blue);
  background: rgba(var(--color-blue-rgb), 0.06);
}

.timeline-item {
  display: flex;
  gap: 16px;
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  position: relative;
  transition: var(--transition);
}

.timeline-item::before {
  content: '';
  position: absolute;
  left: 21px;
  top: 30px;
  bottom: -14px;
  width: 2px;
  background: var(--border-color);
}

.timeline-item:last-child::before {
  display: none;
}

.timeline-item:hover {
  background: var(--bg-hover);
}

.timeline-item.current {
  background: linear-gradient(135deg, rgba(var(--color-blue-rgb), 0.08), rgba(0, 102, 204, 0.04));
  border: 1px solid rgba(var(--color-blue-rgb), 0.3);
}

.timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--text-muted);
  border: 2px solid var(--bg-card);
  margin-top: 4px;
  flex-shrink: 0;
  position: relative;
  z-index: 1;
}

.timeline-dot.active {
  background: var(--color-blue);
  box-shadow: 0 0 10px var(--color-blue);
}

.timeline-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.timeline-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.timeline-version {
  display: flex;
  align-items: center;
  gap: 8px;
}

.version-number {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.timeline-item.current .version-number {
  color: var(--color-blue);
}

.timeline-date {
  font-size: 12px;
  color: var(--text-muted);
}

.timeline-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.timeline-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}

.meta-label {
  font-size: 12px;
  color: var(--text-muted);
}

.meta-value {
  font-size: 13px;
  font-weight: 700;
}

.state-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-radius: var(--radius-md);
  font-size: 14px;
}

.error-banner {
  background: rgba(var(--color-red-rgb), 0.08);
  border: 1px solid rgba(var(--color-red-rgb), 0.3);
  color: var(--color-red);
  justify-content: space-between;
}

.retry-btn {
  padding: 4px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-red);
  background: transparent;
  color: var(--color-red);
  font-size: 12px;
  cursor: pointer;
  transition: var(--transition);
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.snapshot-item {
  background: rgba(26, 38, 65, 0.6);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
}

.snapshot-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.snapshot-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.suggest-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.suggest-list.compact { margin-top: 4px; }

.suggest-item {
  padding: 12px 14px;
  background: rgba(26, 38, 65, 0.45);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.suggest-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.suggest-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.suggest-detail {
  margin: 8px 0 4px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.suggest-action {
  margin: 0;
  font-size: 12px;
  color: var(--color-blue);
  line-height: 1.5;
}

.empty-hint {
  text-align: center;
  color: var(--text-muted);
  padding: 16px 0;
  font-size: 13px;
}

.table-wrapper { overflow-x: auto; }

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.data-table th {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: 12px;
}

.data-table tbody tr:hover { background: var(--bg-hover); }

.link-btn {
  background: none;
  border: none;
  color: var(--color-blue);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 6px;
}

.link-btn:hover { text-decoration: underline; }

.modal-tip {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 16px 0;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px 24px;
  margin-bottom: 12px;
}

.detail-item { display: flex; flex-direction: column; gap: 4px; }
.detail-label { font-size: 11px; color: var(--text-muted); }
.detail-value { font-size: 14px; color: var(--text-primary); font-weight: 500; }

.detail-section-title {
  margin: 16px 0 10px;
  font-size: 14px;
  color: var(--text-primary);
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.result-card {
  padding: 12px;
  background: rgba(26, 38, 65, 0.55);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.result-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.result-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.result-row b { color: var(--text-primary); font-weight: 600; }

.league-avg-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.league-avg-chip {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(var(--color-blue-rgb), 0.1);
  color: var(--color-blue);
}

.league-filter {
  display: flex;
  gap: 6px;
}

.chip-btn {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 999px;
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: var(--transition);
}

.chip-btn:hover { color: var(--color-blue); border-color: var(--color-blue); }

.chip-btn.active {
  background: rgba(var(--color-blue-rgb), 0.12);
  border-color: var(--color-blue);
  color: var(--color-blue);
}

.global-weight-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding: 10px 12px;
  background: rgba(26, 38, 65, 0.45);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.strip-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-right: 4px;
}

.weight-pill {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  color: var(--wcolor);
  background: rgba(var(--color-blue-rgb), 0.08);
  border: 1px solid rgba(138, 155, 181, 0.35);
}

.league-weight-table .league-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.league-id { font-weight: 700; color: var(--text-primary); }
.league-name { font-size: 11px; color: var(--text-muted); }

.acc-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 110px;
}

.acc-bar {
  flex: 1;
  height: 6px;
  min-width: 48px;
  background: rgba(138, 155, 181, 0.15);
  border-radius: 3px;
  overflow: hidden;
}

.acc-bar.tall { height: 8px; }

.acc-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.25s ease;
}

.acc-text {
  font-size: 12px;
  font-weight: 700;
  min-width: 42px;
  text-align: right;
}

.text-muted { color: var(--text-muted); }

.mini-stack {
  display: flex;
  height: 8px;
  width: 88px;
  border-radius: 4px;
  overflow: hidden;
  background: rgba(138, 155, 181, 0.12);
}

.mini-seg { height: 100%; display: block; }

.weight-compact {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  white-space: nowrap;
}

.weight-legend {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-muted);
}

.insight-league-block {
  margin: 8px 0 18px;
  padding: 12px;
  background: rgba(26, 38, 65, 0.4);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.insight-league-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.insight-league-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.insight-league-list { display: flex; flex-direction: column; gap: 8px; }

.insight-league-row {
  display: grid;
  grid-template-columns: 140px 1fr auto;
  gap: 12px;
  align-items: center;
}

.insight-league-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.insight-league-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  min-width: 96px;
}

.league-weight-table.compact td,
.league-weight-table.compact th {
  padding: 8px 10px;
  font-size: 12px;
}

@media (max-width: 1100px) {
  .snapshot-grid { grid-template-columns: repeat(2, 1fr); }
  .insight-league-row { grid-template-columns: 1fr; }
}
</style>

/**
 * 模型管理页共享状态（模块单例）。
 *
 * 设计原则：只有「真正跨 tab 共享」的状态放这里——
 *  - 训练任务轮询（概览触发，训练记录/质量页都要感知完成时机）
 *  - 模型版本与状态（概览与训练记录两 tab 共用）
 *  - P0/UEL/扩展补齐管线（质量页触发，概览页训练态需互斥）
 *  - 过期预测统计与重算（概览展示 + 质量 CTA 跳转触发）
 * tab 私有状态（监控图表、缺口明细、别名草稿等）一律留在各 tab 组件内。
 */
import { ref, computed } from 'vue'
import { modelApi, predictApi, predictionApi, scheduleApi } from '@/api'
import { formatDate } from './modelFormatters'

// ---------- 模型版本 / 状态（overview + training 共用） ----------
export const modelVersions = ref([])
export const modelStatus = ref(null)
export const modelStatusDetail = ref([])
export const overviewLoading = ref(false)
export const overviewError = ref(null)

// ---------- 训练任务 ----------
export const isTraining = ref(false)
export const trainingProgress = ref(0)
export const trainingMessage = ref('')
let trainingPollInterval = null

// 训练完成后需要刷新的订阅者（tab 自行注册，如刷新记录列表）
const trainingDoneCallbacks = new Set()
export function onTrainingDone(fn) {
  trainingDoneCallbacks.add(fn)
  return () => trainingDoneCallbacks.delete(fn)
}

// ---------- P0 / 补齐管线（quality 触发，全局互斥展示） ----------
export const p0Pipeline = ref({ running: false, phase: '', message: '', error: false })
let p0PollInterval = null

export const P0_PHASE_LABELS = {
  queued: '排队中',
  snapshot: '记录数据质量',
  stats: '补采射门统计',
  environment: '补全气象环境',
  schedule: '启用气象定时任务',
  train: '全量训练',
  done: '完成',
}

export const p0PhaseLabel = computed(() => {
  const phase = p0Pipeline.value.phase
  return P0_PHASE_LABELS[phase] || (p0Pipeline.value.running ? 'P0 执行中...' : '')
})

// ---------- 过期预测统计（overview 展示 + quality CTA） ----------
export const staleStats = ref(null)
export const staleStatsLoading = ref(false)
export const recalcState = ref({ running: false, mode: '', message: '', error: false })

// ---------- 数据质量（quality tab 写入；parent 徽章读取） ----------
export const qualityData = ref(null)
export const qualityBadge = computed(() =>
  (qualityData.value?.training_lag?.is_stale || (qualityData.value?.quality_alerts || []).length) ? '!' : null
)

// ---------- 数据版本号：训练/P0 完成后自增，tab watch 后自行刷新 ----------
export const dataEpoch = ref(0)
function bumpEpoch() {
  dataEpoch.value++
}

// ==================== 拉取 ====================

export async function fetchModelVersions() {
  const res = await modelApi.getAll()
  const models = res?.models || res || []
  modelVersions.value = models.map(m => ({
    ...m,
    date: formatDate(m.created_at || m.date),
  }))
  return modelVersions.value
}

export async function fetchOverviewData() {
  overviewLoading.value = true
  overviewError.value = null
  try {
    const [, statusRes] = await Promise.all([
      fetchModelVersions(),
      predictApi.status(),
    ])
    modelStatus.value = statusRes
    modelStatusDetail.value = statusRes?.models_detail || []
  } catch (e) {
    overviewError.value = e?.message || '数据加载失败，请检查后端服务'
  } finally {
    overviewLoading.value = false
  }
  fetchStaleStats()
}

export async function fetchStaleStats() {
  staleStatsLoading.value = true
  try {
    staleStats.value = await predictionApi.staleStats({ limit: 200 })
  } catch (e) {
    console.error('加载未赛预测统计失败:', e)
  } finally {
    staleStatsLoading.value = false
  }
}

export async function recalculateUpcoming(onlyStale = true) {
  if (recalcState.value.running) return
  recalcState.value = {
    running: true,
    mode: onlyStale ? 'stale' : 'force',
    message: '',
    error: false,
  }
  try {
    const res = await predictionApi.recalculate({
      scope: 'upcoming',
      only_stale: onlyStale,
      include_unpredicted: true,
      limit: 80,
    })
    const failedN = (res?.failed || []).length
    recalcState.value.message =
      `已按 ${res?.model_version || '当前模型'} 更新 ${res?.calculated ?? 0} 场` +
      `（跳过 ${res?.skipped ?? 0}` +
      (failedN ? `，失败 ${failedN}` : '') +
      '）。赛事列表刷新后即可看到完整融合细节。'
    recalcState.value.error = failedN > 0 && !(res?.calculated > 0)
    await fetchStaleStats()
  } catch (e) {
    recalcState.value.message = e?.message || '批量重算失败'
    recalcState.value.error = true
  } finally {
    recalcState.value.running = false
    recalcState.value.mode = ''
  }
}

// ==================== 训练 ====================

async function handleTrainingFinished(status) {
  for (const fn of trainingDoneCallbacks) {
    try { await fn(status) } catch (e) { console.error(e) }
  }
  await fetchStaleStats()
  bumpEpoch()
  const needs = staleStats.value?.needs_recalc || 0
  recalcState.value.message = needs > 0
    ? `训练已完成。仍有 ${needs} 场未赛待同步，可点「一键补齐过期未赛」。`
    : '训练已完成，未赛预测已自动按新模型同步（或无需补齐）。'
  recalcState.value.error = false
}

export async function startTraining() {
  if (isTraining.value || p0Pipeline.value.running) return
  isTraining.value = true
  trainingProgress.value = 0
  trainingMessage.value = '正在启动训练...'
  try {
    await modelApi.train()
    trainingPollInterval = setInterval(async () => {
      try {
        const status = await modelApi.getTrainingStatus()
        isTraining.value = status.is_training
        trainingProgress.value = status.progress
        trainingMessage.value = status.message
        if (!status.is_training) {
          clearInterval(trainingPollInterval)
          trainingPollInterval = null
          await handleTrainingFinished(status)
        }
      } catch (e) {
        console.error('获取训练状态失败:', e)
      }
    }, 2000)
  } catch (e) {
    isTraining.value = false
    overviewError.value = e?.message || '训练启动失败'
  }
}

/** 进入页面时检查是否有正在进行的训练（刷新兜底） */
export async function attachRunningTraining() {
  try {
    const status = await modelApi.getTrainingStatus()
    if (status?.is_training) {
      isTraining.value = true
      trainingProgress.value = status.progress
      trainingMessage.value = status.message
      if (trainingPollInterval) clearInterval(trainingPollInterval)
      trainingPollInterval = setInterval(async () => {
        try {
          const s = await modelApi.getTrainingStatus()
          isTraining.value = s.is_training
          trainingProgress.value = s.progress
          trainingMessage.value = s.message
          if (!s.is_training) {
            clearInterval(trainingPollInterval)
            trainingPollInterval = null
            await handleTrainingFinished(s)
          }
        } catch (e) {
          console.error('获取训练状态失败:', e)
        }
      }, 2000)
    }
  } catch (e) {
    console.error('检查训练状态失败:', e)
  }
}

export function stopAllPolling() {
  if (trainingPollInterval) { clearInterval(trainingPollInterval); trainingPollInterval = null }
  stopP0Poll()
}

// ==================== P0 / 补齐管线 ====================

function applyP0Status(st) {
  if (!st) return
  p0Pipeline.value.running = !!st.running
  p0Pipeline.value.phase = st.phase || ''
  p0Pipeline.value.error = st.status === 'failed'
  p0Pipeline.value.message = st.message || P0_PHASE_LABELS[st.phase] || ''
}

async function fetchP0Status() {
  try {
    const st = await scheduleApi.getP0Status()
    applyP0Status(st)
    return st
  } catch {
    return null
  }
}

function stopP0Poll() {
  if (p0PollInterval) {
    clearInterval(p0PollInterval)
    p0PollInterval = null
  }
}

function startP0Poll() {
  if (p0PollInterval) return
  p0PollInterval = setInterval(async () => {
    const st = await fetchP0Status()
    if (st?.running) return
    stopP0Poll()
    if (st?.status && st.status !== 'idle') {
      bumpEpoch()
    }
  }, 4000)
}

export async function runP0Pipeline() {
  if (p0Pipeline.value.running) return
  p0Pipeline.value = { running: true, phase: 'queued', message: '正在启动 P0...', error: false }
  try {
    const res = await scheduleApi.runP0Pipeline()
    applyP0Status(res)
    startP0Poll()
  } catch (e) {
    p0Pipeline.value.running = false
    p0Pipeline.value.error = true
    p0Pipeline.value.message = e?.message || 'P0 启动失败'
  }
}

/** 质量页进入时探测运行中的 P0（刷新兜底） */
export async function attachRunningP0() {
  const st = await fetchP0Status()
  if (st?.running) startP0Poll()
  return st
}

export const currentVersion = computed(() =>
  modelVersions.value.find(v => v.status === 'current')
)

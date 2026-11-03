import { ref, computed } from 'vue'
import { predictionApi } from '@/api'
import {
  getScenarioEntry,
  normalizePrediction,
  tendencyFromProbs,
  confidenceFromMax,
} from '@/components/match/detail/matchDetailFormat'

/**
 * Scenario browse / lock + derived display prediction for MatchDetail.
 * @param {import('vue').Ref} matchRef
 * @param {{ predictError?: import('vue').Ref<string> }} [opts]
 */
export function useMatchDetailScenarios(matchRef, opts = {}) {
  const viewScenarioId = ref('')
  const lockingScenario = ref(false)
  const predictError = opts.predictError

  function syncViewScenarioFromPrediction(p) {
    const primary = p?.primaryScenario || ''
    const order = p?.scenarioOrder || []
    if (primary) viewScenarioId.value = primary
    else if (order.length) viewScenarioId.value = order[0]
    else viewScenarioId.value = ''
  }

  const scenarioList = computed(() => {
    const p = matchRef.value?.prediction
    if (!p?.scenarios || typeof p.scenarios !== 'object') return []
    const order = p.scenarioOrder?.length
      ? p.scenarioOrder
      : Object.keys(p.scenarios)
    return order
      .map((id) => {
        const s = getScenarioEntry(p.scenarios, id)
        if (!s) return null
        return {
          id: s.id || id,
          label: s.label || id,
          short: s.short || s.label || id,
          desc: s.desc || '',
          available: s.available !== false,
          isPrimary: !!(s.isPrimary || (s.id || id) === p.primaryScenario),
          homeWinProb: Number(s.homeWinProb ?? 0),
          drawProb: Number(s.drawProb ?? 0),
          awayWinProb: Number(s.awayWinProb ?? 0),
          mainScore: s.mainScore,
          altScores: Array.isArray(s.altScores) ? s.altScores : [],
          note: s.note || '',
          weights: s.weights || null,
        }
      })
      .filter(Boolean)
  })

  const primaryScenarioLabel = computed(() => {
    const id = matchRef.value?.prediction?.primaryScenario
    if (!id) return ''
    const hit = scenarioList.value.find((s) => s.id === id)
    return hit?.label || id
  })

  const viewScenarioLabel = computed(() => {
    const hit = scenarioList.value.find((s) => s.id === viewScenarioId.value)
    return hit?.label || viewScenarioId.value || ''
  })

  const scenarioReasonText = computed(() => matchRef.value?.prediction?.scenarioReason || '')

  const viewingNonPrimary = computed(() => {
    const primary = matchRef.value?.prediction?.primaryScenario
    return !!(primary && viewScenarioId.value && viewScenarioId.value !== primary)
  })

  const canLockViewedScenario = computed(() => {
    const hit = scenarioList.value.find((s) => s.id === viewScenarioId.value)
    if (!hit || hit.available === false) return false
    const p = matchRef.value?.prediction
    if (!p?.scenarios) return false
    if (hit.isPrimary && p.scenarioLocked) return false
    return true
  })

  function onSelectScenario(s) {
    if (!s || s.available === false) return
    viewScenarioId.value = s.id
  }

  async function lockViewedScenario(lock) {
    if (!matchRef.value?.id || lockingScenario.value) return
    const sid = viewScenarioId.value || matchRef.value.prediction?.primaryScenario
    if (!sid) return
    lockingScenario.value = true
    if (predictError) predictError.value = ''
    try {
      const data = await predictionApi.setScenario(matchRef.value.id, sid, lock)
      matchRef.value.prediction = normalizePrediction(data)
      syncViewScenarioFromPrediction(matchRef.value.prediction)
    } catch (err) {
      if (predictError) {
        predictError.value = err?.message || (lock ? '锁定场景失败' : '解除锁定失败')
      }
    } finally {
      lockingScenario.value = false
    }
  }

  const displayPrediction = computed(() => {
    const base = matchRef.value?.prediction || {}
    const sid = viewScenarioId.value
    const hit = scenarioList.value.find((s) => s.id === sid)
    if (!hit || !sid || sid === base.primaryScenario) {
      return base
    }
    const h = hit.homeWinProb
    const d = hit.drawProb
    const a = hit.awayWinProb
    const maxP = Math.max(h, d, a)
    return {
      ...base,
      homeWinProb: h,
      drawProb: d,
      awayWinProb: a,
      mainScore: hit.mainScore != null && hit.mainScore !== '' ? hit.mainScore : (hit.id === 'elo' ? '-' : base.mainScore),
      altScores: hit.altScores?.length ? hit.altScores : (hit.id === 'elo' ? [] : base.altScores),
      tendency: tendencyFromProbs(h, d, a),
      confidence: confidenceFromMax(maxP),
      analysis: hit.note
        ? `【对照·${hit.label}】${hit.note}`
        : `【对照·${hit.label}】胜 ${(h * 100).toFixed(1)}% / 平 ${(d * 100).toFixed(1)}% / 客 ${(a * 100).toFixed(1)}%。本场落库主结论为「${primaryScenarioLabel.value}」。`,
    }
  })

  const chartMatch = computed(() => {
    if (!matchRef.value) return null
    return {
      ...matchRef.value,
      prediction: displayPrediction.value,
    }
  })

  const predictionLockedFields = computed(() => {
    const p = matchRef.value?.prediction
    return Array.isArray(p?.lockedFields) ? p.lockedFields : []
  })

  function isPredLocked(field) {
    return predictionLockedFields.value.includes(field)
  }

  const weightUsedList = computed(() => {
    const hit = scenarioList.value.find((s) => s.id === viewScenarioId.value)
    const w = hit?.weights || matchRef.value?.prediction?.weightsUsed
    if (!w || typeof w !== 'object') return []
    const pairs = [
      { key: 'elo', label: 'ELO', color: '#ffd700' },
      { key: 'poisson', label: '泊松', color: '#00d4ff' },
      { key: 'xg', label: 'xG', color: '#ff9f43' },
      { key: 'monte_carlo', label: '蒙特卡洛', color: '#00ff88', alt: 'monteCarlo' },
    ]
    return pairs
      .map((m) => {
        const val = w[m.key] ?? (m.alt != null ? w[m.alt] : undefined)
        return {
          key: m.key,
          label: m.label,
          color: m.color,
          pct: `${Math.round(Number(val || 0) * 100)}%`,
        }
      })
      .filter((x) => Number.parseFloat(x.pct) > 0)
  })

  function weightSourceText(source) {
    if (!source) return '未记录'
    if (String(source).startsWith('league:')) return `联赛权重 · ${String(source).slice(7)}`
    if (String(source).startsWith('scenario:')) {
      const id = String(source).slice(9)
      const hit = scenarioList.value.find((s) => s.id === id)
      return `场景 · ${hit?.label || id}`
    }
    if (source === 'global') return '全局权重'
    if (source === 'explicit') return '显式权重'
    return source
  }

  const hasXgLambda = computed(() => {
    const p = matchRef.value?.prediction
    return p && p.xgCoverage != null && Number(p.xgCoverage) > 0 && p.xgHome != null
  })

  return {
    viewScenarioId,
    lockingScenario,
    scenarioList,
    primaryScenarioLabel,
    viewScenarioLabel,
    scenarioReasonText,
    viewingNonPrimary,
    canLockViewedScenario,
    displayPrediction,
    chartMatch,
    predictionLockedFields,
    weightUsedList,
    hasXgLambda,
    syncViewScenarioFromPrediction,
    onSelectScenario,
    lockViewedScenario,
    isPredLocked,
    weightSourceText,
  }
}

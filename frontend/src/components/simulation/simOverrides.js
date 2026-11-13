/**
 * Simulation 页面共享纯函数：参数构建 + 格式化工具。
 * 供父组件 Simulation.vue 与各子组件统一导入，避免逻辑重复。
 */

// 空值转 null（v-model.number 空串归一）
export function numOrNull(v) {
  return v == null || v === '' ? null : Number(v)
}

// 解析比分手动 SP 文本："1:0=4.5,2:1=8.0,胜其它=15" -> { "1:0": 4.5, "2:1": 8.0, "胜其它": 15 }
export function parseBfManual(text) {
  const out = {}
  if (!text || typeof text !== 'string') return out
  for (const seg of text.split(',')) {
    const idx = seg.indexOf('=')
    if (idx <= 0) continue
    const k = seg.slice(0, idx).trim()
    const v = Number(seg.slice(idx + 1).trim())
    if (!k || !Number.isFinite(v) || v <= 0) continue
    out[k] = v
  }
  return out
}

// 将高级选项 adv 组装为后端 SimulationOverrides 对象（null 表示无覆盖）
export function buildOverrides(adv) {
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
  const manualSp = {}
  const spfManual = {
    win: numOrNull(adv.manualSpfWin),
    draw: numOrNull(adv.manualSpfDraw),
    lose: numOrNull(adv.manualSpfLose),
  }
  const nspfManual = {
    win: numOrNull(adv.manualNspfWin),
    draw: numOrNull(adv.manualNspfDraw),
    lose: numOrNull(adv.manualNspfLose),
  }
  for (const [k, v] of Object.entries(spfManual)) {
    if (v != null) {
      if (!manualSp.spf) manualSp.spf = {}
      manualSp.spf[k] = v
    }
  }
  for (const [k, v] of Object.entries(nspfManual)) {
    if (v != null) {
      if (!manualSp.nspf) manualSp.nspf = {}
      manualSp.nspf[k] = v
    }
  }
  const tgManual = {
    '0': numOrNull(adv.manualTg0),
    '1': numOrNull(adv.manualTg1),
    '2': numOrNull(adv.manualTg2),
    '3': numOrNull(adv.manualTg3),
    '4': numOrNull(adv.manualTg4),
    '5': numOrNull(adv.manualTg5),
    '6': numOrNull(adv.manualTg6),
    '7+': numOrNull(adv.manualTg7Plus),
  }
  for (const [k, v] of Object.entries(tgManual)) {
    if (v != null) {
      if (!manualSp.tg) manualSp.tg = {}
      manualSp.tg[k] = v
    }
  }
  const bfManual = parseBfManual(adv.manualBfText)
  if (Object.keys(bfManual).length) manualSp.bf = bfManual
  if (Object.keys(manualSp).length) o.manual_sp = manualSp
  return Object.keys(o).length ? o : null
}

// ---- 格式化工具 ----

export function pct(v) {
  return v == null ? '—' : (v * 100).toFixed(1) + '%'
}

export function fmt(v) {
  return v == null ? '—' : Number(v).toFixed(2)
}

export function signed(v) {
  return v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(2)
}

export function signedPct(v) {
  return v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + 'pp'
}

export function deltaClass(v) {
  if (v == null || Math.abs(v) < 1e-9) return 'flat'
  return v > 0 ? 'pos' : 'neg'
}

export function fmtLambda(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : '—'
}

export function outcomeLabel(v) {
  return ({ home: '主胜', draw: '平局', away: '客胜' })[v] || v || '—'
}

export function bfKeyOf(score) {
  return (score || '').replace('-', ':')
}

export const STAGE_LABELS = {
  group: '小组赛',
  round_of_16: '十六强',
  quarter_final: '四分之一决赛',
  semi_final: '半决赛',
  third_place: '三四名决赛',
  final: '决赛',
  league: '联赛',
}

export const CATEGORY_LABELS = {
  international: '国际赛事',
  domestic: '国内联赛',
}

export function getStageLabel(stage) {
  return STAGE_LABELS[stage] || stage
}

export function stageTagClass(stage) {
  const classes = {
    group: 'tag-group',
    round_of_16: 'tag-round16',
    quarter_final: 'tag-quarter',
    semi_final: 'tag-semi',
    third_place: 'tag-third',
    final: 'tag-final',
    league: 'tag-league',
  }
  return classes[stage] || ''
}

export function getCategoryLabel(cat) {
  return CATEGORY_LABELS[cat] || cat
}

export function confidenceTagClass(level) {
  return (
    {
      high: 'tag tag-low',
      mid: 'tag tag-mid',
      low: 'tag tag-high',
    }[level] || 'tag tag-info'
  )
}

export function riskTagClass(level) {
  return (
    {
      low: 'tag tag-low',
      mid: 'tag tag-mid',
      high: 'tag tag-high',
    }[level] || 'tag tag-info'
  )
}

export function levelText(level) {
  return { high: '高', mid: '中', low: '低' }[level] || level
}

export function weightSourceTagClass(source) {
  if (!source) return 'tag-mid'
  if (String(source).startsWith('league:')) return 'tag-low'
  if (String(source).startsWith('scenario:')) return 'tag-info'
  if (source === 'global') return 'tag-info'
  return 'tag-mid'
}

export function weightSourceShort(source) {
  if (!source) return ''
  if (String(source).startsWith('league:')) return String(source).slice(7)
  if (String(source).startsWith('scenario:')) {
    const id = String(source).slice(9)
    return scenarioShort(id)
  }
  if (source === 'global') return '全局权重'
  return source
}

export const SCENARIO_SHORT = {
  ensemble: '整合',
  elo: 'ELO',
  poisson: '泊松',
  xg: 'xG',
  monte_carlo: 'MC',
}

export function scenarioShort(id) {
  if (!id) return ''
  return SCENARIO_SHORT[id] || id
}

export function scenarioTagClass(id) {
  if (id === 'ensemble') return 'tag-low'
  if (id === 'poisson' || id === 'elo') return 'tag-info'
  if (id === 'xg') return 'tag-mid'
  return 'tag-mid'
}

export function resultBadgeClass(result) {
  return {
    'result-home': result === 'H',
    'result-away': result === 'A',
    'result-draw': result === 'D',
  }
}

export function resultText(result) {
  return { H: '主队胜', A: '客队胜', D: '平局' }[result] || '-'
}

export function pct(val) {
  return (Number(val || 0) * 100).toFixed(1) + '%'
}

/** 竞彩赔率展示（分析用，非投注建议） */
export function fmtOdds(v) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : String(v)
}

export function formatHandicap(hc) {
  if (hc == null || hc === '') return null
  const n = Number(hc)
  if (!Number.isFinite(n)) return String(hc)
  if (n === 0) return '0'
  return n > 0 ? `+${n}` : String(n)
}

export function pickOddsFields(raw = {}) {
  let oddsBf = raw.odds_bf ?? raw.oddsBf ?? null
  if (typeof oddsBf === 'string') {
    try {
      oddsBf = JSON.parse(oddsBf)
    } catch {
      oddsBf = null
    }
  }
  return {
    handicap: raw.handicap ?? null,
    fixtureId: raw.fixture_id ?? raw.fixtureId ?? null,
    isSingle: !!(raw.is_single ?? raw.isSingle),
    oddsNspfWin: raw.odds_nspf_win ?? raw.oddsNspfWin ?? null,
    oddsNspfDraw: raw.odds_nspf_draw ?? raw.oddsNspfDraw ?? null,
    oddsNspfLose: raw.odds_nspf_lose ?? raw.oddsNspfLose ?? null,
    oddsSpfWin: raw.odds_spf_win ?? raw.oddsSpfWin ?? null,
    oddsSpfDraw: raw.odds_spf_draw ?? raw.oddsSpfDraw ?? null,
    oddsSpfLose: raw.odds_spf_lose ?? raw.oddsSpfLose ?? null,
    oddsBf: oddsBf && typeof oddsBf === 'object' ? oddsBf : null,
    oddsBfLocked: !!(raw.odds_bf_locked ?? raw.oddsBfLocked),
  }
}

export function hasMatchOdds(m) {
  if (!m) return false
  return [
    m.oddsNspfWin, m.oddsNspfDraw, m.oddsNspfLose,
    m.oddsSpfWin, m.oddsSpfDraw, m.oddsSpfLose,
    m.handicap,
  ].some((v) => v != null && v !== '')
}

export function compactOddsLine(m) {
  if (!hasMatchOdds(m)) return ''
  const parts = []
  if (m.oddsNspfWin != null || m.oddsNspfDraw != null || m.oddsNspfLose != null) {
    parts.push(`胜平负 ${fmtOdds(m.oddsNspfWin)}/${fmtOdds(m.oddsNspfDraw)}/${fmtOdds(m.oddsNspfLose)}`)
  }
  const hc = formatHandicap(m.handicap)
  if (m.oddsSpfWin != null || m.oddsSpfDraw != null || m.oddsSpfLose != null || hc != null) {
    const hcPart = hc != null ? `让球${hc}` : '让球'
    parts.push(`${hcPart} ${fmtOdds(m.oddsSpfWin)}/${fmtOdds(m.oddsSpfDraw)}/${fmtOdds(m.oddsSpfLose)}`)
  }
  return parts.join(' · ')
}

function _posSp(v) {
  const n = Number(v)
  return Number.isFinite(n) && n > 0 ? n : null
}

/** SP → 隐含概率 / 抽水（与后端 odds_analysis 同公式） */
export function impliedFromSp(win, draw, lose) {
  const w = _posSp(win)
  const d = _posSp(draw)
  const l = _posSp(lose)
  if (w == null || d == null || l == null) return null
  const rw = 1 / w
  const rd = 1 / d
  const rl = 1 / l
  const s = rw + rd + rl
  if (s <= 0) return null
  const home = rw / s
  const drawP = rd / s
  const away = rl / s
  let tendency = 'H'
  if (drawP >= home && drawP >= away) tendency = 'D'
  else if (away >= home && away >= drawP) tendency = 'A'
  const labels = { H: '主胜', D: '平局', A: '客胜' }
  return {
    home,
    draw: drawP,
    away,
    overround: s - 1,
    overroundPct: (s - 1) * 100,
    tendency,
    tendencyLabel: labels[tendency],
  }
}

export function compareImpliedToModel(implied, model) {
  if (!implied || !model) return null
  const mh = Number(model.home)
  const md = Number(model.draw)
  const ma = Number(model.away)
  if (![mh, md, ma].every((x) => Number.isFinite(x))) return null
  const s = mh + md + ma
  if (s <= 0) return null
  const home = mh / s
  const draw = md / s
  const away = ma / s
  const deltas = {
    home: implied.home - home,
    draw: implied.draw - draw,
    away: implied.away - away,
  }
  const abs = {
    home: Math.abs(deltas.home),
    draw: Math.abs(deltas.draw),
    away: Math.abs(deltas.away),
  }
  let maxSide = 'home'
  if (abs.draw >= abs.home && abs.draw >= abs.away) maxSide = 'draw'
  else if (abs.away >= abs.home && abs.away >= abs.draw) maxSide = 'away'
  const maxAbs = abs[maxSide]
  let level = 'low'
  if (maxAbs >= 0.12) level = 'high'
  else if (maxAbs >= 0.06) level = 'mid'
  let modelTendency = 'H'
  if (draw >= home && draw >= away) modelTendency = 'D'
  else if (away >= home && away >= draw) modelTendency = 'A'
  return {
    deltaHome: deltas.home,
    deltaDraw: deltas.draw,
    deltaAway: deltas.away,
    maxAbsDeltaPct: maxAbs * 100,
    maxSide,
    maxSideLabel: { home: '主胜', draw: '平局', away: '客胜' }[maxSide],
    level,
    agreeTendency: implied.tendency === modelTendency,
  }
}

export function buildOddsAnalysisClient(match, prediction) {
  if (!match) return null
  const nspf = impliedFromSp(match.oddsNspfWin, match.oddsNspfDraw, match.oddsNspfLose)
  const spf = impliedFromSp(match.oddsSpfWin, match.oddsSpfDraw, match.oddsSpfLose)
  if (!nspf && !spf) return null
  const primary = nspf || spf
  const model = prediction
    ? {
        home: prediction.homeWinProb,
        draw: prediction.drawProb,
        away: prediction.awayWinProb,
      }
    : null
  const vs = compareImpliedToModel(primary, model)
  return {
    nspf,
    spf,
    primary: nspf ? 'nspf' : 'spf',
    marketTendency: primary.tendency,
    marketTendencyLabel: primary.tendencyLabel,
    overroundPct: primary.overroundPct,
    impliedHome: primary.home,
    impliedDraw: primary.draw,
    impliedAway: primary.away,
    vsModel: vs,
  }
}

export function adaptOddsAnalysis(raw) {
  if (!raw || typeof raw !== 'object') return null
  const nspf = raw.nspf || null
  const spf = raw.spf || null
  const vsRaw = raw.vs_model || raw.vsModel || null
  const tendency = raw.market_tendency ?? raw.marketTendency ?? nspf?.tendency ?? spf?.tendency ?? null
  const label = raw.market_tendency_label ?? raw.marketTendencyLabel
    ?? nspf?.tendency_label ?? spf?.tendency_label ?? null
  if (!tendency && !nspf && !spf && raw.has_odds == null && raw.implied_home == null && raw.impliedHome == null) {
    return null
  }
  return {
    hasOdds: true,
    hasNspf: raw.has_nspf ?? raw.hasNspf ?? !!nspf,
    marketTendency: tendency,
    marketTendencyLabel: label,
    overroundPct: raw.overround_pct ?? raw.overroundPct ?? nspf?.overround_pct ?? spf?.overround_pct ?? null,
    impliedHome: raw.implied_home ?? raw.impliedHome ?? nspf?.home ?? null,
    impliedDraw: raw.implied_draw ?? raw.impliedDraw ?? nspf?.draw ?? null,
    impliedAway: raw.implied_away ?? raw.impliedAway ?? nspf?.away ?? null,
    deltaLevel: raw.delta_level ?? raw.deltaLevel ?? vsRaw?.level ?? null,
    maxAbsDeltaPct: raw.max_abs_delta_pct ?? raw.maxAbsDeltaPct ?? vsRaw?.max_abs_delta_pct ?? vsRaw?.maxAbsDeltaPct ?? null,
    agreeTendency: raw.agree_tendency ?? raw.agreeTendency ?? vsRaw?.agree_tendency ?? vsRaw?.agreeTendency ?? null,
    nspf,
    spf,
    heuristics: adaptHeuristics(raw.heuristics || raw.heuristic),
    heuristicLean: raw.heuristic_lean ?? raw.heuristicLean ?? null,
    heuristicLeanLabel: raw.heuristic_lean_label ?? raw.heuristicLeanLabel ?? null,
    vsModel: vsRaw
      ? {
          deltaHome: vsRaw.delta_home ?? vsRaw.deltaHome,
          deltaDraw: vsRaw.delta_draw ?? vsRaw.deltaDraw,
          deltaAway: vsRaw.delta_away ?? vsRaw.deltaAway,
          maxAbsDeltaPct: vsRaw.max_abs_delta_pct ?? vsRaw.maxAbsDeltaPct,
          maxSide: vsRaw.max_side ?? vsRaw.maxSide,
          maxSideLabel: vsRaw.max_side_label ?? vsRaw.maxSideLabel,
          level: vsRaw.level,
          agreeTendency: vsRaw.agree_tendency ?? vsRaw.agreeTendency,
        }
      : null,
  }
}

export function adaptHeuristics(raw) {
  if (!raw || typeof raw !== 'object') return null
  const nspf = raw.nspf || null
  const spf = raw.spf || null
  const goals = raw.total_goals || raw.totalGoals || null
  const htft = raw.htft || null
  return {
    disclaimer: raw.disclaimer || '看盘启发式仅供分析对照，不构成投注建议',
    source: raw.source || null,
    nspf,
    spf,
    mainScore: raw.main_score ?? raw.mainScore ?? nspf?.main_score ?? nspf?.mainScore ?? null,
    altScores: raw.alt_scores ?? raw.altScores ?? nspf?.alt_scores ?? nspf?.altScores ?? [],
    totalGoals: goals
      ? {
          fromScore: goals.from_score ?? goals.fromScore,
          total: goals.total,
          band: goals.band,
          note: goals.note,
        }
      : null,
    htft: htft
      ? {
          fromScore: htft.from_score ?? htft.fromScore,
          combos: htft.combos || [],
          note: htft.note,
        }
      : null,
    leanLabel: nspf?.lean_label ?? nspf?.leanLabel ?? null,
    handicapLeanLabel: spf?.lean_label ?? spf?.leanLabel ?? null,
    rulesHit: [
      ...((nspf?.rules_hit || nspf?.rulesHit || [])),
      ...((spf?.rules_hit || spf?.rulesHit || [])),
    ],
  }
}

/** 是否具备完整胜平负三路 SP（仅盘口展示，不影响预测计算） */
export function hasNspfOdds(match) {
  if (!match) return false
  const w = match.oddsNspfWin ?? match.odds_nspf_win
  const d = match.oddsNspfDraw ?? match.odds_nspf_draw
  const l = match.oddsNspfLose ?? match.odds_nspf_lose
  const ok = (v) => v != null && v !== '' && Number(v) > 0
  return ok(w) && ok(d) && ok(l)
}

export function marketTendencyTagClass(tendency) {
  if (tendency === 'H') return 'tag-low'
  if (tendency === 'A') return 'tag-high'
  if (tendency === 'D') return 'tag-mid'
  return 'tag-info'
}

export function deltaLevelTagClass(level) {
  if (level === 'high') return 'tag-high'
  if (level === 'mid') return 'tag-mid'
  if (level === 'low') return 'tag-low'
  return 'tag-info'
}

export function pct1(v) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '-'
}

export function pctPoints(v) {
  if (v == null || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  const signed = n > 0 ? `+${n.toFixed(1)}` : n.toFixed(1)
  return `${signed}pt`
}

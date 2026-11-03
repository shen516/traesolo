/**
 * ECharts 图表统一色板。
 *
 * ECharts 渲染在 canvas 中，无法解析 CSS 变量（var(--...)），
 * 因此图表用色必须使用此处的字面量色值。
 * 色值与 assets/styles/main.css 中的设计 token 保持一致，
 * 若调整 main.css 的品牌色，请同步修改此处。
 */
export const CHART_COLORS = {
  gold: '#ffd700',       // --color-gold
  green: '#3dff9a',      // --color-green
  blue: '#4de0ff',       // --color-blue
  blueDeep: '#0099cc',   // --color-blue-deep
  red: '#ff6b78',        // --color-red
  orange: '#ffb14a',     // --color-orange
  textPrimary: '#f4f8fd',   // --text-primary
  textSecondary: '#c5d2e6', // --text-secondary
  textMuted: '#9aadc8',     // --text-muted
  bgPrimary: '#0d1b30',     // --bg-primary
  bgSecondary: '#132544',   // --bg-secondary
  bgCard: '#1a3358',        // --bg-card
  border: '#2d4f7a',        // --border-color
}

/** 常用语义色快捷引用 */
export const MODEL_COLORS = {
  poisson: CHART_COLORS.blue,
  elo: CHART_COLORS.gold,
  xg: CHART_COLORS.orange,
  monte_carlo: CHART_COLORS.green,
}

/** 通用 tooltip / 坐标轴样式片段 */
export const CHART_TOOLTIP = {
  backgroundColor: 'rgba(19, 37, 68, 0.95)',
  borderColor: CHART_COLORS.border,
  textStyle: { color: CHART_COLORS.textPrimary },
}

export const axisLabelStyle = (fontSize = 11) => ({
  color: CHART_COLORS.textMuted,
  fontSize,
})

export default CHART_COLORS

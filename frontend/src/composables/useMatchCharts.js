import { nextTick, onBeforeUnmount, onMounted } from 'vue'
import echarts from '@/utils/echarts'
import { CHART_COLORS, CHART_TOOLTIP, axisLabelStyle } from '@/utils/chartTheme'

/**
 * Match detail prediction charts (pie / lambda / heatmap).
 * @param {{
 *   pieChartRef: import('vue').Ref<HTMLElement|null>,
 *   lambdaChartRef: import('vue').Ref<HTMLElement|null>,
 *   heatmapChartRef: import('vue').Ref<HTMLElement|null>,
 *   getChartContext: () => ({
 *     prediction: object,
 *     homeShort: string,
 *     awayShort: string,
 *     hasXgLambda: boolean,
 *   } | null),
 *   autoBindResize?: boolean,
 * }} opts
 */
export function useMatchCharts(opts) {
  const {
    pieChartRef,
    lambdaChartRef,
    heatmapChartRef,
    getChartContext,
    autoBindResize = true,
  } = opts

  let pieChart = null
  let lambdaChart = null
  let heatmapChart = null

  function initPieChart() {
    const ctx = getChartContext()
    if (!pieChartRef.value || !ctx?.prediction) return
    if (pieChart) pieChart.dispose()
    pieChart = echarts.init(pieChartRef.value, 'dark')
    const p = ctx.prediction
    pieChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: '{b}: {d}%',
        ...CHART_TOOLTIP,
      },
      legend: {
        bottom: 5,
        icon: 'circle',
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { color: CHART_COLORS.textMuted, fontSize: 12 },
      },
      series: [{
        name: '胜平负概率',
        type: 'pie',
        radius: ['42%', '70%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderColor: CHART_COLORS.bgPrimary,
          borderWidth: 2,
        },
        label: {
          show: true,
          color: CHART_COLORS.textPrimary,
          formatter: '{b}\n{d}%',
          fontSize: 12,
        },
        labelLine: {
          lineStyle: { color: CHART_COLORS.border },
        },
        data: [
          {
            value: (p.homeWinProb * 100).toFixed(1),
            name: '主队胜',
            itemStyle: { color: CHART_COLORS.blue },
          },
          {
            value: (p.drawProb * 100).toFixed(1),
            name: '平局',
            itemStyle: { color: CHART_COLORS.orange },
          },
          {
            value: (p.awayWinProb * 100).toFixed(1),
            name: '客队胜',
            itemStyle: { color: CHART_COLORS.red },
          },
        ],
      }],
    })
  }

  function initLambdaChart() {
    const ctx = getChartContext()
    if (!lambdaChartRef.value || !ctx?.prediction) return
    if (lambdaChart) lambdaChart.dispose()
    lambdaChart = echarts.init(lambdaChartRef.value, 'dark')
    const p = ctx.prediction
    const homeName = ctx.homeShort || '主'
    const awayName = ctx.awayShort || '客'
    const showXg = !!ctx.hasXgLambda
    const vals = [Number(p.lambdaHome || 0), Number(p.lambdaAway || 0)]
    if (showXg) vals.push(Number(p.xgHome || 0), Number(p.xgAway || 0))
    const maxVal = Math.max(...vals, 0.5) * 1.35
    const series = [{
      name: '泊松 λ',
      type: 'bar',
      data: [
        {
          value: Number(p.lambdaHome || 0),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#0055aa' },
              { offset: 1, color: CHART_COLORS.blue },
            ]),
            borderRadius: [0, 6, 6, 0],
          },
        },
        {
          value: Number(p.lambdaAway || 0),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: '#aa1f2c' },
              { offset: 1, color: CHART_COLORS.red },
            ]),
            borderRadius: [0, 6, 6, 0],
          },
        },
      ],
      label: {
        show: true,
        position: 'right',
        color: CHART_COLORS.gold,
        fontSize: 13,
        fontWeight: 700,
        formatter: 'λ={c}',
      },
      barMaxWidth: 28,
    }]
    if (showXg) {
      series.push({
        name: 'xG λ',
        type: 'bar',
        data: [
          {
            value: Number(p.xgHome || 0),
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: '#c45c00' },
                { offset: 1, color: CHART_COLORS.orange },
              ]),
              borderRadius: [0, 6, 6, 0],
            },
          },
          {
            value: Number(p.xgAway || 0),
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: '#7a5b00' },
                { offset: 1, color: CHART_COLORS.gold },
              ]),
              borderRadius: [0, 6, 6, 0],
            },
          },
        ],
        label: {
          show: true,
          position: 'right',
          color: CHART_COLORS.orange,
          fontSize: 13,
          fontWeight: 700,
          formatter: 'xG={c}',
        },
        barMaxWidth: 28,
      })
    }
    lambdaChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        ...CHART_TOOLTIP,
      },
      legend: {
        show: showXg,
        top: 0,
        right: 8,
        textStyle: { color: CHART_COLORS.textMuted, fontSize: 11 },
      },
      grid: { left: 90, right: 80, top: showXg ? 36 : 20, bottom: 30 },
      xAxis: {
        type: 'value',
        max: maxVal,
        axisLabel: axisLabelStyle(11),
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
        splitLine: { lineStyle: { color: 'rgba(45, 79, 122, 0.4)' } },
      },
      yAxis: {
        type: 'category',
        data: [`${homeName} (主)`, `${awayName} (客)`],
        axisLabel: { color: CHART_COLORS.textPrimary, fontSize: 13, fontWeight: 600 },
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
        axisTick: { show: false },
      },
      series,
    })
  }

  function initHeatmapChart() {
    const ctx = getChartContext()
    if (!heatmapChartRef.value || !ctx?.prediction) return
    if (heatmapChart) heatmapChart.dispose()
    heatmapChart = echarts.init(heatmapChartRef.value, 'dark')
    const p = ctx.prediction
    const matrix = Array.isArray(p.scoreMatrix) ? p.scoreMatrix : []
    // matrix[i][j] : i = 主队进球, j = 客队进球
    // echarts heatmap data: [x, y, value]
    // x = 客队进球 (列), y = 主队进球 (行)
    const data = []
    let maxVal = 0.01
    for (let i = 0; i < 5; i++) {
      const row = Array.isArray(matrix[i]) ? matrix[i] : []
      for (let j = 0; j < 5; j++) {
        const v = Number(row[j] ?? 0) || 0
        if (v > maxVal) maxVal = v
        data.push([j, i, v])
      }
    }
    heatmapChart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        position: 'top',
        ...CHART_TOOLTIP,
        formatter: (params) => {
          const homeGoals = params.value[1]
          const awayGoals = params.value[0]
          return `比分 ${homeGoals}-${awayGoals}<br/>概率: <b style="color:${CHART_COLORS.gold}">${(params.value[2] * 100).toFixed(2)}%</b>`
        },
      },
      grid: { left: 70, right: 30, top: 20, bottom: 80 },
      xAxis: {
        type: 'category',
        name: '客队进球数',
        nameLocation: 'middle',
        nameGap: 30,
        nameTextStyle: { color: CHART_COLORS.textMuted, fontSize: 12 },
        data: ['0', '1', '2', '3', '4'],
        splitArea: { show: true, areaStyle: { color: ['rgba(19,37,68,0.3)', 'rgba(13,27,48,0.3)'] } },
        axisLabel: { color: CHART_COLORS.textMuted },
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
      },
      yAxis: {
        type: 'category',
        name: '主队进球数',
        nameLocation: 'middle',
        nameGap: 50,
        nameTextStyle: { color: CHART_COLORS.textMuted, fontSize: 12 },
        data: ['0', '1', '2', '3', '4'],
        splitArea: { show: true, areaStyle: { color: ['rgba(19,37,68,0.3)', 'rgba(13,27,48,0.3)'] } },
        axisLabel: { color: CHART_COLORS.textMuted },
        axisLine: { lineStyle: { color: CHART_COLORS.border } },
      },
      visualMap: {
        min: 0,
        max: maxVal,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 5,
        textStyle: { color: CHART_COLORS.textMuted, fontSize: 11 },
        inRange: {
          color: ['#0a1628', '#003366', '#0066cc', CHART_COLORS.blue, CHART_COLORS.gold, CHART_COLORS.orange, CHART_COLORS.red],
        },
        formatter: (v) => (v * 100).toFixed(0) + '%',
      },
      series: [{
        type: 'heatmap',
        data,
        label: {
          show: true,
          color: '#fff',
          formatter: (params) => (params.value[2] * 100).toFixed(1),
          fontSize: 11,
          fontWeight: 600,
          textShadowColor: 'rgba(0,0,0,0.6)',
          textShadowBlur: 2,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 12,
            shadowColor: 'rgba(77, 224, 255, 0.6)',
          },
        },
      }],
    })
  }

  function refreshCharts() {
    const ctx = getChartContext()
    if (!ctx?.prediction) return
    nextTick(() => {
      initPieChart()
      initLambdaChart()
      initHeatmapChart()
    })
  }

  function handleResize() {
    pieChart?.resize()
    lambdaChart?.resize()
    heatmapChart?.resize()
  }

  function disposeCharts() {
    pieChart?.dispose()
    lambdaChart?.dispose()
    heatmapChart?.dispose()
    pieChart = null
    lambdaChart = null
    heatmapChart = null
  }

  if (autoBindResize) {
    onMounted(() => {
      window.addEventListener('resize', handleResize)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('resize', handleResize)
      disposeCharts()
    })
  }

  return {
    refreshCharts,
    handleResize,
    disposeCharts,
    initPieChart,
    initLambdaChart,
    initHeatmapChart,
  }
}

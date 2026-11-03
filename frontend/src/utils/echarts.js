/**
 * 轻量 ECharts：按需注册常用图，避免整包引入
 */
import * as echarts from 'echarts/core'
import { PieChart, BarChart, LineChart, HeatmapChart } from 'echarts/charts'
import {
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  PieChart,
  BarChart,
  LineChart,
  HeatmapChart,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  VisualMapComponent,
  CanvasRenderer,
])

export default echarts
export { echarts }

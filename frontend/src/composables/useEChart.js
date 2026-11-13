/**
 * 通用 ECharts 单图生命周期管理：init / setOption / resize（rAF 节流）/ dispose 全自动收口。
 *
 * 使用方式：
 *   const { render, resize, setOption } = useEChart(chartRef, () => buildOption(data.value))
 *   // 数据就绪后调用 render()；窗口 resize 自动节流处理；组件卸载自动 dispose
 */
import { onMounted, onBeforeUnmount, shallowRef } from 'vue'
import echarts from '@/utils/echarts'

/**
 * @param {import('vue').Ref<HTMLElement|null>} chartRef 图表容器 DOM 引用
 * @param {() => object|null} getOption 返回 ECharts option 的工厂函数；返回 null 时跳过渲染
 * @param {{ theme?: string|null, notMerge?: boolean, autoResize?: boolean }} [opts]
 * @returns {{
 *   chart: import('vue').ShallowRef<object|null>,
 *   render: () => void,
 *   setOption: (opt: object, notMerge?: boolean) => void,
 *   resize: () => void,
 *   dispose: () => void,
 * }}
 */
export function useEChart(chartRef, getOption, opts = {}) {
  const { theme = null, notMerge = true, autoResize = true } = opts

  // shallowRef：避免 ECharts 实例被深度响应式代理导致性能问题
  const chart = shallowRef(null)

  /** 初始化（幂等）并按 getOption 工厂渲染；容器不可见或无 option 时跳过 */
  function render() {
    if (!chartRef.value) return
    if (!chart.value) chart.value = echarts.init(chartRef.value, theme)
    const option = getOption()
    if (option) chart.value.setOption(option, notMerge)
  }

  /** 外部数据变化时直接更新 option（实例必须已存在） */
  function setOption(opt, merge = notMerge) {
    chart.value?.setOption(opt, merge)
  }

  function resize() {
    chart.value?.resize()
  }

  function dispose() {
    chart.value?.dispose()
    chart.value = null
  }

  // window resize 用 rAF 节流：一帧至多触发一次 resize，避免拖拽时高频重排
  let resizeRafId = null
  function throttledResize() {
    if (resizeRafId != null) return
    resizeRafId = requestAnimationFrame(() => {
      resizeRafId = null
      resize()
    })
  }

  if (autoResize) {
    onMounted(() => window.addEventListener('resize', throttledResize))
    onBeforeUnmount(() => {
      window.removeEventListener('resize', throttledResize)
      if (resizeRafId != null) cancelAnimationFrame(resizeRafId)
      dispose()
    })
  } else {
    onBeforeUnmount(dispose)
  }

  return { chart, render, setOption, resize, dispose }
}

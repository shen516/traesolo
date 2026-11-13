/**
 * window resize 监听（rAF 节流）：适用于多个回调统一 resize 的场景。
 * 已使用 useEChart 的组件无需再用本 composable（其内部已内置节流 resize）。
 */
import { onMounted, onBeforeUnmount } from 'vue'

/**
 * @param {(() => void) | Array<() => void>} handlers resize 回调或回调数组
 * @returns {{ trigger: () => void }} 手动触发一次全部回调（如 tab 切换后补偿尺寸）
 */
export function useChartResize(handlers) {
  const fns = Array.isArray(handlers) ? handlers : [handlers]

  let rafId = null

  function runAll() {
    for (const fn of fns) {
      try {
        fn()
      } catch (e) {
        console.error('resize handler error:', e)
      }
    }
  }

  function onResize() {
    if (rafId != null) return
    rafId = requestAnimationFrame(() => {
      rafId = null
      runAll()
    })
  }

  onMounted(() => window.addEventListener('resize', onResize))
  onBeforeUnmount(() => {
    window.removeEventListener('resize', onResize)
    if (rafId != null) cancelAnimationFrame(rafId)
  })

  return { trigger: runAll }
}

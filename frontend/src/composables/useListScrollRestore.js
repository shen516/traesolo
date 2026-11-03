import { onActivated, onDeactivated } from 'vue'

/** 列表页被 keep-alive 缓存时，离开前记下主区域滚动，返回后还原。 */
export function useListScrollRestore() {
  let top = 0

  function scroller() {
    return document.querySelector('.app-main')
  }

  onDeactivated(() => {
    const el = scroller()
    if (el) top = el.scrollTop
  })

  onActivated(() => {
    const el = scroller()
    if (!el) return
    const y = top
    requestAnimationFrame(() => {
      el.scrollTop = y
    })
  })
}

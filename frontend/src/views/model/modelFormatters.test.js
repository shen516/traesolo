import { describe, expect, it } from 'vitest'
import {
  formatAccuracy,
  formatDate,
  formatDuration,
  formatRange,
  leagueName,
} from './modelFormatters'

describe('modelFormatters', () => {
  it('leagueName', () => {
    expect(leagueName('EPL')).toBe('英超')
    expect(leagueName('XYZ')).toBe('XYZ')
  })

  it('formatAccuracy 支持 0~1 与百分数', () => {
    expect(formatAccuracy(0.735)).toBe('73.5%')
    expect(formatAccuracy(73.5)).toBe('73.5%')
    expect(formatAccuracy(null)).toBe('-')
  })

  it('formatDate / formatRange / formatDuration', () => {
    expect(formatDate('2026-11-06 08:00:00')).toBe('2026-11-06')
    expect(formatRange('2026-01-01', '2026-06-01')).toBe('2026-01-01 ~ 2026-06-01')
    expect(formatDuration(500)).toBe('500ms')
    expect(formatDuration(2500)).toBe('2.5s')
  })
})

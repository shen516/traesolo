import { describe, expect, it } from 'vitest'
import {
  getStageLabel,
  levelText,
  scenarioShort,
  weightSourceShort,
  weightSourceTagClass,
} from './matchMeta'

describe('matchMeta labels', () => {
  it('getStageLabel 映射已知阶段', () => {
    expect(getStageLabel('final')).toBe('决赛')
    expect(getStageLabel('custom')).toBe('custom')
  })

  it('levelText 中英映射', () => {
    expect(levelText('high')).toBe('高')
    expect(levelText('mid')).toBe('中')
    expect(levelText('low')).toBe('低')
  })

  it('scenarioShort / weightSourceShort', () => {
    expect(scenarioShort('ensemble')).toBe('整合')
    expect(weightSourceShort('global')).toBe('全局权重')
    expect(weightSourceShort('league:EPL')).toBe('EPL')
    expect(weightSourceShort('scenario:poisson')).toBe('泊松')
    expect(weightSourceTagClass('league:EPL')).toBe('tag-low')
  })
})

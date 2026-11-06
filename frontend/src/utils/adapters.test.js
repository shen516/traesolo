import { describe, expect, it } from 'vitest'
import { adaptLeague, adaptTeam, formatDate, formatTime } from './adapters'

describe('adapters formatters', () => {
  it('formatDate / formatTime', () => {
    expect(formatDate('2026-11-06T12:00:00')).toBe('2026-11-06')
    expect(formatDate(null)).toBe('')
    expect(formatTime('15:30:00')).toBe('15:30')
  })

  it('adaptTeam 缺省与字段映射', () => {
    expect(adaptTeam(null).name).toBe('未知')
    expect(adaptTeam({ id: 'MCI', name: '曼城', elo_rating: 2000, league_id: 'EPL' })).toMatchObject({
      id: 'MCI',
      name: '曼城',
      elo: 2000,
      league: 'EPL',
    })
  })

  it('adaptLeague 缺省', () => {
    expect(adaptLeague(null).name).toBe('未知联赛')
    expect(adaptLeague({ id: 'EPL', name: '英超' }).id).toBe('EPL')
  })
})

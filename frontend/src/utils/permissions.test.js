import { describe, expect, it } from 'vitest'
import {
  ROUTE_PERMISSIONS,
  canAccessRouteFrom,
  hasAnyPermissionFrom,
} from './permissions'

describe('hasAnyPermissionFrom', () => {
  it('admin 始终通过', () => {
    expect(hasAnyPermissionFrom([], true, 'user:manage')).toBe(true)
  })

  it('空权限列表不锁死（兼容旧会话）', () => {
    expect(hasAnyPermissionFrom([], false, 'dashboard:view')).toBe(true)
  })

  it('无要求码时通过', () => {
    expect(hasAnyPermissionFrom(['a'], false)).toBe(true)
  })

  it('命中任一权限码即通过', () => {
    expect(hasAnyPermissionFrom(['match:upcoming', 'x'], false, 'match:finished', 'match:upcoming')).toBe(true)
  })

  it('全部不命中则拒绝', () => {
    expect(hasAnyPermissionFrom(['a'], false, 'b', 'c')).toBe(false)
  })
})

describe('canAccessRouteFrom', () => {
  it('未配置路由默认放行', () => {
    expect(canAccessRouteFrom(['x'], false, 'UnknownRoute')).toBe(true)
  })

  it('Simulation 需要 simulation:view 或 model:manage', () => {
    expect(ROUTE_PERMISSIONS.Simulation).toContain('simulation:view')
    expect(canAccessRouteFrom(['simulation:view'], false, 'Simulation')).toBe(true)
    expect(canAccessRouteFrom(['model:manage'], false, 'Simulation')).toBe(true)
    expect(canAccessRouteFrom(['dashboard:view'], false, 'Simulation')).toBe(false)
  })
})

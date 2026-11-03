import request from './http'

/** 角色权限管理 */
export const permissionApi = {
  // 角色管理
  getRoles: (params = {}) => request.get('/permissions/roles', { params }),
  getAllRoles: () => request.get('/permissions/roles/all'),
  getRole: (id) => request.get(`/permissions/roles/${id}`),
  createRole: (data) => request.post('/permissions/roles', data),
  updateRole: (id, data) => request.put(`/permissions/roles/${id}`, data),
  deleteRole: (id) => request.delete(`/permissions/roles/${id}`),
  getRolePermissions: (id) => request.get(`/permissions/roles/${id}/permissions`),
  updateRolePermissions: (id, permissionIds) => request.put(`/permissions/roles/${id}/permissions`, { permission_ids: permissionIds }),

  // 权限管理
  getPermissions: (params = {}) => request.get('/permissions/permissions', { params }),
  getAllPermissions: () => request.get('/permissions/permissions/all'),
  createPermission: (data) => request.post('/permissions/permissions', data),
  updatePermission: (id, data) => request.put(`/permissions/permissions/${id}`, data),
  deletePermission: (id) => request.delete(`/permissions/permissions/${id}`),
}

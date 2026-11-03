<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">角色权限管理</h1>
      <p class="page-subtitle">管理系统角色和权限配置，支持角色创建、权限分配等功能</p>
    </div>

    <!-- 加载状态 -->
    <StateBlock v-if="loading" type="loading" text="数据加载中..." />

    <!-- 错误提示 -->
    <StateBlock
      v-if="error"
      type="error"
      :text="error"
      retry-text="重试"
      @retry="fetchData"
    />

    <!-- 角色列表 -->
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">角色列表</h2>
        <div class="card-actions">
          <button class="refresh-btn" @click="fetchData" :disabled="loading">
            <span v-if="loading" class="btn-spinner"></span>
            刷新
          </button>
          <button class="btn btn-primary btn-sm" @click="openRoleDialog">+ 新增角色</button>
        </div>
      </div>

      <!-- 角色表格 -->
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>角色名称</th>
              <th>角色编码</th>
              <th>描述</th>
              <th>权限数</th>
              <th>类型</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="role in roles" :key="role.id">
              <td>{{ role.id }}</td>
              <td>
                <div class="role-cell">
                  <span class="role-icon">{{ role.is_system ? '👑' : '🎭' }}</span>
                  <span>{{ role.name }}</span>
                  <span v-if="role.is_system" class="tag tag-mid">系统</span>
                </div>
              </td>
              <td><code class="code-text">{{ role.code }}</code></td>
              <td>{{ role.description || '-' }}</td>
              <td>{{ role.permission_count || 0 }}</td>
              <td>
                <span class="tag" :class="role.is_system ? 'tag-mid' : 'tag-info'">
                  {{ role.is_system ? '系统内置' : '自定义' }}
                </span>
              </td>
              <td>{{ formatDateTime(role.created_at) }}</td>
              <td>
                <button class="link-btn" @click="openPermDialog(role)">分配权限</button>
                <button
                  v-if="!role.is_system"
                  class="link-btn"
                  @click="openRoleDialog(role)"
                >编辑</button>
                <button
                  v-if="!role.is_system"
                  class="link-btn link-danger"
                  @click="deleteRole(role)"
                >删除</button>
              </td>
            </tr>
            <tr v-if="roles.length === 0">
              <td colspan="8" class="empty-row">暂无角色数据</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页 -->
      <Pagination
        v-if="total > 0"
        :page="filters.page"
        :page-size="filters.page_size"
        :total="total"
        @change="changePage"
      />
    </div>

    <!-- 角色创建/编辑弹窗 -->
    <BaseModal
      v-model="roleDialogVisible"
      :title="editRole ? '编辑角色' : '新增角色'"
      width="480px"
    >
      <div class="form-group">
        <label><span class="required">*</span>角色名称</label>
        <input v-model="roleForm.name" placeholder="请输入角色名称" />
      </div>
      <div class="form-group">
        <label><span class="required">*</span>角色编码</label>
        <input v-model="roleForm.code" placeholder="请输入角色编码，如：admin" />
        <span class="form-hint">英文编码，用于权限判断，创建后不可修改</span>
      </div>
      <div class="form-group">
        <label>角色描述</label>
        <input v-model="roleForm.description" placeholder="请输入角色描述" />
      </div>
      <template #footer>
        <button class="btn" @click="roleDialogVisible = false">取消</button>
        <button class="btn btn-primary" @click="saveRole" :disabled="saving">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </template>
    </BaseModal>

    <!-- 权限分配弹窗 -->
    <BaseModal
      v-model="permDialogVisible"
      :title="'分配权限 - ' + (currentRole?.name || '')"
      width="680px"
    >
      <div class="perm-tips">
        <span>💡 勾选需要分配给角色的权限，支持菜单权限和操作权限</span>
      </div>
      <div class="perm-tree">
        <div v-for="group in permissionGroups" :key="group.id" class="perm-group">
          <div class="perm-group-header">
            <label class="checkbox-label">
              <input
                type="checkbox"
                :checked="isAllChecked(group)"
                :indeterminate.prop="isIndeterminate(group)"
                @change="toggleGroup(group)"
              />
              <span class="perm-icon">{{ group.icon || '📁' }}</span>
              <span class="perm-name">{{ group.name }}</span>
            </label>
          </div>
          <div v-if="group.children && group.children.length > 0" class="perm-children">
            <div v-for="child in group.children" :key="child.id" class="perm-item">
              <label class="checkbox-label">
                <input
                  type="checkbox"
                  :value="child.id"
                  v-model="selectedPermIds"
                />
                <span class="perm-icon">{{ child.icon || '📄' }}</span>
                <span class="perm-name">{{ child.name }}</span>
                <span class="tag tag-sm" :class="child.type === 'button' ? 'tag-mid' : 'tag-info'">
                  {{ child.type === 'button' ? '操作' : '菜单' }}
                </span>
              </label>
              <div v-if="child.children && child.children.length > 0" class="perm-subchildren">
                <div v-for="sub in child.children" :key="sub.id" class="perm-item sub">
                  <label class="checkbox-label">
                    <input
                      type="checkbox"
                      :value="sub.id"
                      v-model="selectedPermIds"
                    />
                    <span class="perm-icon">{{ sub.icon || '🔘' }}</span>
                    <span class="perm-name">{{ sub.name }}</span>
                    <span class="tag tag-sm" :class="sub.type === 'button' ? 'tag-mid' : 'tag-info'">
                      {{ sub.type === 'button' ? '操作' : '菜单' }}
                    </span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="btn" @click="permDialogVisible = false">取消</button>
        <button class="btn btn-primary" @click="savePermissions" :disabled="saving">
          {{ saving ? '保存中...' : '确认分配' }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { permissionApi } from '@/api'
import Pagination from '@/components/common/Pagination.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import BaseModal from '@/components/common/BaseModal.vue'

const loading = ref(false)
const saving = ref(false)
const error = ref(null)

const roles = ref([])
const total = ref(0)

const filters = reactive({
  keyword: '',
  page: 1,
  page_size: 15
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filters.page_size)))

// 角色弹窗
const roleDialogVisible = ref(false)
const editRole = ref(null)
const roleForm = reactive({
  name: '',
  code: '',
  description: ''
})

// 权限弹窗
const permDialogVisible = ref(false)
const currentRole = ref(null)
const allPermissions = ref([])
const selectedPermIds = ref([])

const permissionGroups = computed(() => {
  const list = allPermissions.value || []
  return list.filter(p => !p.parent_id || p.parent_id === 0)
})

function formatDateTime(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return String(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function isAllChecked(group) {
  const childIds = getAllChildIds(group)
  if (childIds.length === 0) return selectedPermIds.value.includes(group.id)
  return childIds.every(id => selectedPermIds.value.includes(id))
}

function isIndeterminate(group) {
  const childIds = getAllChildIds(group)
  if (childIds.length === 0) return false
  const checked = childIds.filter(id => selectedPermIds.value.includes(id)).length
  return checked > 0 && checked < childIds.length
}

function getAllChildIds(node) {
  let ids = [node.id]
  if (node.children) {
    for (const child of node.children) {
      ids = ids.concat(getAllChildIds(child))
    }
  }
  return ids
}

function toggleGroup(group) {
  const childIds = getAllChildIds(group)
  const allChecked = childIds.every(id => selectedPermIds.value.includes(id))

  if (allChecked) {
    selectedPermIds.value = selectedPermIds.value.filter(id => !childIds.includes(id))
  } else {
    for (const id of childIds) {
      if (!selectedPermIds.value.includes(id)) {
        selectedPermIds.value.push(id)
      }
    }
  }
}

async function fetchData() {
  loading.value = true
  error.value = null
  try {
    const res = await permissionApi.getRoles({
      page: filters.page,
      page_size: filters.page_size,
      keyword: filters.keyword || undefined
    })
    roles.value = res.roles || []
    total.value = res.total || 0
  } catch (e) {
    error.value = e?.message || '数据加载失败'
  } finally {
    loading.value = false
  }
}

async function fetchAllPermissions() {
  try {
    const res = await permissionApi.getPermissions()
    allPermissions.value = res.permissions || []
  } catch (e) {
    error.value = e?.message || '权限数据加载失败'
  }
}

function changePage(p) {
  if (p < 1 || p > totalPages.value) return
  filters.page = p
  fetchData()
}

function openRoleDialog(role = null) {
  editRole.value = role
  if (role) {
    roleForm.name = role.name
    roleForm.code = role.code
    roleForm.description = role.description || ''
  } else {
    roleForm.name = ''
    roleForm.code = ''
    roleForm.description = ''
  }
  roleDialogVisible.value = true
}

async function saveRole() {
  if (!roleForm.name || !roleForm.code) {
    error.value = '角色名称和编码不能为空'
    return
  }

  saving.value = true
  error.value = null
  try {
    if (editRole.value) {
      await permissionApi.updateRole(editRole.value.id, {
        name: roleForm.name,
        description: roleForm.description
      })
    } else {
      await permissionApi.createRole(roleForm)
    }
    roleDialogVisible.value = false
    await fetchData()
  } catch (e) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function deleteRole(role) {
  if (!confirm(`确认删除角色 "${role.name}" 吗？此操作不可恢复！`)) return
  try {
    await permissionApi.deleteRole(role.id)
    await fetchData()
  } catch (e) {
    error.value = e?.message || '删除失败'
  }
}

async function openPermDialog(role) {
  currentRole.value = role
  selectedPermIds.value = []
  permDialogVisible.value = true

  await fetchAllPermissions()

  try {
    const res = await permissionApi.getRolePermissions(role.id)
    selectedPermIds.value = res.permission_ids || []
  } catch (e) {
    error.value = e?.message || '获取角色权限失败'
  }
}

async function savePermissions() {
  if (!currentRole.value) return

  saving.value = true
  error.value = null
  try {
    await permissionApi.updateRolePermissions(currentRole.value.id, selectedPermIds.value)
    permDialogVisible.value = false
    await fetchData()
  } catch (e) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.page-container {
  height: 100%;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header { margin-bottom: 4px; }
.page-title { font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }
.page-subtitle { font-size: 13px; color: var(--text-muted); }

.card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px;
}
.card-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.card-actions { display: flex; align-items: center; gap: 12px; }

.refresh-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: transparent;
  color: var(--text-secondary); font-size: 13px; cursor: pointer;
  transition: var(--transition);
}
.refresh-btn:hover:not(:disabled) {
  border-color: var(--color-blue); color: var(--color-blue);
}
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(var(--color-blue-rgb), 0.3);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 表格 */
.table-wrapper { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th, .data-table td {
  padding: 10px 12px; text-align: left;
  border-bottom: 1px solid var(--border-color);
}
.data-table th {
  background: var(--bg-secondary); color: var(--text-secondary);
  font-weight: 600; font-size: 12px;
  position: sticky; top: 0; z-index: 1;
}
.data-table tbody tr:hover { background: var(--bg-hover); }
.empty-row { text-align: center; color: var(--text-muted); padding: 24px 0 !important; }

.role-cell { display: flex; align-items: center; gap: 8px; }
.role-icon {
  width: 26px; height: 26px; border-radius: 6px;
  background: rgba(139, 92, 246, 0.12);
  display: flex; align-items: center; justify-content: center;
  font-size: 14px;
}
.code-text {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  padding: 2px 6px;
  background: var(--bg-secondary);
  border-radius: 4px;
  color: var(--color-blue);
}

.link-btn {
  background: none; border: none; color: var(--color-blue);
  cursor: pointer; font-size: 12px; padding: 2px 6px;
  margin-right: 4px; transition: var(--transition);
}
.link-btn:hover { text-decoration: underline; }
.link-danger { color: var(--color-red); }

/* 弹窗表单 */
.form-group { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
.form-group:last-child { margin-bottom: 0; }
.form-group label { font-size: 13px; color: var(--text-secondary); }
.required { color: var(--color-red); margin-right: 2px; }
.form-group input {
  padding: 8px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-primary); font-size: 14px;
}
.form-group input:focus { outline: none; border-color: var(--color-blue); }
.form-hint { font-size: 11px; color: var(--text-muted); }

/* 权限树 */
.perm-tips {
  padding: 10px 14px;
  background: rgba(var(--color-blue-rgb), 0.08);
  border: 1px solid rgba(var(--color-blue-rgb), 0.2);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--color-blue);
  margin-bottom: 16px;
}

.perm-tree {
  max-height: 450px;
  overflow-y: auto;
}

.perm-group {
  margin-bottom: 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.perm-group-header {
  padding: 10px 14px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.perm-children {
  padding: 8px 0;
}

.perm-item {
  padding: 6px 14px 6px 28px;
}

.perm-item.sub {
  padding-left: 48px;
}

.perm-subchildren {
  margin-top: 4px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-primary);
}

.checkbox-label input[type="checkbox"] {
  cursor: pointer;
  width: 16px;
  height: 16px;
  accent-color: var(--color-blue);
}

.perm-icon {
  font-size: 14px;
  width: 20px;
  text-align: center;
}

.perm-name {
  flex: 1;
}

.tag-sm {
  font-size: 10px;
  padding: 1px 6px;
}
</style>

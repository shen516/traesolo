<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">用户管理</h1>
      <p class="page-subtitle">管理后台用户账号，支持创建、编辑、删除、启用/禁用等操作</p>
    </div>

    <!-- 加载状态 -->
    <StateBlock v-if="loading" type="loading" text="数据加载中..." />

    <!-- 错误提示 -->
    <StateBlock v-if="error" type="error" :text="error" retry-text="重试" @retry="fetchData" />

    <!-- 用户统计卡片 -->
    <div class="overview-grid">
      <div class="overview-card card" v-for="s in statsCards" :key="s.label">
        <div class="overview-icon" :style="{ background: s.bg, color: s.color }">{{ s.icon }}</div>
        <div class="overview-info">
          <div class="overview-value" :style="{ color: s.color }">{{ s.value }}</div>
          <div class="overview-label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <!-- 用户列表 -->
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">用户列表</h2>
        <div class="card-actions">
          <button class="refresh-btn" @click="fetchData" :disabled="loading">
            <span v-if="loading" class="btn-spinner"></span>
            刷新
          </button>
          <button class="btn btn-primary btn-sm" @click="openCreateDialog">+ 新增用户</button>
        </div>
      </div>

      <!-- 筛选器 -->
      <div class="filters">
        <div class="filter-item">
          <label>关键词</label>
          <input
            v-model="filters.keyword"
            placeholder="用户名/邮箱"
            @keyup.enter="onFilterChange"
            class="filter-input"
          />
        </div>
        <div class="filter-item">
          <label>等级</label>
          <select v-model="filters.level" @change="onFilterChange">
            <option :value="null">全部</option>
            <option value="free">免费</option>
            <option value="professional">专业</option>
          </select>
        </div>
        <div class="filter-item">
          <label>状态</label>
          <select v-model="filters.is_active" @change="onFilterChange">
            <option :value="null">全部</option>
            <option :value="true">启用</option>
            <option :value="false">禁用</option>
          </select>
        </div>
        <button class="btn btn-sm" @click="onFilterChange">搜索</button>
        <button class="btn btn-sm" @click="resetFilters">重置</button>
      </div>

      <!-- 表格 -->
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>用户名</th>
              <th>邮箱</th>
              <th>角色</th>
              <th>等级</th>
              <th>订阅</th>
              <th>分析次数</th>
              <th>注册日期</th>
              <th>最近登录</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>
                <div class="user-cell">
                  <span class="user-avatar">{{ u.avatar || (u.username?.[0]?.toUpperCase() || '?') }}</span>
                  <span>{{ u.username }}</span>
                  <span v-if="u.username === 'admin'" class="tag tag-mid">管理员</span>
                </div>
              </td>
              <td>{{ u.email }}</td>
              <td>
                <div class="role-tags">
                  <template v-if="u.roles && u.roles.length > 0">
                    <span v-for="r in u.roles" :key="r.id" class="tag tag-info tag-sm">
                      {{ r.name }}
                    </span>
                  </template>
                  <span v-else class="text-muted">未分配</span>
                </div>
              </td>
              <td>
                <span class="tag" :class="u.level === 'professional' ? 'tag-info' : 'tag-low'">
                  {{ u.level === 'professional' ? '专业' : '免费' }}
                </span>
              </td>
              <td>
                <div class="sub-cell">
                  <span class="sub-plan-name">{{ planLabel(u.subscription_plan) }}</span>
                  <span class="tag" :class="subscriptionTagClass(u.subscription_status)">
                    {{ subscriptionText(u.subscription_status) }}
                  </span>
                  <span class="sub-expire text-muted" v-if="u.subscription_expire">{{ formatDate(u.subscription_expire) }} 到期</span>
                </div>
              </td>
              <td>{{ u.total_analysis || 0 }}</td>
              <td>{{ formatDate(u.join_date) }}</td>
              <td>{{ formatDateTime(u.last_login_at) }}</td>
              <td>
                <span class="tag" :class="u.is_active ? 'tag-low' : 'tag-high'">
                  {{ u.is_active ? '启用' : '禁用' }}
                </span>
              </td>
              <td>
                <button class="link-btn" @click="openEditDialog(u)">编辑</button>
                <button class="link-btn" @click="openSubscriptionDialog(u)">订阅</button>
                <button class="link-btn" @click="openRoleDialog(u)">分配角色</button>
                <button class="link-btn" @click="openPasswordDialog(u)">重置密码</button>
                <button
                  v-if="u.username !== 'admin'"
                  class="link-btn"
                  @click="toggleStatus(u)"
                >{{ u.is_active ? '禁用' : '启用' }}</button>
                <button
                  v-if="u.username !== 'admin'"
                  class="link-btn link-danger"
                  @click="deleteUser(u)"
                >删除</button>
              </td>
            </tr>
            <tr v-if="users.length === 0">
              <td colspan="11" class="empty-row">暂无用户数据</td>
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

    <!-- 用户创建/编辑弹窗 -->
    <BaseModal v-model="userDialogVisible" :title="editMode ? '编辑用户' : '新增用户'" width="640px">
      <div class="form-grid">
        <div class="form-group">
          <label><span class="required">*</span>用户名</label>
          <input v-model="userForm.username" placeholder="请输入用户名" />
        </div>
        <div class="form-group">
          <label><span class="required">*</span>邮箱</label>
          <input v-model="userForm.email" type="email" placeholder="请输入邮箱" />
        </div>
        <div class="form-group" v-if="!editMode">
          <label><span class="required">*</span>密码</label>
          <input v-model="userForm.password" type="password" placeholder="至少6位" />
        </div>
        <div class="form-group">
          <label>头像（emoji或URL）</label>
          <input v-model="userForm.avatar" placeholder="例如：👤" />
        </div>
        <div class="form-group">
          <label>用户等级</label>
          <select v-model="userForm.level">
            <option value="free">免费用户</option>
            <option value="professional">专业用户</option>
          </select>
        </div>
      </div>
      <p class="form-hint" style="margin-top:12px;">订阅开通/续费/取消请在用户列表的「订阅」入口操作，时长由套餐决定。</p>
      <template #footer>
        <button class="btn" @click="userDialogVisible = false">取消</button>
        <button class="btn btn-primary" @click="saveUser" :disabled="saving">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </template>
    </BaseModal>

    <!-- 重置密码弹窗 -->
    <BaseModal v-model="passwordDialogVisible" :title="`重置密码 - ${currentUser?.username || ''}`">
      <div class="form-group">
        <label><span class="required">*</span>新密码</label>
        <input v-model="passwordForm.new_password" type="password" placeholder="至少6位" />
        <span class="form-hint">密码长度不能少于6位</span>
      </div>
      <div class="form-group">
        <label><span class="required">*</span>确认密码</label>
        <input v-model="passwordForm.confirm" type="password" placeholder="再次输入新密码" />
      </div>
      <template #footer>
        <button class="btn" @click="passwordDialogVisible = false">取消</button>
        <button class="btn btn-primary" @click="savePassword" :disabled="saving">
          {{ saving ? '保存中...' : '确认重置' }}
        </button>
      </template>
    </BaseModal>

    <!-- 角色分配弹窗 -->
    <BaseModal v-model="roleDialogVisible" :title="`分配角色 - ${roleUser?.username || ''}`">
      <div class="role-select-tip">
        <span>💡 选择要分配给用户的角色，可多选</span>
      </div>
      <div class="role-list">
        <label v-for="role in allRoles" :key="role.id" class="role-item">
          <input type="checkbox" :value="role.id" v-model="selectedRoleIds" />
          <div class="role-info">
            <div class="role-name">
              <span>{{ role.name }}</span>
              <span v-if="role.is_system" class="tag tag-mid tag-sm">系统</span>
            </div>
            <div class="role-code">{{ role.code }}</div>
          </div>
        </label>
        <div v-if="allRoles.length === 0" class="empty-text">
          暂无角色数据
        </div>
      </div>
      <template #footer>
        <button class="btn" @click="roleDialogVisible = false">取消</button>
        <button class="btn btn-primary" @click="saveUserRoles" :disabled="saving">
          {{ saving ? '保存中...' : '确认分配' }}
        </button>
      </template>
    </BaseModal>

    <!-- 订阅管理弹窗 -->
    <BaseModal v-model="subDialogVisible" :title="`订阅管理 - ${subUser?.username || ''}`" width="640px">
      <!-- 当前状态 -->
      <div class="sub-current" v-if="subCurrent">
        <div class="sub-current-item">
          <span class="sub-label">当前套餐</span>
          <span class="sub-value">{{ subCurrent.plan_name || subCurrent.plan_code }}</span>
        </div>
        <div class="sub-current-item">
          <span class="sub-label">状态</span>
          <span class="tag" :class="subscriptionTagClass(subCurrent.status)">
            {{ subscriptionText(subCurrent.status) }}
          </span>
        </div>
        <div class="sub-current-item">
          <span class="sub-label">到期日</span>
          <span class="sub-value">{{ subCurrent.expire_date || '不限' }}</span>
        </div>
        <div class="sub-current-item" v-if="subCurrent.remaining_days != null">
          <span class="sub-label">剩余</span>
          <span class="sub-value">{{ subCurrent.remaining_days }} 天</span>
        </div>
      </div>

      <!-- 开通/续费 -->
      <div class="form-grid" style="margin-top:16px;">
        <div class="form-group">
          <label>开通/变更套餐</label>
          <select v-model="subForm.plan_code">
            <option v-for="p in plans" :key="p.code" :value="p.code">
              {{ p.name }}（{{ p.duration_days > 0 ? p.duration_days + '天' : '不限' }}）
            </option>
          </select>
          <span class="form-hint">同档续费自动叠加时长；降档保持原到期日</span>
        </div>
        <div class="form-group">
          <label>备注</label>
          <input v-model="subForm.note" placeholder="可选，如：线下收款" />
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px;">
        <button class="btn btn-primary btn-sm" @click="grantSubscription" :disabled="saving">
          {{ saving ? '提交中...' : '开通/续费' }}
        </button>
        <button
          v-if="subCurrent && subCurrent.status === 'active' && subCurrent.tier !== 'free'"
          class="btn btn-sm btn-danger-outline"
          @click="cancelSubscription"
          :disabled="saving"
        >取消订阅</button>
      </div>

      <!-- 流水 -->
      <div class="sub-records">
        <h4 class="sub-records-title">订阅流水</h4>
        <table class="data-table" v-if="subRecords.length">
          <thead>
            <tr>
              <th>时间</th>
              <th>套餐</th>
              <th>周期</th>
              <th>状态</th>
              <th>操作人</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in subRecords" :key="r.id">
              <td>{{ formatDateTime(r.created_at) }}</td>
              <td>{{ r.plan_name || r.plan_code }}</td>
              <td>{{ r.start_date }} ~ {{ r.end_date || '不限' }}</td>
              <td>
                <span class="tag tag-sm" :class="subscriptionTagClass(r.status)">
                  {{ subscriptionText(r.status) }}
                </span>
              </td>
              <td>{{ r.operator_name || '-' }}</td>
              <td>{{ r.note || '-' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-text">暂无流水记录</div>
      </div>
      <template #footer>
        <button class="btn" @click="subDialogVisible = false">关闭</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { userApi, permissionApi, subscriptionApi } from '@/api'
import { formatDate as baseFormatDate, formatCompactDateTime } from '@/utils/formatters'
import Pagination from '@/components/common/Pagination.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import BaseModal from '@/components/common/BaseModal.vue'

const loading = ref(false)
const saving = ref(false)
const error = ref(null)

const users = ref([])
const total = ref(0)
const stats = ref({ total: 0, active: 0, disabled: 0, professional: 0, free: 0, new_today: 0 })
const allRoles = ref([])

const filters = reactive({
  keyword: '',
  level: null,
  is_active: null,
  page: 1,
  page_size: 15
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filters.page_size)))

const statsCards = computed(() => [
  { label: '总用户数', value: stats.value.total, icon: '👥', color: 'var(--color-blue)', bg: 'rgba(var(--color-blue-rgb), 0.12)' },
  { label: '启用用户', value: stats.value.active, icon: '✅', color: 'var(--color-green)', bg: 'rgba(var(--color-green-rgb), 0.12)' },
  { label: '禁用用户', value: stats.value.disabled, icon: '⛔', color: 'var(--color-red)', bg: 'rgba(var(--color-red-rgb), 0.12)' },
  { label: '专业用户', value: stats.value.professional, icon: '⭐', color: 'var(--color-gold)', bg: 'rgba(var(--color-gold-rgb), 0.12)' },
  { label: '今日新增', value: stats.value.new_today, icon: '🆕', color: 'var(--color-orange)', bg: 'rgba(var(--color-orange-rgb), 0.12)' }
])

// 弹窗状态
const userDialogVisible = ref(false)
const editMode = ref(false)
const currentUser = ref(null)
const userForm = reactive({
  username: '',
  email: '',
  password: '',
  avatar: '',
  level: 'free'
})

const passwordDialogVisible = ref(false)
const passwordForm = reactive({ new_password: '', confirm: '' })

// 角色分配弹窗
const roleDialogVisible = ref(false)
const roleUser = ref(null)
const selectedRoleIds = ref([])

// 订阅管理弹窗
const subDialogVisible = ref(false)
const subUser = ref(null)
const subCurrent = ref(null)
const subRecords = ref([])
const plans = ref([])
const subForm = reactive({ plan_code: 'pro_month', note: '' })

// 订阅日期展示：YYYY-MM-DD，空值显示 '-'
const formatDate = (dateStr) => baseFormatDate(dateStr, '-')

// 最近登录展示：紧凑 M-D HH:MM，从未登录显示提示文案
const formatDateTime = (dateStr) => formatCompactDateTime(dateStr, '从未登录')

function subscriptionText(s) {
  return { active: '有效', expired: '过期', cancelled: '取消' }[s] || s
}

function planLabel(code) {
  return {
    free: '免费版',
    pro_month: '专业·月',
    pro_quarter: '专业·季',
    pro_year: '专业·年',
    flag_month: '旗舰·月',
    flag_quarter: '旗舰·季',
    flag_year: '旗舰·年',
    professional: '专业版',
  }[code] || code || '免费版'
}

function subscriptionTagClass(s) {
  return { active: 'tag-low', expired: 'tag-high', cancelled: 'tag-mid' }[s] || 'tag-mid'
}

async function fetchData() {
  loading.value = true
  error.value = null
  try {
    await Promise.all([fetchUsers(), fetchStats(), fetchAllRoles()])
  } catch (e) {
    error.value = e?.message || '数据加载失败'
  } finally {
    loading.value = false
  }
}

async function fetchAllRoles() {
  try {
    const res = await permissionApi.getAllRoles()
    allRoles.value = res.roles || []
  } catch (e) {
    // 角色列表加载失败不影响主流程
    console.warn('加载角色列表失败:', e)
  }
}

async function fetchUsers() {
  const params = { page: filters.page, page_size: filters.page_size }
  if (filters.keyword) params.keyword = filters.keyword
  if (filters.level) params.level = filters.level
  if (filters.is_active !== null) params.is_active = filters.is_active

  const res = await userApi.getList(params)
  users.value = res.users || []
  total.value = res.total || 0
}

async function fetchStats() {
  const res = await userApi.getStats()
  stats.value = res
}

function onFilterChange() {
  filters.page = 1
  fetchUsers()
}

function resetFilters() {
  filters.keyword = ''
  filters.level = null
  filters.is_active = null
  filters.page = 1
  fetchUsers()
}

function changePage(p) {
  if (p < 1 || p > totalPages.value) return
  filters.page = p
  fetchUsers()
}

function openCreateDialog() {
  editMode.value = false
  currentUser.value = null
  Object.assign(userForm, {
    username: '',
    email: '',
    password: '',
    avatar: '',
    level: 'free'
  })
  userDialogVisible.value = true
}

function openEditDialog(user) {
  editMode.value = true
  currentUser.value = user
  Object.assign(userForm, {
    username: user.username,
    email: user.email,
    password: '',
    avatar: user.avatar || '',
    level: user.level || 'free'
  })
  userDialogVisible.value = true
}

// 邮箱格式正则（前端预校验，后端仍做权威校验）
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

async function saveUser() {
  if (!userForm.username || !userForm.email) {
    error.value = '用户名和邮箱不能为空'
    return
  }
  if (!EMAIL_RE.test(userForm.email)) {
    error.value = '邮箱格式不正确'
    return
  }
  if (!editMode.value && !userForm.password) {
    error.value = '密码不能为空'
    return
  }
  if (!editMode.value && userForm.password.length < 6) {
    error.value = '密码长度不能少于6位'
    return
  }

  saving.value = true
  error.value = null
  try {
    if (editMode.value) {
      const updateData = {
        username: userForm.username,
        email: userForm.email,
        avatar: userForm.avatar || null,
        level: userForm.level
      }
      await userApi.update(currentUser.value.id, updateData)
    } else {
      const createData = {
        username: userForm.username,
        email: userForm.email,
        password: userForm.password,
        avatar: userForm.avatar || null,
        level: userForm.level
      }
      await userApi.register(createData)
    }
    userDialogVisible.value = false
    await fetchData()
  } catch (e) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

function openPasswordDialog(user) {
  currentUser.value = user
  passwordForm.new_password = ''
  passwordForm.confirm = ''
  passwordDialogVisible.value = true
}

async function savePassword() {
  if (!passwordForm.new_password) {
    error.value = '新密码不能为空'
    return
  }
  if (passwordForm.new_password.length < 6) {
    error.value = '密码长度不能少于6位'
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm) {
    error.value = '两次输入的密码不一致'
    return
  }

  saving.value = true
  error.value = null
  try {
    await userApi.resetPassword(currentUser.value.id, passwordForm.new_password)
    passwordDialogVisible.value = false
  } catch (e) {
    error.value = e?.message || '重置密码失败'
  } finally {
    saving.value = false
  }
}

function openRoleDialog(user) {
  roleUser.value = user
  selectedRoleIds.value = user.roles ? user.roles.map(r => r.id) : []
  roleDialogVisible.value = true
}

async function saveUserRoles() {
  if (!roleUser.value) return

  saving.value = true
  error.value = null
  try {
    await userApi.update(roleUser.value.id, {
      role_ids: selectedRoleIds.value
    })
    roleDialogVisible.value = false
    await fetchUsers()
  } catch (e) {
    error.value = e?.message || '保存角色失败'
  } finally {
    saving.value = false
  }
}

async function openSubscriptionDialog(user) {
  subUser.value = user
  subForm.plan_code = 'pro_month'
  subForm.note = ''
  subCurrent.value = null
  subRecords.value = []
  subDialogVisible.value = true
  try {
    if (!plans.value.length) {
      const res = await subscriptionApi.getPlans()
      plans.value = res.plans || []
    }
    // 管理员视角：直接查该用户的订阅快照（/my 只面向当前登录人，这里用用户详情+流水拼装）
    const [detail, recordsRes] = await Promise.all([
      userApi.getById(user.id),
      subscriptionApi.getRecords({ user_id: user.id, page_size: 10 }),
    ])
    const plan = plans.value.find(p => p.code === (detail.subscription_plan || 'free'))
    subCurrent.value = {
      plan_code: detail.subscription_plan || 'free',
      plan_name: plan?.name || detail.subscription_plan || '免费版',
      tier: plan?.tier || 'free',
      status: detail.subscription_status || 'expired',
      expire_date: detail.subscription_expire || null,
      remaining_days: detail.subscription_expire
        ? Math.max(0, Math.ceil((new Date(detail.subscription_expire) - Date.now()) / 86400000) + 1)
        : null,
    }
    subRecords.value = recordsRes.records || []
  } catch (e) {
    error.value = e?.message || '加载订阅信息失败'
  }
}

async function grantSubscription() {
  if (!subUser.value) return
  saving.value = true
  error.value = null
  try {
    await subscriptionApi.grant({
      user_id: subUser.value.id,
      plan_code: subForm.plan_code,
      note: subForm.note || null,
    })
    await openSubscriptionDialog(subUser.value)
    await fetchUsers()
  } catch (e) {
    error.value = e?.message || '开通失败'
  } finally {
    saving.value = false
  }
}

async function cancelSubscription() {
  if (!subUser.value) return
  if (!confirm(`确认取消用户 "${subUser.value.username}" 的订阅吗？权益将立即回落免费版。`)) return
  saving.value = true
  error.value = null
  try {
    await subscriptionApi.cancel({ user_id: subUser.value.id, note: subForm.note || null })
    await openSubscriptionDialog(subUser.value)
    await fetchUsers()
  } catch (e) {
    error.value = e?.message || '取消失败'
  } finally {
    saving.value = false
  }
}

async function toggleStatus(user) {
  const action = user.is_active ? '禁用' : '启用'
  if (!confirm(`确认${action}用户 "${user.username}" 吗？`)) return
  try {
    await userApi.toggleStatus(user.id, !user.is_active)
    await fetchData()
  } catch (e) {
    error.value = e?.message || `${action}失败`
  }
}

async function deleteUser(user) {
  if (!confirm(`确认删除用户 "${user.username}" 吗？此操作不可恢复！`)) return
  try {
    await userApi.delete(user.id)
    await fetchData()
  } catch (e) {
    error.value = e?.message || '删除失败'
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

.overview-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}
.overview-card { display: flex; align-items: center; gap: 14px; }
.overview-icon {
  width: 44px; height: 44px; border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; flex-shrink: 0;
}
.overview-info { display: flex; flex-direction: column; }
.overview-value { font-size: 20px; font-weight: 700; line-height: 1.2; }
.overview-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

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

/* 筛选器 */
.filters {
  display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;
  margin-bottom: 16px; padding: 14px;
  background: rgba(26, 38, 65, 0.4); border-radius: var(--radius-sm);
}
.filter-item { display: flex; flex-direction: column; gap: 4px; }
.filter-item label { font-size: 11px; color: var(--text-muted); }
.filter-item select,
.filter-input {
  padding: 6px 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-primary); font-size: 13px; min-width: 140px;
}
.filter-input { cursor: text; }
.filter-item select { cursor: pointer; min-width: 120px; }
.filter-item select:focus,
.filter-input:focus { outline: none; border-color: var(--color-blue); }

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

.user-cell { display: flex; align-items: center; gap: 8px; }
.user-avatar {
  width: 26px; height: 26px; border-radius: 50%;
  background: var(--bg-hover); color: var(--color-blue);
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
}

.link-btn {
  background: none; border: none; color: var(--color-blue);
  cursor: pointer; font-size: 12px; padding: 2px 6px;
  margin-right: 4px; transition: var(--transition);
}
.link-btn:hover { text-decoration: underline; }
.link-danger { color: var(--color-red); }

@keyframes spin { to { transform: rotate(360deg); } }

.form-grid {
  display: grid; grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; color: var(--text-secondary); }
.required { color: var(--color-red); margin-right: 2px; }
.form-group input,
.form-group select {
  padding: 8px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-primary); font-size: 14px;
}
.form-group input:focus,
.form-group select:focus { outline: none; border-color: var(--color-blue); }
.form-hint { font-size: 11px; color: var(--text-muted); }

.role-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.tag-sm {
  font-size: 10px;
  padding: 1px 6px;
}

.role-select-tip {
  padding: 10px 14px;
  background: rgba(var(--color-blue-rgb), 0.08);
  border: 1px solid rgba(var(--color-blue-rgb), 0.2);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--color-blue);
  margin-bottom: 16px;
}

.role-list {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.role-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
  transition: var(--transition);
}

.role-item:last-child {
  border-bottom: none;
}

.role-item:hover {
  background: var(--bg-hover);
}

.role-item input[type="checkbox"] {
  margin-top: 3px;
  cursor: pointer;
  accent-color: var(--color-blue);
}

.role-info {
  flex: 1;
}

.role-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.role-code {
  font-size: 11px;
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
}

.empty-text {
  padding: 30px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
}

/* 订阅列 */
.sub-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.sub-plan-name {
  font-size: 12px;
  color: var(--text-secondary);
}
.sub-expire {
  font-size: 11px;
}

/* 订阅管理弹窗 */
.sub-current {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  padding: 12px 14px;
  background: rgba(26, 38, 65, 0.4);
  border-radius: var(--radius-sm);
}
.sub-current-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sub-label {
  font-size: 11px;
  color: var(--text-muted);
}
.sub-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.sub-records {
  margin-top: 18px;
}
.sub-records-title {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 8px 0;
}
.btn-danger-outline {
  border: 1px solid var(--color-red);
  color: var(--color-red);
  background: transparent;
}
.btn-danger-outline:hover:not(:disabled) {
  background: rgba(var(--color-red-rgb), 0.12);
}
</style>

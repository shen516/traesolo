<template>
  <header class="app-header">
    <div class="header-left">
      <div class="logo">
        <span class="logo-icon">⚽</span>
        <div class="logo-text">
          <span class="logo-title">足球量化分析</span>
          <span class="logo-version">5.0 职业版</span>
        </div>
      </div>
    </div>

    <div class="header-center">
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input
          v-model="searchKeyword"
          placeholder="搜索球队、赛事、联赛..."
          @keyup.enter="handleSearch"
        />
      </div>
    </div>

    <div class="header-right">
      <div class="header-stat">
        <span class="stat-label">模型准确率</span>
        <span v-if="accuracyLoading" class="stat-value text-muted">—</span>
        <span v-else-if="accuracyError" class="stat-value text-muted" :title="accuracyError">—</span>
        <span v-else class="stat-value text-green">{{ modelAccuracy }}</span>
      </div>
      <div class="header-divider"></div>
      <div class="header-stat">
        <span class="stat-label">今日赛事</span>
        <span v-if="matchLoading" class="stat-value text-muted">—</span>
        <span v-else-if="matchError" class="stat-value text-muted" :title="matchError">—</span>
        <span v-else class="stat-value text-gold">{{ todayMatchCount }}</span>
      </div>
      <div class="header-divider"></div>
      <!-- 用户下拉菜单：用户信息 / 修改密码 / 退出 -->
      <div class="user-menu" ref="userMenuRef">
        <div class="user-entry" @click="menuOpen = !menuOpen" title="账号菜单">
          <div class="user-avatar">{{ userAvatar }}</div>
          <span class="user-name">{{ username }}</span>
          <span class="caret" :class="{ open: menuOpen }">▾</span>
        </div>
        <transition name="dropdown-fade">
          <div v-if="menuOpen" class="user-dropdown">
            <div class="dropdown-item" @click="goProfile">
              <span class="item-icon">👤</span>
              <span>用户信息</span>
            </div>
            <div class="dropdown-item" @click="goChangePassword">
              <span class="item-icon">🔑</span>
              <span>修改密码</span>
            </div>
            <div class="dropdown-divider"></div>
            <div class="dropdown-item danger" :class="{ disabled: loggingOut }" @click="handleLogout">
              <span class="item-icon">🚪</span>
              <span>{{ loggingOut ? '退出中...' : '退出' }}</span>
              <span v-if="loggingOut" class="logout-spinner"></span>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { matchApi, modelApi } from '@/api'

const router = useRouter()
const userStore = useUserStore()
const searchKeyword = ref('')

const todayMatchCount = ref(0)
const matchLoading = ref(false)
const matchError = ref('')

const modelAccuracy = ref('0%')
const accuracyLoading = ref(false)
const accuracyError = ref('')

const loggingOut = ref(false)

// 下拉菜单状态与外部点击关闭
const menuOpen = ref(false)
const userMenuRef = ref(null)

const username = computed(() => userStore.user?.username || '用户')

const userAvatar = computed(() => {
  const user = userStore.user
  if (user?.avatar) return user.avatar
  const name = user?.username || ''
  return name.slice(0, 2).toUpperCase()
})

function handleSearch() {
  if (searchKeyword.value.trim()) {
    router.push({ path: '/matches/upcoming', query: { q: searchKeyword.value } })
  }
}

function goProfile() {
  menuOpen.value = false
  router.push('/profile')
}

function goChangePassword() {
  menuOpen.value = false
  // 与 Profile 的 PasswordChangeCard 共用表单（?tab=password）
  router.push({ path: '/profile', query: { tab: 'password' } })
}

function onDocClick(e) {
  if (userMenuRef.value && !userMenuRef.value.contains(e.target)) {
    menuOpen.value = false
  }
}

async function loadTodayMatches() {
  matchLoading.value = true
  matchError.value = ''
  try {
    const today = new Date()
    const dateStr = today.toISOString().slice(0, 10)
    const res = await matchApi.getByDate(dateStr)
    todayMatchCount.value = (res.matches || []).length
  } catch (e) {
    matchError.value = e.message || '获取今日赛事失败'
    todayMatchCount.value = 0
  } finally {
    matchLoading.value = false
  }
}

async function loadModelAccuracy() {
  accuracyLoading.value = true
  accuracyError.value = ''
  try {
    const res = await modelApi.getCurrent()
    let accuracy = 0
    if (res.accuracy != null) {
      accuracy = parseFloat(res.accuracy)
      if (accuracy < 1) {
        accuracy = accuracy * 100
      }
    }
    modelAccuracy.value = accuracy.toFixed(1) + '%'
  } catch (e) {
    accuracyError.value = e.message || '获取模型准确率失败'
    modelAccuracy.value = '0%'
  } finally {
    accuracyLoading.value = false
  }
}

async function handleLogout() {
  if (loggingOut.value) return
  loggingOut.value = true
  menuOpen.value = false
  try {
    await userStore.logout()
  } finally {
    loggingOut.value = false
    router.push('/login')
  }
}

onMounted(() => {
  loadTodayMatches()
  loadModelAccuracy()
  document.addEventListener('click', onDocClick)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
})
</script>

<style scoped>
.app-header {
  height: 60px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}

.header-left .logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  font-size: 28px;
}

.logo-text {
  display: flex;
  flex-direction: column;
}

.logo-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-gold);
}

.logo-version {
  font-size: 11px;
  color: var(--text-muted);
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
  max-width: 500px;
  margin: 0 40px;
}

.search-box {
  width: 100%;
  height: 38px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 19px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  transition: var(--transition);
}

.search-box:focus-within {
  border-color: var(--color-blue);
  box-shadow: 0 0 12px rgba(var(--color-blue-rgb), 0.2);
}

.search-icon {
  font-size: 14px;
  margin-right: 8px;
  opacity: 0.6;
}

.search-box input {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 13px;
}

.search-box input::placeholder {
  color: var(--text-muted);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-stat {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.stat-label {
  font-size: 11px;
  color: var(--text-muted);
}

.stat-value {
  font-size: 16px;
  font-weight: 700;
}

.header-divider {
  width: 1px;
  height: 24px;
  background: var(--border-color);
}

.user-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 20px;
  transition: var(--transition);
}

.user-entry:hover {
  background: var(--bg-hover);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--color-blue), #0066cc);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}

.user-name {
  font-size: 13px;
  color: var(--text-secondary);
}

.caret {
  font-size: 11px;
  color: var(--text-muted);
  transition: transform 0.2s;
}

.caret.open {
  transform: rotate(180deg);
}

/* 用户下拉菜单 */
.user-menu {
  position: relative;
}

.user-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 168px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  padding: 6px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s;
  user-select: none;
}

.dropdown-item:hover {
  background: var(--bg-hover);
}

.dropdown-item.danger {
  color: var(--color-red);
}

.dropdown-item.danger:hover {
  background: rgba(var(--color-red-rgb), 0.1);
}

.dropdown-item.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.dropdown-item.disabled:hover {
  background: transparent;
}

.item-icon {
  font-size: 14px;
  width: 18px;
  text-align: center;
}

.dropdown-divider {
  height: 1px;
  background: var(--border-color);
  margin: 4px 6px;
}

.dropdown-fade-enter-active,
.dropdown-fade-leave-active {
  transition: opacity 0.15s, transform 0.15s;
}

.dropdown-fade-enter-from,
.dropdown-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.logout-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: logout-spin 0.8s linear infinite;
}

@keyframes logout-spin {
  to { transform: rotate(360deg); }
}
</style>

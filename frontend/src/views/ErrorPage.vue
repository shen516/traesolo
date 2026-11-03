<template>
  <div class="error-page">
    <div class="error-card card">
      <div class="error-icon">{{ isForbidden ? '🔒' : '🧭' }}</div>
      <h1 class="error-title">{{ isForbidden ? '403 无访问权限' : '404 页面不存在' }}</h1>
      <p class="error-desc">
        {{ isForbidden
          ? '当前账号没有访问该页面的权限，请联系管理员分配相应权限。'
          : '页面不存在或已被移动，请从菜单重新导航。' }}
      </p>
      <div class="error-actions">
        <button class="btn btn-primary" @click="goHome">返回首页</button>
        <button v-if="isForbidden" class="btn" @click="goProfile">查看我的权限</button>
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * 403 / 404 兜底页。route.meta.code 决定类型（403 无权限 / 404 未找到）。
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const isForbidden = computed(() => route.meta.code === 403)

function goHome() {
  router.push('/')
}

function goProfile() {
  router.push('/profile')
}
</script>

<style scoped>
.error-page {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.error-card {
  max-width: 420px;
  padding: 48px 36px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
}

.error-icon {
  font-size: 48px;
}

.error-title {
  margin: 0;
  font-size: var(--font-xl);
  color: var(--text-primary);
}

.error-desc {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.6;
}

.error-actions {
  display: flex;
  gap: var(--space-sm);
  margin-top: var(--space-sm);
}
</style>

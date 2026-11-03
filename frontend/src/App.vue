<template>
  <div v-if="isLoginPage">
    <router-view />
  </div>
  <div v-else-if="route.name" class="app-container">
    <AppHeader />
    <div class="app-body">
      <AppSidebar />
      <main class="app-main">
        <router-view v-slot="{ Component, route: r }">
          <keep-alive>
            <component :is="Component" v-if="r.meta.keepAlive" :key="r.name" />
          </keep-alive>
          <component :is="Component" v-if="!r.meta.keepAlive" :key="r.fullPath" />
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from '@/components/Layout/AppHeader.vue'
import AppSidebar from '@/components/Layout/AppSidebar.vue'
import { useUserStore } from '@/stores/user'
import { useFollowsStore } from '@/stores/follows'

const route = useRoute()
const isLoginPage = computed(() => route.name === 'Login' || route.path === '/login')
const userStore = useUserStore()
const followsStore = useFollowsStore()

onMounted(() => {
  if (userStore.isLoggedIn) {
    userStore.refreshSubscription()
    followsStore.hydrateFromPreferences(userStore.user?.id)
  }
})
</script>

<style scoped>
.app-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.app-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.app-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>

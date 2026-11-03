import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import MediaImg from './components/MediaImg.vue'
import './assets/styles/main.css'

const app = createApp(App)
app.component('MediaImg', MediaImg)
app.use(createPinia())
app.use(router)
// 等路由就绪后再挂载，避免 route.name 未解析时误渲染主布局触发 401 循环
router.isReady().then(() => {
  app.mount('#app')
})

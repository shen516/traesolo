<template>
  <div class="login-container">
    <div class="login-bg">
      <div class="bg-circle circle-1"></div>
      <div class="bg-circle circle-2"></div>
      <div class="bg-circle circle-3"></div>
    </div>

    <div class="login-box">
      <div class="login-header">
        <div class="logo-icon">⚽</div>
        <h1>足球量化分析系统</h1>
        <p>纯竞技量化模型 5.0 职业版</p>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label>账号</label>
          <div class="input-wrapper">
            <span class="input-icon">👤</span>
            <input
              v-model="form.username"
              type="text"
              placeholder="请输入用户名"
              autocomplete="username"
            />
          </div>
        </div>

        <div class="form-group">
          <label>密码</label>
          <div class="input-wrapper">
            <span class="input-icon">🔒</span>
            <input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="请输入密码"
              autocomplete="current-password"
            />
            <span class="input-action" @click="showPassword = !showPassword">
              {{ showPassword ? '🙈' : '👁' }}
            </span>
          </div>
        </div>

        <div class="form-group">
          <label>验证码</label>
          <div class="captcha-wrapper">
            <div class="input-wrapper captcha-input">
              <span class="input-icon">🛡</span>
              <input
                v-model="form.captchaCode"
                type="text"
                placeholder="请输入验证码"
                maxlength="4"
              />
            </div>
            <div class="captcha-image" @click="refreshCaptcha" title="点击刷新验证码">
              <img v-if="captchaImage" :src="captchaImage" alt="验证码" />
              <div v-else class="captcha-loading">加载中...</div>
            </div>
          </div>
        </div>

        <div v-if="errorMsg" class="error-message">
          ⚠ {{ errorMsg }}
        </div>

        <button type="submit" class="login-btn" :disabled="loading">
          <span v-if="loading" class="loading-spinner"></span>
          {{ loading ? '登录中...' : '登 录' }}
        </button>

        <div class="login-tips">
          <!--<span>仅供学习研究 · 请使用管理员分配的账号登录</span>-->
        </div>
      </form>

      <div class="login-footer">
        <p>© 2026 足球量化分析系统 | 仅供研究使用</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { authApi } from '@/api'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const form = ref({
  username: '',
  password: '',
  captchaId: '',
  captchaCode: ''
})

const showPassword = ref(false)
const loading = ref(false)
const errorMsg = ref('')
const captchaImage = ref('')

const refreshCaptcha = async () => {
  try {
    const res = await authApi.getCaptcha()
    form.value.captchaId = res.captcha_id
    // 后端返回 hex 编码的 PNG 位图（验证码图片，非 SVG，无法反解出明文）
    const hex = res.captcha_image
    if (!hex || hex.length % 2 !== 0) {
      throw new Error('验证码数据格式错误')
    }
    // Uint8Array → base64，避免 Latin1/btoa 在部分浏览器下损坏 PNG
    const bytes = new Uint8Array(hex.length / 2)
    for (let i = 0; i < bytes.length; i++) {
      bytes[i] = parseInt(hex.substr(i * 2, 2), 16)
    }
    let bin = ''
    for (let i = 0; i < bytes.length; i++) {
      bin += String.fromCharCode(bytes[i])
    }
    captchaImage.value = `data:image/png;base64,${btoa(bin)}`
  } catch (_e) {
    errorMsg.value = '获取验证码失败，请检查后端服务'
  }
}

const handleLogin = async () => {
  errorMsg.value = ''

  if (!form.value.username) {
    errorMsg.value = '请输入用户名'
    return
  }
  if (!form.value.password) {
    errorMsg.value = '请输入密码'
    return
  }
  if (!form.value.captchaCode) {
    errorMsg.value = '请输入验证码'
    return
  }

  loading.value = true
  try {
    await userStore.login({
      username: form.value.username,
      password: form.value.password,
      captcha_id: form.value.captchaId,
      captcha_code: form.value.captchaCode
    })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.push(redirect.startsWith('/') ? redirect : '/')
  } catch (e) {
    errorMsg.value = e.message || '登录失败'
    refreshCaptcha()
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refreshCaptcha()
})
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 50%, var(--bg-card) 100%);
  position: relative;
  overflow: hidden;
}

.login-bg {
  position: absolute;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.bg-circle {
  position: absolute;
  border-radius: 50%;
  opacity: 0.08;
}

.circle-1 {
  width: 600px;
  height: 600px;
  background: var(--color-blue);
  top: -200px;
  right: -150px;
  animation: float 8s ease-in-out infinite;
}

.circle-2 {
  width: 400px;
  height: 400px;
  background: var(--color-gold);
  bottom: -100px;
  left: -100px;
  animation: float 10s ease-in-out infinite reverse;
}

.circle-3 {
  width: 300px;
  height: 300px;
  background: var(--color-green);
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation: float 12s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-30px) scale(1.05); }
}

.login-box {
  width: 420px;
  background: rgba(19, 37, 68, 0.85);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(var(--color-blue-rgb), 0.2);
  border-radius: var(--radius-lg);
  padding: 40px 36px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  position: relative;
  z-index: 1;
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.login-header h1 {
  font-size: 24px;
  color: var(--text-primary);
  margin: 0 0 8px 0;
  font-weight: 700;
  letter-spacing: 2px;
}

.login-header p {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

.input-wrapper {
  display: flex;
  align-items: center;
  background: rgba(var(--color-blue-rgb), 0.05);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  transition: all 0.3s;
}

.input-wrapper:focus-within {
  border-color: var(--color-blue);
  box-shadow: 0 0 0 3px rgba(var(--color-blue-rgb), 0.1);
}

.input-icon {
  padding: 0 12px;
  font-size: 16px;
  opacity: 0.6;
}

.input-wrapper input {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  padding: 12px 0;
  color: var(--text-primary);
  font-size: var(--font-md);
}

.input-wrapper input::placeholder {
  color: var(--text-muted);
}

.input-action {
  padding: 0 12px;
  cursor: pointer;
  font-size: 16px;
  opacity: 0.6;
  transition: opacity 0.3s;
}

.input-action:hover {
  opacity: 1;
}

.captcha-wrapper {
  display: flex;
  gap: 12px;
  align-items: center;
}

.captcha-input {
  flex: 1;
}

.captcha-image {
  width: 120px;
  height: 44px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--color-blue-rgb), 0.05);
  transition: border-color 0.3s;
}

.captcha-image:hover {
  border-color: var(--color-blue);
}

.captcha-image img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  image-rendering: pixelated;
}

.captcha-loading {
  font-size: var(--font-sm);
  color: var(--text-muted);
}

.error-message {
  background: rgba(var(--color-red-rgb), 0.1);
  border: 1px solid rgba(var(--color-red-rgb), 0.3);
  color: var(--color-red);
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
}

.login-btn {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, var(--color-blue) 0%, var(--color-blue-deep) 100%);
  border: none;
  border-radius: var(--radius-sm);
  color: #07131f;
  font-size: var(--font-lg);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  margin-top: 4px;
}

.login-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(var(--color-blue-rgb), 0.3);
}

.login-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(var(--color-blue-rgb), 0.3);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.login-tips {
  text-align: center;
  font-size: var(--font-sm);
  color: var(--text-muted);
  margin-top: 4px;
}

.login-footer {
  text-align: center;
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
}

.login-footer p {
  font-size: var(--font-sm);
  color: var(--text-muted);
  margin: 0;
}
</style>

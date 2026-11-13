<template>
  <section class="card password-card">
    <div class="section-header">
      <h2 class="section-title"><span class="section-bar"></span>修改密码</h2>
      <span v-if="mustChange" class="tag tag-high">首次登录需修改初始密码</span>
    </div>
    <form class="password-form" @submit.prevent="submitPassword">
      <p class="password-hint text-muted">
        密码长度需 6–128 位；修改成功后将登出当前账号，请用新密码重新登录。
      </p>
      <div class="form-group">
        <label>当前密码</label>
        <input v-model="passwordForm.oldPassword" type="password" autocomplete="current-password"
          placeholder="请输入当前密码" :disabled="pwdSaving" />
      </div>
      <div class="form-group">
        <label>新密码</label>
        <input v-model="passwordForm.newPassword" type="password" autocomplete="new-password"
          placeholder="6–128 位" :disabled="pwdSaving" />
      </div>
      <div v-if="pwdMsg" class="form-msg form-msg-error">⚠ {{ pwdMsg }}</div>
      <button type="submit" class="btn btn-primary pwd-submit" :disabled="pwdSaving">
        {{ pwdSaving ? '提交中...' : '确认修改' }}
      </button>
    </form>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

defineProps({
  // 是否处于强制改密（首次登录改初始密码）：展示高亮提示
  mustChange: { type: Boolean, default: false },
})

const router = useRouter()
const userStore = useUserStore()

const passwordForm = ref({ oldPassword: '', newPassword: '' })
const pwdSaving = ref(false)
const pwdMsg = ref('')

// 与后端密码策略保持一致：6–128 位
const PASSWORD_MIN_LEN = 6
const PASSWORD_MAX_LEN = 128

async function submitPassword() {
  pwdMsg.value = ''
  const { oldPassword, newPassword } = passwordForm.value
  if (!oldPassword || !newPassword) {
    pwdMsg.value = '请填写当前密码与新密码'
    return
  }
  if (newPassword.length < PASSWORD_MIN_LEN || newPassword.length > PASSWORD_MAX_LEN) {
    pwdMsg.value = `新密码长度需 ${PASSWORD_MIN_LEN}–${PASSWORD_MAX_LEN} 位`
    return
  }
  if (oldPassword === newPassword) {
    pwdMsg.value = '新密码不能与当前密码相同'
    return
  }
  pwdSaving.value = true
  try {
    await userStore.changePassword({
      oldPassword: passwordForm.value.oldPassword,
      newPassword: passwordForm.value.newPassword,
    })
    // 后端会吊销当前 token；跳登录页提示用新密码
    await router.replace({ path: '/login', query: { message: '密码已修改，请用新密码登录' } })
  } catch (e) {
    pwdMsg.value = e?.message || '修改失败'
  } finally {
    pwdSaving.value = false
  }
}
</script>

<style scoped>
/* 密码修改 */
.password-card {
  max-width: 520px;
  margin: 0 auto;
}

.password-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.password-hint {
  margin: 0 0 6px 0;
  line-height: 1.6;
}

.password-form .form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.password-form .form-group label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.password-form .form-group input {
  height: 40px;
  padding: 0 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.password-form .form-group input:focus {
  border-color: var(--color-blue);
  box-shadow: 0 0 0 3px rgba(var(--color-blue-rgb), 0.15);
}

.password-form .form-group input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-msg {
  font-size: 13px;
  line-height: 1.5;
}

.form-msg-error {
  color: var(--color-red);
  background: rgba(var(--color-red-rgb), 0.12);
  border: 1px solid rgba(var(--color-red-rgb), 0.3);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
}

.pwd-submit {
  margin-top: 6px;
  min-width: 140px;
}
</style>

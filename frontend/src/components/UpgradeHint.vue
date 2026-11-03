<template>
  <div class="upgrade-hint" :class="{ inline }">
    <span class="lock-icon">🔒</span>
    <span class="hint-text">{{ text }}</span>
    <router-link to="/profile" class="upgrade-link">查看订阅</router-link>
  </div>
</template>

<script setup>
defineProps({
  text: { type: String, default: '该内容需要更高等级订阅' },
  inline: { type: Boolean, default: false },
})
</script>

<style scoped>
.upgrade-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--radius-sm, 6px);
  background: rgba(var(--color-gold-rgb), 0.08);
  border: 1px solid rgba(var(--color-gold-rgb), 0.25);
  font-size: 12px;
  color: var(--color-gold, #ffd700);
}
.upgrade-hint.inline {
  display: inline-flex;
  padding: 4px 10px;
}
.lock-icon { font-size: 13px; }
.hint-text { flex: 1; color: var(--text-secondary); }
.upgrade-link {
  color: var(--color-gold, #ffd700);
  text-decoration: none;
  font-weight: 600;
  white-space: nowrap;
}
.upgrade-link:hover { text-decoration: underline; }
</style>

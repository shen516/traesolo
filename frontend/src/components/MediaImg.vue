<template>
  <img
    v-if="resolved && !failed"
    :src="resolved"
    :alt="alt"
    class="media-img"
    :class="[imgClass, sizeClass]"
    @error="failed = true"
  />
  <span v-else class="media-fallback" :class="[imgClass, sizeClass]">{{ fallback }}</span>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { isMediaSrc, mediaUrl } from '@/utils/media'

const props = defineProps({
  src: { type: String, default: '' },
  fallback: { type: String, default: '⚽' },
  alt: { type: String, default: '' },
  imgClass: { type: String, default: '' },
  size: { type: String, default: 'md' }
})

const failed = ref(false)
const resolved = computed(() => (isMediaSrc(props.src) ? mediaUrl(props.src) : ''))
const sizeClass = computed(() => `size-${props.size}`)

watch(() => props.src, () => {
  failed.value = false
})
</script>

<style scoped>
.media-img {
  object-fit: contain;
  display: inline-block;
  vertical-align: middle;
  flex-shrink: 0;
  background: var(--logo-plate, #f3f6fb);
  border-radius: 8px;
  padding: 3px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08);
}

.media-fallback {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  flex-shrink: 0;
}

.size-xs { width: 22px; height: 22px; font-size: 14px; border-radius: 5px; padding: 2px; }
.size-sm { width: 36px; height: 36px; font-size: 22px; }
.size-md { width: 48px; height: 48px; font-size: 32px; }
.size-lg { width: 64px; height: 64px; font-size: 48px; padding: 5px; }
.size-xl { width: 88px; height: 88px; font-size: 64px; padding: 6px; border-radius: 12px; }
</style>

<template>
  <span class="badge" :class="[level, { negative: cents < 0 }]">
    <span class="badge-dot"></span>
    <span class="badge-val">¥{{ formatCents(cents) }}</span>
    <span v-if="bonusCents > 0" class="cash-hint">
      （押金 ¥{{ formatCents(depositCents) }}）
    </span>
  </span>
</template>

<script setup lang="ts">
import { formatCents } from '@/utils/money'

withDefaults(
  defineProps<{
    cents: number
    depositCents?: number
    bonusCents?: number
    level: 'low' | 'warn' | 'safe' | string
  }>(),
  { depositCents: 0, bonusCents: 0 },
)
</script>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  font-size: 13.5px;
  line-height: 1.3;
}

.badge-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex: none;
  opacity: 0.85;
}

.badge.low {
  color: var(--el-color-danger);
}

.badge.warn {
  color: var(--el-color-warning);
}

.badge.safe {
  color: var(--el-color-success);
}

.badge.negative {
  padding: 2px 7px;
  border-radius: 6px;
  background: var(--app-danger-soft);
  color: var(--el-color-danger);
}

.cash-hint {
  font-size: 11.5px;
  font-weight: 400;
  color: var(--app-text-muted);
}
</style>

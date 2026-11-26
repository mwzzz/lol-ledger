<template>
  <nav v-if="!auth.isSuperadmin" class="bottom-nav">
    <button
      v-for="item in items"
      :key="item.name"
      type="button"
      class="bottom-item"
      :class="{ active: isActive(item.name) }"
      @click="router.push({ name: item.name })"
    >
      <span class="icon-wrap">
        <el-icon><component :is="item.icon" /></el-icon>
      </span>
      <span>{{ item.label }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { DataAnalysis, MagicStick, TrendCharts, User } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const items = [
  { name: 'pos', label: '玩家库', icon: User },
  { name: 'dashboard', label: '看板', icon: DataAnalysis },
  { name: 'reports', label: '账本', icon: TrendCharts },
  { name: 'tools', label: '小工具', icon: MagicStick },
]

function isActive(name: string): boolean {
  if (name === 'tools') return route.path.startsWith('/tools')
  return route.name === name
}
</script>

<style scoped>
.bottom-nav {
  display: none;
}

@media (max-width: 768px) {
  .bottom-nav {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 30;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    padding: 6px 6px calc(6px + env(safe-area-inset-bottom));
    background: var(--app-bg-panel-glass);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-top: 1px solid var(--app-border);
  }

  .bottom-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 4px 0;
    border: none;
    background: transparent;
    font: inherit;
    font-size: 11px;
    color: var(--app-text-muted);
    border-radius: 8px;
    cursor: pointer;
  }

  .icon-wrap {
    position: relative;
    display: inline-grid;
    place-items: center;
  }

  .bottom-item .el-icon {
    font-size: 19px;
  }

  .nav-badge {
    position: absolute;
    top: -4px;
    right: -10px;
    min-width: 15px;
    height: 15px;
    padding: 0 3px;
    border-radius: 999px;
    background: var(--app-primary);
    color: var(--app-on-primary);
    font-size: 10px;
    font-weight: 700;
    line-height: 15px;
  }

  .bottom-item.active {
    color: var(--app-primary);
    font-weight: 650;
  }
}
</style>

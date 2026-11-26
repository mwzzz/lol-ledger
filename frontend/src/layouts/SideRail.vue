<template>
  <aside class="side-rail desktop-only">
    <button
      type="button"
      class="rail-brand"
      :title="auth.isSuperadmin ? 'LOL 平台管理' : 'LOL 玩家库'"
      @click="router.push(auth.isSuperadmin ? '/platform' : '/')"
    >
      <span class="rail-mark">L</span>
    </button>

    <nav class="rail-nav" aria-label="主导航">
      <button
        v-for="item in navs"
        :key="item.name"
        type="button"
        class="rail-item"
        :class="{ active: isActive(item.name) }"
        @click="router.push({ name: item.name })"
      >
        <span class="rail-icon-wrap">
          <el-icon><component :is="item.icon" /></el-icon>
        </span>
        <span class="rail-label">{{ item.label }}</span>
      </button>
    </nav>

    <div class="rail-foot">
      <el-tooltip content="更新日志" placement="right">
        <button
          type="button"
          class="rail-tool"
          aria-label="更新日志"
          @click="app.changelogVisible = true"
        >
          <el-icon><Memo /></el-icon>
        </button>
      </el-tooltip>

      <ThemePicker placement="right-end">
        <template #default="{ current }">
          <button
            type="button"
            class="rail-tool"
            :title="`切换主题（当前：${current.label}）`"
            aria-label="切换主题"
          >
            <span
              class="rail-theme-dot"
              :style="{
                background: `linear-gradient(135deg, ${current.swatchBg} 50%, ${current.swatchAccent} 50%)`,
              }"
            ></span>
          </button>
        </template>
      </ThemePicker>

      <el-dropdown trigger="click" placement="right-end" @command="onUserCommand">
        <button type="button" class="rail-avatar" :title="auth.displayName || '当前账号'">
          <span>{{ avatarChar }}</span>
          <span class="online-dot"></span>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <span class="acct-head">{{ auth.displayName }}（{{ auth.isAdmin ? '店长' : auth.isSuperadmin ? '开发者' : '店员' }}）</span>
            </el-dropdown-item>
            <el-dropdown-item command="password" divided>修改密码</el-dropdown-item>
            <el-dropdown-item command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {
  DataAnalysis,
  MagicStick,
  Memo,
  Setting,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ThemePicker from '@/components/common/ThemePicker.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const app = useAppStore()

const navs = computed(() =>
  auth.isSuperadmin
    ? [{ name: 'platform', label: '平台', icon: Setting }]
    : [
        { name: 'pos', label: '玩家库', icon: User },
        { name: 'dashboard', label: '看板', icon: DataAnalysis },
        { name: 'reports', label: '账本', icon: TrendCharts },
        { name: 'tools', label: '工具', icon: MagicStick },
        { name: 'settings', label: '设置', icon: Setting },
      ],
)

const avatarChar = computed(() => {
  const name = (auth.displayName || '用').trim()
  return name.slice(0, 1).toUpperCase()
})

function isActive(name: string): boolean {
  if (name === 'tools') {
    return route.path.startsWith('/tools')
  }
  return route.name === name
}

async function onUserCommand(command: string) {
  if (command === 'password') {
    app.passwordDialogVisible = true
    return
  }
  if (command === 'logout') {
    await auth.logout()
    router.replace({ name: 'login' })
  }
}
</script>

<style scoped>
.side-rail {
  width: 72px;
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 8px;
  background: var(--app-bg-rail);
  border-right: 1px solid var(--app-border);
  position: sticky;
  top: 0;
  height: 100vh;
  z-index: 30;
  user-select: none;
}

.rail-brand {
  width: 40px;
  height: 40px;
  padding: 0;
  margin-bottom: 14px;
  border: none;
  border-radius: 11px;
  background: var(--app-brand-gradient);
  color: var(--app-on-primary);
  display: grid;
  place-items: center;
  cursor: pointer;
  box-shadow: 0 4px 14px var(--app-primary-ring);
  transition: transform 0.15s ease;
}

.rail-brand:hover {
  transform: translateY(-1px);
}

.rail-mark {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.rail-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  flex: 1;
}

.rail-item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  padding: 9px 4px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--app-text-muted);
  font: inherit;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.rail-item:hover {
  background: var(--app-bg-hover);
  color: var(--app-text-main);
}

.rail-item.active {
  background: var(--app-bg-active);
  border-color: var(--app-primary-ring);
  color: var(--app-primary);
}

.rail-item.active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 14px;
  bottom: 14px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--app-primary);
}

.rail-icon-wrap {
  position: relative;
  display: inline-grid;
  place-items: center;
  font-size: 19px;
}

.rail-badge {
  position: absolute;
  top: -6px;
  right: -10px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--app-primary);
  color: var(--app-on-primary);
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  font-variant-numeric: tabular-nums;
}

.rail-theme-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1.5px solid var(--app-border-strong);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14);
}

.rail-label {
  font-size: 11.5px;
  font-weight: 500;
  line-height: 1.1;
}

.rail-item.active .rail-label {
  font-weight: 650;
}

.rail-foot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--app-border);
  width: 100%;
}

.rail-tool {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--app-text-muted);
  display: grid;
  place-items: center;
  font-size: 17px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.rail-tool:hover {
  background: var(--app-bg-hover);
  color: var(--app-text-main);
}

.rail-avatar {
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid var(--app-border-strong);
  background: var(--app-bg-subtle);
  color: var(--app-text-main);
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  display: grid;
  place-items: center;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s ease;
}

.rail-avatar:hover {
  border-color: var(--app-primary);
}

.online-dot {
  position: absolute;
  right: -2px;
  bottom: -2px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--el-color-success);
  border: 2px solid var(--app-bg-rail);
}

.acct-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-main);
}
</style>

<template>
  <div class="login-wrap">
    <button
      type="button"
      class="theme-switch"
      :title="app.theme === 'dark' ? '切换亮色模式' : '切换暗色模式'"
      @click="app.toggleTheme()"
    >
      <el-icon>
        <Sunny v-if="app.theme === 'dark'" />
        <Moon v-else />
      </el-icon>
      <span>{{ app.theme === 'dark' ? '亮色' : '暗色' }}</span>
    </button>

    <div class="login-card">
      <div class="brand">
        <span class="brand-mark">L</span>
        <div>
          <div class="brand-title">LOL 门店收银台</div>
          <div class="brand-sub">快速收退押金 · 5v5 组局扣费 · 经营对账</div>
        </div>
      </div>

      <el-form class="form" @submit.prevent="submit">
        <el-form-item>
          <el-input
            v-model="username"
            size="large"
            placeholder="用户名"
            autocomplete="username"
            :prefix-icon="User"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="password"
            size="large"
            type="password"
            placeholder="密码"
            show-password
            autocomplete="current-password"
            :prefix-icon="Lock"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button class="submit" type="primary" size="large" :loading="loading" @click="submit">
          进入收银台
        </el-button>
      </el-form>

      <div class="foot">门店账号由店长分配，忘记密码请联系店长重置。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Lock, Moon, Sunny, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const app = useAppStore()

const username = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    if (auth.isSuperadmin) {
      router.replace({ name: 'platform' })
      return
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.replace(redirect)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  background:
    radial-gradient(960px 520px at 50% -12%, var(--app-primary-soft), transparent 62%),
    var(--app-bg-canvas);
  padding: 24px;
}

.theme-switch {
  position: absolute;
  top: 20px;
  right: 24px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 11px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-bg-panel);
  color: var(--app-text-muted);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.14s ease, color 0.14s ease;
}

.theme-switch:hover {
  border-color: var(--app-border-strong);
  color: var(--app-text-main);
}

.login-card {
  width: min(396px, 100%);
  padding: 34px 32px 26px;
  background: var(--app-bg-panel);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  box-shadow: var(--app-shadow), var(--app-panel-highlight);
}

.brand {
  display: flex;
  align-items: center;
  gap: 13px;
  margin-bottom: 28px;
}

.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 11px;
  background: linear-gradient(135deg, var(--app-primary), #2563eb);
  color: #ffffff;
  font-size: 20px;
  font-weight: 800;
  display: grid;
  place-items: center;
  box-shadow: 0 4px 14px var(--app-primary-ring);
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.015em;
}

.brand-sub {
  margin-top: 3px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.submit {
  width: 100%;
  margin-top: 4px;
  font-weight: 650;
}

.foot {
  margin-top: 20px;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.6;
}
</style>

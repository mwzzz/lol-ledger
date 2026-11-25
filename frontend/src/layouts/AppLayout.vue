<template>
  <div class="pos-shell">
    <SideRail />
    <div class="pos-body">
      <PosHeader />
      <main class="pos-main">
        <router-view />
      </main>
    </div>
    <BottomNav />

    <!-- 全局更新日志抽屉 -->
    <el-drawer v-model="app.changelogVisible" title="更新日志" size="min(440px, 92vw)">
      <div class="changelog">
        <section v-for="entry in CHANGELOG" :key="entry.date" class="log-entry">
          <div class="log-head">
            <span class="log-date">{{ entry.date }}</span>
            <span v-if="entry.version" class="log-version">{{ entry.version }}</span>
          </div>
          <div v-for="group in entry.groups" :key="group.title" class="log-group">
            <div class="log-group-title">{{ group.title }}</div>
            <ul class="log-list">
              <li v-for="item in group.items" :key="item">{{ item }}</li>
            </ul>
          </div>
        </section>
      </div>
    </el-drawer>

    <!-- 全局修改密码弹窗 -->
    <el-dialog
      v-model="app.passwordDialogVisible"
      title="修改密码"
      width="420px"
      :close-on-click-modal="false"
    >
      <el-form label-width="86px">
        <el-form-item label="原密码">
          <el-input v-model="pwd.old" type="password" show-password autocomplete="off" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwd.next" type="password" show-password autocomplete="off" />
        </el-form-item>
        <el-form-item label="再输一次">
          <el-input
            v-model="pwd.confirm"
            type="password"
            show-password
            autocomplete="off"
            @keyup.enter="submitPassword"
          />
        </el-form-item>
        <div class="pwd-hint">至少 8 位，包含字母和数字。改完需要重新登录。</div>
      </el-form>
      <template #footer>
        <el-button @click="app.passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPwd" @click="submitPassword">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { authApi } from '@/api'
import { CHANGELOG } from '@/data/changelog'
import BottomNav from '@/layouts/BottomNav.vue'
import PosHeader from '@/layouts/PosHeader.vue'
import SideRail from '@/layouts/SideRail.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useSessionDraftStore } from '@/stores/sessionDraft'

const router = useRouter()
const route = useRoute()
const app = useAppStore()
const auth = useAuthStore()
const draft = useSessionDraftStore()

const savingPwd = ref(false)
const pwd = reactive({ old: '', next: '', confirm: '' })

watch(
  () => app.passwordDialogVisible,
  (visible) => {
    if (visible) {
      pwd.old = ''
      pwd.next = ''
      pwd.confirm = ''
    }
  },
)

async function submitPassword() {
  if (pwd.next.length < 8) {
    ElMessage.warning('新密码至少 8 位')
    return
  }
  if (pwd.next !== pwd.confirm) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  savingPwd.value = true
  try {
    await authApi.changePassword(pwd.old, pwd.next)
    ElMessage.success('密码已修改，请重新登录')
    app.passwordDialogVisible = false
    draft.resetAll()
    auth.reset()
    router.replace({ name: 'login' })
  } finally {
    savingPwd.value = false
  }
}

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  return Boolean(el?.closest('input, textarea, select, [contenteditable="true"]'))
}

function onGlobalKeydown(event: KeyboardEvent) {
  if (auth.isSuperadmin) return
  if (document.querySelector('.el-overlay:not([style*="display: none"])')) return

  // Ctrl+K 或 非输入框下的 '/' 聚焦玩家搜索
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    if (route.name !== 'pos') {
      void router.push({ name: 'pos' }).then(() => app.requestFocusSearch())
    } else {
      app.requestFocusSearch()
    }
    return
  }

  if (isEditableTarget(event.target)) return

  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    if (route.name !== 'pos') {
      void router.push({ name: 'pos' }).then(() => app.requestFocusSearch())
    } else {
      app.requestFocusSearch()
    }
    return
  }

  if (event.key.toLowerCase() === 'n' && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    if (route.name !== 'pos') {
      void router.push({ name: 'pos' }).then(() => app.requestFocusDock())
    } else {
      app.requestFocusDock()
    }
  }
}

onMounted(() => {
  app.applyTheme()
  window.addEventListener('keydown', onGlobalKeydown)
  if (!auth.isSuperadmin) {
    void app.refreshToday()
    void app.refreshMyShift()
    void draft.loadMeta()
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
})

watch(
  () => route.fullPath,
  () => {
    if (!auth.isSuperadmin) {
      void app.refreshToday()
    }
  },
)

watch(
  () => auth.user?.id,
  () => {
    if (!auth.isSuperadmin && auth.user) {
      void app.refreshMyShift()
      void draft.loadMeta(true)
    }
  },
)
</script>

<style scoped>
.pos-shell {
  min-height: 100vh;
  display: flex;
  background: var(--app-bg-canvas);
}

.pos-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.pos-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.pwd-hint {
  margin-left: 86px;
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.6;
}

.changelog {
  padding-bottom: 8px;
}

.log-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.log-date {
  font-size: 15px;
  font-weight: 600;
}

.log-version {
  padding: 1px 8px;
  border: 1px solid var(--app-primary-ring);
  border-radius: 999px;
  background: var(--app-primary-soft);
  font-size: 11px;
  color: var(--app-primary);
}

.log-group {
  margin-bottom: 14px;
}

.log-group-title {
  margin-bottom: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--app-text-main);
}

.log-list {
  margin: 0;
  padding-left: 18px;
  color: var(--el-text-color-regular);
  font-size: 12.5px;
  line-height: 1.85;
}

.log-list li::marker {
  color: var(--app-primary);
}

@media (max-width: 768px) {
  .pos-main {
    padding-bottom: 64px;
  }
}
</style>

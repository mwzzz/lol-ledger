<template>
  <header class="pos-header">
    <div class="ph-left">
      <button
        type="button"
        class="mobile-brand mobile-only"
        @click="router.push(auth.isSuperadmin ? '/platform' : '/')"
      >
        L
      </button>

      <span v-if="auth.isSuperadmin" class="shop-pill dev">开发者平台</span>
      <span v-else class="shop-pill">{{ auth.merchantName || '本店收银台' }}</span>

      <template v-if="!auth.isSuperadmin">
        <span class="ph-divider desktop-only"></span>
        <div class="today-brief">
          <span class="live-dot"></span>
          <template v-if="app.todayError">
            <span class="err-text">今日数据不可用</span>
            <el-button link type="primary" size="small" @click="app.refreshToday()">重试</el-button>
          </template>
          <template v-else-if="app.todayLoading && !app.today">
            <span class="muted">同步中…</span>
          </template>
          <template v-else-if="app.today">
            <span class="muted">今日</span>
            <b>{{ app.today.session_count }} 局</b>
            <span class="dot-sep">·</span>
            <span>茶水 <b class="val-in">¥{{ formatCents(app.today.tea_cents) }}</b></span>
            <span class="dot-sep desktop-only">·</span>
            <span class="muted desktop-only">
              收 ¥{{ formatCents(app.today.add_deposit_cents) }} / 退 ¥{{ formatCents(app.today.refund_cents) }}
            </span>
          </template>
          <template v-else>
            <span class="muted">今日暂未开局</span>
          </template>
        </div>
      </template>
    </div>

    <div class="ph-right">
      <div v-if="!auth.isSuperadmin" class="shortcut-hints desktop-only">
        <button type="button" class="hint-chip" @click="triggerSearch">
          <kbd class="pos-kbd">/</kbd>
          <span>搜玩家</span>
        </button>
        <button v-if="route.name !== 'pos'" type="button" class="hint-chip primary" @click="triggerGroup">
          <kbd class="pos-kbd">N</kbd>
          <span>去组局</span>
          <span v-if="draft.filledCount > 0" class="chip-count">{{ draft.filledCount }}</span>
        </button>
      </div>

      <div v-if="!auth.isSuperadmin" class="shift-zone">
        <template v-if="!app.clockedIn">
          <el-tooltip content="打卡后实时统计你本班的场次、茶水、差额与分红" placement="bottom">
            <button type="button" class="clock-btn" @click="onClockIn">
              <el-icon><AlarmClock /></el-icon>
              <span>上班打卡</span>
            </button>
          </el-tooltip>
        </template>
        <template v-else>
          <el-tooltip placement="bottom-end">
            <template #content>
              <div class="shift-tip">
                <div>本班开始：{{ app.shiftStartText ? formatClock(app.shiftStartText) : '--' }}</div>
                <div>
                  人次 {{ app.myShift?.player_times ?? 0 }} · 收押金 ¥{{ formatCents(app.myShift?.add_deposit_cents ?? 0) }} ·
                  退押金 ¥{{ formatCents(app.myShift?.refund_cents ?? 0) }}
                </div>
                <div v-if="app.shiftStale" class="tip-warn">
                  打卡已超过 24 小时，仅统计最近 24 小时，建议重新打卡
                </div>
              </div>
            </template>
            <div class="my-shift-pill">
              <span class="ms-title">
                本班
                <span class="muted">{{ app.shiftStartText ? formatClock(app.shiftStartText) : '--' }}</span>
              </span>
              <span v-if="app.shiftStale" class="stale-badge">!</span>
              <span><b>{{ app.myShift?.session_count ?? 0 }}</b> 局</span>
              <span class="dot-sep">·</span>
              <span>茶水 <b>¥{{ formatCents(app.myShift?.tea_cents ?? 0) }}</b></span>
              <span class="dot-sep">·</span>
              <span>
                差额
                <b :class="(app.myShift?.cash_diff_cents ?? 0) < 0 ? 'val-out' : 'val-in'">
                  ¥{{ formatCents(app.myShift?.cash_diff_cents ?? 0) }}
                </b>
              </span>
              <span class="dot-sep desktop-only">·</span>
              <span class="desktop-only">
                分红 <b class="val-div">¥{{ formatCents(app.myShift?.dividend_cents ?? 0) }}</b>
              </span>
            </div>
          </el-tooltip>
          <button type="button" class="mini-action" @click="onClockIn">重打</button>
          <button
            type="button"
            class="mini-action icon"
            title="刷新本班数据"
            @click="app.refreshMyShift()"
          >
            <el-icon :class="{ 'is-loading': app.myShiftLoading }"><Refresh /></el-icon>
          </button>
        </template>
      </div>

      <!-- 移动端账号菜单（桌面端在左侧 SideRail 底部） -->
      <el-dropdown trigger="click" class="mobile-user mobile-only" @command="onMobileCommand">
        <button type="button" class="m-avatar">
          {{ (auth.displayName || '用').slice(0, 1) }}
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-if="!auth.isSuperadmin" command="settings">店铺设置</el-dropdown-item>
            <el-dropdown-item command="theme">
              {{ app.theme === 'dark' ? '切换到亮色' : '切换到暗色' }}
            </el-dropdown-item>
            <el-dropdown-item command="changelog">更新日志</el-dropdown-item>
            <el-dropdown-item command="password" divided>修改密码</el-dropdown-item>
            <el-dropdown-item command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup lang="ts">
import { AlarmClock, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useSessionDraftStore } from '@/stores/sessionDraft'
import { formatClock } from '@/utils/datetime'
import { formatCents } from '@/utils/money'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const app = useAppStore()
const draft = useSessionDraftStore()

function onClockIn() {
  app.clockIn()
  ElMessage.success('已更新本班打卡时间')
}

function triggerSearch() {
  if (route.name !== 'pos') {
    void router.push({ name: 'pos' }).then(() => app.requestFocusSearch())
  } else {
    app.requestFocusSearch()
  }
}

function triggerGroup() {
  void router.push({ name: 'pos' }).then(() => app.requestFocusDock())
}

async function onMobileCommand(cmd: string) {
  if (cmd === 'settings') router.push({ name: 'settings' })
  else if (cmd === 'theme') app.toggleTheme()
  else if (cmd === 'changelog') app.changelogVisible = true
  else if (cmd === 'password') app.passwordDialogVisible = true
  else if (cmd === 'logout') {
    draft.resetAll()
    await auth.logout()
    router.replace({ name: 'login' })
  }
}
</script>

<style scoped>
.pos-header {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 5px 18px;
  background: var(--app-bg-panel-glass);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--app-border);
  position: sticky;
  top: 0;
  z-index: 25;
  font-size: 12.5px;
}

.ph-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.mobile-brand {
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 7px;
  background: var(--app-primary);
  color: #ffffff;
  font-weight: 800;
  font-size: 13px;
  cursor: pointer;
}

.shop-pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 9px;
  border-radius: 6px;
  background: var(--app-primary-soft);
  color: var(--app-primary);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.shop-pill.dev {
  background: var(--app-warning-soft);
  color: var(--el-color-warning);
}

.ph-divider {
  width: 1px;
  height: 14px;
  background: var(--app-border-strong);
}

.today-brief {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  white-space: nowrap;
}

.today-brief b,
.my-shift-pill b {
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-success);
  box-shadow: 0 0 0 3px var(--app-success-soft);
  flex: none;
}

.dot-sep {
  color: var(--app-border-strong);
}

.val-in {
  color: var(--el-color-success);
}

.val-out,
.err-text {
  color: var(--el-color-danger);
}

.val-div {
  color: var(--app-primary);
}

.ph-right {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
  flex: none;
}

.shortcut-hints {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.hint-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 8px;
  border-radius: 7px;
  border: 1px solid var(--app-border);
  background: var(--app-bg-subtle);
  color: var(--app-text-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.14s ease, color 0.14s ease;
}

.hint-chip:hover {
  border-color: var(--app-border-strong);
  color: var(--app-text-main);
}

.hint-chip.primary {
  border-color: var(--app-primary-ring);
  background: var(--app-primary-soft);
  color: var(--app-primary);
  font-weight: 600;
}

.chip-count {
  padding: 0 5px;
  border-radius: 999px;
  background: var(--app-primary);
  color: #fff;
  font-size: 11px;
  line-height: 16px;
}

.shift-zone {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.clock-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 10px;
  border-radius: 7px;
  border: 1px solid var(--app-primary-ring);
  background: var(--app-primary-soft);
  color: var(--app-primary);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.14s ease;
}

.clock-btn:hover {
  background: var(--app-bg-active);
}

.my-shift-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border);
  font-size: 12px;
}

.ms-title {
  font-weight: 600;
  color: var(--app-text-main);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.stale-badge {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--el-color-warning);
  color: #111;
  font-size: 10px;
  font-weight: 700;
  display: inline-grid;
  place-items: center;
}

.mini-action {
  height: 24px;
  padding: 0 6px;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--app-text-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.mini-action:hover {
  background: var(--app-bg-hover);
  color: var(--app-primary);
}

.mini-action.icon {
  display: inline-grid;
  place-items: center;
  width: 24px;
  padding: 0;
}

.shift-tip {
  font-size: 12px;
  line-height: 1.6;
}

.tip-warn {
  color: var(--el-color-warning);
  margin-top: 2px;
}

.m-avatar {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid var(--app-border-strong);
  background: var(--app-bg-subtle);
  color: var(--app-text-main);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

@media (max-width: 768px) {
  .pos-header {
    padding: 6px 12px;
    flex-wrap: wrap;
    row-gap: 6px;
  }

  .ph-right {
    width: 100%;
    justify-content: space-between;
    margin-left: 0;
  }

  .shift-zone {
    flex: 1;
    min-width: 0;
  }

  .my-shift-pill {
    max-width: 100%;
    overflow-x: auto;
    white-space: nowrap;
  }
}
</style>

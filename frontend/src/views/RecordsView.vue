<template>
  <div class="page" :class="{ embedded }">
    <div v-if="!embedded" class="page-head">
      <span class="page-title">记录管理</span>
      <span class="page-sub">押金变动与场次流水，最新在前</span>
    </div>

    <div class="toolbar">
      <div class="mode-seg" role="group" aria-label="记录类型">
        <button
          type="button"
          class="seg-btn"
          :class="{ active: tab === 'deposits' }"
          @click="switchTab('deposits')"
        >
          押金记录
        </button>
        <button
          type="button"
          class="seg-btn"
          :class="{ active: tab === 'sessions' }"
          @click="switchTab('sessions')"
        >
          场次记录
        </button>
      </div>

      <el-input
        v-model="keyword"
        placeholder="搜索玩家名或场次名"
        clearable
        style="width: 220px"
        @keyup.enter="reload"
        @clear="reload"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>

      <el-date-picker
        v-model="dateRange"
        type="datetimerange"
        value-format="YYYY-MM-DDTHH:mm:ss"
        format="MM-DD HH:mm:ss"
        start-placeholder="开始时间"
        end-placeholder="结束时间"
        :shortcuts="shortcuts"
        style="width: 320px"
        @change="reload"
      />

      <el-select v-if="tab === 'deposits'" v-model="reason" placeholder="全部原因" style="width: 150px" @change="reload">
        <el-option label="全部原因" value="" />
        <el-option label="正常扣押" value="normal_deduct" />
        <el-option label="撤回局退茶水" value="session_void" />
        <el-option label="加押金" value="add_deposit" />
        <el-option label="加赠金" value="add_bonus" />
        <el-option label="撤销加赠金" value="bonus_void" />
        <el-option label="退押金" value="refund" />
        <el-option label="划押转出" value="transfer_out" />
        <el-option label="划押转入" value="transfer_in" />
      </el-select>

      <el-select
        v-model="operatorId"
        placeholder="全部操作人"
        clearable
        style="width: 160px"
        @change="reload"
      >
        <el-option v-for="op in operators" :key="op.id" :label="op.display_name" :value="op.id">
          {{ op.display_name }}
          <span class="muted small">
            {{ op.username }}{{ op.is_active ? '' : '（已停用）' }}
          </span>
        </el-option>
      </el-select>

      <el-button :icon="Refresh" @click="reload">刷新</el-button>
      <div class="spacer"></div>
      <span class="muted small">共 {{ total }} 条</span>
    </div>

    <div v-if="tab === 'deposits' && operatorId && cashSummary" class="cash-summary">
      <span>操作人：<b>{{ cashSummary.operator?.display_name || '-' }}</b></span>
      <span>收押金 <b>¥{{ formatCents(cashSummary.add_deposit_cents) }}</b></span>
      <span>退押金 <b>¥{{ formatCents(cashSummary.refund_cents) }}</b></span>
      <span :class="cashSummary.cash_diff_cents < 0 ? 'diff-out' : 'diff-in'">
        差额 <b>¥{{ formatCents(cashSummary.cash_diff_cents) }}</b>
      </span>
      <span class="muted small">
        {{ cashSummary.cash_diff_cents < 0 ? '店长应补' : '店员应交' }}，按当前时间范围统计
      </span>
    </div>

    <template v-if="tab === 'deposits'">
        <div class="panel desktop-only">
          <el-table v-loading="loading" :data="entries">
            <el-table-column label="时间" width="168">
              <template #default="{ row }">
                <span class="muted nowrap">{{ formatFull(row.created_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="玩家" min-width="150">
              <template #default="{ row }">
                <span class="cell-main">{{ row.player.game_id }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动金额" width="120" align="right">
              <template #default="{ row }">
                <MoneyText :cents="row.signed_amount_cents" change />
              </template>
            </el-table-column>
            <el-table-column label="变动后余额" width="140" align="right">
              <template #default="{ row }">
                <span class="mono muted">¥{{ formatCents(row.balance_after_cents) }}</span>
                <div v-if="row.bonus_after_cents > 0" class="cell-sub">
                  赠金 ¥{{ formatCents(row.bonus_after_cents) }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="操作人" width="96">
              <template #default="{ row }">
                <span class="muted">{{ row.operator?.display_name || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="原因" min-width="200">
              <template #default="{ row }">
                <div class="cell-main">{{ row.reason_label }}</div>
                <div v-if="row.note" class="cell-sub">{{ row.note }}</div>
                <div v-if="row.bonus_amount_cents > 0" class="cell-sub">
                  其中赠金抵扣 ¥{{ formatCents(row.bonus_amount_cents) }}
                </div>
              </template>
            </el-table-column>
            <el-table-column label="场次" min-width="150">
              <template #default="{ row }">
                <span class="muted">{{ row.session?.name || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!loading && !entries.length" class="empty-hint">没有记录</div>
        </div>

        <div class="mobile-only">
          <div v-loading="loading" class="record-cards">
            <div v-for="row in entries" :key="row.id" class="record-card">
              <div class="record-card-head">
                <span class="cell-main">{{ row.player.game_id }}</span>
                <MoneyText :cents="row.signed_amount_cents" change />
              </div>
              <div class="cell-sub">
                {{ row.reason_label }}
                <template v-if="row.note"> · {{ row.note }}</template>
                <template v-if="row.bonus_amount_cents > 0">
                  · 赠金抵扣 ¥{{ formatCents(row.bonus_amount_cents) }}
                </template>
              </div>
              <div class="record-card-meta">
                <span>{{ formatFull(row.created_at) }}</span>
                <span class="mono">余额 ¥{{ formatCents(row.balance_after_cents) }}</span>
                <span v-if="row.bonus_after_cents > 0">
                  赠金 ¥{{ formatCents(row.bonus_after_cents) }}
                </span>
                <span>{{ row.operator?.display_name || '-' }}</span>
                <span v-if="row.session">{{ row.session.name }}</span>
              </div>
            </div>
            <div v-if="!loading && !entries.length" class="empty-hint">没有记录</div>
          </div>
        </div>
    </template>

    <template v-else>
        <div class="panel desktop-only">
          <el-table v-loading="loading" :data="sessions" :row-class-name="sessionRowClass">
            <el-table-column label="时间" width="140">
              <template #default="{ row }">
                <span class="muted nowrap">{{ formatShort(row.played_at) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="场次名" min-width="210">
              <template #default="{ row }">
                <div class="session-title-cell">
                  <span class="cell-main" :class="{ 'line-through': row.voided }">{{ row.name }}</span>
                  <el-tag v-if="row.voided" type="info" size="small" effect="plain">已撤回</el-tag>
                </div>
                <div v-if="row.voided" class="cell-sub">
                  {{ row.voided_by?.display_name || '-' }} 撤回于 {{ formatShort(row.voided_at) }}
                  <template v-if="row.void_note"> · {{ row.void_note }}</template>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="人数" width="80" align="right">
              <template #default="{ row }">
                <span class="mono">{{ row.player_count }}</span>
              </template>
            </el-table-column>
            <el-table-column label="茶水/人" width="110" align="right">
              <template #default="{ row }">
                <span class="mono">¥{{ formatCents(row.tea_fee_cents) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="茶水合计" width="120" align="right">
              <template #default="{ row }">
                <span class="mono" :class="{ 'line-through muted': row.voided }">
                  ¥{{ formatCents(row.tea_total_cents) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作人" width="100">
              <template #default="{ row }">
                <span class="muted">{{ row.operator?.display_name || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="玩家" min-width="260">
              <template #default="{ row }">
                <span class="muted players">{{ row.players.map((p: any) => p.game_id).join('、') }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="96" align="right">
              <template #default="{ row }">
                <el-button
                  v-if="row.voidable"
                  link
                  type="warning"
                  :disabled="submittingVoid || restoringId !== null"
                  @click="openVoidDialog(row)"
                >
                  撤回
                </el-button>
                <el-button
                  v-else-if="row.restorable"
                  link
                  type="primary"
                  :loading="restoringId === row.id"
                  :disabled="restoringId !== null || submittingVoid"
                  @click="restoreSession(row)"
                >
                  恢复
                </el-button>
                <span v-else-if="row.voided" class="muted small">已撤回</span>
                <span v-else-if="row.void_block_reason === 'salary_paid'" class="muted small">
                  已发薪
                </span>
                <span v-else-if="row.void_block_reason === 'player_deleted'" class="muted small">
                  含已删玩家
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!loading && !sessions.length" class="empty-hint">没有记录</div>
        </div>

        <div class="mobile-only">
          <div v-loading="loading" class="record-cards">
            <div
              v-for="row in sessions"
              :key="row.id"
              class="record-card"
              :class="{ 'is-voided-card': row.voided }"
            >
              <div class="record-card-head">
                <div class="session-title-cell">
                  <span class="cell-main" :class="{ 'line-through': row.voided }">{{ row.name }}</span>
                  <el-tag v-if="row.voided" type="info" size="small" effect="plain">已撤回</el-tag>
                </div>
                <span class="mono">{{ row.player_count }} 人</span>
              </div>
              <div class="cell-sub">
                茶水 ¥{{ formatCents(row.tea_fee_cents) }}/人 · 合计 ¥{{ formatCents(row.tea_total_cents) }}
              </div>
              <div class="record-card-meta">
                <span>{{ formatShort(row.played_at) }}</span>
                <span>操作人 {{ row.operator?.display_name || '-' }}</span>
              </div>
              <div class="record-card-players">{{ row.players.map((p) => p.game_id).join('、') }}</div>
              <div v-if="row.voided" class="cell-sub">
                {{ row.voided_by?.display_name || '-' }} 撤回于 {{ formatShort(row.voided_at) }}
                <template v-if="row.void_note"> · {{ row.void_note }}</template>
              </div>
              <div v-if="row.restorable" class="record-card-actions">
                <el-button
                  link
                  type="primary"
                  :loading="restoringId === row.id"
                  :disabled="restoringId !== null || submittingVoid"
                  @click="restoreSession(row)"
                >
                  恢复这一局
                </el-button>
              </div>
              <div v-else-if="!row.voided && row.voidable" class="record-card-actions">
                <el-button
                  link
                  type="warning"
                  :disabled="submittingVoid || restoringId !== null"
                  @click="openVoidDialog(row)"
                >
                  撤回这一局
                </el-button>
              </div>
              <div v-else-if="!row.voided && row.void_block_reason === 'salary_paid'" class="record-card-actions">
                <span class="muted small">已发薪（不可撤回）</span>
              </div>
            </div>
            <div v-if="!loading && !sessions.length" class="empty-hint">没有记录</div>
          </div>
        </div>
    </template>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="reload"
      />
    </div>

    <el-dialog
      v-model="voidDialogOpen"
      title="撤回这一局"
      width="440px"
      :close-on-click-modal="false"
      :close-on-press-escape="!submittingVoid"
      :show-close="!submittingVoid"
    >
      <div v-if="voidTarget" class="void-dialog-body" @keydown.enter.prevent>
        <p class="void-dialog-desc">
          确定撤回<b>「{{ voidTarget.name }}」</b>（原操作人：{{ voidTarget.operator?.display_name || '-' }}）？
          系统将为 {{ voidTarget.player_count }} 名玩家写一条「撤回局退茶水」冲正流水，原路退回押金/赠金（每人 ¥{{ formatCents(voidTarget.tea_fee_cents) }}）并局数 −1；不影响操作人差额。
        </p>
        <el-input
          v-model="voidNote"
          maxlength="200"
          placeholder="可选：填写撤回原因（留空可直接点下方确认）"
          :disabled="submittingVoid"
          @keydown.enter.prevent
        />
        <div class="void-dialog-hint muted small">为防止误触，请手动点击「确认撤回」（已禁用回车直接确认）。</div>
      </div>
      <template #footer>
        <el-button :disabled="submittingVoid" @click="voidDialogOpen = false">取消</el-button>
        <el-button type="warning" :loading="submittingVoid" @click="confirmVoidSession">
          确认撤回
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { recordApi, sessionApi } from '@/api'
import type { LedgerEntryRow, OperatorCashSummary, OperatorOption, SessionRow } from '@/api/types'
import MoneyText from '@/components/common/MoneyText.vue'
import { useAppStore } from '@/stores/app'
import { formatFull, formatShort, momentShortcuts } from '@/utils/datetime'
import { formatCents } from '@/utils/money'

const route = useRoute()
const app = useAppStore()

withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

const shortcuts = momentShortcuts()
const tab = ref<'deposits' | 'sessions'>('deposits')
const keyword = ref('')
const dateRange = ref<[string, string] | null>(null)
const reason = ref('')
const operatorId = ref<number | ''>('')
const operators = ref<OperatorOption[]>([])
const cashSummary = ref<OperatorCashSummary | null>(null)
const entries = ref<LedgerEntryRow[]>([])
const sessions = ref<SessionRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const voidDialogOpen = ref(false)
const voidTarget = ref<SessionRow | null>(null)
const voidNote = ref('')
const submittingVoid = ref(false)
const restoringId = ref<number | null>(null)

async function loadOperators() {
  try {
    operators.value = await recordApi.operators()
  } catch {
    operators.value = []
  }
}

async function loadCashSummary() {
  if (!operatorId.value) {
    cashSummary.value = null
    return
  }
  try {
    cashSummary.value = await recordApi.operatorSummary({
      operator_id: operatorId.value,
      date_from: dateRange.value?.[0],
      date_to: dateRange.value?.[1],
    })
  } catch {
    cashSummary.value = null
  }
}

async function load() {
  loading.value = true
  try {
    const common = {
      keyword: keyword.value.trim(),
      date_from: dateRange.value?.[0],
      date_to: dateRange.value?.[1],
      operator_id: operatorId.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    }
    if (tab.value === 'deposits') {
      const data = await recordApi.deposits({ ...common, reason: reason.value || undefined })
      entries.value = data.items
      total.value = data.total
      await loadCashSummary()
    } else {
      const data = await recordApi.sessions(common)
      sessions.value = data.items
      total.value = data.total
      cashSummary.value = null
    }
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
}

function sessionRowClass({ row }: { row: SessionRow }): string {
  return row.voided ? 'is-voided-row' : ''
}

function openVoidDialog(row: SessionRow) {
  if (submittingVoid.value || restoringId.value !== null) return
  voidTarget.value = row
  voidNote.value = ''
  voidDialogOpen.value = true
}

async function confirmVoidSession() {
  if (!voidTarget.value || submittingVoid.value) return
  const target = voidTarget.value
  submittingVoid.value = true
  try {
    await sessionApi.void(target.id, voidNote.value.trim())
    voidDialogOpen.value = false
    voidTarget.value = null
    voidNote.value = ''
    ElMessage.success('已撤回这一局，茶水已原路退回')
    await load()
    app.notifySessionCreated()
  } finally {
    submittingVoid.value = false
  }
}

async function restoreSession(row: SessionRow) {
  if (restoringId.value !== null || submittingVoid.value) return
  try {
    await ElMessageBox.confirm(
      `确定恢复「${row.name}」（原操作人：${row.operator?.display_name || '-'}）？` +
        `系统将为 ${row.player_count} 名玩家按原茶水（每人 ¥${formatCents(row.tea_fee_cents)}，先扣赠金再扣现金）重新扣费并局数 +1，` +
        `同时恢复原操作人的场次、茶水与分红归属。`,
      '恢复已撤回的场次',
      {
        confirmButtonText: '确认恢复',
        cancelButtonText: '取消',
        type: 'info',
      },
    )
  } catch {
    return
  }
  restoringId.value = row.id
  try {
    await sessionApi.restore(row.id)
    ElMessage.success(`已恢复「${row.name}」，茶水与操作人归属已还原`)
    await load()
    app.notifySessionCreated()
  } finally {
    restoringId.value = null
  }
}

function switchTab(next: 'deposits' | 'sessions') {
  if (tab.value === next) return
  tab.value = next
  reload()
}

watch(
  () => route.query.keyword,
  (value) => {
    const text = typeof value === 'string' ? value : ''
    if (text === keyword.value) return
    keyword.value = text
    reload()
  },
)

onMounted(() => {
  if (typeof route.query.keyword === 'string') keyword.value = route.query.keyword
  void loadOperators()
  load()
})
</script>

<style scoped>
.small {
  font-size: 12px;
}

.cash-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 18px;
  margin-bottom: 10px;
  padding: 10px 14px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-bg-panel);
  font-size: 12.5px;
}

.cash-summary b {
  font-variant-numeric: tabular-nums;
}

.diff-in {
  color: var(--el-color-success);
}

.diff-out {
  color: var(--el-color-warning);
}

.panel {
  padding: 2px 0 0;
}

.nowrap {
  white-space: nowrap;
}

.record-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.record-card {
  padding: 12px 14px;
  background: var(--app-bg-panel);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
}

.record-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 2px;
}

.record-card-head :deep(.amount) {
  font-weight: 600;
  white-space: nowrap;
}

.record-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.record-card-players {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--app-border);
  font-size: 12px;
  color: var(--app-text-muted);
  line-height: 1.6;
}

.record-card-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 6px;
}

.session-title-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.line-through {
  text-decoration: line-through;
}

.is-voided-card {
  opacity: 0.62;
}

:deep(.is-voided-row) {
  opacity: 0.62;
}

.players {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}

.void-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.void-dialog-desc {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.void-dialog-hint {
  margin-top: -2px;
}

.page.embedded {
  max-width: none;
  padding: 0;
}

.mode-seg {
  display: inline-flex;
  align-items: center;
  padding: 2px;
  border-radius: 8px;
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border);
  gap: 2px;
  flex: 0 0 auto;
}

.seg-btn {
  height: 26px;
  padding: 0 11px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--app-text-muted);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.seg-btn:hover {
  color: var(--el-text-color-primary);
}

.seg-btn.active {
  background: var(--app-bg-panel);
  color: var(--el-text-color-primary);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}
</style>

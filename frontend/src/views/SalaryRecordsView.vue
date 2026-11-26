<template>
  <div class="salary-records-view">
    <div class="toolbar">
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="工资日起"
        end-placeholder="工资日止"
        :shortcuts="shortcuts"
        clearable
        style="width: 260px"
        @change="reload"
      />

      <el-select
        v-model="userId"
        placeholder="全部店员"
        clearable
        style="width: 150px"
        @change="reload"
      >
        <el-option v-for="op in operators" :key="op.id" :label="op.display_name" :value="op.id">
          {{ op.display_name }}
          <span class="muted small">
            {{ op.username }}{{ op.is_active ? '' : '（已停用）' }}
          </span>
        </el-option>
      </el-select>

      <el-select v-model="status" style="width: 120px" @change="reload">
        <el-option label="全部状态" value="all" />
        <el-option label="已发放" value="live" />
        <el-option label="已撤销" value="voided" />
      </el-select>

      <el-button :icon="Refresh" :loading="loading" @click="reload">刷新</el-button>
      <div class="spacer"></div>
      <el-button type="primary" @click="router.push({ name: 'dashboard' })">
        去看板发工资
      </el-button>
    </div>

    <div class="summary-grid">
      <div class="summary">
        <span>已发放金额</span>
        <b class="good">¥{{ formatCents(summary.live_total_cents) }}</b>
      </div>
      <div class="summary">
        <span>发放批次</span>
        <b>{{ summary.live_batch_count }} 批</b>
      </div>
      <div class="summary">
        <span>发放人次</span>
        <b>{{ summary.live_payment_count }} 人次</b>
      </div>
      <div class="summary">
        <span>已撤销金额</span>
        <b class="muted">¥{{ formatCents(summary.voided_total_cents) }}</b>
      </div>
    </div>

    <div class="panel block">
      <div class="section-head">
        <div class="section-title">发薪批次记录</div>
        <span class="muted small">共 {{ total }} 批，每批对应看板里的一次「发工资」</span>
        <div class="spacer"></div>
        <el-pagination
          v-if="total > pageSize"
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          small
          @current-change="load"
        />
      </div>

      <el-table
        v-loading="loading"
        class="desktop-only"
        :data="batches"
        empty-text="还没有发薪记录，可前往「看板」按时段发工资"
      >
        <el-table-column label="工资日 / 发放时间" width="166">
          <template #default="{ row }">
            <div class="cell-main mono">{{ row.wage_date }}</div>
            <div class="cell-sub">{{ formatShort(row.created_at) }}</div>
          </template>
        </el-table-column>

        <el-table-column label="统计区间" width="210">
          <template #default="{ row }">
            <div v-if="row.period_start || row.period_end" class="period-cell">
              <span>{{ formatMoment(row.period_start) }}</span>
              <span class="muted">至 {{ formatMoment(row.period_end) }}</span>
            </div>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>

        <el-table-column label="发放明细" min-width="260">
          <template #default="{ row }">
            <div class="line-chips">
              <span
                v-for="line in row.lines"
                :key="line.id"
                class="line-chip"
                :class="{ highlight: userId && line.user?.id === userId }"
              >
                <span class="chip-staff">{{ line.user?.display_name || '未知' }}</span>
                <span class="chip-arrow">→</span>
                <span class="chip-player">{{ line.player.game_id }}</span>
                <b class="chip-money mono">¥{{ formatCents(line.amount_cents) }}</b>
              </span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="合计" width="112" align="right">
          <template #default="{ row }">
            <b class="mono" :class="row.status === 'voided' ? 'muted line-through' : 'good'">
              ¥{{ formatCents(row.total_cents) }}
            </b>
            <div class="cell-sub">{{ row.people_count }} 人</div>
          </template>
        </el-table-column>

        <el-table-column label="经办 / 备注" min-width="140">
          <template #default="{ row }">
            <div class="cell-main">{{ row.paid_by?.display_name || '-' }}</div>
            <div class="cell-sub">{{ row.note || '-' }}</div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="112">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'live'" type="success" size="small" effect="plain">
              已发放
            </el-tag>
            <template v-else>
              <el-tag type="info" size="small" effect="plain">已撤销</el-tag>
              <div v-if="row.voided_at" class="cell-sub">
                {{ formatShort(row.voided_at) }}
                <template v-if="row.voided_by"> · {{ row.voided_by.display_name }}</template>
              </div>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="96" align="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'live'"
              link
              type="danger"
              :loading="voidingBatchId === row.batch_id"
              @click="voidBatch(row)"
            >
              撤销这批
            </el-button>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-loading="loading" class="mobile-only batch-cards">
        <div v-for="row in batches" :key="row.batch_id" class="batch-card">
          <div class="batch-card-head">
            <div>
              <span class="cell-main mono">{{ row.wage_date }}</span>
              <el-tag
                :type="row.status === 'live' ? 'success' : 'info'"
                size="small"
                effect="plain"
                style="margin-left: 6px"
              >
                {{ row.status === 'live' ? '已发放' : '已撤销' }}
              </el-tag>
            </div>
            <b class="mono" :class="row.status === 'voided' ? 'muted line-through' : 'good'">
              ¥{{ formatCents(row.total_cents) }}
            </b>
          </div>

          <div class="batch-card-meta">
            <span>{{ formatShort(row.created_at) }}</span>
            <span v-if="row.period_start || row.period_end">
              {{ formatMoment(row.period_start) }} 至 {{ formatMoment(row.period_end) }}
            </span>
            <span>经办 {{ row.paid_by?.display_name || '-' }}</span>
          </div>

          <div class="line-chips">
            <span
              v-for="line in row.lines"
              :key="line.id"
              class="line-chip"
              :class="{ highlight: userId && line.user?.id === userId }"
            >
              <span class="chip-staff">{{ line.user?.display_name || '未知' }}</span>
              <span class="chip-arrow">→</span>
              <span class="chip-player">{{ line.player.game_id }}</span>
              <b class="chip-money mono">¥{{ formatCents(line.amount_cents) }}</b>
            </span>
          </div>

          <div v-if="row.note" class="cell-sub">{{ row.note }}</div>
          <div v-if="row.status === 'live'" class="batch-card-foot">
            <el-button
              link
              type="danger"
              :loading="voidingBatchId === row.batch_id"
              @click="voidBatch(row)"
            >
              撤销这批
            </el-button>
          </div>
          <div v-else-if="row.voided_at" class="cell-sub">
            已于 {{ formatShort(row.voided_at) }}
            <template v-if="row.voided_by">由 {{ row.voided_by.display_name }}</template>
            撤销
          </div>
        </div>

        <div v-if="!loading && !batches.length" class="empty-hint">
          还没有发薪记录，可前往「看板」按时段发工资
        </div>
      </div>

      <div v-if="total > pageSize" class="pager-foot">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          small
          @current-change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { recordApi, salaryApi } from '@/api'
import type { OperatorOption, SalaryRecordBatch, SalaryRecordsSummary } from '@/api/types'
import { formatMoment, formatShort } from '@/utils/datetime'
import { formatCents } from '@/utils/money'

const router = useRouter()

function offsetDay(days: number): Date {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d
}

function monthStart(offset = 0): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth() + offset, 1)
}

function monthEnd(offset = 0): Date {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth() + offset + 1, 0)
}

const shortcuts = [
  { text: '最近 7 天', value: () => [offsetDay(-6), offsetDay(0)] },
  { text: '最近 30 天', value: () => [offsetDay(-29), offsetDay(0)] },
  { text: '本月', value: () => [monthStart(0), offsetDay(0)] },
  { text: '上月', value: () => [monthStart(-1), monthEnd(-1)] },
]

const dateRange = ref<[string, string] | null>(null)
const userId = ref<number | undefined>(undefined)
const status = ref<'all' | 'live' | 'voided'>('all')
const operators = ref<OperatorOption[]>([])

const loading = ref(false)
const voidingBatchId = ref<string | null>(null)
const batches = ref<SalaryRecordBatch[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 15
const summary = ref<SalaryRecordsSummary>({
  live_total_cents: 0,
  live_batch_count: 0,
  live_payment_count: 0,
  voided_total_cents: 0,
  voided_payment_count: 0,
})

function errDetail(e: unknown, fallback: string): string {
  const resp = (e as { response?: { data?: { detail?: string } } })?.response
  return resp?.data?.detail || fallback
}

async function loadOperators() {
  try {
    operators.value = await recordApi.operators()
  } catch {
    operators.value = []
  }
}

async function load() {
  loading.value = true
  try {
    const res = await salaryApi.records({
      page: page.value,
      page_size: pageSize,
      status: status.value,
      user_id: userId.value || undefined,
      date_from: dateRange.value?.[0] || undefined,
      date_to: dateRange.value?.[1] || undefined,
    })
    batches.value = res.items
    total.value = res.total
    summary.value = res.summary
  } catch (e) {
    ElMessage.error(errDetail(e, '发薪记录加载失败'))
  } finally {
    loading.value = false
  }
}

async function reload() {
  page.value = 1
  await load()
}

async function voidBatch(batch: SalaryRecordBatch) {
  const names = batch.lines.map((line) => line.user?.display_name || '未知').join('、')
  let reason = ''
  try {
    const answer = await ElMessageBox.prompt(
      `确认撤销 ${batch.wage_date} 这批工资？共 ${batch.people_count} 人（${names}），` +
        `合计 ¥${formatCents(batch.total_cents)}。系统将从各工资账户原额退回（若余额不足会撤销失败）。`,
      '撤销这批工资',
      {
        confirmButtonText: '确认撤销',
        cancelButtonText: '取消',
        type: 'warning',
        inputPlaceholder: '可选：填写撤销原因（记入退押金备注）',
      },
    )
    reason = String(answer.value || '').trim()
  } catch {
    return
  }

  voidingBatchId.value = batch.batch_id
  try {
    const res = await salaryApi.void(batch.batch_id, reason)
    ElMessage.success(`已撤销，退回 ¥${formatCents(res.total_cents)}`)
    await load()
  } catch (e) {
    ElMessage.error(errDetail(e, '撤销失败'))
  } finally {
    voidingBatchId.value = null
  }
}

onMounted(() => {
  void loadOperators()
  void load()
})
</script>

<style scoped>
.salary-records-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: var(--app-bg-panel);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  font-size: 12px;
  color: var(--app-text-muted);
}

.summary b {
  font-size: 20px;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}

.summary b.good,
.good {
  color: var(--el-color-success);
}

.line-through {
  text-decoration: line-through;
}

.block {
  padding: 14px 16px;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.section-head .section-title {
  margin: 0;
}

.period-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
  line-height: 1.4;
}

.line-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.line-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: var(--app-radius-sm);
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border);
  font-size: 12px;
  line-height: 1.4;
}

.line-chip.highlight {
  border-color: var(--app-primary);
  background: var(--app-bg-elevated);
}

.chip-staff {
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.chip-arrow {
  color: var(--app-text-muted);
  font-size: 11px;
}

.chip-player {
  color: var(--app-text-muted);
}

.chip-money {
  color: var(--el-color-success);
  margin-left: 2px;
}

.pager-foot {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.batch-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.batch-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
}

.batch-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.batch-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.batch-card-foot {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 768px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .section-head {
    flex-wrap: wrap;
    row-gap: 4px;
  }
}
</style>

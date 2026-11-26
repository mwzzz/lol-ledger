<template>
  <div v-loading="loading && loaded" element-loading-text="正在刷新…" class="page dashboard-view">
    <div class="page-head">
      <span class="page-title">经营看板</span>
      <span class="page-sub">今日全店概况 · 时段操作人对账与发薪</span>
      <div class="spacer"></div>
      <el-button size="small" :icon="Refresh" :loading="loading" @click="loadAll">刷新全部</el-button>
    </div>

    <!-- 第一部分：今日实时经营大盘 -->
    <section v-if="overview" class="today-board">
      <div class="kpi-grid">
        <div
          class="kpi-card"
          :class="(overview.today.cash_diff_cents || 0) < 0 ? 'accent-danger' : 'accent-success'"
        >
          <span class="kpi-label">今日现金差额</span>
          <b
            class="kpi-val"
            :class="(overview.today.cash_diff_cents || 0) < 0 ? 'diff-out' : 'diff-in'"
          >
            ¥{{ formatCents(overview.today.cash_diff_cents || 0) }}
          </b>
          <small class="kpi-sub">
            {{ (overview.today.cash_diff_cents || 0) < 0 ? '店长应补' : '店员应交' }} · 收 ¥{{
              formatCents(overview.today.add_deposit_cents)
            }}
            / 退 ¥{{ formatCents(overview.today.refund_cents) }}
          </small>
        </div>

        <div class="kpi-card accent-primary">
          <span class="kpi-label">今日茶水收入</span>
          <b class="kpi-val">¥{{ formatCents(overview.today.tea_cents || 0) }}</b>
          <small class="kpi-sub">今日已开 {{ overview.today.session_count || 0 }} 局</small>
        </div>

        <div class="kpi-card accent-neutral">
          <span class="kpi-label">在库总押金</span>
          <b class="kpi-val">¥{{ formatCents(overview.total_deposit_cents || 0) }}</b>
          <small class="kpi-sub">
            现金在库
            <template v-if="(overview.total_bonus_cents || 0) > 0">
              · 另含赠金 ¥{{ formatCents(overview.total_bonus_cents) }}
            </template>
          </small>
        </div>

        <div
          class="kpi-card clickable"
          :class="(overview.low_deposit_count || 0) > 0 ? 'alert accent-warn' : 'accent-neutral'"
          @click="goLowDepositPlayers"
        >
          <span class="kpi-label">押金不足预警</span>
          <b class="kpi-val" :class="{ 'diff-out': (overview.low_deposit_count || 0) > 0 }">
            {{ overview.low_deposit_count || 0 }} 人
          </b>
          <small class="kpi-sub">
            低于 ¥{{ formatCents(overview.deposit_low_cents || 3000) }}，点此直达收银台催补 →
          </small>
        </div>
      </div>
    </section>

    <!-- 第二部分：按时段操作人汇总与工资结算 -->
    <div v-if="error" class="panel state-panel">
      <div class="state-title">汇总数据暂不可用</div>
      <div class="state-desc muted">操作人汇总没有加载成功，请检查网络或服务后重试。</div>
      <el-button type="primary" :loading="loading" @click="loadAll">重试</el-button>
    </div>

    <div
      v-else-if="!loaded"
      v-loading="true"
      element-loading-text="正在加载看板数据…"
      class="panel state-panel state-loading"
    >
      <div class="state-title">正在加载看板数据…</div>
    </div>

    <template v-else>
      <section class="panel summary-section">
        <div class="sum-head">
          <div class="sh-left">
            <span class="section-title">时段操作人汇总</span>
            <span class="rule-pill">
              {{
                data.dividend_mode === 'fixed'
                  ? `每局固定 ¥${formatCents(data.dividend_fixed_cents)}`
                  : `茶水比例 ${data.dividend_rate_percent}%`
              }}
            </span>
          </div>

          <div class="sh-actions">
            <el-date-picker
              v-model="range"
              type="datetimerange"
              value-format="YYYY-MM-DDTHH:mm:ss"
              format="MM-DD HH:mm:ss"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              :clearable="false"
              :shortcuts="shortcuts"
              :style="{ width: '326px' }"
              @change="loadSummary"
            />
            <el-button v-if="auth.isAdmin" size="small" @click="continueFromLastPay">
              续接上次发薪
            </el-button>
            <el-button size="small" @click="generateReport">复制工资单</el-button>
            <el-button v-if="auth.isAdmin" size="small" type="primary" @click="payVisible = true">
              发工资
            </el-button>
          </div>
        </div>

        <!-- 区间合计条 -->
        <div class="period-strip">
          <div class="ps-item">
            <span>区间场次</span><b>{{ data.totals.session_count }}</b>
          </div>
          <div class="ps-item">
            <span>茶水合计</span><b>¥{{ formatCents(data.totals.tea_cents) }}</b>
          </div>
          <div class="ps-item">
            <span>收押金</span><b>¥{{ formatCents(data.totals.add_deposit_cents) }}</b>
          </div>
          <div class="ps-item">
            <span>退押金</span><b>¥{{ formatCents(data.totals.refund_cents) }}</b>
          </div>
          <div class="ps-item">
            <span>现金差额</span>
            <b :class="data.totals.cash_diff_cents < 0 ? 'diff-out' : 'diff-in'">
              ¥{{ formatCents(data.totals.cash_diff_cents) }}
            </b>
          </div>
          <div class="ps-item">
            <span>分红合计</span><b class="div">¥{{ formatCents(data.totals.dividend_cents) }}</b>
          </div>
        </div>

        <el-table
          v-if="displayRows.length"
          :data="displayRows"
          show-summary
          :summary-method="summaryMethod"
          class="desktop-only"
          style="width: 100%"
        >
          <el-table-column label="操作人" min-width="150">
            <template #default="{ row }">
              <div class="cell-main">{{ row.user?.display_name || '未知' }}</div>
              <div class="cell-sub">{{ row.user?.username || '-' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="场次" width="84" align="right">
            <template #default="{ row }"><b class="mono">{{ row.session_count }}</b></template>
          </el-table-column>
          <el-table-column label="人次" width="84" align="right">
            <template #default="{ row }"><span class="mono">{{ row.player_times }}</span></template>
          </el-table-column>
          <el-table-column label="茶水" width="118" align="right">
            <template #default="{ row }"><span class="mono">¥{{ formatCents(row.tea_cents) }}</span></template>
          </el-table-column>
          <el-table-column label="收押金" width="118" align="right">
            <template #default="{ row }"><span class="mono">¥{{ formatCents(row.add_deposit_cents) }}</span></template>
          </el-table-column>
          <el-table-column label="退押金" width="118" align="right">
            <template #default="{ row }"><span class="mono">¥{{ formatCents(row.refund_cents) }}</span></template>
          </el-table-column>
          <el-table-column label="现金差额（正=应交 / 负=应补）" width="170" align="right">
            <template #default="{ row }">
              <span :class="row.cash_diff_cents < 0 ? 'diff-out' : 'diff-in'">
                ¥{{ formatCents(row.cash_diff_cents) }}
              </span>
              <div class="cell-sub">
                {{ row.cash_diff_cents < 0 ? '店长应补' : '店员应交' }}
              </div>
            </template>
          </el-table-column>
          <el-table-column label="分红" width="118" align="right">
            <template #default="{ row }">
              <b class="div mono">¥{{ formatCents(row.dividend_cents) }}</b>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="displayRows.length" class="mobile-only summary-cards">
          <div v-for="row in displayRows" :key="row.user?.id || 'x'" class="summary-card">
            <div class="sc-head">
              <div class="cell-main">{{ row.user?.display_name || '未知' }}</div>
              <span :class="row.cash_diff_cents < 0 ? 'diff-out' : 'diff-in'">
                {{ row.cash_diff_cents < 0 ? '应补' : '应交' }}
                ¥{{ formatCents(Math.abs(row.cash_diff_cents)) }}
              </span>
            </div>
            <div class="sc-grid">
              <div><span>场次</span><b>{{ row.session_count }}</b></div>
              <div><span>茶水</span><b>¥{{ formatCents(row.tea_cents) }}</b></div>
              <div><span>收押金</span><b>¥{{ formatCents(row.add_deposit_cents) }}</b></div>
              <div><span>退押金</span><b>¥{{ formatCents(row.refund_cents) }}</b></div>
              <div><span>分红</span><b class="div">¥{{ formatCents(row.dividend_cents) }}</b></div>
            </div>
          </div>
        </div>

        <el-empty v-if="!displayRows.length" description="所选时间区间暂无记录" :image-size="76" />

        <div v-if="reportVisible" class="report-box">
          <el-input v-model="reportText" type="textarea" :rows="reportRows" readonly resize="none" />
          <div class="report-actions">
            <el-button size="small" type="primary" @click="copyReport">再次复制</el-button>
            <el-button size="small" @click="reportVisible = false">收起</el-button>
          </div>
        </div>
      </section>

      <!-- 第三部分：底部双栏（最近场次 + 最新押金流水） -->
      <div class="feed-grid">
        <section class="panel feed-panel">
          <div class="feed-head">
            <span class="section-title">本区间最近场次</span>
            <el-button
              link
              type="primary"
              @click="router.push({ name: 'reports', query: { tab: 'records' } })"
            >
              全部场次
            </el-button>
          </div>

          <div v-if="sessions.length" class="feed-list">
            <div v-for="row in sessions" :key="row.id" class="feed-row">
              <div class="fr-main">
                <div class="fr-title">
                  <span>{{ row.name }}</span>
                  <span class="dim-tag">{{ row.player_count }}人</span>
                </div>
                <div class="fr-sub">
                  {{ row.players.map((x: SessionPlayerRow) => x.game_id).join('、') || '无玩家' }}
                </div>
              </div>
              <div class="fr-right">
                <b class="mono">¥{{ formatCents(row.tea_total_cents) }}</b>
                <span class="muted small">{{ formatShort(row.played_at) }} · {{ row.operator?.display_name || '-' }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-hint">该区间暂无场次</div>
        </section>

        <section class="panel feed-panel">
          <div class="feed-head">
            <span class="section-title">全店最新流水</span>
            <el-button link type="primary" @click="router.push({ name: 'reports' })">
              全部流水
            </el-button>
          </div>

          <div v-if="overview?.recent_records?.length" class="feed-list">
            <div v-for="row in overview.recent_records.slice(0, 8)" :key="row.id" class="feed-row">
              <div class="fr-main">
                <div class="fr-title">
                  <span>{{ row.player.game_id }}</span>
                  <span class="muted small">{{ row.reason_label }}</span>
                </div>
                <div class="fr-sub">
                  {{ formatShort(row.created_at) }} · 操作人 {{ row.operator?.display_name || '-' }}
                  <template v-if="row.note"> · {{ row.note }}</template>
                </div>
              </div>
              <div class="fr-right">
                <MoneyText :cents="row.signed_amount_cents" change />
                <span class="muted small mono">余 ¥{{ formatCents(row.balance_after_cents) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-hint">暂无流水</div>
        </section>
      </div>
    </template>

    <SalaryPayDialog
      v-model="payVisible"
      :date-from="range[0]"
      :date-to="range[1]"
      @paid="loadAll"
    />
  </div>
</template>

<script setup lang="ts">
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { overviewApi, salaryApi, sessionApi, summaryApi } from '@/api'
import type {
  OperatorSummary,
  OperatorSummaryRow,
  OverviewPayload,
  SessionPlayerRow,
  SessionRow,
} from '@/api/types'
import MoneyText from '@/components/common/MoneyText.vue'
import SalaryPayDialog from '@/components/summary/SalaryPayDialog.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import {
  formatShort,
  momentShortcuts,
  recentMorningRange,
  todayText,
  withSeconds,
} from '@/utils/datetime'
import { formatCents, formatYuanShort } from '@/utils/money'

const router = useRouter()
const route = useRoute()
const app = useAppStore()
const auth = useAuthStore()

const MOMENT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/

function queryRange(): [string, string] | null {
  const from = typeof route.query.from === 'string' ? route.query.from : ''
  const to = typeof route.query.to === 'string' ? route.query.to : ''
  if (MOMENT_RE.test(from) && MOMENT_RE.test(to)) return [withSeconds(from), withSeconds(to)]
  return null
}

function initialRange(): { value: [string, string]; needAutoContinue: boolean } {
  const fromUrl = queryRange()
  if (fromUrl) return { value: fromUrl, needAutoContinue: false }
  const todaySaved = app.getTodaySummaryRange()
  if (todaySaved) {
    return {
      value: [withSeconds(todaySaved[0]), withSeconds(todaySaved[1])],
      needAutoContinue: false,
    }
  }
  return { value: recentMorningRange(1), needAutoContinue: true }
}

const shortcuts = momentShortcuts()
const day = todayText()
const init = initialRange()
const range = ref<[string, string]>(init.value)

const overview = ref<OverviewPayload | null>(null)
const data = ref<OperatorSummary>({
  date_from: day,
  date_to: day,
  dividend_mode: 'percent',
  dividend_rate_percent: 50,
  dividend_fixed_cents: 0,
  rows: [],
  totals: {
    session_count: 0,
    player_times: 0,
    tea_cents: 0,
    add_deposit_cents: 0,
    refund_cents: 0,
    cash_diff_cents: 0,
    dividend_cents: 0,
  },
})

const sessions = ref<SessionRow[]>([])
const payVisible = ref(false)
const loading = ref(false)
const error = ref(false)
const loaded = ref(false)
let loadSeq = 0

function goLowDepositPlayers() {
  router.push({ name: 'pos', query: { level: 'low' } })
}

async function loadOverview() {
  try {
    const payload = await overviewApi.get()
    overview.value = payload
    app.today = payload.today
    app.todayLoaded = true
    app.todayError = false
  } catch {
    /* keep previous overview if any */
  }
}

async function loadSummary() {
  reportVisible.value = false
  reportText.value = ''
  const [from, to] = range.value || [day, day]
  if (MOMENT_RE.test(from) && MOMENT_RE.test(to)) {
    app.setSummaryRange([from, to])
  }
  const seq = ++loadSeq
  loading.value = true
  error.value = false
  try {
    const [summary, page] = await Promise.all([
      summaryApi.operators(from, to),
      sessionApi.list({ date_from: from, date_to: to, page: 1, page_size: 8 }),
    ])
    if (seq !== loadSeq) return
    data.value = summary
    sessions.value = page.items
    loaded.value = true
  } catch {
    if (seq !== loadSeq) return
    error.value = true
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

async function loadAll() {
  await Promise.all([loadOverview(), loadSummary()])
}

async function continueFromLastPay() {
  try {
    const w = await salaryApi.nextWindow()
    range.value = [w.start, w.end]
    await loadSummary()
    ElMessage.success(
      w.source === 'last_paid'
        ? `已续接上次发薪：${w.start} ~ ${w.end}`
        : `暂无发薪记录，已用默认区间：${w.start} ~ ${w.end}`,
    )
  } catch {
    ElMessage.error('续接失败，请重试')
  }
}

const displayRows = computed<OperatorSummaryRow[]>(() =>
  data.value.rows
    .filter((row) => !(row.cash_diff_cents === 0 && row.dividend_cents === 0))
    .slice()
    .sort(
      (a, b) =>
        b.session_count - a.session_count ||
        b.cash_diff_cents - a.cash_diff_cents ||
        (a.user?.id ?? 0) - (b.user?.id ?? 0),
    ),
)

function summaryMethod({ columns }: { columns: unknown[] }): string[] {
  const t = data.value.totals
  return columns.map((_column, index) => {
    switch (index) {
      case 0:
        return '总计'
      case 1:
        return String(t.session_count)
      case 2:
        return String(t.player_times)
      case 3:
        return `¥${formatCents(t.tea_cents)}`
      case 4:
        return `¥${formatCents(t.add_deposit_cents)}`
      case 5:
        return `¥${formatCents(t.refund_cents)}`
      case 6:
        return `¥${formatCents(t.cash_diff_cents)}`
      case 7:
        return `¥${formatCents(t.dividend_cents)}`
      default:
        return ''
    }
  })
}

const reportVisible = ref(false)
const reportText = ref('')
const reportRows = computed(() =>
  Math.min(24, Math.max(6, reportText.value.split('\n').length)),
)

function momentDate(text: string): string {
  return `${Number(text.slice(5, 7))}月${Number(text.slice(8, 10))}日`
}

function momentLabel(text: string): string {
  const date = momentDate(text)
  const hhmm = text.slice(11, 16)
  if (!hhmm) return date
  const ss = text.slice(17, 19)
  return `${date}${hhmm}${ss && ss !== '00' ? `:${ss}` : ''}`
}

function displayWidth(text: string): number {
  let width = 0
  for (const ch of text) {
    const code = ch.codePointAt(0) || 0
    const wide =
      (code >= 0x1100 && code <= 0x115f) ||
      (code >= 0x2e80 && code <= 0x303e) ||
      (code >= 0x3041 && code <= 0x33ff) ||
      (code >= 0x3400 && code <= 0x4dbf) ||
      (code >= 0x4e00 && code <= 0x9fff) ||
      (code >= 0xac00 && code <= 0xd7a3) ||
      (code >= 0xf900 && code <= 0xfaff) ||
      (code >= 0xfe30 && code <= 0xfe6f) ||
      (code >= 0xff00 && code <= 0xff60) ||
      (code >= 0xffe0 && code <= 0xffe6)
    width += wide ? 2 : 1
  }
  return width
}

function padWidth(text: string, target: number): string {
  let out = text
  let width = displayWidth(text)
  while (width < target) {
    if (target - width >= 2) {
      out += '　'
      width += 2
    } else {
      out += ' '
      width += 1
    }
  }
  return out
}

function generateReport() {
  const [from, to] = range.value || [day, day]
  const rows = displayRows.value
  const names = rows.map((row) => row.user?.display_name || row.user?.username || '未知')
  const wages = rows.map((row) => formatYuanShort(row.dividend_cents))
  const nameWidth = Math.max(0, ...names.map(displayWidth))
  const wageWidth = Math.max(0, ...wages.map(displayWidth))

  const lines = rows.map((row, index) => {
    const diff =
      row.cash_diff_cents > 0
        ? `应交${formatYuanShort(row.cash_diff_cents)}`
        : row.cash_diff_cents < 0
          ? `应补${formatYuanShort(-row.cash_diff_cents)}***`
          : ''
    const body = `${padWidth(names[index], nameWidth)}　工资${padWidth(wages[index], wageWidth)}`
    return diff ? `${body}　${diff}` : body
  })

  const head = `【${momentDate(from)}工资与差额明细】`
  const period = `统计时段：${momentLabel(from)} 至 ${momentLabel(to)}`
  const tail = `总计工资支出：${formatYuanShort(data.value.totals.dividend_cents)}元`
  reportText.value = [head, period, ...lines, tail].join('\n')
  reportVisible.value = true
  void copyReport()
}

async function copyReport() {
  const text = reportText.value
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('工资单已复制到剪贴板')
    return
  } catch {
    // fallback for non-secure http context
  }
  const el = document.createElement('textarea')
  el.value = text
  el.style.position = 'fixed'
  el.style.opacity = '0'
  document.body.appendChild(el)
  el.select()
  try {
    document.execCommand('copy')
    ElMessage.success('工资单已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选中文本复制')
  }
  document.body.removeChild(el)
}

onMounted(async () => {
  if (init.needAutoContinue && auth.isAdmin) {
    await Promise.all([
      loadOverview(),
      (async () => {
        try {
          const w = await salaryApi.nextWindow()
          range.value = [w.start, w.end]
        } catch {
          // 续接接口异常时回落默认区间
        }
        await loadSummary()
      })(),
    ])
    return
  }
  await loadAll()
})

watch(
  () => app.sessionTick,
  () => void loadAll(),
)
</script>

<style scoped>
.today-board {
  margin-bottom: 16px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.kpi-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 15px 17px;
  border-radius: var(--app-radius-md);
  border: 1px solid var(--app-border);
  background: var(--app-bg-panel);
  box-shadow: var(--app-panel-shadow), var(--app-panel-highlight);
  overflow: hidden;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.kpi-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2.5px;
  background: transparent;
}

.kpi-card.accent-success::before {
  background: var(--el-color-success);
}
.kpi-card.accent-danger::before {
  background: var(--el-color-danger);
}
.kpi-card.accent-primary::before {
  background: var(--app-primary);
}
.kpi-card.accent-warn::before {
  background: var(--el-color-warning);
}
.kpi-card.accent-neutral::before {
  background: var(--app-border-strong);
}

.kpi-card.clickable:hover {
  border-color: var(--app-primary);
  transform: translateY(-1px);
}

.kpi-card.alert {
  background: var(--app-warning-soft);
  border-color: rgba(245, 181, 68, 0.35);
}

.kpi-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--app-text-muted);
}

.kpi-val {
  font-size: 25px;
  font-weight: 700;
  letter-spacing: -0.025em;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}

.kpi-sub {
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.summary-section {
  padding: 16px 18px;
  margin-bottom: 16px;
}

.sum-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.sh-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sh-left .section-title {
  margin: 0;
  font-size: 15px;
}

.rule-pill {
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--app-primary-soft);
  color: var(--app-primary);
  font-size: 11.5px;
  font-weight: 600;
}

.sh-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.period-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.ps-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border-radius: var(--app-radius-sm);
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border);
}

.ps-item span {
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.ps-item b {
  font-size: 17px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.diff-in {
  color: var(--el-color-success);
  font-variant-numeric: tabular-nums;
}

.diff-out {
  color: var(--el-color-danger);
  font-variant-numeric: tabular-nums;
}

.div {
  color: var(--app-primary);
}

.report-box {
  margin-top: 14px;
}

.report-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.feed-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.feed-panel {
  padding: 14px 16px;
}

.feed-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.feed-head .section-title {
  margin: 0;
}

.feed-list {
  display: flex;
  flex-direction: column;
}

.feed-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid var(--app-border);
}

.feed-row:last-child {
  border-bottom: none;
}

.fr-main {
  min-width: 0;
  flex: 1;
}

.fr-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
}

.fr-sub {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--app-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fr-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex: none;
}

.small {
  font-size: 11.5px;
}

.summary-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-card {
  padding: 12px;
  border-radius: var(--app-radius-sm);
  border: 1px solid var(--app-border);
  background: var(--app-bg-subtle);
}

.sc-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.sc-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  font-size: 12px;
}

.sc-grid > div {
  display: flex;
  flex-direction: column;
}

.sc-grid span {
  font-size: 11px;
  color: var(--app-text-muted);
}

.state-panel {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 24px;
}

.state-title {
  font-size: 16px;
  font-weight: 600;
}

.state-loading {
  min-height: 180px;
  align-items: center;
  justify-content: center;
}

@media (max-width: 960px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .period-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .feed-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .period-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .sh-actions {
    width: 100%;
  }

  .sh-actions .el-date-editor {
    flex: 1 1 100%;
  }
}
</style>

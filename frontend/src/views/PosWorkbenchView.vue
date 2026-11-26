<template>
  <div class="pos-workbench">
    <!-- 左栏：玩家检索与收银主工作区 -->
    <div class="pos-main-pane">
      <!-- 顶部收银操作头 -->
      <div class="wb-head">
        <div class="wb-title-group">
          <h1 class="wb-title">收银台</h1>
          <div class="wb-metrics">
            <span>玩家 <b>{{ total }}</b></span>
            <span class="sep">·</span>
            <span>在库押金 <b>¥{{ formatCents(totalDeposit) }}</b></span>
            <template v-if="totalBonus > 0">
              <span class="sep">·</span>
              <span>赠金 <b class="bonus-val">¥{{ formatCents(totalBonus) }}</b></span>
            </template>
          </div>
        </div>

        <div class="wb-actions">
          <el-button size="small" :icon="Upload" @click="importVisible = true">导入</el-button>
          <el-button size="small" :icon="Download" :loading="exporting" @click="exportPlayers">
            导出
          </el-button>
          <el-button size="small" type="primary" :icon="Plus" @click="openCreate">
            新增玩家
          </el-button>
          <button
            v-if="!app.dockOpen"
            type="button"
            class="expand-dock-btn desktop-wide-only"
            @click="app.toggleDock(true)"
          >
            <el-icon><DArrowLeft /></el-icon>
            <span>展开组局台</span>
            <span class="ed-count">{{ draft.filledCount }}/10</span>
          </button>
        </div>
      </div>

      <!-- 搜索与筛选条 -->
      <div class="wb-filters">
        <div class="pos-search-box">
          <el-icon class="ps-icon"><Search /></el-icon>
          <input
            ref="searchInputRef"
            v-model="keyword"
            type="text"
            class="ps-input"
            placeholder="搜游戏名、段位或备注…"
            autocomplete="off"
            @keydown.enter="reload"
            @keydown.esc="clearKeyword"
          />
          <button v-if="keyword" type="button" class="ps-clear" @click="clearKeyword">×</button>
          <kbd v-else class="pos-kbd ps-kbd desktop-only">/</kbd>
        </div>

        <div class="pos-seg" role="group" aria-label="押金状态筛选">
          <button
            v-for="opt in levelOptions"
            :key="opt.value"
            type="button"
            class="pos-seg-btn"
            :class="{ active: level === opt.value }"
            @click="selectLevel(opt.value)"
          >
            <span v-if="opt.dot" class="seg-dot" :class="opt.dot"></span>
            {{ opt.label }}
          </button>
        </div>

        <el-select
          v-model="blacklisted"
          size="small"
          style="width: 112px"
          @change="reload"
        >
          <el-option label="全部状态" value="" />
          <el-option label="正常玩家" value="normal" />
          <el-option label="仅黑名单" value="only" />
        </el-select>

        <el-select v-model="sort" size="small" style="width: 132px" @change="reload">
          <el-option label="最近活跃 ↓" value="last_active_desc" />
          <el-option label="总局数 ↓" value="games_played_desc" />
          <el-option label="押金 ↓" value="deposit_desc" />
          <el-option label="押金 ↑" value="deposit_asc" />
          <el-option label="游戏名 ↑" value="game_id_asc" />
        </el-select>

        <el-button size="small" :icon="Refresh" @click="reload">刷新</el-button>
        <div class="spacer desktop-only"></div>
        <span class="threshold-hint desktop-only">
          &lt;¥{{ formatCents(lowCents) }} 不足 · &gt;¥{{ formatCents(highCents) }} 充足
        </span>
      </div>

      <!-- 桌面端：高密度定制收银列表（去后台表格感） -->
      <div v-loading="loading" class="pos-list-panel panel desktop-only">
        <div class="pl-header">
          <span class="col-board">上车</span>
          <span class="col-player">玩家 / 备注</span>
          <span class="col-balance">账户余额</span>
          <span class="col-games">局数</span>
          <span class="col-active">最近活跃</span>
          <span class="col-ops">收银操作</span>
        </div>

        <div v-if="rows.length" class="pl-body">
          <div
            v-for="row in rows"
            :key="row.id"
            class="pl-row"
            :class="{
              'in-cart': draft.slotIndexOf(row.id) >= 0,
              'is-black': row.is_blacklisted,
            }"
            @dblclick="openLedger(row)"
          >
            <!-- 上车列 -->
            <div class="col-board">
              <span v-if="row.is_blacklisted" class="board-disabled">拉黑</span>
              <span v-else-if="isTeaFree(row.game_id)" class="board-free" title="免茶水名单，开局不扣茶水">
                免茶
              </span>
              <button
                v-else-if="draft.slotIndexOf(row.id) >= 0"
                type="button"
                class="board-btn active"
                title="点击从当前组局移出"
                @click="draft.togglePlayer(row.id)"
              >
                #{{ draft.slotIndexOf(row.id) + 1 }} 在局
              </button>
              <button
                v-else
                type="button"
                class="board-btn"
                @click="draft.togglePlayer(row.id)"
              >
                + 上车
              </button>
            </div>

            <!-- 玩家信息列 -->
            <div class="col-player">
              <div class="p-primary">
                <button
                  type="button"
                  class="p-name-btn"
                  title="点击查看押金与场次流水"
                  @click="openLedger(row)"
                >
                  {{ row.game_id }}
                </button>
                <span v-if="row.account" class="p-rank">{{ row.account }}</span>
                <el-tag v-if="row.is_blacklisted" type="danger" size="small" effect="dark">
                  黑名单
                </el-tag>
              </div>
              <div class="p-secondary">
                <span v-if="row.remark" class="p-remark">{{ row.remark }} · </span>
                <span>创建 {{ row.creator?.display_name || '-' }}</span>
              </div>
            </div>

            <!-- 余额列 -->
            <div class="col-balance">
              <DepositBadge
                :cents="row.balance_cents"
                :deposit-cents="row.deposit_cents"
                :bonus-cents="row.bonus_cents"
                :level="row.deposit_level"
              />
            </div>

            <!-- 局数列 -->
            <div class="col-games mono">{{ row.games_played }}</div>

            <!-- 最近活跃列 -->
            <div class="col-active">
              <el-tooltip :content="formatFull(row.last_active_at)" placement="top">
                <span class="muted">{{ relative(row.last_active_at) }}</span>
              </el-tooltip>
            </div>

            <!-- 收银操作列 -->
            <div class="col-ops">
              <button
                type="button"
                class="cash-btn add"
                @click="openDeposit(row, 'add')"
              >
                + 加押
              </button>
              <button
                type="button"
                class="cash-btn refund"
                @click="openDeposit(row, 'refund')"
              >
                退押
              </button>
              <button
                type="button"
                class="cash-btn"
                @click="openTransfer(row)"
              >
                划押
              </button>
              <el-dropdown trigger="click" @command="(cmd: string) => onMoreCommand(cmd, row)">
                <button type="button" class="cash-btn more" aria-label="更多操作">
                  <el-icon><MoreFilled /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="ledger">查看流水</el-dropdown-item>
                    <el-dropdown-item command="edit">编辑资料</el-dropdown-item>
                    <el-dropdown-item command="bonus">加赠金</el-dropdown-item>
                    <el-dropdown-item
                      v-if="auth.isAdmin && row.bonus_cents > 0"
                      command="delete-bonus"
                    >
                      删除剩余赠金
                    </el-dropdown-item>
                    <el-dropdown-item command="blacklist" divided>
                      {{ row.is_blacklisted ? '移出黑名单' : '加入黑名单' }}
                    </el-dropdown-item>
                    <el-dropdown-item v-if="auth.isAdmin" command="delete">
                      删除玩家
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </div>

        <div v-else-if="!loading" class="empty-hint">
          {{ keyword || level || blacklisted ? '没有匹配筛选条件的玩家' : '还没有玩家，点右上角「新增玩家」开始' }}
        </div>

        <div class="pl-footer">
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
      </div>

      <!-- 移动端：紧凑触控卡片列表 -->
      <div v-loading="loading" class="mobile-only m-player-list">
        <div v-for="row in rows" :key="row.id" class="m-card" @click="openLedger(row)">
          <div class="mc-top">
            <div class="mc-who">
              <div class="mc-name">
                <span>{{ row.game_id }}</span>
                <span v-if="row.account" class="p-rank">{{ row.account }}</span>
                <el-tag v-if="row.is_blacklisted" type="danger" size="small" effect="dark">黑名单</el-tag>
              </div>
              <div class="mc-meta">
                <span>{{ row.games_played }} 局</span>
                <span>· {{ relative(row.last_active_at) }}</span>
                <span v-if="row.remark">· {{ row.remark }}</span>
              </div>
            </div>
            <DepositBadge
              :cents="row.balance_cents"
              :deposit-cents="row.deposit_cents"
              :bonus-cents="row.bonus_cents"
              :level="row.deposit_level"
            />
          </div>
          <div class="mc-actions" @click.stop>
            <button
              v-if="!row.is_blacklisted && !isTeaFree(row.game_id)"
              type="button"
              class="cash-btn"
              :class="{ 'in-slot': draft.slotIndexOf(row.id) >= 0 }"
              @click="draft.togglePlayer(row.id)"
            >
              {{ draft.slotIndexOf(row.id) >= 0 ? `#${draft.slotIndexOf(row.id) + 1} 在局` : '+ 上车' }}
            </button>
            <button type="button" class="cash-btn add" @click="openDeposit(row, 'add')">+ 加押</button>
            <button type="button" class="cash-btn refund" @click="openDeposit(row, 'refund')">退押</button>
            <button type="button" class="cash-btn" @click="openTransfer(row)">划押</button>
            <el-dropdown trigger="click" @command="(cmd: string) => onMoreCommand(cmd, row)">
              <button type="button" class="cash-btn more">
                <el-icon><MoreFilled /></el-icon>
              </button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="ledger">查看流水</el-dropdown-item>
                  <el-dropdown-item command="edit">编辑资料</el-dropdown-item>
                  <el-dropdown-item command="bonus">加赠金</el-dropdown-item>
                  <el-dropdown-item
                    v-if="auth.isAdmin && row.bonus_cents > 0"
                    command="delete-bonus"
                  >
                    删除剩余赠金
                  </el-dropdown-item>
                  <el-dropdown-item command="blacklist" divided>
                    {{ row.is_blacklisted ? '移出黑名单' : '加入黑名单' }}
                  </el-dropdown-item>
                  <el-dropdown-item v-if="auth.isAdmin" command="delete">删除玩家</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <div v-if="!loading && !rows.length" class="empty-hint">暂无匹配玩家</div>

        <div class="m-pager">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            layout="total, prev, pager, next"
            small
            @current-change="load"
          />
        </div>
      </div>
    </div>

    <!-- 右栏（宽屏常驻）：10 人组局台 -->
    <aside v-if="app.dockOpen" class="pos-dock-pane desktop-wide-only">
      <SessionDock
        @collapse="app.toggleDock(false)"
        @quick-deposit="openQuickDepositById"
      />
    </aside>

    <!-- 窄屏 / 移动端：底部悬浮组局胶囊条 + 抽屉 -->
    <div class="compact-dock-bar">
      <button type="button" class="cdb-main" @click="app.mobileDockVisible = true">
        <span class="cdb-badge">{{ draft.filledCount }}/10</span>
        <span class="cdb-label">
          {{ draft.filledCount > 0 ? `当前组局 · 茶水 ¥${formatCents(draft.teaTotalCents)}` : '打开组局台（开一局）' }}
        </span>
        <span class="cdb-go">展开 ↑</span>
      </button>
    </div>

    <el-drawer
      v-model="app.mobileDockVisible"
      direction="rtl"
      size="min(400px, 94vw)"
      :with-header="false"
      class="dock-drawer"
    >
      <SessionDock
        embedded
        @quick-deposit="openQuickDepositById"
        @submitted="app.mobileDockVisible = false"
      />
    </el-drawer>

    <!-- 业务弹窗与流水抽屉 -->
    <PlayerFormDialog v-model="formVisible" :player="editing" @saved="onSaved" />
    <PlayerImportDialog v-model="importVisible" @saved="onSaved" />
    <DepositDialog
      v-model="depositVisible"
      :player="active"
      :mode="depositMode"
      @saved="onPlayerChanged"
    />
    <TransferDialog
      v-model="transferVisible"
      :player="active"
      :default-amount-cents="defaultTransferCents"
      @saved="onTransferSaved"
    />
    <PlayerLedgerDrawer v-model="ledgerVisible" :player="active" @changed="onSaved" />
  </div>
</template>

<script setup lang="ts">
import {
  DArrowLeft,
  Download,
  MoreFilled,
  Plus,
  Refresh,
  Search,
  Upload,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { moneyApi, overviewApi, playerApi } from '@/api'
import type { PlayerRow } from '@/api/types'
import DepositBadge from '@/components/common/DepositBadge.vue'
import DepositDialog from '@/components/players/DepositDialog.vue'
import PlayerFormDialog from '@/components/players/PlayerFormDialog.vue'
import PlayerImportDialog from '@/components/players/PlayerImportDialog.vue'
import PlayerLedgerDrawer from '@/components/players/PlayerLedgerDrawer.vue'
import TransferDialog from '@/components/players/TransferDialog.vue'
import SessionDock from '@/components/pos/SessionDock.vue'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { useSessionDraftStore } from '@/stores/sessionDraft'
import { formatFull, relative } from '@/utils/datetime'
import { formatCents } from '@/utils/money'
import { nameKey } from '@/utils/names'

const app = useAppStore()
const auth = useAuthStore()
const draft = useSessionDraftStore()
const route = useRoute()
const router = useRouter()

const VALID_LEVELS = ['', 'low', 'warn', 'safe'] as const
type LevelFilter = (typeof VALID_LEVELS)[number]

function parseLevel(val: unknown): LevelFilter {
  return typeof val === 'string' && (VALID_LEVELS as readonly string[]).includes(val)
    ? (val as LevelFilter)
    : ''
}

const levelOptions: { value: LevelFilter; label: string; dot?: string }[] = [
  { value: '', label: '全部' },
  { value: 'low', label: '不足', dot: 'low' },
  { value: 'warn', label: '偏低', dot: 'warn' },
  { value: 'safe', label: '充足', dot: 'safe' },
]

const searchInputRef = ref<HTMLInputElement | null>(null)
const rows = ref<PlayerRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const keyword = ref(typeof route.query.keyword === 'string' ? route.query.keyword : '')
const level = ref<LevelFilter>(parseLevel(route.query.level))
const sort = ref('last_active_desc')
const blacklisted = ref<'' | 'only' | 'normal'>('')
const loading = ref(false)

const totalDeposit = ref(0)
const totalBonus = ref(0)
const lowCents = ref(3000)
const highCents = ref(6000)

const formVisible = ref(false)
const importVisible = ref(false)
const exporting = ref(false)
const depositVisible = ref(false)
const transferVisible = ref(false)
const ledgerVisible = ref(false)
const editing = ref<PlayerRow | null>(null)
const active = ref<PlayerRow | null>(null)
const depositMode = ref<'add' | 'refund' | 'bonus'>('add')

const defaultTransferCents = computed(() => draft.teaCents * 10)

function isTeaFree(gameId: string): boolean {
  return draft.teaFreeKeys.includes(nameKey(gameId))
}

function selectLevel(next: LevelFilter) {
  if (level.value === next) return
  level.value = next
  reload()
}

function clearKeyword() {
  if (!keyword.value) return
  keyword.value = ''
  reload()
}

let searchTimer: number | undefined

async function load() {
  loading.value = true
  try {
    const data = await playerApi.list({
      keyword: keyword.value.trim(),
      level: level.value || undefined,
      sort: sort.value,
      blacklisted:
        blacklisted.value === 'only'
          ? true
          : blacklisted.value === 'normal'
            ? false
            : undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  try {
    const data = await overviewApi.get()
    totalDeposit.value = data.total_deposit_cents
    totalBonus.value = data.total_bonus_cents || 0
    lowCents.value = data.deposit_low_cents
    highCents.value = data.deposit_high_cents
  } catch {
    /* ignore */
  }
}

function reload() {
  page.value = 1
  void load()
}

async function exportPlayers() {
  exporting.value = true
  try {
    const { blob, filename } = await playerApi.exportFile()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  } catch {
    /* handled by interceptor */
  } finally {
    exporting.value = false
  }
}

function openCreate() {
  editing.value = null
  formVisible.value = true
}

function openEdit(row: PlayerRow) {
  editing.value = row
  formVisible.value = true
}

function openDeposit(row: PlayerRow, mode: 'add' | 'refund' | 'bonus') {
  active.value = row
  depositMode.value = mode
  depositVisible.value = true
}

async function openQuickDepositById(playerId: number) {
  const existing = rows.value.find((r) => r.id === playerId)
  if (existing) {
    openDeposit(existing, 'add')
    return
  }
  try {
    const fetched = await playerApi.get(playerId)
    openDeposit(fetched, 'add')
  } catch {
    ElMessage.warning('未能读取该玩家信息')
  }
}

function openTransfer(row: PlayerRow) {
  active.value = row
  transferVisible.value = true
}

function openLedger(row: PlayerRow) {
  active.value = row
  ledgerVisible.value = true
}

function onMoreCommand(cmd: string, row: PlayerRow) {
  if (cmd === 'ledger') openLedger(row)
  else if (cmd === 'edit') openEdit(row)
  else if (cmd === 'bonus') openDeposit(row, 'bonus')
  else if (cmd === 'delete-bonus') void deleteBonus(row)
  else if (cmd === 'blacklist') void toggleBlacklist(row)
  else if (cmd === 'delete') void remove(row)
}

function syncAllStats() {
  void loadSummary()
  void app.refreshToday()
  void app.refreshMyShift()
  draft.refreshPreviewIfNeeded()
}

function onSaved() {
  reload()
  syncAllStats()
}

function onTransferSaved() {
  reload()
  syncAllStats()
}

function onPlayerChanged(player: PlayerRow) {
  const index = rows.value.findIndex((item) => item.id === player.id)
  if (index >= 0) rows.value[index] = player
  if (active.value?.id === player.id) active.value = player
  syncAllStats()
}

async function toggleBlacklist(row: PlayerRow) {
  const next = !row.is_blacklisted
  try {
    await ElMessageBox.confirm(
      next
        ? `将「${row.game_id}」加入黑名单？加入后不能开游戏。`
        : `将「${row.game_id}」移出黑名单？`,
      next ? '加入黑名单' : '移出黑名单',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await playerApi.update(row.id, { is_blacklisted: next })
  if (next && draft.slotIndexOf(row.id) >= 0) {
    draft.togglePlayer(row.id)
  }
  ElMessage.success(next ? '已加入黑名单' : '已移出黑名单')
  reload()
}

async function deleteBonus(row: PlayerRow) {
  const cents = row.bonus_cents || 0
  if (cents <= 0) {
    ElMessage.warning('该玩家当前没有赠金')
    return
  }
  let note = ''
  try {
    const result = await ElMessageBox.prompt(
      `将删除「${row.game_id}」全部剩余赠金 ¥${formatCents(cents)}` +
        '（只清赠金、不动现金押金）。常用于误把加押金点成加赠金、且已被茶水消耗无法单笔撤销的收尾。请填写原因。',
      '删除赠金',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        inputPlaceholder: '删除原因（记入流水备注）',
        type: 'warning',
      },
    )
    note = (result.value || '').trim()
  } catch {
    return
  }
  const res = await moneyApi.deleteBonus(row.id, note)
  onPlayerChanged(res.player)
  ElMessage.success('已删除该玩家剩余赠金')
}

async function remove(row: PlayerRow) {
  try {
    await ElMessageBox.confirm(
      `确定删除玩家「${row.game_id}」？押金必须为 0，历史流水会保留但不再显示。`,
      '删除玩家',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await playerApi.remove(row.id)
  if (draft.slotIndexOf(row.id) >= 0) {
    draft.togglePlayer(row.id)
  }
  ElMessage.success('已删除')
  reload()
  void loadSummary()
}

watch(keyword, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(reload, 320)
})

watch(
  () => route.query.keyword,
  (value) => {
    const text = typeof value === 'string' ? value : ''
    if (text !== keyword.value) keyword.value = text
  },
)

watch(
  () => route.query.level,
  (value) => {
    const next = parseLevel(value)
    if (next !== level.value) {
      level.value = next
      reload()
    }
  },
)

watch(
  () => app.posFocusSearchTick,
  async () => {
    await nextTick()
    searchInputRef.value?.focus()
    searchInputRef.value?.select()
  },
)

function handleQueryAction() {
  if (route.query.import === '1') {
    importVisible.value = true
    router.replace({ name: 'pos' })
  }
}

watch(
  () => route.query.import,
  () => handleQueryAction(),
)

watch(
  () => app.sessionTick,
  () => {
    void load()
    void loadSummary()
  },
)

watch(
  () => app.playerTick,
  () => {
    void load()
    void loadSummary()
  },
)

onMounted(async () => {
  await Promise.all([load(), loadSummary(), draft.loadMeta()])
  handleQueryAction()
})
</script>

<style scoped>
.pos-workbench {
  flex: 1;
  display: flex;
  align-items: stretch;
  min-height: calc(100vh - 42px);
}

.pos-main-pane {
  flex: 1;
  min-width: 0;
  padding: 16px 20px 36px;
  display: flex;
  flex-direction: column;
}

.pos-dock-pane {
  width: 382px;
  flex: none;
  border-left: 1px solid var(--app-border);
  position: sticky;
  top: 42px;
  height: calc(100vh - 42px);
}

.wb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.wb-title-group {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.wb-title {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.wb-metrics {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  color: var(--app-text-muted);
}

.wb-metrics b {
  color: var(--app-text-main);
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.wb-metrics .bonus-val {
  color: var(--app-primary);
}

.wb-metrics .sep {
  color: var(--app-border-strong);
}

.wb-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.expand-dock-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 11px;
  border-radius: var(--app-radius-sm);
  border: 1px solid var(--app-primary-ring);
  background: var(--app-primary-soft);
  color: var(--app-primary);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.ed-count {
  padding: 0 5px;
  border-radius: 999px;
  background: var(--app-primary);
  color: var(--app-on-primary);
  font-size: 11px;
  line-height: 16px;
}

.wb-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.pos-search-box {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: 248px;
  height: 30px;
  padding: 0 8px 0 10px;
  border-radius: var(--app-radius-sm);
  border: 1px solid var(--app-border-strong);
  background: var(--app-bg-panel);
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}

.pos-search-box:focus-within {
  border-color: var(--app-primary);
  box-shadow: 0 0 0 3px var(--app-primary-ring);
}

.ps-icon {
  color: var(--app-text-muted);
  font-size: 14px;
  margin-right: 6px;
  flex: none;
}

.ps-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--app-text-main);
  font: inherit;
  font-size: 13px;
}

.ps-input::placeholder {
  color: var(--app-text-faint);
}

.ps-clear {
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  font-size: 15px;
  cursor: pointer;
  padding: 0 2px;
}

.seg-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.seg-dot.low {
  background: var(--el-color-danger);
}

.seg-dot.warn {
  background: var(--el-color-warning);
}

.seg-dot.safe {
  background: var(--el-color-success);
}

.threshold-hint {
  font-size: 11.5px;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}

/* 桌面端高密度收银列表 */
.pos-list-panel {
  display: flex;
  flex-direction: column;
}

.pl-header,
.pl-row {
  display: grid;
  grid-template-columns: 82px minmax(180px, 1fr) 176px 64px 96px 218px;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
}

.pl-header {
  height: 36px;
  background: var(--app-bg-subtle);
  border-bottom: 1px solid var(--app-border);
  font-size: 11.5px;
  font-weight: 600;
  color: var(--app-text-muted);
  letter-spacing: 0.02em;
}

.pl-header .col-balance,
.pl-header .col-games,
.pl-header .col-ops {
  text-align: right;
}

.pl-row {
  padding-top: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--app-border);
  transition: background-color 0.12s ease;
}

.pl-row:last-child {
  border-bottom: none;
}

.pl-row:hover {
  background: var(--app-bg-hover);
}

.pl-row.in-cart {
  background: var(--app-primary-soft);
}

.pl-row.is-black {
  opacity: 0.68;
}

.board-btn {
  height: 26px;
  padding: 0 9px;
  border-radius: 6px;
  border: 1px solid var(--app-border-strong);
  background: var(--app-bg-subtle);
  color: var(--app-text-main);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.14s ease;
}

.board-btn:hover {
  border-color: var(--app-primary);
  color: var(--app-primary);
  background: var(--app-primary-soft);
}

.board-btn.active {
  border-color: var(--app-primary);
  background: var(--app-primary);
  color: var(--app-on-primary);
  font-variant-numeric: tabular-nums;
}

.board-btn.active:hover {
  background: var(--el-color-danger);
  border-color: var(--el-color-danger);
  color: #ffffff;
}

.board-disabled,
.board-free {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 7px;
  border-radius: 5px;
  font-size: 11px;
  background: var(--app-bg-subtle);
  color: var(--app-text-faint);
}

.col-player {
  min-width: 0;
}

.p-primary {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.p-name-btn {
  padding: 0;
  border: none;
  background: transparent;
  color: var(--app-text-main);
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

.p-name-btn:hover {
  color: var(--app-primary);
  text-decoration: underline;
}

.p-rank {
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border);
  font-size: 11px;
  color: var(--app-text-muted);
  white-space: nowrap;
}

.p-secondary {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--app-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-balance {
  text-align: right;
}

.col-games {
  text-align: right;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.col-active {
  font-size: 12px;
}

.col-ops {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
}

.cash-btn {
  height: 26px;
  padding: 0 9px;
  border-radius: 6px;
  border: 1px solid var(--app-border);
  background: var(--app-bg-subtle);
  color: var(--el-text-color-regular);
  font: inherit;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.12s ease;
}

.cash-btn:hover {
  border-color: var(--app-border-strong);
  color: var(--app-text-main);
  background: var(--app-bg-hover);
}

.cash-btn.add {
  border-color: rgba(52, 211, 153, 0.35);
  background: var(--app-success-soft);
  color: var(--el-color-success);
  font-weight: 600;
}

.cash-btn.add:hover {
  border-color: var(--el-color-success);
}

.cash-btn.refund:hover {
  border-color: var(--el-color-warning);
  color: var(--el-color-warning);
}

.cash-btn.in-slot {
  background: var(--app-primary);
  border-color: var(--app-primary);
  color: var(--app-on-primary);
}

.cash-btn.more {
  width: 26px;
  padding: 0;
  display: inline-grid;
  place-items: center;
}

.pl-footer {
  display: flex;
  justify-content: flex-end;
  padding: 10px 14px;
  border-top: 1px solid var(--app-border);
  background: var(--app-bg-panel);
}

/* 窄屏与移动端组局悬浮条 */
.compact-dock-bar {
  display: none;
}

.dock-drawer :deep(.el-drawer__body) {
  padding: 0;
}

@media (max-width: 1120px) {
  .desktop-wide-only {
    display: none !important;
  }

  .compact-dock-bar {
    display: block;
    position: fixed;
    right: 20px;
    bottom: 20px;
    z-index: 28;
  }

  .cdb-main {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    height: 42px;
    padding: 0 16px;
    border: none;
    border-radius: 999px;
    background: var(--app-primary);
    color: var(--app-on-primary);
    box-shadow: 0 8px 24px var(--app-primary-ring);
    font: inherit;
    font-size: 13px;
    font-weight: 650;
    cursor: pointer;
  }

  .cdb-badge {
    padding: 1px 7px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.22);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .cdb-go {
    opacity: 0.88;
    font-size: 12px;
  }
}

@media (max-width: 768px) {
  .pos-main-pane {
    padding: 12px 12px 124px;
  }

  .pos-search-box {
    flex: 1 1 100%;
    width: 100%;
  }

  .compact-dock-bar {
    left: 12px;
    right: 12px;
    bottom: 68px;
  }

  .cdb-main {
    width: 100%;
    justify-content: space-between;
  }

  .m-card {
    padding: 12px;
    border-radius: var(--app-radius-md);
    border: 1px solid var(--app-border);
    background: var(--app-bg-panel);
  }

  .m-card + .m-card {
    margin-top: 8px;
  }

  .mc-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }

  .mc-name {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 650;
    font-size: 14px;
  }

  .mc-meta {
    margin-top: 3px;
    font-size: 11.5px;
    color: var(--app-text-muted);
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .mc-actions {
    display: flex;
    gap: 6px;
    margin-top: 10px;
    flex-wrap: wrap;
  }

  .mc-actions .cash-btn {
    flex: 1;
    height: 30px;
  }

  .mc-actions .cash-btn.more {
    flex: none;
    width: 30px;
  }

  .m-pager {
    display: flex;
    justify-content: center;
    padding-top: 12px;
  }
}
</style>

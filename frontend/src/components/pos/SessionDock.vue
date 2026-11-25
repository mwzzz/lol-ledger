<template>
  <section class="session-dock" :class="{ embedded }">
    <!-- 顶部栏：标题 + 人数 + AI识图 + 收起 -->
    <header class="dock-head">
      <div class="dh-left">
        <span class="dock-title">当前组局</span>
        <span class="dock-count" :class="{ full: draft.filledCount === 10 }">
          {{ draft.filledCount }}/10
        </span>
      </div>
      <div class="dh-right">
        <button
          type="button"
          class="ai-trigger"
          title="AI 截图识别玩家（也可直接在收银台按 Ctrl+V 粘贴截图）"
          @click="aiModalVisible = true"
        >
          <el-icon><MagicStick /></el-icon>
          <span>AI 识图</span>
        </button>
        <button
          v-if="draft.filledCount > 0"
          type="button"
          class="text-btn danger"
          @click="draft.clearAll()"
        >
          清空
        </button>
        <button
          v-if="!embedded"
          type="button"
          class="collapse-btn"
          title="收起组局台"
          @click="emit('collapse')"
        >
          <el-icon><DArrowRight /></el-icon>
        </button>
      </div>
    </header>

    <!-- 快速搜索加入 -->
    <div class="dock-quick-add">
      <PlayerSelect
        ref="quickSelectRef"
        v-model="addingId"
        :exclude-ids="draft.filledIds"
        :tea-free-keys="draft.teaFreeKeys"
        placeholder="搜名字加入空位（或点左侧玩家 +上车）"
      />
    </div>

    <!-- 10 人槽位列表（分 1-5 / 6-10 两组） -->
    <div class="dock-slots">
      <div class="team-group">
        <div class="team-bar blue">
          <span>1–5 号位</span>
          <span class="muted">每人茶水 ¥{{ formatCents(draft.teaCents) }}</span>
        </div>
        <div
          v-for="idx in [0, 1, 2, 3, 4]"
          :key="idx"
          class="dock-slot"
          :class="slotStateClass(idx)"
        >
          <span class="slot-num">#{{ idx + 1 }}</span>

          <template v-if="draft.slots[idx] && itemAt(idx)">
            <div class="slot-filled">
              <div class="sf-top">
                <span class="sf-name" :title="itemAt(idx)!.game_id">{{ itemAt(idx)!.game_id }}</span>
                <span class="sf-after" :class="afterClass(itemAt(idx)!)">
                  扣后 ¥{{ formatCents(itemAt(idx)!.after_cents) }}
                </span>
              </div>
              <div class="sf-sub">
                <span>现余 ¥{{ formatCents(itemAt(idx)!.before_cents) }}</span>
                <span v-if="itemAt(idx)!.bonus_deduct_cents > 0" class="bonus-chip">
                  赠抵 ¥{{ formatCents(itemAt(idx)!.bonus_deduct_cents) }}
                </span>
                <button
                  v-if="itemAt(idx)!.negative || isLow(itemAt(idx)!)"
                  type="button"
                  class="topup-chip"
                  @click="emit('quickDeposit', itemAt(idx)!.player_id)"
                >
                  + 补押
                </button>
              </div>
            </div>
            <button
              type="button"
              class="slot-remove"
              title="移出本局"
              @click="draft.setSlot(idx, null)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </template>

          <template v-else>
            <div class="slot-picker">
              <PlayerSelect
                :model-value="draft.slots[idx]"
                :exclude-ids="draft.otherSelected(idx)"
                :tea-free-keys="draft.teaFreeKeys"
                :placeholder="draft.slots[idx] ? '校验中…' : '+ 选择玩家'"
                @update:model-value="(val) => draft.setSlot(idx, val)"
              />
            </div>
            <button
              v-if="draft.slots[idx]"
              type="button"
              class="slot-remove"
              @click="draft.setSlot(idx, null)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </template>
        </div>
      </div>

      <div class="team-group">
        <div class="team-bar red">
          <span>6–10 号位</span>
          <span class="muted">支持 Ctrl+V 粘截图</span>
        </div>
        <div
          v-for="idx in [5, 6, 7, 8, 9]"
          :key="idx"
          class="dock-slot"
          :class="slotStateClass(idx)"
        >
          <span class="slot-num">#{{ idx + 1 }}</span>

          <template v-if="draft.slots[idx] && itemAt(idx)">
            <div class="slot-filled">
              <div class="sf-top">
                <span class="sf-name" :title="itemAt(idx)!.game_id">{{ itemAt(idx)!.game_id }}</span>
                <span class="sf-after" :class="afterClass(itemAt(idx)!)">
                  扣后 ¥{{ formatCents(itemAt(idx)!.after_cents) }}
                </span>
              </div>
              <div class="sf-sub">
                <span>现余 ¥{{ formatCents(itemAt(idx)!.before_cents) }}</span>
                <span v-if="itemAt(idx)!.bonus_deduct_cents > 0" class="bonus-chip">
                  赠抵 ¥{{ formatCents(itemAt(idx)!.bonus_deduct_cents) }}
                </span>
                <button
                  v-if="itemAt(idx)!.negative || isLow(itemAt(idx)!)"
                  type="button"
                  class="topup-chip"
                  @click="emit('quickDeposit', itemAt(idx)!.player_id)"
                >
                  + 补押
                </button>
              </div>
            </div>
            <button
              type="button"
              class="slot-remove"
              title="移出本局"
              @click="draft.setSlot(idx, null)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </template>

          <template v-else>
            <div class="slot-picker">
              <PlayerSelect
                :model-value="draft.slots[idx]"
                :exclude-ids="draft.otherSelected(idx)"
                :tea-free-keys="draft.teaFreeKeys"
                :placeholder="draft.slots[idx] ? '校验中…' : '+ 选择玩家'"
                @update:model-value="(val) => draft.setSlot(idx, val)"
              />
            </div>
            <button
              v-if="draft.slots[idx]"
              type="button"
              class="slot-remove"
              @click="draft.setSlot(idx, null)"
            >
              <el-icon><Close /></el-icon>
            </button>
          </template>
        </div>
      </div>
    </div>

    <!-- 底部固定结算区 -->
    <footer class="dock-foot">
      <!-- 刚开完一局的防错一键撤回条 -->
      <div v-if="draft.lastCreated && draft.filledCount === 0" class="undo-bar">
        <div class="undo-info">
          <span class="undo-tag">刚开</span>
          <span class="undo-name">{{ draft.lastCreated.name }}</span>
          <span class="muted">
            {{ draft.lastCreated.player_count }}人 · ¥{{ formatCents(draft.lastCreated.tea_total_cents) }}
          </span>
        </div>
        <div class="undo-ops">
          <el-button
            link
            type="warning"
            size="small"
            :loading="draft.voiding"
            @click="draft.voidLastSession()"
          >
            撤回
          </el-button>
          <button type="button" class="undo-dismiss" title="关闭提示" @click="draft.lastCreated = null">
            ×
          </button>
        </div>
      </div>

      <!-- 风险告警条 -->
      <div v-if="draft.previewState === 'error'" class="dock-alert danger">
        <span>押金校验失败</span>
        <el-button link type="primary" size="small" @click="draft.schedulePreview(true)">重试</el-button>
      </div>
      <div v-else-if="draft.previewState === 'negative'" class="dock-alert danger">
        <span>
          {{ draft.preview?.negative_count }} 人将扣成负数：{{ draft.preview?.negative_players.join('、') }}
        </span>
      </div>
      <div v-else-if="draft.lowDepositPlayers.length" class="dock-alert warn">
        <span>押金偏低（低于茶水×11）：{{ draft.lowDepositPlayers.join('、') }}</span>
      </div>

      <div class="checkout-row">
        <div class="checkout-nums">
          <div class="cn-main">
            <span class="muted">茶水合计</span>
            <b>¥{{ formatCents(draft.teaTotalCents) }}</b>
          </div>
          <div class="cn-sub">
            <span>已选 {{ draft.filledCount }} 人</span>
            <span v-if="draft.bonusDeductTotal > 0" class="bonus-chip">
              含赠金抵 ¥{{ formatCents(draft.bonusDeductTotal) }}
            </span>
            <span v-else-if="draft.previewState === 'loading'">校验中…</span>
          </div>
        </div>
        <el-button
          type="primary"
          size="large"
          class="submit-btn"
          :loading="draft.saving"
          :disabled="!draft.canCreate"
          @click="onSubmit"
        >
          开局扣茶水
        </el-button>
      </div>
    </footer>

    <!-- AI 识图弹窗 -->
    <el-dialog
      v-model="aiModalVisible"
      title="AI 截图识别玩家"
      width="620px"
      append-to-body
      :close-on-click-modal="false"
    >
      <AiPlayerRecognition
        ref="aiRef"
        :active="aiModalVisible"
        :tea-free-keys="draft.teaFreeKeys"
        :tea-fee-cents="draft.teaCents"
        @apply="onAiApply"
      />
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { Close, DArrowRight, MagicStick } from '@element-plus/icons-vue'
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import AiPlayerRecognition from '@/components/batches/AiPlayerRecognition.vue'
import PlayerSelect from '@/components/common/PlayerSelect.vue'
import { useAppStore } from '@/stores/app'
import { type PreviewItem, useSessionDraftStore } from '@/stores/sessionDraft'
import { formatCents } from '@/utils/money'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

const emit = defineEmits<{
  (event: 'collapse'): void
  (event: 'quickDeposit', playerId: number): void
  (event: 'submitted'): void
}>()

const app = useAppStore()
const draft = useSessionDraftStore()

const addingId = ref<number | null>(null)
const aiModalVisible = ref(false)
const quickSelectRef = ref<{ focus?: () => void } | null>(null)
const aiRef = ref<{ recognizeFile?: (file: File) => Promise<void> } | null>(null)

watch(addingId, (val) => {
  if (!val) return
  draft.addPlayer(val)
  addingId.value = null
})

watch(
  () => app.posFocusDockTick,
  async () => {
    await nextTick()
    quickSelectRef.value?.focus?.()
  },
)

function itemAt(idx: number): PreviewItem | null {
  const id = draft.slots[idx]
  if (!id) return null
  return draft.previewMap.get(id) || null
}

function isLow(item: PreviewItem): boolean {
  return Boolean(draft.teaCents) && item.before_cents < draft.teaCents * 11
}

function slotStateClass(idx: number) {
  const id = draft.slots[idx]
  if (!id) return 'is-empty'
  const item = draft.previewMap.get(id)
  if (!item) return 'is-filled'
  if (item.negative) return 'is-filled is-danger'
  if (isLow(item)) return 'is-filled is-warn'
  return 'is-filled'
}

function afterClass(item: PreviewItem) {
  if (item.negative) return 'danger'
  if (isLow(item)) return 'warn'
  return 'ok'
}

async function onAiApply(ids: number[], meta?: { auto: boolean; hasPending: boolean }) {
  await draft.applyAiPlayers(ids, !meta?.auto)
  // 自动预填时：若还有未匹配或候选待确认的玩家，保持弹窗打开以便店员直接点「+ 新建并选用」
  if (!meta?.auto || !meta.hasPending) {
    aiModalVisible.value = false
  }
}

async function onSubmit() {
  const ok = await draft.submit()
  if (ok) emit('submitted')
}

// 在收银台界面直接按 Ctrl+V 粘贴截图时，自动弹出 AI 识图弹窗并开始识别
function onGlobalPaste(event: ClipboardEvent) {
  if (aiModalVisible.value) return
  if (props.embedded && !app.mobileDockVisible) return
  if (document.querySelector('.el-overlay:not([style*="display: none"])')) return
  const target = event.target as HTMLElement | null
  if (target?.closest('input, textarea, [contenteditable="true"]')) return

  const file = Array.from(event.clipboardData?.files || []).find((item) =>
    item.type.startsWith('image/'),
  )
  if (!file) return
  event.preventDefault()
  aiModalVisible.value = true
  void nextTick(() => {
    setTimeout(() => {
      void aiRef.value?.recognizeFile?.(file)
    }, 60)
  })
}

onMounted(() => {
  void draft.loadMeta()
  if (!props.embedded) {
    window.addEventListener('paste', onGlobalPaste)
  }
})

onUnmounted(() => {
  if (!props.embedded) {
    window.removeEventListener('paste', onGlobalPaste)
  }
})
</script>

<style scoped>
.session-dock {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-bg-panel);
}

.dock-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px 10px;
  border-bottom: 1px solid var(--app-border);
}

.dh-left,
.dh-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.dock-title {
  font-size: 14.5px;
  font-weight: 650;
  color: var(--app-text-main);
}

.dock-count {
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border);
  font-size: 11.5px;
  font-weight: 600;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}

.dock-count.full {
  background: var(--app-primary-soft);
  border-color: var(--app-primary-ring);
  color: var(--app-primary);
}

.ai-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 9px;
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

.ai-trigger:hover {
  background: var(--app-bg-active);
}

.text-btn {
  border: none;
  background: transparent;
  padding: 2px 5px;
  border-radius: 5px;
  font: inherit;
  font-size: 12px;
  color: var(--app-text-muted);
  cursor: pointer;
}

.text-btn.danger:hover {
  color: var(--el-color-danger);
  background: var(--app-danger-soft);
}

.collapse-btn {
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--app-text-muted);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.collapse-btn:hover {
  background: var(--app-bg-hover);
  color: var(--app-text-main);
}

.dock-quick-add {
  padding: 10px 14px 8px;
}

.dock-slots {
  flex: 1;
  overflow-y: auto;
  padding: 4px 14px 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.team-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.team-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  padding-left: 7px;
  border-left: 2.5px solid var(--app-border-strong);
  color: var(--app-text-muted);
}

.team-bar.blue {
  border-left-color: var(--app-primary);
}

.team-bar.red {
  border-left-color: var(--el-color-danger);
}

.dock-slot {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 40px;
  padding: 4px 7px 4px 6px;
  border-radius: 8px;
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border);
  transition: border-color 0.14s ease, background 0.14s ease;
}

.dock-slot.is-empty {
  border-style: dashed;
  min-height: 36px;
  padding-top: 2px;
  padding-bottom: 2px;
}

.dock-slot.is-empty :deep(.el-select__wrapper) {
  box-shadow: none !important;
  background: transparent !important;
  min-height: 28px;
  padding: 2px 6px;
}

.dock-slot.is-danger {
  border-color: rgba(248, 113, 113, 0.5);
  background: var(--app-danger-soft);
}

.dock-slot.is-warn {
  border-color: rgba(245, 181, 68, 0.45);
  background: var(--app-warning-soft);
}

.slot-num {
  width: 24px;
  flex: none;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--app-text-faint);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.slot-picker {
  flex: 1;
  min-width: 0;
}

.slot-filled {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sf-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}

.sf-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-main);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sf-after {
  font-size: 11.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.sf-after.ok {
  color: var(--el-color-success);
}

.sf-after.warn {
  color: var(--el-color-warning);
}

.sf-after.danger {
  color: var(--el-color-danger);
}

.sf-sub {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}

.bonus-chip {
  color: var(--app-primary);
  font-weight: 500;
}

.topup-chip {
  margin-left: auto;
  padding: 0 6px;
  height: 18px;
  border-radius: 4px;
  border: 1px solid currentColor;
  background: transparent;
  color: var(--app-primary);
  font: inherit;
  font-size: 10.5px;
  font-weight: 600;
  cursor: pointer;
}

.topup-chip:hover {
  background: var(--app-primary-soft);
}

.slot-remove {
  width: 22px;
  height: 22px;
  flex: none;
  border: none;
  border-radius: 5px;
  background: transparent;
  color: var(--app-text-muted);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.slot-remove:hover {
  background: var(--app-danger-soft);
  color: var(--el-color-danger);
}

.dock-foot {
  padding: 10px 14px 12px;
  border-top: 1px solid var(--app-border);
  background: var(--app-bg-panel);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.undo-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 6px 9px;
  border-radius: 7px;
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border-strong);
  font-size: 11.5px;
}

.undo-info {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  overflow: hidden;
}

.undo-tag {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--app-success-soft);
  color: var(--el-color-success);
  font-size: 10.5px;
  font-weight: 600;
  flex: none;
}

.undo-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.undo-ops {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: none;
}

.undo-dismiss {
  border: none;
  background: transparent;
  color: var(--app-text-muted);
  cursor: pointer;
  font-size: 14px;
  padding: 0 3px;
}

.dock-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 6px 9px;
  border-radius: 7px;
  font-size: 11.5px;
  line-height: 1.45;
}

.dock-alert.danger {
  background: var(--app-danger-soft);
  border: 1px solid rgba(248, 113, 113, 0.35);
  color: var(--el-color-danger);
}

.dock-alert.warn {
  background: var(--app-warning-soft);
  border: 1px solid rgba(245, 181, 68, 0.35);
  color: var(--el-color-warning);
}

.checkout-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.checkout-nums {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.cn-main {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.cn-main b {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--app-text-main);
  font-variant-numeric: tabular-nums;
}

.cn-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  color: var(--app-text-muted);
}

.submit-btn {
  min-width: 124px;
  font-weight: 650;
}
</style>

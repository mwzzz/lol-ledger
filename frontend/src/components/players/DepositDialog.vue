<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="460px"
    :close-on-click-modal="false"
    @opened="focusAmount"
    @update:model-value="close"
  >
    <div v-if="player" class="who">
      <div class="who-row">
        <span class="name">{{ player.game_id }}</span>
        <DepositBadge
          :cents="player.balance_cents"
          :deposit-cents="player.deposit_cents"
          :bonus-cents="player.bonus_cents"
          :level="player.deposit_level"
        />
      </div>
      <div class="who-meta">
        <span>现金押金 ¥{{ formatCents(player.deposit_cents) }}</span>
        <span>赠金 ¥{{ formatCents(player.bonus_cents) }}</span>
      </div>
    </div>

    <div v-if="mode === 'refund' && hasBonus" class="blocked-tip">
      该玩家还有赠金 ¥{{ formatCents(player?.bonus_cents || 0) }}，赠金不参与退款；
      本次最多可退现金押金 ¥{{ formatCents(player?.deposit_cents || 0) }}。
    </div>

    <!-- 收银快捷金额键 -->
    <div v-if="quickPresets.length" class="preset-section">
      <div class="preset-label">快捷金额</div>
      <div class="preset-grid">
        <button
          v-for="preset in quickPresets"
          :key="preset.key"
          type="button"
          class="preset-chip"
          :class="{ active: parsed === preset.cents, campaign: Boolean(preset.giftCents) }"
          @click="pickPreset(preset.cents)"
        >
          <span class="pc-main">{{ preset.label }}</span>
          <span v-if="preset.giftCents" class="pc-gift">送 ¥{{ formatCents(preset.giftCents) }}</span>
        </button>
      </div>
    </div>

    <el-form label-width="64px" class="form" @submit.prevent="submit">
      <el-form-item label="金额">
        <el-input
          ref="amountInputRef"
          v-model="amount"
          size="large"
          placeholder="0.00（按回车直接提交）"
          autocomplete="off"
          @keyup.enter="submit"
        >
          <template #prefix>¥</template>
        </el-input>
      </el-form-item>
      <el-form-item label="备注">
        <el-input
          v-model="note"
          placeholder="选填（按回车直接提交）"
          maxlength="200"
          @keyup.enter="submit"
        />
      </el-form-item>
    </el-form>

    <div v-if="mode === 'bonus'" class="bonus-tip">
      赠金不计入现金收款，且<b>不能退款、不能划押</b>，只能用于扣茶水。
      如果只是要收押金，请改用「加押金」。
    </div>

    <div v-if="mode === 'add'" class="campaign-line">
      <span v-if="campaignLoading" class="muted">正在读取充值活动…</span>
      <span v-else-if="campaignError" class="warn">
        活动信息读取失败，本笔赠送金额以提交后的结果为准
      </span>
      <span v-else-if="matchedCampaign" class="matched-gift">
        已命中活动：充满 ¥{{ formatCents(matchedCampaign.threshold_cents) }} 自动赠送
        <b>¥{{ formatCents(matchedCampaign.bonus_cents) }}</b>
      </span>
      <span v-else-if="campaigns.length && parsed !== null" class="muted">
        本笔未达到充值活动门槛
      </span>
    </div>

    <div class="preview">
      <span v-if="error" class="error">{{ error }}</span>
      <span v-else-if="after !== null">
        变动后余额
        <b :class="after < 0 ? 'negative' : 'after-val'">
          ¥{{ formatBalance(after, afterBonus, afterDeposit) }}
        </b>
        <span v-if="after < 0" class="negative-hint">（会变成负数）</span>
      </span>
      <span v-else class="muted">{{ hint }}</span>
    </div>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button
        :type="mode === 'bonus' ? 'warning' : 'primary'"
        :loading="saving"
        :disabled="Boolean(error)"
        @click="submit"
      >
        确认（Enter）
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, ref, watch } from 'vue'

import { campaignApi, moneyApi } from '@/api'
import type { PlayerRow, RechargeCampaign } from '@/api/types'
import DepositBadge from '@/components/common/DepositBadge.vue'
import { formatBalance, formatCents, formatYuanShort, parseYuan } from '@/utils/money'

const props = defineProps<{
  modelValue: boolean
  player: PlayerRow | null
  mode: 'add' | 'refund' | 'bonus'
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'saved', value: PlayerRow): void
}>()

const amountInputRef = ref<{ focus?: () => void; select?: () => void } | null>(null)
const amount = ref('')
const note = ref('')
const saving = ref(false)
const campaigns = ref<RechargeCampaign[]>([])
const campaignLoading = ref(false)
const campaignError = ref(false)

const title = computed(() => {
  if (props.mode === 'add') return '收银 · 加押金'
  if (props.mode === 'refund') return '收银 · 退押金'
  return '加赠金'
})

const hint = computed(() => {
  if (props.mode === 'add') return '金额必须大于 0，达到活动档位会自动送赠金'
  if (props.mode === 'refund') return '不能超过当前现金押金'
  return '赠金只能用于扣茶水，不能退款或划押'
})

const parsed = computed(() => parseYuan(amount.value))

interface QuickPreset {
  key: string
  cents: number
  label: string
  giftCents?: number
}

const quickPresets = computed<QuickPreset[]>(() => {
  if (props.mode === 'add') {
    const map = new Map<number, number>()
    for (const c of campaigns.value) {
      map.set(c.threshold_cents, c.bonus_cents)
    }
    const baseCents = [3000, 5000, 10000, 20000, 50000]
    const merged = new Set<number>([...baseCents, ...campaigns.value.map((c) => c.threshold_cents)])
    return [...merged]
      .filter((c) => c > 0)
      .sort((a, b) => a - b)
      .slice(0, 8)
      .map((cents) => {
        // 计算该金额命中的最高档赠金
        const matched = campaigns.value
          .filter((item) => item.threshold_cents <= cents)
          .sort((a, b) => b.threshold_cents - a.threshold_cents)[0]
        return {
          key: `add-${cents}`,
          cents,
          label: `¥${formatYuanShort(cents)}`,
          giftCents: matched ? matched.bonus_cents : map.get(cents),
        }
      })
  }
  if (props.mode === 'refund' && props.player && props.player.deposit_cents > 0) {
    const max = props.player.deposit_cents
    const list: QuickPreset[] = [{ key: 'all', cents: max, label: `全退 ¥${formatCents(max)}` }]
    for (const c of [2000, 5000, 10000]) {
      if (c < max) list.push({ key: `ref-${c}`, cents: c, label: `¥${formatYuanShort(c)}` })
    }
    return list
  }
  if (props.mode === 'bonus') {
    return [1000, 2000, 5000, 10000].map((cents) => ({
      key: `bon-${cents}`,
      cents,
      label: `¥${formatYuanShort(cents)}`,
    }))
  }
  return []
})

function pickPreset(cents: number) {
  amount.value = formatYuanShort(cents)
  void nextTick(() => amountInputRef.value?.focus?.())
}

function focusAmount() {
  amountInputRef.value?.focus?.()
  amountInputRef.value?.select?.()
}

const matchedCampaign = computed(() => {
  if (props.mode !== 'add' || parsed.value === null) return null
  const matched = campaigns.value
    .filter((item) => item.threshold_cents <= parsed.value!)
    .sort((a, b) => b.threshold_cents - a.threshold_cents)
  return matched[0] || null
})

const estimatedBonus = computed(() =>
  props.mode === 'add' ? matchedCampaign.value?.bonus_cents || 0 : 0,
)

const hasBonus = computed(() => (props.player?.bonus_cents || 0) > 0)

const after = computed(() => {
  if (parsed.value === null || !props.player) return null
  if (props.mode === 'add') {
    return props.player.balance_cents + parsed.value + estimatedBonus.value
  }
  if (props.mode === 'refund') {
    return props.player.deposit_cents - parsed.value
  }
  return props.player.balance_cents + parsed.value
})

const afterDeposit = computed(() => {
  if (parsed.value === null || !props.player) return 0
  if (props.mode === 'add') return props.player.deposit_cents + parsed.value
  if (props.mode === 'refund') return props.player.deposit_cents - parsed.value
  return props.player.deposit_cents
})

const afterBonus = computed(() => {
  if (parsed.value === null || !props.player) return 0
  if (props.mode === 'add') return props.player.bonus_cents + estimatedBonus.value
  if (props.mode === 'refund') return props.player.bonus_cents
  return props.player.bonus_cents + parsed.value
})

const error = computed(() => {
  if (!amount.value.trim()) return ''
  if (parsed.value === null) return '金额格式不正确，最多两位小数'
  if (parsed.value <= 0) return '金额必须大于 0'
  if (
    props.mode === 'refund' &&
    props.player &&
    parsed.value > props.player.deposit_cents
  ) {
    return '现金押金不足，不能退这么多'
  }
  return ''
})

async function loadCampaigns() {
  if (props.mode !== 'add') return
  campaignLoading.value = true
  campaignError.value = false
  try {
    campaigns.value = await campaignApi.list()
  } catch {
    campaigns.value = []
    campaignError.value = true
  } finally {
    campaignLoading.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return
    note.value = ''
    campaignError.value = false
    campaigns.value = []
    if (props.mode === 'refund' && props.player && props.player.deposit_cents > 0) {
      amount.value = formatCents(props.player.deposit_cents)
    } else {
      amount.value = ''
    }
    void loadCampaigns()
  },
)

function close() {
  emit('update:modelValue', false)
}

async function submit() {
  if (saving.value) return
  const cents = parsed.value
  if (cents === null) {
    ElMessage.warning('请输入正确的金额')
    return
  }
  if (error.value) {
    ElMessage.warning(error.value)
    return
  }
  if (!props.player) return

  if (props.mode === 'bonus') {
    try {
      await ElMessageBox.confirm(
        `确认为 ${props.player.game_id} 加赠金 ¥${formatCents(cents)}？` +
          '赠金不计入现金收款，且不可退款、不可划押。',
        '确认加赠金',
        {
          type: 'warning',
          confirmButtonText: '确认加赠金',
          cancelButtonText: '取消',
        },
      )
    } catch {
      return
    }
  }

  saving.value = true
  try {
    const playerId = props.player.id
    if (props.mode === 'add') {
      const result = await moneyApi.addDeposit(playerId, cents, note.value.trim())
      ElMessage.success(
        result.bonus_entry
          ? `加押金成功，自动赠送 ¥${formatCents(result.bonus_entry.amount_cents)}`
          : '加押金成功',
      )
      emit('saved', result.player)
    } else if (props.mode === 'refund') {
      const result = await moneyApi.refund(playerId, cents, note.value.trim())
      ElMessage.success('退押金成功')
      emit('saved', result.player)
    } else {
      const result = await moneyApi.addBonus(playerId, cents, note.value.trim())
      ElMessage.success('加赠金成功')
      emit('saved', result.player)
    }
    close()
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.who {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 11px 14px;
  margin-bottom: 14px;
  background: var(--app-bg-subtle);
  border: 1px solid var(--app-border-strong);
  border-radius: 10px;
}

.who-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.who-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: var(--app-text-muted);
  font-variant-numeric: tabular-nums;
}

.name {
  font-weight: 650;
  font-size: 15px;
}

.preset-section {
  margin-bottom: 14px;
}

.preset-label {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--app-text-muted);
  margin-bottom: 6px;
}

.preset-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.preset-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 11px;
  border-radius: 8px;
  border: 1px solid var(--app-border-strong);
  background: var(--app-bg-subtle);
  color: var(--app-text-main);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: border-color 0.14s ease, background 0.14s ease, color 0.14s ease;
}

.preset-chip:hover {
  border-color: var(--app-primary);
}

.preset-chip.active {
  background: var(--app-primary-soft);
  border-color: var(--app-primary);
  color: var(--app-primary);
}

.pc-gift {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--app-success-soft);
  color: var(--el-color-success);
  font-size: 11px;
  font-weight: 600;
}

.blocked-tip,
.bonus-tip {
  margin-bottom: 14px;
  padding: 9px 11px;
  border: 1px solid rgba(245, 181, 68, 0.35);
  background: var(--app-warning-soft);
  border-radius: 8px;
  font-size: 12px;
  color: var(--el-color-warning);
  line-height: 1.6;
}

.form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.campaign-line {
  min-height: 18px;
  padding-left: 64px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--app-primary);
  line-height: 1.5;
}

.matched-gift {
  color: var(--el-color-success);
}

.preview {
  min-height: 22px;
  padding-left: 64px;
  font-size: 12.5px;
  color: var(--el-text-color-regular);
  font-variant-numeric: tabular-nums;
}

.after-val {
  color: var(--app-text-main);
  font-size: 14px;
}

.error {
  color: var(--el-color-danger);
}

.warn {
  color: var(--el-color-warning);
}

.negative {
  color: var(--el-color-danger);
  font-weight: 600;
}

.negative-hint {
  color: var(--el-color-danger);
  margin-left: 4px;
}
</style>

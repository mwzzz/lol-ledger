import { ElMessage, ElMessageBox } from 'element-plus'
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import { sessionApi, settingsApi, toolListApi } from '@/api'
import type { PreviewPayload } from '@/api/types'
import { useAppStore } from '@/stores/app'
import { formatCents } from '@/utils/money'
import { nameKey } from '@/utils/names'

export type PreviewState = 'idle' | 'loading' | 'error' | 'safe' | 'negative'
export type PreviewItem = PreviewPayload['items'][number]

export interface LastCreatedSession {
  id: number
  name: string
  player_count: number
  tea_fee_cents: number
  tea_total_cents: number
}

export const useSessionDraftStore = defineStore('sessionDraft', () => {
  const slots = ref<(number | null)[]>(Array(10).fill(null))
  const teaCents = ref(200)
  const teaFreeKeys = ref<string[]>([])
  const preview = ref<PreviewPayload | null>(null)
  const previewLoading = ref(false)
  const previewError = ref(false)
  const saving = ref(false)
  const voiding = ref(false)
  const metaLoaded = ref(false)
  const lastCreated = ref<LastCreatedSession | null>(null)

  let previewTimer: number | undefined
  let previewSeq = 0

  const filledIds = computed(() =>
    slots.value.filter((item): item is number => typeof item === 'number' && item > 0),
  )
  const filledCount = computed(() => filledIds.value.length)
  const teaTotalCents = computed(() => teaCents.value * filledCount.value)

  const bonusDeductTotal = computed(
    () => preview.value?.items.reduce((sum, item) => sum + item.bonus_deduct_cents, 0) || 0,
  )

  const lowDepositPlayers = computed(() => {
    if (!preview.value || !teaCents.value) return []
    const threshold = teaCents.value * 11
    return preview.value.items
      .filter((item) => item.before_cents < threshold)
      .map((item) => item.game_id)
  })

  const previewMap = computed(() => {
    const map = new Map<number, PreviewItem>()
    for (const item of preview.value?.items || []) {
      map.set(item.player_id, item)
    }
    return map
  })

  const previewState = computed<PreviewState>(() => {
    if (!filledCount.value) return 'idle'
    if (previewLoading.value) return 'loading'
    if (previewError.value || !preview.value) return 'error'
    return preview.value.negative_count > 0 ? 'negative' : 'safe'
  })

  const previewReady = computed(
    () => previewState.value === 'safe' || previewState.value === 'negative',
  )
  const canCreate = computed(
    () => filledCount.value > 0 && previewReady.value && !saving.value,
  )

  function slotIndexOf(playerId: number): number {
    return slots.value.findIndex((id) => id === playerId)
  }

  function otherSelected(index: number): number[] {
    return slots.value.filter(
      (item, position): item is number => Boolean(item) && position !== index,
    )
  }

  function setSlot(index: number, playerId: number | null) {
    if (index < 0 || index >= 10) return
    slots.value[index] = playerId
  }

  function addPlayer(playerId: number): boolean {
    if (slotIndexOf(playerId) >= 0) {
      ElMessage.info('该玩家已在当前组局中')
      return false
    }
    const emptyIdx = slots.value.findIndex((item) => !item)
    if (emptyIdx < 0) {
      ElMessage.warning('当前组局已满 10 人')
      return false
    }
    slots.value[emptyIdx] = playerId
    return true
  }

  function togglePlayer(playerId: number) {
    const existing = slotIndexOf(playerId)
    if (existing >= 0) {
      slots.value[existing] = null
      return
    }
    addPlayer(playerId)
  }

  function clearAll() {
    slots.value = Array(10).fill(null)
  }

  async function applyAiPlayers(ids: number[], silentNoOp = false) {
    const unique = [...new Set(ids)].slice(0, 10)
    if (!unique.length) return

    const existing = new Set(filledIds.value)
    const fresh = unique.filter((id) => !existing.has(id))
    if (!fresh.length) {
      if (!silentNoOp) ElMessage.info('识别到的人已经在组局台里了')
      return
    }

    const emptySlots = slots.value
      .map((value, index) => (value === null ? index : -1))
      .filter((index) => index >= 0)

    if (fresh.length <= emptySlots.length) {
      fresh.forEach((id, position) => {
        slots.value[emptySlots[position]] = id
      })
      ElMessage.success(`已填入 ${fresh.length} 个玩家`)
      return
    }

    try {
      await ElMessageBox.confirm(
        `识别出 ${unique.length} 人，但当前只剩 ${emptySlots.length} 个空位，是否用识别结果覆盖已选玩家？`,
        '覆盖当前选择',
        { confirmButtonText: '覆盖', cancelButtonText: '不覆盖', type: 'warning' },
      )
    } catch {
      return
    }
    const next = Array<(number | null)>(10).fill(null)
    unique.forEach((id, position) => {
      next[position] = id
    })
    slots.value = next
    ElMessage.success(`已填入 ${unique.length} 个玩家`)
  }

  async function loadMeta(force = false) {
    if (metaLoaded.value && !force) return
    try {
      const [settings, listData] = await Promise.all([
        settingsApi.get().catch(() => null),
        toolListApi.list().catch(() => null),
      ])
      if (settings && Number.isFinite(settings.last_tea_cents)) {
        teaCents.value = settings.last_tea_cents
      }
      if (listData) {
        const list = listData.lists.find((item) => item.name === '免茶水')
        teaFreeKeys.value = (list?.items || [])
          .map((item) => nameKey(item.content))
          .filter(Boolean)
      }
      metaLoaded.value = true
    } catch {
      // keep safe defaults
    }
  }

  async function runPreview(seq: number) {
    try {
      const payload = await sessionApi.preview(filledIds.value, teaCents.value)
      if (seq !== previewSeq) return
      preview.value = payload
    } catch {
      if (seq !== previewSeq) return
      preview.value = null
      previewError.value = true
    } finally {
      if (seq === previewSeq) previewLoading.value = false
    }
  }

  function schedulePreview(immediate = false) {
    window.clearTimeout(previewTimer)
    previewSeq += 1
    const seq = previewSeq
    previewError.value = false
    if (!filledCount.value) {
      preview.value = null
      previewLoading.value = false
      return
    }
    previewLoading.value = true
    if (immediate) {
      void runPreview(seq)
    } else {
      previewTimer = window.setTimeout(() => void runPreview(seq), 240)
    }
  }

  function refreshPreviewIfNeeded() {
    if (filledCount.value > 0) {
      schedulePreview(true)
    }
  }

  watch([() => filledIds.value.join(','), teaCents], () => schedulePreview())

  async function submit(): Promise<boolean> {
    if (!filledCount.value) {
      ElMessage.warning('请至少选择 1 个玩家')
      return false
    }
    if (!previewReady.value) {
      ElMessage.warning(
        previewState.value === 'loading' ? '正在校验押金，请稍候' : '押金校验失败，请先重试',
      )
      return false
    }
    if (preview.value && preview.value.negative_count > 0) {
      try {
        await ElMessageBox.confirm(
          `有 ${preview.value.negative_count} 人会扣成负数：${preview.value.negative_players.join('、')}。仍要创建吗？`,
          '押金会变成负数',
          { confirmButtonText: '仍然创建', cancelButtonText: '先去补押金', type: 'warning' },
        )
      } catch {
        return false
      }
    }

    saving.value = true
    try {
      const created = await sessionApi.create({
        tea_fee_cents: teaCents.value,
        player_ids: filledIds.value,
      })
      if (created.tea_free_removed?.length) {
        ElMessage.info(`已自动去掉免茶水玩家：${created.tea_free_removed.join('、')}`)
      }
      lastCreated.value = {
        id: created.id,
        name: created.name,
        player_count: created.player_count,
        tea_fee_cents: created.tea_fee_cents,
        tea_total_cents: created.tea_total_cents,
      }
      clearAll()
      ElMessage.success(`已开局：${created.name}`)
      const app = useAppStore()
      app.notifySessionCreated()
      return true
    } finally {
      saving.value = false
    }
  }

  async function voidLastSession() {
    const target = lastCreated.value
    if (!target || voiding.value) return
    try {
      await ElMessageBox.confirm(
        `确定撤回刚创建的「${target.name}」？将删除该场次并原路退回 ${target.player_count} 名玩家的押金与局数（每人 ¥${formatCents(target.tea_fee_cents)}），不产生加押/退押流水。`,
        '撤回刚开的这一局',
        { confirmButtonText: '确认撤回', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
    voiding.value = true
    try {
      await sessionApi.void(target.id)
      lastCreated.value = null
      ElMessage.success('已撤回该局，玩家余额已恢复')
      const app = useAppStore()
      app.notifySessionCreated()
    } finally {
      voiding.value = false
    }
  }

  function resetAll() {
    clearAll()
    lastCreated.value = null
    metaLoaded.value = false
  }

  return {
    slots,
    teaCents,
    teaFreeKeys,
    preview,
    previewLoading,
    previewError,
    saving,
    voiding,
    lastCreated,
    filledIds,
    filledCount,
    teaTotalCents,
    bonusDeductTotal,
    lowDepositPlayers,
    previewMap,
    previewState,
    previewReady,
    canCreate,
    slotIndexOf,
    otherSelected,
    setSlot,
    addPlayer,
    togglePlayer,
    clearAll,
    applyAiPlayers,
    loadMeta,
    schedulePreview,
    refreshPreviewIfNeeded,
    submit,
    voidLastSession,
    resetAll,
  }
})

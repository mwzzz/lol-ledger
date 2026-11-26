import { defineStore } from 'pinia'

import { overviewApi, summaryApi } from '@/api'
import type { SummaryTotals } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { todayText } from '@/utils/datetime'
import { getThemeMeta, normalizeTheme, THEMES, type ThemeId } from '@/utils/themes'

const THEME_KEY = 'lol_theme'
const SUMMARY_RANGE_KEY = 'lol_summary_range'

const MOMENT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/
const MINUTE_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/
const DAY_RE = /^\d{4}-\d{2}-\d{2}$/

const pad2 = (n: number) => String(n).padStart(2, '0')
function minuteText(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

interface StoredSummaryRange {
  range: [string, string]
  savedDay: string
}

function readSummaryRange(): StoredSummaryRange | null {
  try {
    const raw = localStorage.getItem(SUMMARY_RANGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (
      parsed &&
      typeof parsed === 'object' &&
      !Array.isArray(parsed) &&
      typeof parsed.savedDay === 'string' &&
      DAY_RE.test(parsed.savedDay) &&
      Array.isArray(parsed.range) &&
      parsed.range.length === 2 &&
      typeof parsed.range[0] === 'string' &&
      typeof parsed.range[1] === 'string' &&
      MOMENT_RE.test(parsed.range[0]) &&
      MOMENT_RE.test(parsed.range[1])
    ) {
      return { range: [parsed.range[0], parsed.range[1]], savedDay: parsed.savedDay }
    }
  } catch {
    // 脏数据或旧版无日期格式直接忽略，触发重新计算区间
  }
  return null
}

const initialStoredSummaryRange = readSummaryRange()

export const useAppStore = defineStore('app', {
  state: () => ({
    theme: normalizeTheme(localStorage.getItem(THEME_KEY)) as ThemeId,
    summaryRange: (initialStoredSummaryRange?.range ?? null) as [string, string] | null,
    summaryRangeDay: (initialStoredSummaryRange?.savedDay ?? null) as string | null,
    changelogVisible: false,
    passwordDialogVisible: false,
    posFocusSearchTick: 0,
    today: null as SummaryTotals | null,
    todayLoaded: false,
    todayLoading: false,
    todayError: false,
    clockedIn: false,
    shiftStartText: null as string | null,
    shiftStale: false,
    myShift: null as SummaryTotals | null,
    myShiftLoading: false,
    sessionDialogVisible: false,
    sessionTick: 0,
    playerTick: 0,
  }),
  actions: {
    applyTheme() {
      const meta = getThemeMeta(this.theme)
      const root = document.documentElement
      root.classList.toggle('dark', meta.isDark)
      root.setAttribute('data-theme', meta.id)
    },
    setTheme(id: ThemeId) {
      this.theme = normalizeTheme(id)
      try {
        localStorage.setItem(THEME_KEY, this.theme)
      } catch {
        // ignore storage quota errors
      }
      this.applyTheme()
    },
    toggleTheme() {
      const idx = THEMES.findIndex((t) => t.id === this.theme)
      const next = THEMES[(idx + 1) % THEMES.length]
      this.setTheme(next.id)
    },
    requestFocusSearch() {
      this.posFocusSearchTick += 1
    },
    openSessionDialog() {
      this.sessionDialogVisible = true
    },
    notifySessionCreated() {
      this.sessionTick += 1
      void this.refreshToday()
      void this.refreshMyShift()
    },
    notifyPlayerCreated() {
      this.playerTick += 1
    },
    getTodaySummaryRange(): [string, string] | null {
      const today = todayText()
      if (this.summaryRange && this.summaryRangeDay === today) {
        return this.summaryRange
      }
      const stored = readSummaryRange()
      if (stored && stored.savedDay === today) {
        this.summaryRange = stored.range
        this.summaryRangeDay = stored.savedDay
        return stored.range
      }
      return null
    },
    setSummaryRange(range: [string, string]) {
      const savedDay = todayText()
      this.summaryRange = range
      this.summaryRangeDay = savedDay
      try {
        localStorage.setItem(SUMMARY_RANGE_KEY, JSON.stringify({ range, savedDay }))
      } catch {
        // 存储写满等异常不影响本次会话内记忆
      }
    },
    async refreshToday() {
      this.todayLoading = true
      this.todayError = false
      try {
        const payload = await overviewApi.get()
        this.today = payload.today
      } catch {
        this.today = null
        this.todayError = true
      } finally {
        this.todayLoading = false
        this.todayLoaded = true
      }
    },
    clockIn() {
      const auth = useAuthStore()
      if (!auth.user || auth.isSuperadmin) return
      localStorage.setItem(`lol_shift_start_${auth.user.id}`, minuteText(new Date()))
      void this.refreshMyShift()
    },
    async refreshMyShift() {
      const auth = useAuthStore()
      if (!auth.user || auth.isSuperadmin) {
        this.clockedIn = false
        this.shiftStartText = null
        this.shiftStale = false
        this.myShift = null
        return
      }
      const raw = localStorage.getItem(`lol_shift_start_${auth.user.id}`)
      const clockIn = raw && MINUTE_RE.test(raw) ? raw : null
      if (!clockIn) {
        this.clockedIn = false
        this.shiftStartText = null
        this.shiftStale = false
        this.myShift = null
        return
      }
      this.clockedIn = true
      const floor = minuteText(new Date(Date.now() - 24 * 3600 * 1000))
      this.shiftStale = clockIn <= floor
      const start = clockIn > floor ? clockIn : floor
      const end = minuteText(new Date())
      this.shiftStartText = start
      this.myShiftLoading = true
      try {
        const data = await summaryApi.operators(start, end)
        const me = data.rows.find((r) => r.user?.id === auth.user?.id)
        this.myShift = me
          ? {
              session_count: me.session_count,
              player_times: me.player_times,
              tea_cents: me.tea_cents,
              add_deposit_cents: me.add_deposit_cents,
              refund_cents: me.refund_cents,
              cash_diff_cents: me.cash_diff_cents,
              dividend_cents: me.dividend_cents,
            }
          : {
              session_count: 0,
              player_times: 0,
              tea_cents: 0,
              add_deposit_cents: 0,
              refund_cents: 0,
              cash_diff_cents: 0,
              dividend_cents: 0,
            }
      } catch {
        this.myShift = null
      } finally {
        this.myShiftLoading = false
      }
    },
  },
})

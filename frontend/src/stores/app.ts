import { defineStore } from 'pinia'

import { overviewApi, summaryApi } from '@/api'
import type { SummaryTotals } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

const THEME_KEY = 'lol_theme'
const SUMMARY_RANGE_KEY = 'lol_summary_range'
const DOCK_OPEN_KEY = 'lol_pos_dock_open'

const MOMENT_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/
const MINUTE_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/

const pad2 = (n: number) => String(n).padStart(2, '0')
function minuteText(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

function readSummaryRange(): [string, string] | null {
  try {
    const raw = localStorage.getItem(SUMMARY_RANGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (
      Array.isArray(parsed) &&
      parsed.length === 2 &&
      typeof parsed[0] === 'string' &&
      typeof parsed[1] === 'string' &&
      MOMENT_RE.test(parsed[0]) &&
      MOMENT_RE.test(parsed[1])
    ) {
      return [parsed[0], parsed[1]]
    }
  } catch {
    // 脏数据直接忽略，用默认区间
  }
  return null
}

export const useAppStore = defineStore('app', {
  state: () => ({
    theme: localStorage.getItem(THEME_KEY) || 'dark',
    summaryRange: readSummaryRange() as [string, string] | null,
    dockOpen: localStorage.getItem(DOCK_OPEN_KEY) !== '0',
    mobileDockVisible: false,
    changelogVisible: false,
    passwordDialogVisible: false,
    posFocusSearchTick: 0,
    posFocusDockTick: 0,
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
      document.documentElement.classList.toggle('dark', this.theme === 'dark')
    },
    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark'
      localStorage.setItem(THEME_KEY, this.theme)
      this.applyTheme()
    },
    toggleDock(force?: boolean) {
      this.dockOpen = typeof force === 'boolean' ? force : !this.dockOpen
      try {
        localStorage.setItem(DOCK_OPEN_KEY, this.dockOpen ? '1' : '0')
      } catch {
        // ignore storage quota errors
      }
    },
    requestFocusSearch() {
      this.posFocusSearchTick += 1
    },
    requestFocusDock() {
      this.toggleDock(true)
      this.posFocusDockTick += 1
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
    setSummaryRange(range: [string, string]) {
      this.summaryRange = range
      try {
        localStorage.setItem(SUMMARY_RANGE_KEY, JSON.stringify(range))
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

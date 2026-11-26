export type ThemeId = 'dark' | 'light' | 'hextech' | 'warm' | 'cyber'

export interface ThemeMeta {
  id: ThemeId
  label: string
  desc: string
  isDark: boolean
  swatchBg: string
  swatchAccent: string
}

export const DEFAULT_THEME: ThemeId = 'warm'

export const THEMES: ThemeMeta[] = [
  {
    id: 'warm',
    label: '暖纸护眼',
    desc: '米白低蓝光（默认）',
    isDark: false,
    swatchBg: '#f3ede2',
    swatchAccent: '#1f7a7a',
  },
  {
    id: 'light',
    label: '清爽白',
    desc: '明亮简洁',
    isDark: false,
    swatchBg: '#f3f5fa',
    swatchAccent: '#3b82f6',
  },
  {
    id: 'dark',
    label: '暗夜蓝',
    desc: '深色专业终端',
    isDark: true,
    swatchBg: '#0c0f16',
    swatchAccent: '#4f8cff',
  },
  {
    id: 'hextech',
    label: '海克斯金',
    desc: 'LOL 经典暗金',
    isDark: true,
    swatchBg: '#09111a',
    swatchAccent: '#c8aa6e',
  },
  {
    id: 'cyber',
    label: '电竞霓虹紫',
    desc: '暗紫电竞氛围',
    isDark: true,
    swatchBg: '#0f0c1a',
    swatchAccent: '#a855f7',
  },
]

const VALID_IDS = new Set<string>(THEMES.map((t) => t.id))

export function normalizeTheme(value: unknown): ThemeId {
  return typeof value === 'string' && VALID_IDS.has(value) ? (value as ThemeId) : DEFAULT_THEME
}

export function getThemeMeta(id: ThemeId): ThemeMeta {
  return THEMES.find((t) => t.id === id) || THEMES[0]
}

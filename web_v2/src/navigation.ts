export type ProductPage =
  | 'overview'
  | 'history'
  | 'rounds'
  | 'courses'
  | 'holes'
  | 'clubs'
  | 'issues'
  | 'reports'
  | 'caddie'
  | 'record'
  | 'prep'
  | 'corrections'
  | 'sync-quality'
  | 'club-bag'
  | 'settings'

export type ProductSection = 'home' | 'history' | 'prep' | 'live' | 'settings'

export const PAGE_TO_SECTION: Record<ProductPage, ProductSection> = {
  overview: 'home',
  history: 'history',
  rounds: 'history',
  courses: 'history',
  holes: 'history',
  clubs: 'history',
  issues: 'history',
  reports: 'history',
  prep: 'prep',
  caddie: 'live',
  record: 'live',
  corrections: 'settings',
  'sync-quality': 'settings',
  'club-bag': 'settings',
  settings: 'settings',
}

export const SECTION_ORDER: ProductSection[] = ['home', 'history', 'prep', 'live', 'settings']

export const SECTION_LABELS: Record<ProductSection, string> = {
  home: '概览',
  history: '历史',
  prep: '备战',
  live: '实战',
  settings: '设置',
}

export const SECTION_DEFAULT_PAGE: Record<ProductSection, ProductPage> = {
  home: 'overview',
  history: 'history',
  prep: 'prep',
  live: 'caddie',
  settings: 'settings',
}

export interface SubNavItem {
  page: ProductPage
  label: string
  activeFor?: ProductPage[]
}

export const HISTORY_SUBNAV: SubNavItem[] = [
  { page: 'history', label: '趋势总览' },
  { page: 'rounds', label: '球局' },
  { page: 'holes', label: '强弱分析', activeFor: ['holes', 'clubs', 'issues'] },
  { page: 'courses', label: '球场' },
]

// Consumer settings nav. The owner-only diagnostics console (sync-quality) and the
// obsolete player-link manager (players, removed — members self-register via Apple)
// are no longer here; consumers get 账号/连接 Garmin/隐私 on the settings hub plus the
// 球包 and 数据更正 tools.
export const SETTINGS_SUBNAV: SubNavItem[] = [
  { page: 'settings', label: '账号' },
  { page: 'club-bag', label: '球包管理' },
  { page: 'corrections', label: '订正' },
]

export function subnavForPage(page: ProductPage): SubNavItem[] | null {
  const section = PAGE_TO_SECTION[page]
  if (section === 'history') return HISTORY_SUBNAV
  if (section === 'settings') return SETTINGS_SUBNAV
  return null
}

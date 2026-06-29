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
  | 'players'
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
  players: 'settings',
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
  settings: 'sync-quality',
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
  { page: 'reports', label: '报告' },
]

export const SETTINGS_SUBNAV: SubNavItem[] = [
  { page: 'sync-quality', label: '同步与数据健康' },
  { page: 'players', label: '球员管理' },
  { page: 'club-bag', label: '球包管理' },
  { page: 'corrections', label: '订正' },
  { page: 'settings', label: '后端配置' },
]

export function subnavForPage(page: ProductPage): SubNavItem[] | null {
  const section = PAGE_TO_SECTION[page]
  if (section === 'history') return HISTORY_SUBNAV
  if (section === 'settings') return SETTINGS_SUBNAV
  return null
}

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
  | 'account'
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
  account: 'settings',
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
]

// Settings tabs in display order. Consumer-facing tabs come first (连接 Garmin /
// 球包管理 / 账户 / 订正); the owner-only family + backend tabs trail and are filtered
// out for everyone except the owner by `visibleSettingsSubnav`.
export const SETTINGS_SUBNAV: SubNavItem[] = [
  { page: 'sync-quality', label: '连接 Garmin' },
  { page: 'club-bag', label: '球包管理' },
  { page: 'account', label: '账户' },
  { page: 'corrections', label: '订正' },
  { page: 'players', label: '球员管理' },
  { page: 'settings', label: '后端配置' },
]

// Who may see which settings tab. The owner sees everything; a signed-in member
// sees only the consumer tabs (连接 Garmin / 球包管理 / 账户 / 订正); a credential-less
// or legacy per-player-link visitor sees neither the owner tabs nor account/球包.
export interface SettingsAccess {
  isOwner: boolean
  hasSession: boolean
}

// Owner-only settings tabs — never shown to a member or a fresh/legacy-link visitor.
const OWNER_ONLY_SETTINGS_PAGES: ReadonlySet<ProductPage> = new Set(['players', 'settings'])

export function visibleSettingsSubnav(access: SettingsAccess): SubNavItem[] {
  return SETTINGS_SUBNAV.filter((item) => {
    if (OWNER_ONLY_SETTINGS_PAGES.has(item.page)) return access.isOwner
    // A user edits their OWN club bag (member via session) or any member's (owner).
    if (item.page === 'club-bag') return access.isOwner || access.hasSession
    // Account = sign-out; only meaningful for an Apple session.
    if (item.page === 'account') return access.hasSession
    return true
  })
}

export function subnavForPage(page: ProductPage): SubNavItem[] | null {
  const section = PAGE_TO_SECTION[page]
  if (section === 'history') return HISTORY_SUBNAV
  if (section === 'settings') return SETTINGS_SUBNAV
  return null
}

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

// Web redesign (2026-07): the desktop workbench has five primary sections —
// 复盘 / 备战 / 统计 / 球包 / 设置 — and does NOT do live play. The old 实战/live
// section is gone from the rail; the caddie sandbox + phone scorer stay routable
// but off the primary rail (see UTILITY_NAV / OFF_RAIL_PAGES).
export type ProductSection = 'review' | 'prep' | 'stats' | 'bag' | 'settings'

export const PAGE_TO_SECTION: Record<ProductPage, ProductSection> = {
  // 复盘 (review) — rounds list → round detail → shot-map. 概览 is its landing.
  overview: 'review',
  rounds: 'review',
  holes: 'review',
  issues: 'review',
  reports: 'review',
  record: 'review',
  // 备战 (prep)
  prep: 'prep',
  caddie: 'prep',
  // 统计 (stats) — trends + course performance (strokes-gained).
  history: 'stats',
  courses: 'stats',
  // 球包 (bag) — club distances / performance.
  clubs: 'bag',
  // 设置 (settings) — connectors, corrections, bag management, roster, backend.
  corrections: 'settings',
  'sync-quality': 'settings',
  players: 'settings',
  'club-bag': 'settings',
  account: 'settings',
  settings: 'settings',
}

export const SECTION_ORDER: ProductSection[] = ['review', 'prep', 'stats', 'bag', 'settings']

export const SECTION_LABELS: Record<ProductSection, string> = {
  review: '复盘',
  prep: '备战',
  stats: '统计',
  bag: '球包',
  settings: '设置',
}

export const SECTION_DEFAULT_PAGE: Record<ProductSection, ProductPage> = {
  review: 'overview',
  prep: 'prep',
  stats: 'history',
  bag: 'clubs',
  settings: 'sync-quality',
}

// Routable but NOT on the primary rail. Web does no live play, so the caddie
// sandbox (球童沙盘) and the phone scorer (手机记分) live in a small secondary
// utility group in the sidebar rather than a primary section.
export const OFF_RAIL_PAGES: readonly ProductPage[] = ['caddie', 'record']

export interface UtilityNavItem {
  page: ProductPage
  label: string
}

export const UTILITY_NAV: UtilityNavItem[] = [
  { page: 'caddie', label: '球童沙盘' },
  { page: 'record', label: '手机记分' },
]

export interface SubNavItem {
  page: ProductPage
  label: string
  activeFor?: ProductPage[]
}

// 复盘 subnav — the review workspace tabs (概览 is the section landing above them).
export const REVIEW_SUBNAV: SubNavItem[] = [
  { page: 'rounds', label: '球局' },
  { page: 'holes', label: '强弱分析', activeFor: ['holes', 'issues'] },
]

// 统计 subnav — trends landing + course performance (strokes-gained content).
export const STATS_SUBNAV: SubNavItem[] = [
  { page: 'history', label: '趋势总览' },
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
  // Off-rail pages (caddie sandbox / phone scorer) render without a section subnav.
  if (OFF_RAIL_PAGES.includes(page)) return null
  const section = PAGE_TO_SECTION[page]
  if (section === 'review') return REVIEW_SUBNAV
  if (section === 'stats') return STATS_SUBNAV
  if (section === 'settings') return SETTINGS_SUBNAV
  return null
}

// Top-bar title for a page: off-rail pages show their utility label, every other
// page shows its section label.
export function pageTitle(page: ProductPage): string {
  const utility = UTILITY_NAV.find((item) => item.page === page)
  return utility ? utility.label : SECTION_LABELS[PAGE_TO_SECTION[page]]
}

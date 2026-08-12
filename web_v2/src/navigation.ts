export type ProductPage =
  | 'overview'
  | 'review'
  | 'history'
  | 'rounds'
  | 'courses'
  | 'holes'
  | 'result-clubs'
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

// Historical rounds are the evidence behind performance statistics, so Web exposes
// one 成绩 section. Detail routes remain distinct, but no longer compete on the rail.
export type ProductSection = 'results' | 'prep' | 'bag' | 'settings'

export const PAGE_TO_SECTION: Record<ProductPage, ProductSection> = {
  // 成绩 — answer-first landing → archive/trends/analysis/course detail.
  overview: 'results',
  review: 'results',
  rounds: 'results',
  history: 'results',
  courses: 'results',
  holes: 'results',
  'result-clubs': 'results',
  issues: 'results',
  reports: 'results',
  record: 'results',
  // 备战 (prep)
  prep: 'prep',
  caddie: 'prep',
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

export const SECTION_ORDER: ProductSection[] = ['results', 'prep', 'bag', 'settings']

export const SECTION_LABELS: Record<ProductSection, string> = {
  results: '成绩',
  prep: '备战',
  bag: '球包',
  settings: '设置',
}

export const SECTION_DEFAULT_PAGE: Record<ProductSection, ProductPage> = {
  results: 'overview',
  prep: 'prep',
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
export const RESULTS_SUBNAV: SubNavItem[] = [
  { page: 'overview', label: '总览' },
  { page: 'rounds', label: '全部球局' },
  { page: 'history', label: '时间趋势' },
  { page: 'holes', label: '表现分析', activeFor: ['holes', 'result-clubs', 'issues', 'reports'] },
  { page: 'courses', label: '球场' },
]

// Compatibility aliases for code/tests that import the old names. Both now point
// at the one results information architecture, not two independent sections.
export const REVIEW_SUBNAV = RESULTS_SUBNAV
export const STATS_SUBNAV = RESULTS_SUBNAV

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
  if (page === 'review') return null
  // Off-rail pages (caddie sandbox / phone scorer) render without a section subnav.
  if (OFF_RAIL_PAGES.includes(page)) return null
  const section = PAGE_TO_SECTION[page]
  if (section === 'results') return RESULTS_SUBNAV
  if (section === 'settings') return SETTINGS_SUBNAV
  return null
}

// Top-bar title for a page: off-rail pages show their utility label, every other
// page shows its section label.
export function pageTitle(page: ProductPage): string {
  const utility = UTILITY_NAV.find((item) => item.page === page)
  return utility ? utility.label : SECTION_LABELS[PAGE_TO_SECTION[page]]
}

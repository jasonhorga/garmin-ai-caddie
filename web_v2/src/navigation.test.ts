import { describe, expect, it } from 'vitest'
import {
  HISTORY_SUBNAV,
  PAGE_TO_SECTION,
  SECTION_DEFAULT_PAGE,
  SECTION_LABELS,
  SECTION_ORDER,
  SETTINGS_SUBNAV,
  subnavForPage,
  visibleSettingsSubnav,
} from './navigation'

describe('navigation map', () => {
  it('assigns every page to a section whose default page maps back to that section', () => {
    for (const section of Object.values(PAGE_TO_SECTION)) {
      expect(SECTION_ORDER).toContain(section)
      expect(PAGE_TO_SECTION[SECTION_DEFAULT_PAGE[section]]).toBe(section)
    }
  })

  it('labels all five sections in Chinese, settings last', () => {
    expect(SECTION_ORDER.map((section) => SECTION_LABELS[section])).toEqual(['概览', '历史', '备战', '实战', '设置'])
  })

  it('returns the history subnav for any history page and the settings subnav for plumbing pages', () => {
    expect(subnavForPage('clubs')).toBe(HISTORY_SUBNAV)
    expect(subnavForPage('rounds')).toBe(HISTORY_SUBNAV)
    expect(subnavForPage('corrections')).toBe(SETTINGS_SUBNAV)
    expect(subnavForPage('overview')).toBeNull()
    expect(subnavForPage('prep')).toBeNull()
    expect(subnavForPage('caddie')).toBeNull()
    expect(subnavForPage('record')).toBeNull()
  })

  it('puts the 手机记分 recorder in the 实战 (live) section', () => {
    expect(PAGE_TO_SECTION.record).toBe('live')
  })

  it('marks 强弱分析 active for holes/clubs/issues', () => {
    const analysis = HISTORY_SUBNAV.find((item) => item.label === '强弱分析')
    expect(analysis?.page).toBe('holes')
    expect(analysis?.activeFor).toEqual(['holes', 'clubs', 'issues'])
  })

  it('places 球员管理 in the settings section subnav', () => {
    expect(PAGE_TO_SECTION.players).toBe('settings')
    const players = SETTINGS_SUBNAV.find((item) => item.page === 'players')
    expect(players?.label).toBe('球员管理')
    expect(subnavForPage('players')).toBe(SETTINGS_SUBNAV)
  })

  it('renames the connector tab 连接 Garmin and adds an 账户 settings tab', () => {
    expect(SETTINGS_SUBNAV.find((item) => item.page === 'sync-quality')?.label).toBe('连接 Garmin')
    expect(SETTINGS_SUBNAV.find((item) => item.page === 'account')?.label).toBe('账户')
    expect(PAGE_TO_SECTION.account).toBe('settings')
  })

  it('access-gates the settings subnav by owner / Apple session', () => {
    // Owner: everything except 账户 (which needs an Apple session, not the bare-URL owner).
    expect(visibleSettingsSubnav({ isOwner: true, hasSession: false }).map((item) => item.page)).toEqual([
      'sync-quality',
      'club-bag',
      'corrections',
      'players',
      'settings',
    ])
    // Signed-in member: consumer tabs only — never the owner family roster / backend config.
    expect(visibleSettingsSubnav({ isOwner: false, hasSession: true }).map((item) => item.page)).toEqual([
      'sync-quality',
      'club-bag',
      'account',
      'corrections',
    ])
    // Fresh / legacy per-player-link visitor: no account, no club bag, no owner tabs.
    expect(visibleSettingsSubnav({ isOwner: false, hasSession: false }).map((item) => item.page)).toEqual([
      'sync-quality',
      'corrections',
    ])
  })
})

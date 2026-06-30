import { describe, expect, it } from 'vitest'
import {
  HISTORY_SUBNAV,
  PAGE_TO_SECTION,
  SECTION_DEFAULT_PAGE,
  SECTION_LABELS,
  SECTION_ORDER,
  SETTINGS_SUBNAV,
  subnavForPage,
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
    expect(subnavForPage('settings')).toBe(SETTINGS_SUBNAV)
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

  it('keeps the consumer settings subnav free of owner/diagnostic surfaces', () => {
    // De-engineer pass: the owner sync/diagnostics console and the obsolete
    // player-link manager are gone; the consumer tabs are 账号 + 球包 + 数据更正.
    expect(SETTINGS_SUBNAV.map((item) => item.page)).toEqual(['settings', 'club-bag', 'corrections'])
    expect(SETTINGS_SUBNAV.some((item) => item.page === 'sync-quality')).toBe(false)
    expect(SECTION_DEFAULT_PAGE.settings).toBe('settings')
  })
})

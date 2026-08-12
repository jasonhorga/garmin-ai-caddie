import { describe, expect, it } from 'vitest'
import {
  OFF_RAIL_PAGES,
  PAGE_TO_SECTION,
  REVIEW_SUBNAV,
  SECTION_DEFAULT_PAGE,
  SECTION_LABELS,
  SECTION_ORDER,
  SETTINGS_SUBNAV,
  STATS_SUBNAV,
  UTILITY_NAV,
  pageTitle,
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

  it('labels the four task-based sections in Chinese, settings last', () => {
    expect(SECTION_ORDER.map((section) => SECTION_LABELS[section])).toEqual(['成绩', '备战', '球包', '设置'])
  })

  it('returns one results subnav for archive, trends, analysis and courses', () => {
    expect(subnavForPage('rounds')).toBe(REVIEW_SUBNAV)
    expect(subnavForPage('holes')).toBe(REVIEW_SUBNAV)
    // 概览 is the answer-first 成绩 landing.
    expect(subnavForPage('overview')).toBe(REVIEW_SUBNAV)
    expect(subnavForPage('history')).toBe(STATS_SUBNAV)
    expect(subnavForPage('courses')).toBe(STATS_SUBNAV)
    expect(subnavForPage('corrections')).toBe(SETTINGS_SUBNAV)
    expect(subnavForPage('prep')).toBeNull()
    // 球包 (clubs) has no subnav of its own.
    expect(subnavForPage('clubs')).toBeNull()
  })

  it('keeps the caddie sandbox + phone scorer routable but off the primary rail', () => {
    expect(OFF_RAIL_PAGES).toEqual(['caddie', 'record'])
    expect(UTILITY_NAV.map((item) => item.page)).toEqual(['caddie', 'record'])
    expect(UTILITY_NAV.map((item) => item.label)).toEqual(['球童沙盘', '手机记分'])
    // Off-rail pages render without a section subnav…
    expect(subnavForPage('caddie')).toBeNull()
    expect(subnavForPage('record')).toBeNull()
    // …but still resolve to a section (for grouping) and a utility title.
    expect(PAGE_TO_SECTION.caddie).toBe('prep')
    expect(PAGE_TO_SECTION.record).toBe('results')
    expect(pageTitle('caddie')).toBe('球童沙盘')
    expect(pageTitle('record')).toBe('手机记分')
    expect(PAGE_TO_SECTION.review).toBe('results')
    expect(subnavForPage('review')).toBeNull()
  })

  it('titles a normal page with its section label', () => {
    expect(pageTitle('overview')).toBe('成绩')
    expect(pageTitle('history')).toBe('成绩')
    expect(pageTitle('clubs')).toBe('球包')
    expect(pageTitle('sync-quality')).toBe('设置')
  })

  it('marks 表现分析 active for analysis routes in the 成绩 section', () => {
    const analysis = REVIEW_SUBNAV.find((item) => item.label === '表现分析')
    expect(analysis?.page).toBe('holes')
    expect(analysis?.activeFor).toEqual(['holes', 'result-clubs', 'issues', 'reports'])
  })

  it('puts all history and performance routes under 成绩', () => {
    expect(PAGE_TO_SECTION.history).toBe('results')
    expect(PAGE_TO_SECTION.courses).toBe('results')
    expect(STATS_SUBNAV.map((item) => item.page)).toEqual(['overview', 'rounds', 'history', 'holes', 'courses'])
  })

  it('routes the 球包 rail to the clubs page', () => {
    expect(SECTION_DEFAULT_PAGE.bag).toBe('clubs')
    expect(PAGE_TO_SECTION.clubs).toBe('bag')
  })

  it('places 球员管理 in the settings section subnav', () => {
    expect(PAGE_TO_SECTION.players).toBe('settings')
    const players = SETTINGS_SUBNAV.find((item) => item.page === 'players')
    expect(players?.label).toBe('球员管理')
    expect(subnavForPage('players')).toBe(SETTINGS_SUBNAV)
  })

  it('keeps 连接 Garmin, 球包管理 + 账户 as settings tabs', () => {
    expect(SETTINGS_SUBNAV.find((item) => item.page === 'sync-quality')?.label).toBe('连接 Garmin')
    expect(SETTINGS_SUBNAV.find((item) => item.page === 'club-bag')?.label).toBe('球包管理')
    expect(SETTINGS_SUBNAV.find((item) => item.page === 'account')?.label).toBe('账户')
    expect(PAGE_TO_SECTION.account).toBe('settings')
    expect(PAGE_TO_SECTION['club-bag']).toBe('settings')
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

import type { Page } from '@playwright/test'
import {
  ADMIN, COURSE, CSRF, PLAYER_LINK, ROUND, SESSION_HEADER, SHARE_TOKEN,
  correctedShots, expect, productApi, test,
} from './fixtures'

async function openReview(page: Page, path = '/') {
  await page.goto(path)
  await page.getByRole('region', { name: '最近球局' }).getByRole('button', { name: new RegExp(`${COURSE}.*72`) }).click()
  await expect(page.getByRole('heading', { name: '球局回顾', exact: true })).toBeVisible()
  await expect(page.getByLabel('第1洞落点图')).toBeVisible()
  // Wait for the detail fetch before asserting that diagnostics are absent.
  await expect(page.getByRole('heading', { name: '记分卡', exact: true })).toBeVisible()
}

async function openClubs(page: Page) {
  await page.getByRole('navigation', { name: '辅助导航' }).getByRole('button', { name: '表现分析', exact: true }).click()
  await page.getByRole('button', { name: /球杆表现/ }).click()
  await expect(page.getByRole('heading', { name: '球杆表现', exact: true })).toBeVisible()
}

for (const row of [
  { name: 'scores-performance', missingPhases: false },
  { name: 'unknown-phases', missingPhases: true },
  { name: 'prep-sandbox', missingPhases: false },
]) {
  test.describe(`9.1 ${row.name}`, () => {
    test.use({ scenario: row })
    test('j9_1_web_numbers_match_handwritten_golden', async ({ page, api }) => {
      await page.goto('/')
      if (row.name !== 'prep-sandbox') {
        const career = page.getByRole('region', { name: '生涯概览' })
        await expect(career.locator('.results-career-head b')).toHaveText('3')
        // Two complete rounds: (72 + 90)/2 = 81; nine-hole 40 is excluded.
        await expect(career.locator('.results-kpis b')).toHaveText(['81', '72', '—'])
        await expect(page.locator('.results-recent small')).toContainText(/近 10 场 81.*近 20 场 81/)
        await expect(page.getByRole('region', { name: '最近球局' }).locator('.results-round-row b')).toHaveText(['72', '90', '40'])
        await page.getByRole('navigation', { name: '辅助导航' }).getByRole('button', { name: '表现分析', exact: true }).click()
        const phases = page.getByRole('region', { name: '四个环节' })
        // 24/45=53%, 18/45=40%, 108/3=36; unknown is never 0.
        await expect(phases.locator('article > b')).toHaveText(row.missingPhases ? ['—', '—', '—', '—'] : ['53%', '40%', '36', '—'])
        if (!row.missingPhases) {
          await expect(phases.locator('article').nth(0)).toContainText('24/45')
          await expect(phases.locator('article').nth(1)).toContainText('18/45')
          await expect(phases.locator('article').nth(2)).toContainText('3/3')
        }
        await expect(page.getByRole('region', { name: '成绩构成' }).locator('.performance-outcome strong')).toHaveText([
          '0/45 · 0%', '23/45 · 51%', '22/45 · 49%', '0/45 · 0%',
        ])
        const byPar = page.getByRole('region', { name: '按标准杆类型' })
        await expect(byPar).toContainText('45 洞')
        await expect(byPar).toContainText('平均 0.5')
        await expect(byPar).toContainText('23/45 · 51.1%')
        return
      }

      await page.getByRole('button', { name: '备战', exact: true }).click()
      await page.getByRole('button', { name: `去备战 ${COURSE}` }).click()
      await expect(page.getByText('PAR 8 · 547 码', { exact: true })).toBeVisible()
      await expect(page.locator('.prep-holes-record')).toContainText(/3 次.*81/)
      const picker = page.getByRole('combobox', { name: '选择球洞' })
      await expect(page.getByLabel('第1洞球道图').getByLabel('地图推荐球杆')).toHaveText('6I · 164码落点')
      await picker.selectOption('2')
      await expect(page.getByLabel('第2洞球道图').getByLabel('地图推荐球杆')).toHaveText('9I · 109码落点')
      await picker.selectOption('1')
      await expect(page.getByLabel('第1洞球道图').getByLabel('地图推荐球杆')).toHaveText('6I · 164码落点')
      expect(api.prepQueries.length).toBeGreaterThan(0)
      expect(api.prepQueries.every((query) => query.get('include_shots') === 'true')).toBe(true)

      const prepCount = api.prepQueries.length
      await page.getByRole('button', { name: '球童沙盘', exact: true }).click()
      await page.getByRole('button', { name: `开始模拟 ${COURSE}` }).click()
      await expect(page.locator('.live-sandbox-map-distance')).toContainText('328码')
      await page.getByRole('button', { name: '第2洞', exact: true }).click()
      await expect(page.locator('.live-sandbox-map-distance')).toContainText('219码')
      await page.getByRole('button', { name: '第1洞', exact: true }).click()
      await page.getByRole('button', { name: '要建议', exact: true }).click()
      const advice = page.getByRole('region', { name: '沙盘建议' })
      // Same h1_tee_0 inputs as C16c: stock 150 m, safe 100 m, attack 200 m.
      await expect(advice.locator('.live-advice-club')).toHaveText('6I')
      await expect(advice.locator('.live-advice-carry')).toHaveText('落点 164码')
      expect(api.contexts[0]?.get('source_ref')).toBe(`${ROUND}:1`)
      expect(api.contexts[0]?.get('distance_to_pin_m')).toBe('300')
      expect(api.decisions[0]).toMatchObject({ shotType: 'tee', context: { distanceToPin_m: 300 } })
      for (const strategy of [
        { button: '稳', club: '9I', carry: '落点 109码' },
        { button: '博', club: '3W', carry: '落点 219码' },
      ]) {
        await page.getByRole('group', { name: '策略', exact: true }).getByRole('button', { name: strategy.button, exact: true }).click()
        await expect(advice.locator('.live-advice-club')).toHaveText(strategy.club)
        await expect(advice.locator('.live-advice-carry')).toHaveText(strategy.carry)
        expect(api.decisions.at(-1)).toMatchObject({ context: { distanceToPin_m: 300 } })
      }
      expect(api.decisions).toHaveLength(3)
      const sandboxQueries = api.prepQueries.slice(prepCount)
      expect(sandboxQueries.length).toBeGreaterThan(0)
      expect(sandboxQueries.every((query) => query.get('include_shots') === null)).toBe(true)
    })
  })
}

for (const row of [
  { name: 'web-delete', corrected: false, correctionRejected: false },
  { name: 'app-snapshot', corrected: true, correctionRejected: false },
  { name: 'save-rejected', corrected: false, correctionRejected: true },
  { name: 'cached-statistics', corrected: false, correctionRejected: false },
]) {
  test.describe(`9.2 ${row.name}`, () => {
    test.use({ scenario: row })
    test('j9_2_corrections_use_same_fixed_projection', async ({ page, api }) => {
      if (row.name === 'cached-statistics') {
        await page.goto('/')
        await openClubs(page)
        await expect(page.locator('.club-performance article').filter({ hasText: '7I' }).locator('em')).toHaveText('3')
        await page.getByRole('button', { name: '成绩', exact: true }).click()
        await page.getByRole('region', { name: '最近球局' }).getByRole('button', { name: new RegExp(`${COURSE}.*72`) }).click()
        await expect(page.getByLabel('第1洞落点图')).toBeVisible()
      } else {
        await openReview(page)
      }
      const canvas = page.getByLabel('第1洞落点图')
      if (!row.corrected) {
        const readsBeforeSave = api.calls.filter((call) => call.path.endsWith('/shotmap')).length
        await page.getByRole('button', { name: '编辑落点', exact: true }).click()
        await page.getByRole('button', { name: '删除第2杆', exact: true }).click()
        await page.getByRole('button', { name: '保存全部修改', exact: true }).click()
        await expect.poll(() => api.corrections.length).toBe(1)
        expect(api.corrections[0]).toMatchObject({ op: 'replaceHoleShots', hole: 1, shots: correctedShots, manualPenalty: 0, geometryRevision: 'fixture-v1' })
        if (row.correctionRejected) {
          await expect(page.getByRole('alert')).toBeVisible()
          await expect(page.getByLabel('编辑杆序').locator('li')).toHaveCount(2)
          await expect(page.getByRole('button', { name: '保存全部修改', exact: true })).toBeEnabled()
          await page.getByRole('button', { name: '取消', exact: true }).click()
          await expect(canvas.locator('circle[data-shot-id]')).toHaveCount(3)
          return
        }
        await expect.poll(() => api.calls.filter((call) => call.path.endsWith('/shotmap')).length).toBeGreaterThan(readsBeforeSave)
        await expect(page.getByRole('button', { name: '编辑落点', exact: true })).toBeVisible()
      }
      await expect(canvas.locator('circle[data-shot-id]')).toHaveCount(2)
      await expect(canvas.locator('circle[data-shot-id]').nth(0)).toHaveAttribute('data-shot-id', 's1')
      await expect(canvas.locator('circle[data-shot-id]').nth(1)).toHaveAttribute('data-shot-id', 's3')
      // Map-first review hides the inspector; the map chips carry club + yards.
      // 200 and 100 pixels, at 1 px/m, round to 219 and 109 yards.
      const chips = canvas.locator('.review-canvas-chip')
      await expect(chips).toHaveText([/^一号木 · 219码/, /^P杆 · 109码/])
      if (row.name === 'cached-statistics') {
        await page.getByRole('button', { name: '成绩', exact: true }).click()
        await openClubs(page)
        await expect(page.locator('.club-performance article').filter({ hasText: '7I' }).locator('em')).toHaveText('2')
        return
      }
      await openReview(page)
      await expect(canvas.locator('circle[data-shot-id]')).toHaveCount(2)
      await expect(chips).toHaveText([/^一号木 · 219码/, /^P杆 · 109码/])
      expect(api.corrections).toHaveLength(row.corrected ? 0 : 1)
    })
  })
}

for (const row of [
  { name: 'valid-new-session', imported: false, importRejected: false },
  { name: 'invalid-new-session', imported: false, importRejected: true },
  { name: 'invalid-preserves-existing', imported: true, importRejected: true },
]) {
  test.describe(`9.3 ${row.name}`, () => {
    test.use({ scenario: row })
    test('j9_3_session_import_preserves_sync_state', async ({ page, api }) => {
      await page.goto('/')
      await page.getByRole('button', { name: '设置', exact: true }).click()
      const sync = page.getByRole('region', { name: 'Garmin 同步状态' })
      const run = sync.getByRole('button', { name: '立即同步', exact: true })
      await expect(run).toBeEnabled({ enabled: row.imported })
      await sync.getByLabel('管理令牌', { exact: true }).fill(ADMIN)
      await sync.getByLabel('网页会话头', { exact: true }).fill(SESSION_HEADER)
      await sync.getByLabel('防伪令牌', { exact: true }).fill(CSRF)
      await sync.getByRole('button', { name: '保存会话', exact: true }).click()
      await expect.poll(() => api.imports.length).toBe(1)
      expect(api.imports[0]).toEqual({ webSessionHeader: SESSION_HEADER, antiForgeryValue: CSRF, source: 'web_secure_paste' })
      expect(api.calls.find((call) => call.path.endsWith('/session'))?.admin).toBe(ADMIN)
      if (row.importRejected) {
        await expect(sync.locator('.sync-session-error')).toBeVisible()
        await expect(run).toBeEnabled({ enabled: row.imported })
        await expect(sync.getByLabel('网页会话头', { exact: true })).toHaveValue(SESSION_HEADER)
      } else {
        await expect(sync.getByLabel('网页会话头', { exact: true })).toHaveValue('')
        await expect(sync.getByLabel('防伪令牌', { exact: true })).toHaveValue('')
        await expect(run).toBeEnabled()
      }
      if (row.imported || !row.importRejected) {
        await run.click()
        await expect.poll(() => api.calls.filter((call) => call.path === '/api/v2/sync/garmin' && call.method === 'POST').length).toBe(1)
      } else {
        expect(api.calls.filter((call) => call.path === '/api/v2/sync/garmin')).toEqual([])
      }
      const text = await page.locator('body').innerText()
      for (const value of [ADMIN, SESSION_HEADER, CSRF]) expect(text).not.toContain(value)
      const storage = await page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]))
      for (const value of [SESSION_HEADER, CSRF]) expect(storage).not.toContain(value)
    })
  })
}

for (const row of [
  { name: 'owner-default', identity: 'owner', diagnostics: false, visible: false },
  { name: 'owner-diagnostics', identity: 'owner', diagnostics: true, visible: true },
  { name: 'member-forged-diagnostics', identity: 'member', diagnostics: true, visible: false },
  { name: 'legacy-link-forged-diagnostics', identity: 'player-link', diagnostics: true, visible: false },
] as const) {
  test.describe(`9.4 ${row.name}`, () => {
    test.use({ scenario: row })
    test('j9_4_diagnostics_are_owner_only', async ({ page }) => {
      await openReview(page, row.identity === 'player-link' ? `/p/${PLAYER_LINK}` : '/')
      const sources = page.getByRole('region', { name: '相关来源', exact: true })
      if (row.visible) {
        await expect(sources).toBeVisible()
        await expect(sources).toContainText(ROUND)
      } else {
        await expect(sources).toHaveCount(0)
        await expect(page.getByText(ROUND, { exact: true })).toHaveCount(0)
      }
      await page.getByRole('button', { name: '设置', exact: true }).click()
      await expect(page.getByRole('heading', { name: '同步与数据健康', exact: true })).toBeVisible()
      await expect(page.getByLabel('管理令牌', { exact: true })).toHaveCount(row.identity === 'owner' ? 1 : 0)
      await expect(page.getByRole('button', { name: '球员管理', exact: true })).toHaveCount(row.identity === 'owner' ? 1 : 0)
    })
  })
}

test('j9_5_review_has_single_round_share_entry', async ({ page, browser }) => {
  await openReview(page)
  await page.getByRole('button', { name: '分享', exact: true }).click()
  const pageUrl = await page.getByLabel('分享链接').locator('input').inputValue()
  expect(pageUrl).toMatch(new RegExp(`/s/${SHARE_TOKEN}$`))

  // A separate browser context has no session or admin localStorage. It must use only the
  // token-resolved projection and must not be able to reach the authenticated review surface.
  const sharedContext = await browser.newContext()
  const sharedPage = await sharedContext.newPage()
  const sharedApi = await productApi(sharedPage)
  await sharedPage.goto(pageUrl)
  await expect(sharedPage.getByRole('heading', { name: COURSE, exact: true })).toBeVisible()
  await expect(sharedPage.locator('.shared-round-summary')).toContainText(['72', '72', 'E', '18'])
  await expect(sharedPage.getByRole('heading', { name: '记分卡', exact: true })).toBeVisible()
  await expect(sharedPage.getByLabel('前九记分卡')).toBeVisible()
  await expect(sharedPage.getByLabel('后九记分卡')).toBeVisible()
  await expect(sharedPage.getByText('相关来源', { exact: true })).toHaveCount(0)
  await expect(sharedPage.getByRole('button', { name: /编辑落点|保存全部修改|添加订正|取消分享/ })).toHaveCount(0)
  await expect(sharedPage.locator('body')).not.toContainText('90')
  const read = sharedApi.calls.find((call) => call.path === `/api/v2/share/${SHARE_TOKEN}`)
  expect(read?.auth).toBeUndefined()
  expect(read?.admin).toBeUndefined()
  await sharedContext.close()
})

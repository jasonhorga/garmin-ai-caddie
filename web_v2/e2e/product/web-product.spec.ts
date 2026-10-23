import type { Page } from '@playwright/test'
import {
  ADMIN, COURSE, CSRF, LINK, ROUND, SESSION_HEADER,
  correctedShots, expect, test,
} from './fixtures'

async function openReview(page: Page) {
  await page.goto('/')
  await page.getByRole('region', { name: '最近球局' }).getByRole('button', { name: new RegExp(`${COURSE}.*72`) }).click()
  await expect(page.getByRole('heading', { name: '球局回顾', exact: true })).toBeVisible()
  await expect(page.getByLabel('第1洞落点图')).toBeVisible()
  // Wait for the detail fetch before asserting that diagnostics are absent.
  await expect(page.getByRole('heading', { name: '记分卡', exact: true })).toBeVisible()
}

test('9.1 成绩与表现把手算样本的数显示出来', async ({ page }) => {
  await page.goto('/')
  const career = page.getByRole('region', { name: '生涯概览' })
  await expect(career.locator('.results-career-head b')).toHaveText('3')
  await expect(career.locator('.results-kpis b')).toHaveText(['81', '72', '—'])
  await expect(page.locator('.results-recent small')).toContainText(/近 10 场 81.*近 20 场 81/)
  await expect(page.getByRole('region', { name: '最近球局' }).locator('.results-round-row b')).toHaveText(['72', '90', '40'])

  await page.getByRole('navigation', { name: '辅助导航' }).getByRole('button', { name: '表现分析', exact: true }).click()
  const phases = page.getByRole('region', { name: '四个环节' })
  // 24/45=53%, 18/45=40%, 108/3=36; unknown penalties stay unknown.
  await expect(phases.locator('article > b')).toHaveText(['53%', '40%', '36', '—'])
  await expect(phases.locator('article').nth(0)).toContainText('24/45')
  await expect(phases.locator('article').nth(1)).toContainText('18/45')
  await expect(phases.locator('article').nth(2)).toContainText('3/3')
  await expect(page.getByRole('region', { name: '成绩构成' }).locator('.performance-outcome strong')).toHaveText([
    '0/45 · 0%', '23/45 · 51%', '22/45 · 49%', '0/45 · 0%',
  ])
  const byPar = page.getByRole('region', { name: '按标准杆类型' })
  await expect(byPar).toContainText('45 洞')
  await expect(byPar).toContainText('平均 0.5')
  await expect(byPar).toContainText('23/45 · 51.1%')
})

test.describe('9.1 缺少环节样本', () => {
  test.use({ scenario: { missingPhases: true } })
  test('已知成绩仍显示，缺失命中率及推杆不补零', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('region', { name: '生涯概览' }).locator('.results-kpis b')).toHaveText(['81', '72', '—'])
    await page.getByRole('navigation', { name: '辅助导航' }).getByRole('button', { name: '表现分析', exact: true }).click()
    await expect(page.getByRole('region', { name: '四个环节' }).locator('article > b')).toHaveText(['—', '—', '—', '—'])
    await expect(page.getByRole('region', { name: '成绩构成' }).locator('.performance-outcome strong')).toHaveText([
      '0/45 · 0%', '23/45 · 51%', '22/45 · 49%', '0/45 · 0%',
    ])
  })
})

test('9.1 备战与沙盘按各洞 golden 显示距离和球杆，切换策略重算', async ({ page, api }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '备战', exact: true }).click()
  await page.getByRole('button', { name: `去备战 ${COURSE}` }).click()
  await expect(page.getByText('PAR 8 · 547 码', { exact: true })).toBeVisible()
  await expect(page.locator('.prep-holes-record')).toContainText(/3 次.*81/)
  const picker = page.getByRole('combobox', { name: '选择球洞' })
  const firstMap = page.getByLabel('第1洞球道图')
  await expect(firstMap.getByLabel('地图推荐球杆')).toHaveText('1D · 219码落点')
  await picker.selectOption('2')
  await expect(page.getByLabel('第2洞球道图').getByLabel('地图推荐球杆')).toHaveText('7I · 164码落点')
  await picker.selectOption('1')
  await expect(firstMap.getByLabel('地图推荐球杆')).toHaveText('1D · 219码落点')
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
  await expect(advice.locator('.live-advice-club')).toHaveText('1D')
  await expect(advice.locator('.live-advice-carry')).toHaveText('落点 219码')
  expect(api.contexts[0]?.get('source_ref')).toBe(`${ROUND}:1`)
  expect(api.contexts[0]?.get('distance_to_pin_m')).toBe('300')
  expect(api.decisions[0]).toMatchObject({ shotType: 'tee', context: { distanceToPin_m: 300 } })

  await page.getByRole('group', { name: '策略', exact: true }).getByRole('button', { name: '博', exact: true }).click()
  await expect(advice.locator('.live-advice-club')).toHaveText('3W')
  await expect(advice.locator('.live-advice-carry')).toHaveText('落点 241码')
  expect(api.contexts[1]?.get('strategy_mode')).toBe('attack')
  expect(api.decisions[1]).toMatchObject({ context: { strategyMode: 'attack', distanceToPin_m: 300 } })
  expect(api.decisions).toHaveLength(2)
  const sandboxQueries = api.prepQueries.slice(prepCount)
  expect(sandboxQueries.length).toBeGreaterThan(0)
  expect(sandboxQueries.every((query) => query.get('include_shots') === null)).toBe(true)
})

for (const rejected of [false, true]) {
  test.describe(`9.2 会话导入${rejected ? '被拒' : '成功'}`, () => {
    test.use({ scenario: { imported: false, importRejected: rejected } })
    test('同步按钮跟随真实返回状态，成功清空粘贴材料', async ({ page, api }) => {
      await page.goto('/')
      await page.getByRole('button', { name: '设置', exact: true }).click()
      const sync = page.getByRole('region', { name: 'Garmin 同步状态' })
      await expect(sync.getByRole('button', { name: '立即同步', exact: true })).toBeDisabled()
      await sync.getByLabel('管理令牌', { exact: true }).fill(ADMIN)
      await sync.getByLabel('网页会话头', { exact: true }).fill(SESSION_HEADER)
      await sync.getByLabel('防伪令牌', { exact: true }).fill(CSRF)
      await sync.getByRole('button', { name: '保存会话', exact: true }).click()
      await expect.poll(() => api.imports.length).toBe(1)
      expect(api.imports[0]).toEqual({ webSessionHeader: SESSION_HEADER, antiForgeryValue: CSRF, source: 'web_secure_paste' })
      expect(api.calls.find((call) => call.path.endsWith('/session'))?.admin).toBe(ADMIN)
      if (rejected) {
        await expect(sync.getByRole('button', { name: '保存会话', exact: true })).toBeEnabled()
        await expect(sync.getByRole('button', { name: '立即同步', exact: true })).toBeDisabled()
        await expect(sync.getByLabel('网页会话头', { exact: true })).toHaveValue(SESSION_HEADER)
        expect(api.calls.filter((call) => call.path === '/api/v2/sync/garmin')).toEqual([])
      } else {
        await expect(sync.getByLabel('网页会话头', { exact: true })).toHaveValue('')
        await expect(sync.getByLabel('防伪令牌', { exact: true })).toHaveValue('')
        await expect(sync.getByRole('button', { name: '立即同步', exact: true })).toBeEnabled()
        await sync.getByRole('button', { name: '立即同步', exact: true }).click()
        await expect.poll(() => api.calls.filter((call) => call.path === '/api/v2/sync/garmin' && call.method === 'POST').length).toBe(1)
      }
      // Synthetic secrets may exist in request fields; never render in page copy.
      const text = await page.locator('body').innerText()
      for (const value of [ADMIN, SESSION_HEADER, CSRF]) expect(text).not.toContain(value)
    })
  })
}

for (const origin of ['web', 'app'] as const) {
  test.describe(`9.3 ${origin} 订正后的页面投影`, () => {
    test.use({ scenario: { corrected: origin === 'app' } })
    test('删除中间一杆后杆序、落点及重新打开的结果等于固定快照', async ({ page, api }) => {
      await openReview(page)
      const canvas = page.getByLabel('第1洞落点图')
      if (origin === 'web') {
        const readsBeforeSave = api.calls.filter((call) => call.path.endsWith('/shotmap')).length
        await page.getByRole('button', { name: '编辑落点', exact: true }).click()
        await page.getByRole('button', { name: '删除第2杆', exact: true }).click()
        await page.getByRole('button', { name: '保存全部修改', exact: true }).click()
        await expect.poll(() => api.corrections.length).toBe(1)
        expect(api.corrections[0]).toMatchObject({ op: 'replaceHoleShots', hole: 1, shots: correctedShots, manualPenalty: 0, geometryRevision: 'fixture-v1' })
        await expect.poll(() => api.calls.filter((call) => call.path.endsWith('/shotmap')).length).toBeGreaterThan(readsBeforeSave)
        await expect(page.getByRole('button', { name: '编辑落点', exact: true })).toBeVisible()
      }
      await expect(canvas.locator('circle[data-shot-id]')).toHaveCount(2)
      await expect(canvas.locator('circle[data-shot-id]').nth(0)).toHaveAttribute('data-shot-id', 's1')
      await expect(canvas.locator('circle[data-shot-id]').nth(1)).toHaveAttribute('data-shot-id', 's3')
      await expect(canvas.locator('circle[data-shot-id="s3"]')).toHaveAttribute('cx', '150')
      await expect(canvas.locator('circle[data-shot-id="s3"]')).toHaveAttribute('cy', '150')
      const timeline = page.getByRole('complementary', { name: '杆序', exact: true })
      await expect(timeline.locator('.review-shot-club')).toHaveText(['一号木', 'P杆'])
      await expect(timeline.locator('.review-shot-yd')).toHaveText(['219 码', '109 码'])
      // A fresh document reads the persisted projection, not an optimistic draft.
      await openReview(page)
      await expect(canvas.locator('circle[data-shot-id]')).toHaveCount(2)
      await expect(timeline.locator('.review-shot-club')).toHaveText(['一号木', 'P杆'])
      await expect(timeline.locator('.review-shot-yd')).toHaveText(['219 码', '109 码'])
      expect(api.corrections).toHaveLength(origin === 'web' ? 1 : 0)
    })
  })
}

test.describe('9.3 保存失败', () => {
  test.use({ scenario: { correctionRejected: true } })
  test('草稿保留，取消后恢复原来的三杆', async ({ page, api }) => {
    await openReview(page)
    await page.getByRole('button', { name: '编辑落点', exact: true }).click()
    await page.getByRole('button', { name: '删除第2杆', exact: true }).click()
    await page.getByRole('button', { name: '保存全部修改', exact: true }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page.getByLabel('编辑杆序').locator('li')).toHaveCount(2)
    await expect(page.getByRole('button', { name: '保存全部修改', exact: true })).toBeEnabled()
    expect(api.corrections[0]).toMatchObject({ shots: correctedShots })
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await expect(page.getByLabel('第1洞落点图').locator('circle[data-shot-id]')).toHaveCount(3)
  })
})

test.describe('9.5 失效分享链接', () => {
  test.use({ scenario: { identity: 'share', revokedLink: true } })
  test('鉴权失败后收起产品数据且不回退到 owner', async ({ page, api }) => {
    await page.goto(`/p/${LINK}`)
    await expect(page.getByRole('button', { name: /Apple 登录/ })).toBeVisible()
    await expect(page.getByRole('region', { name: '成绩主页', exact: true })).toHaveCount(0)
    await expect(page.getByText(COURSE, { exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '设置', exact: true })).toHaveCount(0)
    expect(api.calls.length).toBeGreaterThan(0)
    expect(api.calls.every((call) => call.auth === `Bearer ${LINK}` && !call.admin)).toBe(true)
    expect(api.calls.filter((call) => call.method !== 'GET')).toEqual([])
  })
})

for (const row of [
  { identity: 'owner', diagnostics: false, visible: false },
  { identity: 'owner', diagnostics: true, visible: true },
  { identity: 'member', diagnostics: true, visible: false },
] as const) {
  test.describe(`9.4 ${row.identity} diagnostics=${row.diagnostics}`, () => {
    test.use({ scenario: row })
    test('只有主动打开诊断的 owner 看到来源面板', async ({ page }) => {
      await openReview(page)
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

test.describe('9.5 分享页面', () => {
  test.use({ scenario: { identity: 'share', diagnostics: true } })
  test('链接打开有数据的复盘，诊断与所有修改入口均不出现', async ({ page, api }) => {
    await page.goto(`/p/${LINK}`)
    await page.getByRole('region', { name: '最近球局' }).getByRole('button', { name: new RegExp(`${COURSE}.*72`) }).click()
    await expect(page.getByRole('heading', { name: '记分卡', exact: true })).toBeVisible()
    await expect(page.getByLabel('第1洞落点图').locator('circle[data-shot-id]')).toHaveCount(3)
    await expect.soft(page.getByRole('region', { name: '相关来源', exact: true })).toHaveCount(0)
    await expect.soft(page.getByRole('button', { name: '编辑落点', exact: true })).toHaveCount(0)
    await expect.soft(page.getByRole('button', { name: '为这一局添加订正', exact: true })).toHaveCount(0)
    await expect.soft(page.getByRole('button', { name: '手机记分', exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: '设置', exact: true }).click()
    await expect(page.getByRole('heading', { name: '同步与数据健康', exact: true })).toBeVisible()
    for (const name of ['保存会话', '立即同步', '球员管理', '订正', '球包管理']) {
      await expect.soft(page.getByRole('button', { name, exact: true })).toHaveCount(0)
    }
    await expect(page.getByLabel('管理令牌', { exact: true })).toHaveCount(0)
    expect(api.calls.length).toBeGreaterThan(0)
    expect(api.calls.every((call) => call.auth === `Bearer ${LINK}` && !call.admin)).toBe(true)
    expect(api.calls.filter((call) => call.method !== 'GET')).toEqual([])
  })
})

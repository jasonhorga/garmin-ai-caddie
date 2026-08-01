import { expect, test, type Page } from '@playwright/test'

const playerToken = process.env.AI_CADDIE_CI_PLAYER_TOKEN?.trim()

test.use({ trace: 'off', screenshot: 'off', video: 'off' })

test.describe('real isolated CI player evidence', () => {
  test.skip(!playerToken, 'AI_CADDIE_CI_PLAYER_TOKEN is required for real evidence')

  async function captureWithoutCredentialInLocation(page: Page, filename: string): Promise<void> {
    const credentialPath = await page.evaluate(
      () => `${window.location.pathname}${window.location.search}${window.location.hash}`,
    )
    await page.evaluate(() => window.history.replaceState(window.history.state, '', '/'))
    try {
      await page.screenshot({
        path: `web-live-evidence/${filename}`,
        animations: 'disabled',
      })
    } finally {
      await page.evaluate(
        (path) => window.history.replaceState(window.history.state, '', path),
        credentialPath,
      )
    }
  }

  test('captures the Watch-created round in review, archive, and detail', async ({ page }) => {
    if (!playerToken) return

    await page.goto(`/p/${encodeURIComponent(playerToken)}`, { waitUntil: 'domcontentloaded' })

    const roundPicker = page.locator('[aria-label="选择球局"]')
    await expect(roundPicker).toBeVisible()
    await expect(roundPicker).toContainText('Cypress Point')
    await expect(page.locator('[aria-label="第1洞落点图"]')).toBeVisible()
    await expect(page.locator('.hole-base-topo.is-ready')).toBeVisible({ timeout: 60_000 })
    await captureWithoutCredentialInLocation(page, 'review-workbench.png')

    await page.getByRole('button', { name: '复盘', exact: true }).click()
    await page
      .getByRole('navigation', { name: '辅助导航' })
      .getByRole('button', { name: '球局', exact: true })
      .click()
    await expect(page.getByRole('heading', { name: '球局', exact: true, level: 1 })).toBeVisible()
    const firstRound = page.getByRole('button', { name: /^打开球局 / }).first()
    await expect(firstRound).toBeVisible()
    await captureWithoutCredentialInLocation(page, 'rounds-list.png')

    await firstRound.click()
    const roundDetail = page.locator('.round-detail-panel')
    await expect(roundDetail.getByRole('heading', { name: '球局回顾', exact: true })).toBeVisible()
    // The heading also exists in the loading shell. Evidence is valid only after the protected
    // detail GET has resolved into the real scorecard, otherwise the browser can close after the
    // CORS preflight and leave a misleading "正在加载球局…" screenshot behind.
    await expect(roundDetail.getByLabel('球局数据')).toBeVisible({ timeout: 60_000 })
    await expect(roundDetail).toContainText('Cypress Point Club')
    await expect(roundDetail.getByText('正在加载球局…')).toHaveCount(0)
    // The panel is taller than the viewport. Scrolling the panel itself aligns its top at y=0,
    // underneath the fixed app bar, and clips the evidence heading. Capture the route at its
    // natural page origin instead.
    await page.evaluate(() => window.scrollTo(0, 0))
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
    await captureWithoutCredentialInLocation(page, 'round-review.png')

    // Leave no capability token in the final page URL when the browser context closes.
    await page.evaluate(() => window.history.replaceState(window.history.state, '', '/'))
  })
})

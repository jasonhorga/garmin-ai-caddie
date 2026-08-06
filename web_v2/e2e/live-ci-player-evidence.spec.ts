import { expect, test, type Locator, type Page } from '@playwright/test'

const playerToken = process.env.AI_CADDIE_CI_PLAYER_TOKEN?.trim()

test.use({ trace: 'off', screenshot: 'off', video: 'off' })

test.describe('real isolated CI player evidence', () => {
  test.skip(!playerToken, 'AI_CADDIE_CI_PLAYER_TOKEN is required for real evidence')

  async function captureWithoutCredentialInLocation(
    page: Page,
    filename: string,
    requiredEvidence?: Locator,
  ): Promise<void> {
    const credentialPath = await page.evaluate(
      () => `${window.location.pathname}${window.location.search}${window.location.hash}`,
    )
    await page.evaluate(() => window.history.replaceState(window.history.state, '', '/'))
    try {
      if (requiredEvidence) {
        await expect(requiredEvidence, `${filename} must capture the requested product state`).toBeInViewport({ ratio: 1 })
      }
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

    // Keep failure evidence useful without ever printing the capability token or request headers.
    // The prior run only said that the topo <img> disappeared; these two boundaries distinguish an
    // old shot-map payload from a browser-side topo fetch/decode failure.
    page.on('response', async (response) => {
      const url = new URL(response.url())
      if (url.pathname.endsWith('/shotmap')) {
        const body = (await response.json().catch(() => null)) as Record<string, unknown> | null
        console.log(
          'LIVE_EVIDENCE_SHOTMAP',
          JSON.stringify({
            status: response.status(),
            found: body?.found ?? null,
            hasMap: body?.map != null,
            globalId: body?.globalId ?? null,
            localHole: body?.localHole ?? null,
          }),
        )
      }
      if (url.pathname.endsWith('/topo.png')) {
        console.log(
          'LIVE_EVIDENCE_TOPO_RESPONSE',
          JSON.stringify({ pathname: url.pathname, status: response.status(), contentType: response.headers()['content-type'] ?? null }),
        )
      }
    })
    page.on('requestfailed', (request) => {
      const url = new URL(request.url())
      if (url.pathname.endsWith('/history/overview')) {
        console.log(
          'LIVE_EVIDENCE_OVERVIEW_FAILED',
          JSON.stringify({ pathname: url.pathname, error: request.failure()?.errorText ?? 'unknown' }),
        )
      } else if (url.pathname.endsWith('/topo.png')) {
        console.log(
          'LIVE_EVIDENCE_TOPO_FAILED',
          JSON.stringify({ pathname: url.pathname, error: request.failure()?.errorText ?? 'unknown' }),
        )
      }
    })

    const overviewResponsePromise = page.waitForResponse(
      (response) => {
        const url = new URL(response.url())
        return response.request().method() === 'GET' && url.pathname.endsWith('/history/overview')
      },
      { timeout: 60_000 },
    )
    await page.goto(`/p/${encodeURIComponent(playerToken)}`, { waitUntil: 'domcontentloaded' })
    const overviewResponse = await overviewResponsePromise
    const overviewPath = new URL(overviewResponse.url()).pathname
    console.log(
      'LIVE_EVIDENCE_OVERVIEW_RESPONSE',
      JSON.stringify({ pathname: overviewPath, status: overviewResponse.status() }),
    )
    expect(overviewResponse.status(), 'isolated player overview must authorize in the browser').toBe(200)

    const roundPicker = page.locator('[aria-label="选择球局"]')
    try {
      await expect(roundPicker).toBeVisible({ timeout: 60_000 })
    } catch (error) {
      await captureWithoutCredentialInLocation(page, 'review-workbench-load-failure.png')
      throw error
    }
    await expect(roundPicker).toContainText('Cypress Point')
    await expect(page.locator('[aria-label="第1洞落点图"]')).toBeVisible()
    try {
      await expect(page.locator('.hole-base-topo.is-ready')).toBeVisible({ timeout: 60_000 })
    } catch (error) {
      await captureWithoutCredentialInLocation(page, 'review-workbench-topo-failure.png')
      throw error
    }
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
    const roundDetailHeading = roundDetail.getByRole('heading', { name: '球局回顾', exact: true })
    await expect(roundDetailHeading).toBeVisible()
    // The heading also exists in the loading shell. Evidence is valid only after the protected
    // detail GET has resolved into the real scorecard, otherwise the browser can close after the
    // CORS preflight and leave a misleading "正在加载球局…" screenshot behind.
    await expect(roundDetail.getByLabel('球局数据')).toBeVisible({ timeout: 60_000 })
    await expect(roundDetail).toContainText('Cypress Point Club')
    await expect(roundDetail.getByText('正在加载球局…')).toHaveCount(0)
    // Keep the loaded detail heading immediately below the sticky 54 px app bar. Capturing from
    // scrollY=0 only shows the archive list above this panel and falsely looks like a duplicate.
    await roundDetail.evaluate((node) => node.scrollIntoView({ block: 'start', behavior: 'instant' }))
    await page.evaluate(() => window.scrollBy(0, -64))
    await expect(roundDetailHeading).toBeInViewport({ ratio: 1 })
    await expect
      .poll(async () => Math.round((await roundDetail.boundingBox())?.y ?? -1))
      .toBeGreaterThanOrEqual(54)
    await captureWithoutCredentialInLocation(page, 'round-review.png', roundDetailHeading)

    // Leave no capability token in the final page URL when the browser context closes.
    await page.evaluate(() => window.history.replaceState(window.history.state, '', '/'))
  })
})

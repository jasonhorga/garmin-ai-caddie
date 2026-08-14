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
    if (requiredEvidence) {
      await expect(requiredEvidence, `${filename} must capture the requested product state`).toBeInViewport({ ratio: 1 })
    }
    // `page.screenshot` captures page pixels, not browser chrome or the address bar. Keep the
    // capability URL intact while React is live: api.ts intentionally reads that URL when it creates
    // each Bearer request, so replacing it with `/` around an asynchronous screenshot can race a
    // state update and silently de-authorize the next detail fetch. The final cleanup below still
    // removes the credential before the browser context closes.
    await page.screenshot({
      path: `web-live-evidence/${filename}`,
      animations: 'disabled',
    })
  }

  test('captures the real results journey from overview through round detail', async ({ page }) => {
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
      if (/\/history\/rounds\/[^/]+$/.test(url.pathname)) {
        console.log(
          'LIVE_EVIDENCE_ROUND_DETAIL_RESPONSE',
          JSON.stringify({ pathname: url.pathname.replace(/\/[^/]+$/, '/[round]'), status: response.status() }),
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
      } else if (/\/history\/rounds\/[^/]+$/.test(url.pathname)) {
        console.log(
          'LIVE_EVIDENCE_ROUND_DETAIL_FAILED',
          JSON.stringify({ pathname: url.pathname.replace(/\/[^/]+$/, '/[round]'), error: request.failure()?.errorText ?? 'unknown' }),
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

    const resultsSubnav = page.getByRole('navigation', { name: '辅助导航' })

    const resultsLanding = page.locator('section[aria-label="成绩主页"]')
    await expect(resultsLanding).toBeVisible({ timeout: 60_000 })
    await expect(resultsLanding).toContainText('Cypress Point')
    await captureWithoutCredentialInLocation(page, 'results-overview.png', resultsLanding)

    await resultsSubnav.getByRole('button', { name: '时间趋势', exact: true }).click()
    const trends = page.locator('section[aria-label="时间趋势"]')
    await expect(trends.getByRole('heading', { name: '时间趋势', exact: true })).toBeVisible({ timeout: 60_000 })
    await expect(page.getByText('统计加载失败')).toHaveCount(0)
    await captureWithoutCredentialInLocation(page, 'time-trends.png', trends)

    await resultsSubnav.getByRole('button', { name: '表现分析', exact: true }).click()
    const performance = page.locator('section[aria-label="表现分析"]')
    await expect(performance.getByRole('heading', { name: '表现分析', exact: true })).toBeVisible({ timeout: 60_000 })
    await expect(performance.locator('section[aria-label="四个环节"]')).toBeVisible()
    await expect(page.getByText('表现分析加载失败')).toHaveCount(0)
    await captureWithoutCredentialInLocation(page, 'performance-analysis.png', performance)

    await resultsSubnav.getByRole('button', { name: '全部球局', exact: true }).click()
    await expect(page.getByRole('heading', { name: '球局', exact: true, level: 1 })).toBeVisible()
    const firstRound = page.getByRole('button', { name: /^打开球局 / }).first()
    try {
      await expect(firstRound).toBeVisible({ timeout: 60_000 })
    } catch (error) {
      await captureWithoutCredentialInLocation(page, 'rounds-list-load-failure.png')
      throw error
    }
    await expect(firstRound).toHaveAccessibleName(/Cypress Point/)
    await captureWithoutCredentialInLocation(page, 'rounds-list.png')

    await firstRound.click()
    await expect(page.locator('[aria-label="选择球局"]')).toContainText('Cypress Point')
    await expect(page.locator('[aria-label="第1洞落点图"]')).toBeVisible()
    try {
      await expect(page.locator('.hole-base-topo.is-ready')).toBeVisible({ timeout: 60_000 })
    } catch (error) {
      await captureWithoutCredentialInLocation(page, 'review-workbench-topo-failure.png')
      throw error
    }
    await captureWithoutCredentialInLocation(page, 'review-workbench.png')

    const roundDetail = page.locator('.round-detail-panel')
    const roundDetailHeading = roundDetail.getByRole('heading', { name: '球局回顾', exact: true })
    await expect(roundDetailHeading).toBeVisible()
    // The heading also exists in the loading shell. Evidence is valid only after the protected
    // detail GET has resolved into the real scorecard, otherwise the browser can close after the
    // CORS preflight and leave a misleading "正在加载球局…" screenshot behind.
    try {
      await expect(roundDetail.getByLabel('球局数据')).toBeVisible({ timeout: 60_000 })
    } catch (error) {
      await captureWithoutCredentialInLocation(page, 'round-review-load-failure.png', roundDetailHeading)
      throw error
    }
    await expect(roundDetail).toContainText('Cypress Point Club')
    await expect(roundDetail.getByText('正在加载球局…')).toHaveCount(0)
    // The product scroll target owns a sticky-bar-safe scroll margin. Exercise that real behavior
    // and compare against the rendered bar instead of baking its old 54 px height into the gate.
    await roundDetail.evaluate((node) => node.scrollIntoView({ block: 'start', behavior: 'instant' }))
    await expect(roundDetailHeading).toBeInViewport({ ratio: 1 })
    await expect
      .poll(async () => {
        const detailBox = await roundDetail.boundingBox()
        const appBarBox = await page.locator('.app-topbar').boundingBox()
        if (!detailBox || !appBarBox) return -1
        return Math.round(detailBox.y - (appBarBox.y + appBarBox.height))
      })
      .toBeGreaterThanOrEqual(8)
    await captureWithoutCredentialInLocation(page, 'round-review.png', roundDetailHeading)

    // Leave no capability token in the final page URL when the browser context closes.
    await page.evaluate(() => window.history.replaceState(window.history.state, '', '/'))
  })
})

import { expect, test, type Locator, type Page } from '@playwright/test'

const playerToken = process.env.AI_CADDIE_CI_PLAYER_TOKEN?.trim()
const adminToken = process.env.AI_CADDIE_ADMIN_TOKEN?.trim()
const reviewRoundRef = process.env.REVIEW_ROUND_REF?.trim()
const useOwnerEvidence = Boolean(adminToken && reviewRoundRef)

test.use({ trace: 'off', screenshot: 'off', video: 'off' })

test.describe('real isolated CI player evidence', () => {
  test.skip(!playerToken && !useOwnerEvidence, 'a CI player token or owner admin token is required for real evidence')

  async function captureWithoutCredentialInLocation(
    page: Page,
    filename: string,
    requiredAnchor?: Locator,
  ): Promise<void> {
    if (requiredAnchor) {
      // The evidence canvas is deliberately fixed at the approved 1440×980 desktop target. Pages
      // such as Time Trends are taller than one viewport, so requiring their entire root section to
      // fit is impossible. Gate the state-specific heading/anchor instead; the assertions at each
      // call site still verify the real data-bearing modules before this viewport is captured.
      await expect(requiredAnchor, `${filename} must capture the requested product state`).toBeInViewport({ ratio: 1 })
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
    if (!playerToken && !useOwnerEvidence) return

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
    if (useOwnerEvidence) {
      // Keep the owner token in Playwright's isolated localStorage only. The app's bare-URL owner
      // path sends it as an admin header; no capability token is placed in the URL or screenshots.
      await page.addInitScript((token) => {
        window.localStorage.setItem('ai-caddie.admin-token', token)
      }, adminToken)
      await page.goto('/', { waitUntil: 'domcontentloaded' })
    } else {
      await page.goto(`/p/${encodeURIComponent(playerToken!)}`, { waitUntil: 'domcontentloaded' })
    }
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
    if (!useOwnerEvidence) {
      await expect(resultsLanding).toContainText('Cypress Point')
    }
    await captureWithoutCredentialInLocation(
      page,
      'results-overview.png',
      resultsLanding.getByRole('heading', { name: '成绩', exact: true }),
    )

    await resultsSubnav.getByRole('button', { name: '时间趋势', exact: true }).click()
    const trends = page.locator('section[aria-label="时间趋势"]')
    const trendsHeading = trends.getByRole('heading', { name: '时间趋势', exact: true })
    await expect(trendsHeading).toBeVisible({ timeout: 60_000 })
    await expect(page.getByText('统计加载失败')).toHaveCount(0)
    await captureWithoutCredentialInLocation(page, 'time-trends.png', trendsHeading)

    await resultsSubnav.getByRole('button', { name: '表现分析', exact: true }).click()
    const performance = page.locator('section[aria-label="表现分析"]')
    const performanceHeading = performance.getByRole('heading', { name: '表现分析', exact: true })
    await expect(performanceHeading).toBeVisible({ timeout: 60_000 })
    await expect(performance.locator('section[aria-label="四个环节"]')).toBeVisible()
    await expect(page.getByText('表现分析加载失败')).toHaveCount(0)
    await captureWithoutCredentialInLocation(page, 'performance-analysis.png', performanceHeading)

    await resultsSubnav.getByRole('button', { name: '全部球局', exact: true }).click()
    await expect(page.getByRole('heading', { name: '球局', exact: true, level: 1 })).toBeVisible()
    let targetRoundLabel: string | null = null
    let targetCourseName: string | null = null
    if (reviewRoundRef) {
      const apiOrigin = process.env.VITE_AI_CADDIE_API_BASE_URL?.trim()
      if (!apiOrigin) throw new Error('VITE_AI_CADDIE_API_BASE_URL is required with REVIEW_ROUND_REF')
      const roundsResponse = await page.request.get(
        `${apiOrigin.replace(/\/$/, '')}/api/v2/history/rounds?hasShots=true&limit=2000`,
        {
          headers: useOwnerEvidence
            ? { 'x-ai-caddie-admin-token': adminToken! }
            : { 'x-ai-caddie-player-token': playerToken! },
        },
      )
      expect(roundsResponse.ok(), 'target round lookup must authorize').toBeTruthy()
      const roundsPayload = (await roundsResponse.json()) as {
        groups?: Array<{ rounds?: Array<{ id?: string; courseName?: string; date?: string | null; score?: number | null }> }>
      }
      const target = (roundsPayload.groups ?? [])
        .flatMap((group) => group.rounds ?? [])
        .find((round) => round.id === reviewRoundRef)
      if (!target) throw new Error(`review round ${reviewRoundRef} was not returned by history rounds`)
      const course = (target.courseName ?? '未知球场').replace(/\s*~\s*/g, ' · ').replace(/\s+-\s+/g, ' · ')
      const date = target.date?.match(/^\d{4}-\d{2}-\d{2}/)?.[0] ?? '未知日期'
      targetCourseName = course
      targetRoundLabel = `打开球局 ${course}，${date}，成绩 ${target.score ?? '-'}`
    }
    const firstRound = targetRoundLabel
      ? page.getByRole('button', { name: targetRoundLabel, exact: true })
      : page.getByRole('button', { name: /^打开球局 / }).first()
    try {
      await expect(firstRound).toBeVisible({ timeout: 60_000 })
    } catch (error) {
      await captureWithoutCredentialInLocation(page, 'rounds-list-load-failure.png')
      throw error
    }
    await expect(firstRound).toHaveAccessibleName(targetRoundLabel ? targetRoundLabel : /Cypress Point/)
    await captureWithoutCredentialInLocation(page, 'rounds-list.png')

    await firstRound.click()
    await expect(page.locator('[aria-label="选择球局"]')).toContainText(targetCourseName ?? 'Cypress Point')
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
    await expect(roundDetail).toContainText(targetCourseName ?? 'Cypress Point Club')
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

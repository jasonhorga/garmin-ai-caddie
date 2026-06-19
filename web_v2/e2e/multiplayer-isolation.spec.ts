import { expect, test, type Page } from '@playwright/test'

// Multiplayer foundation, stage 1 — e2e isolation walk (Task 14).
//
// Reuses the page.route mockApi pattern from history-visual.smoke.spec.ts, but
// the mocks are TOKEN-SCOPED: a player surface only ever answers a request that
// carries THAT player's bearer, so the walk proves URL-token isolation on the
// wire AND that the UI never exposes another player, a switcher, or owner
// controls. Two deployments are exercised:
//   • player-facing (VITE_AI_CADDIE_REQUIRE_LINK=true, server :5175): a bare URL
//     with no credential is locked out behind the "needs a valid link" page and
//     fires zero data requests; a valid /p/<token> link loads only that player.
//   • owner/homeserver (no flag, default server :5174): the admin token unlocks
//     the player-management page, which issues a one-time link, lists only
//     tokenLast4 (never the plaintext token), and shows no score analysis.

const PLAYER_FACING_BASE_URL = 'http://127.0.0.1:5175'

// Player A is the link holder for the player-side walk. Player B and the owner's
// round ids exist ONLY as strings the walk asserts NEVER surface under A's link.
const PLAYER_A = { id: 'lao-wang', name: '老王', token: 'plr-a-1111aaaa' }
const PLAYER_A_MANUAL_ROUND = '700001'
const PLAYER_A_GARMIN_ROUND = '700003'
const OTHER_PLAYER_NAME = '阿强'
const OTHER_PLAYER_ROUND = '800002'

// Owner-side fixtures.
const ADMIN_TOKEN = 'owner-admin-secret-xyz'
const ISSUED_TOKEN = 'one-time-plain-9f8e7d6c5b4a'
const ISSUED_URL = `http://127.0.0.1:5174/p/${ISSUED_TOKEN}`

const EMPTY_OPTIONS = {
  schema: 'ai-caddie-mobile-course-options-v1',
  dataMode: 'fixture',
  total: 0,
  courses: [],
  emptyState: null,
  generatedAt: '2026-05-25T08:00:00Z',
}

const SYNC_STATUS = {
  schema: 'ai-caddie-sync-status-v2',
  connector: {
    name: 'garmin_cn_web_session',
    state: 'ready',
    detail: 'Local Garmin snapshots are available.',
    canSync: true,
    reauthRequired: false,
    nextAction: 'review_history',
  },
  connectors: [
    {
      name: 'garmin_cn_web_session',
      state: 'ready',
      detail: 'CN session connector is ready.',
      canSync: true,
      reauthRequired: false,
      nextAction: 'review_history',
    },
  ],
  snapshot: {
    dataMode: 'fixture',
    scorecardCount: 2,
    shotFileCount: 2,
    summaryPresent: true,
    lastSuccessfulSyncAt: '2026-05-25T10:00:00Z',
  },
  lastRun: { state: 'ready', snapshotId: 'snap-1' },
}

const READINESS = {
  schema: 'ai-caddie-readiness-v1',
  status: 'ready',
  checks: [{ label: 'service', state: 'ready', detail: 'API process is responding.', evidence: {} }],
}

function manualRound() {
  return {
    id: PLAYER_A_MANUAL_ROUND,
    date: '2026-05-20',
    courseName: '梅花山 A',
    courseKey: 'meihua',
    holesCompleted: 18,
    score: 84,
    par: 72,
    toPar: 12,
    scoreStrip: [],
    badges: [],
    primaryIssue: null,
    source: 'manual',
  }
}

function garminRound() {
  return {
    id: PLAYER_A_GARMIN_ROUND,
    date: '2026-05-10',
    courseName: '观澜湖 B',
    courseKey: 'mission_hills',
    holesCompleted: 18,
    score: 80,
    par: 72,
    toPar: 8,
    scoreStrip: [],
    badges: [],
    primaryIssue: null,
    source: 'garmin',
  }
}

function overviewFor(currentPlayer: { id: string; name: string; isOwner: boolean }) {
  return {
    schema: 'ai-caddie-history-overview-v2',
    metrics: {
      totalRounds: 2,
      eighteenHoleRounds: 2,
      nineHoleRounds: 0,
      courseCount: 2,
      shotCount: 100,
      average18: 82,
      recent10Average: 82,
      bestScore: 80,
    },
    recentRounds: [manualRound(), garminRound()],
    distribution: { total: 2, average: 82, best: 80, worst: 84, families: [], histogram: [] },
    dataQuality: [],
    emptyState: null,
    currentPlayer: { ...currentPlayer, avatar: null },
  }
}

function statsPayload() {
  return {
    schema: 'ai-caddie-history-stats-v1',
    dataMode: 'fixture',
    summary: { totalRounds: 2, recent10Average: 82, average18: 82, bestScore: 80, worstScore: 84 },
    time: { byYear: [], byQuarter: [], byMonth: [], playFrequency: {}, improvement: {} },
    scoring: { scoreBands: [], outcomes: {}, phaseStats: [] },
    courseDistribution: [],
    records: {},
    courses: [],
    holes: [],
    clubs: [],
    issues: [],
    dataQuality: [],
    drillDown: { roundIds: [], roundRefs: [] },
  }
}

function summaryPayload() {
  const stats = statsPayload()
  return { schema: 'ai-caddie-history-summary-v1', summary: stats.summary, topIssue: stats.issues[0]?.issue ?? null }
}

function roundsPayload() {
  return {
    schema: 'ai-caddie-history-rounds-v2',
    total: 2,
    groups: [
      {
        key: '2026-05',
        label: 'May 2026',
        count: 2,
        average18: 82,
        bestScore: 80,
        rounds: [manualRound(), garminRound()],
      },
    ],
    emptyState: null,
    availableYears: ['2026'],
    availableCourses: [
      { key: 'meihua', label: '梅花山 A' },
      { key: 'mission_hills', label: '观澜湖 B' },
    ],
  }
}

function ownerPlayers() {
  return {
    players: [
      { id: 'me', name: '我', isOwner: true, createdAt: null, avatar: null, tokenLast4: null, roundCount: 467, sources: { garmin: 460, manual: 7 } },
      { id: 'lao-wang', name: '老王', isOwner: false, createdAt: '2026-05-01', avatar: null, tokenLast4: 'aaaa', roundCount: 5, sources: { garmin: 4, manual: 1 } },
      { id: 'a-qiang', name: '阿强', isOwner: false, createdAt: '2026-05-02', avatar: null, tokenLast4: 'bbbb', roundCount: 3, sources: { garmin: 3 } },
    ],
  }
}

// Token-scoped mock for the player-side walk: every data endpoint returns A's
// data ONLY when the request carries A's bearer; anything else is 401. So if the
// frontend ever dropped the URL token (or tried to reach another player), the
// page would fall to the invalid-link state instead of silently showing data.
async function mockPlayerApi(page: Page, player: { token: string }) {
  const bearerSeen: Array<string | undefined> = []
  await page.route('**/api/v2/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const auth = request.headers()['authorization']
    bearerSeen.push(auth)
    const gated = (json: unknown) =>
      auth === `Bearer ${player.token}`
        ? route.fulfill({ json })
        : route.fulfill({ status: 401, json: { detail: 'unauthorized' } })
    if (path === '/api/v2/history/overview') return gated(overviewFor({ id: PLAYER_A.id, name: PLAYER_A.name, isOwner: false }))
    if (path === '/api/v2/history/stats') return gated(statsPayload())
    if (path === '/api/v2/history/summary') return gated(summaryPayload())
    if (path === '/api/v2/history/rounds') return gated(roundsPayload())
    if (path === '/api/v2/mobile/courses/options') return gated(EMPTY_OPTIONS)
    if (path === '/api/v2/sync/status') return route.fulfill({ json: SYNC_STATUS })
    if (path === '/api/v2/readiness') return route.fulfill({ json: READINESS })
    return route.fulfill({ status: 404, json: { detail: `Unhandled test route: ${path}` } })
  })
  return { bearerSeen }
}

// Owner-side mock: admin/players endpoints are gated on the admin token header
// (never a bearer), mirroring the server-side admin gate. create returns the
// one-time plaintext token+url; the list view never carries token material.
async function mockOwnerApi(page: Page) {
  const adminHeadersSeen: Array<string | undefined> = []
  const createBodies: Array<unknown> = []
  await page.route('**/api/v2/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    const adminHeader = request.headers()['x-ai-caddie-admin-token']
    if (path === '/api/v2/admin/players' && request.method() === 'GET') {
      adminHeadersSeen.push(adminHeader)
      return adminHeader === ADMIN_TOKEN
        ? route.fulfill({ json: ownerPlayers() })
        : route.fulfill({ status: 401, json: { detail: 'admin required' } })
    }
    if (path === '/api/v2/admin/players' && request.method() === 'POST') {
      adminHeadersSeen.push(adminHeader)
      createBodies.push(request.postDataJSON())
      return adminHeader === ADMIN_TOKEN
        ? route.fulfill({ json: { id: 'xiao-li', name: '小李', token: ISSUED_TOKEN, url: ISSUED_URL } })
        : route.fulfill({ status: 401, json: { detail: 'admin required' } })
    }
    if (path === '/api/v2/history/overview') return route.fulfill({ json: overviewFor({ id: 'me', name: '我', isOwner: true }) })
    if (path === '/api/v2/history/stats') return route.fulfill({ json: statsPayload() })
    if (path === '/api/v2/history/summary') return route.fulfill({ json: summaryPayload() })
    if (path === '/api/v2/mobile/courses/options') return route.fulfill({ json: EMPTY_OPTIONS })
    if (path === '/api/v2/sync/status') return route.fulfill({ json: SYNC_STATUS })
    if (path === '/api/v2/readiness') return route.fulfill({ json: READINESS })
    return route.fulfill({ status: 404, json: { detail: `Unhandled test route: ${path}` } })
  })
  return { adminHeadersSeen, createBodies }
}

test.describe('player-facing deployment (link required)', () => {
  test.use({ baseURL: PLAYER_FACING_BASE_URL })

  test('no credential → invalid-link page, zero data requests, no player leaked', async ({ page }) => {
    const browserErrors: string[] = []
    page.on('pageerror', (error) => browserErrors.push(error.message))
    page.on('console', (message) => {
      if (message.type() === 'error') browserErrors.push(message.text())
    })
    // Record every API call that escapes; a locked-out visitor must make none.
    const apiRequests: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/v2/')) apiRequests.push(new URL(request.url()).pathname)
    })

    await page.goto('/')

    await expect(page.getByRole('heading', { name: '需要有效链接' })).toBeVisible()
    // Locked out leaks nothing: no data request fires…
    expect(apiRequests).toEqual([])
    // …no player identity is rendered…
    await expect(page.getByText(PLAYER_A.name)).toHaveCount(0)
    await expect(page.getByText(OTHER_PLAYER_NAME)).toHaveCount(0)
    // …and there is no app shell / navigation at all.
    await expect(page.getByText('想备哪场?')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '概览' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '设置' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '球员管理' })).toHaveCount(0)
    expect(browserErrors).toEqual([])
  })

  test('player link shows only that player, read-only, with no switcher or owner controls', async ({ page }) => {
    const browserErrors: string[] = []
    page.on('pageerror', (error) => browserErrors.push(error.message))
    page.on('console', (message) => {
      if (message.type() === 'error') browserErrors.push(message.text())
    })
    const { bearerSeen } = await mockPlayerApi(page, PLAYER_A)

    await page.goto(`/p/${PLAYER_A.token}`)

    // Read-only "当前是谁" badge: name only, no switcher / dropdown.
    const badge = page.getByLabel(`当前球员 ${PLAYER_A.name}`)
    await expect(badge).toBeVisible()
    await expect(badge.locator('button, select, [role="combobox"], [role="listbox"]')).toHaveCount(0)

    // The home view shows THIS player's last round…
    await expect(page.getByText('梅花山 A')).toBeVisible()
    // …and never another player's identity or round id.
    await expect(page.getByText(OTHER_PLAYER_NAME)).toHaveCount(0)
    await expect(page.getByText(OTHER_PLAYER_ROUND)).toHaveCount(0)

    // A player link cannot reach the owner management surface: the settings
    // section renders, but 球员管理 is absent from its subnav (订正 proves the
    // subnav itself did render).
    await page.getByRole('button', { name: '设置' }).click()
    await expect(page.getByRole('heading', { name: '同步与数据健康', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '订正' })).toBeVisible()
    await expect(page.getByRole('button', { name: '球员管理' })).toHaveCount(0)

    // Wire-level proof: every request carried THIS player's bearer — no
    // anonymous or cross-player call slipped through.
    expect(bearerSeen.length).toBeGreaterThan(0)
    expect(bearerSeen.every((auth) => auth === `Bearer ${PLAYER_A.token}`)).toBe(true)
    expect(browserErrors).toEqual([])
  })

  test('player history marks the manual round with a 手动 chip and leaves the garmin round unmarked', async ({ page }) => {
    const browserErrors: string[] = []
    page.on('pageerror', (error) => browserErrors.push(error.message))
    page.on('console', (message) => {
      if (message.type() === 'error') browserErrors.push(message.text())
    })
    await mockPlayerApi(page, PLAYER_A)

    await page.goto(`/p/${PLAYER_A.token}`)
    await page.getByRole('button', { name: '历史', exact: true }).click()
    await page.getByRole('button', { name: '球局' }).click()
    await expect(page.getByRole('heading', { name: '球局', exact: true, level: 1 })).toBeVisible()

    // Both rounds list as cards (raw round-id refs are owner-diagnostics-only now); the
    // course name is the card heading (disambiguated from the filter <option> of the same text).
    await expect(page.getByRole('heading', { name: '梅花山 A' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '观澜湖 B' })).toBeVisible()
    // …but only the manual one carries the 手动 chip.
    await expect(page.getByLabel('手动录入的球局')).toHaveCount(1)
    // and still no other player's round leaks into this player's history.
    await expect(page.getByText(OTHER_PLAYER_ROUND)).toHaveCount(0)
    expect(browserErrors).toEqual([])
  })
})

test.describe('owner deployment (admin token)', () => {
  test('owner manages players: issues a one-time link, lists only tokenLast4, shows no score analysis', async ({ page }) => {
    const browserErrors: string[] = []
    page.on('pageerror', (error) => browserErrors.push(error.message))
    page.on('console', (message) => {
      if (message.type() === 'error') browserErrors.push(message.text())
    })
    const { adminHeadersSeen, createBodies } = await mockOwnerApi(page)

    await page.goto('/')
    await expect(page.getByText('你好 👋')).toBeVisible()

    await page.getByRole('button', { name: '设置' }).click()
    await expect(page.getByRole('heading', { name: '同步与数据健康', exact: true })).toBeVisible()
    // 球员管理 is hidden until the owner supplies an admin token.
    await expect(page.getByRole('button', { name: '球员管理' })).toHaveCount(0)
    await page.locator('#sync-admin-token').fill(ADMIN_TOKEN)
    await page.getByRole('button', { name: '球员管理' }).click()

    await expect(page.getByRole('heading', { name: '球员管理', exact: true })).toBeVisible()
    // List view: name + tokenLast4 only, never the plaintext token.
    await expect(page.getByText('老王')).toBeVisible()
    await expect(page.getByText('链接尾号 …aaaa')).toBeVisible()
    await expect(page.getByText('链接尾号 …bbbb')).toBeVisible()
    await expect(page.getByText('本人')).toBeVisible()

    // Create a player → one-time link banner carries the plaintext url.
    // Submit via Enter: on the narrow mobile viewport the sticky section head can
    // overlap the submit button's click point, so keyboard submit drives the same
    // handleCreate path without depending on the button being click-reachable.
    await page.getByLabel('球员名字').fill('小李')
    await page.getByLabel('球员名字').press('Enter')
    const banner = page.getByRole('region', { name: '一次性专属链接' })
    await expect(banner).toBeVisible()
    await expect(banner.locator('code.player-admin-url')).toContainText(ISSUED_URL)
    await expect(page.getByRole('heading', { name: '小李 的专属链接' })).toBeVisible()
    // The one-time secret never bleeds into the player list rows.
    await expect(page.getByRole('list', { name: '球员列表' })).not.toContainText(ISSUED_TOKEN)

    // The management page renders NO score analysis — only players + links.
    for (const forbidden of ['成绩走势', '你最该练', '记分卡', '球道命中率', PLAYER_A_MANUAL_ROUND, OTHER_PLAYER_ROUND]) {
      await expect(page.getByText(forbidden, { exact: false })).toHaveCount(0)
    }
    await expect(page.getByLabel('手动录入的球局')).toHaveCount(0)

    // Wire-level proof: admin endpoints were called WITH the admin token, never
    // anonymously, and the create POST carried the new player's name.
    expect(adminHeadersSeen.length).toBeGreaterThan(0)
    expect(adminHeadersSeen.every((token) => token === ADMIN_TOKEN)).toBe(true)
    expect(createBodies).toContainEqual({ name: '小李' })
    expect(browserErrors).toEqual([])
  })
})

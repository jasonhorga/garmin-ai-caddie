import { readFileSync } from 'node:fs'
import { expect, test as base, type Page } from '@playwright/test'

// Synthetic, handwritten API projections. No production data or product helpers.
// The arithmetic and the independent UI oracle are documented in README.md.
export const COURSE = 'Fixture Orchard'
export const GID = 99001
export const ROUND = 'fixture-18-par'
export const PLAYER_LINK = 'fixture-player-capability'
export const ADMIN = 'fixture-admin-only'
export const SESSION_HEADER = 'fixture-session-material'
export const CSRF = 'fixture-antiforgery-material'

const strip = (scores: number[]) => scores.map((score, index) => ({
  hole: index + 1, par: 4, score, toPar: score - 4,
  className: score === 4 ? 'par' : 'bogey',
}))

const rounds = [
  { id: ROUND, date: '2026-05-20T08:00:00Z', courseName: COURSE, courseKey: 'fixture_orchard', holesCompleted: 18, score: 72, par: 72, toPar: 0, shotCount: 3, badges: [], scoreStrip: strip(Array(18).fill(4)) },
  { id: 'fixture-18-bogey', date: '2026-05-13T08:00:00Z', courseName: COURSE, courseKey: 'fixture_orchard', holesCompleted: 18, score: 90, par: 72, toPar: 18, shotCount: 3, badges: [], scoreStrip: strip(Array(18).fill(5)) },
  { id: 'fixture-9', date: '2026-05-06T08:00:00Z', courseName: COURSE, courseKey: 'fixture_orchard', holesCompleted: 9, score: 40, par: 36, toPar: 4, shotCount: 3, badges: [], scoreStrip: strip([5, 5, 5, 5, 4, 4, 4, 4, 4]) },
]

const summary = {
  totalRounds: 3, eighteenHoleRounds: 2, nineHoleRounds: 1, mergedRounds: 0,
  courseCount: 1, average18: 81, median18: 81, bestScore: 72, worstScore: 90,
  recent5Average: 81, recent10Average: 81, recent20Average: 81, shotCount: 9,
  handicapEstimate: null, handicapTrend: null,
}

const stats = {
  schema: 'ai-caddie-history-stats-v1', dataMode: 'fixture', summary,
  time: {
    byYear: [{ key: '2026', roundCount: 3, average18: 81, bestScore: 72, roundIds: [ROUND, 'fixture-18-bogey', 'fixture-9'] }],
    byQuarter: [], byMonth: [], byDay: [],
    playFrequency: { totalMonths: 1, roundsPerMonth: 3 },
  },
  trend: { points: [] },
  scoring: {
    // All 45 holes have Par 4: 23 pars and 22 bogeys.
    outcomes: { eagleOrBetter: 0, birdie: 0, par: 23, bogey: 22, doubleOrWorse: 0 },
    outcomeDistribution: [],
    byPar: [{ par: 4, holeCount: 45, averageToPar: 0.5, parOrBetter: 23, parOrBetterPct: 51.1 }],
    phaseStats: [
      { phase: 'Tee', fairwaysRecorded: 45, fairwaysHit: 24, fairwayMissLeft: 12, fairwayMissRight: 9 },
      { phase: 'Approach', girRecorded: 45, gir: 18, missedGir: 27 },
    ],
    putting: { totalPutts: 108, roundsWithPutts: 3, averagePuttsPerRound: 36, averagePutts: 2.4, threePutts: 18 },
    scoreBands: [{ label: '70s', count: 1, roundIds: [ROUND] }, { label: '90s', count: 1, roundIds: ['fixture-18-bogey'] }],
  },
  courses: [{ courseKey: 'fixture_orchard', courseName: COURSE, roundCount: 3, average18: 81, bestScore: 72, worstScore: 90, nineBreakdown: [], rounds: [], roundRefs: [ROUND] }],
  holes: [
    { courseKey: 'fixture_orchard', hole: 1, sampleCount: 3, averageToPar: 0.7, worstToPar: 1, holeRefs: [`${ROUND}:1`] },
    { courseKey: 'fixture_orchard', hole: 2, sampleCount: 3, averageToPar: 0.7, worstToPar: 1, holeRefs: [`${ROUND}:2`] },
  ],
  clubs: [
    { club: '1D', sampleCount: 3, median: 200, p10: 200, p90: 200, max: 200, confidence: 'low', shotRefs: [`${ROUND}:1:0`] },
    { club: '7I', sampleCount: 3, median: 50, p10: 50, p90: 50, max: 50, confidence: 'low', shotRefs: [`${ROUND}:1:1`] },
    { club: 'PW', sampleCount: 3, median: 50, p10: 50, p90: 50, max: 50, confidence: 'low', shotRefs: [`${ROUND}:1:2`] },
  ],
  issues: [], diagnosis: {}, courseDistribution: [], records: {}, dataQuality: [],
  drillDown: { roundIds: [ROUND], roundRefs: [ROUND] },
}

const overlay = { w: 300, h: 500, ppm: 1, ln: 300, route: [[150, 450, 0], [150, 150, 300]] }
const secondOverlay = { w: 300, h: 500, ppm: 1, ln: 200, route: [[150, 450, 0], [150, 250, 200]] }
const topo = readFileSync(new URL('../../public/hole-sample.png', import.meta.url))
const prep = {
  schema: 'ai-caddie-course-prep-v1', globalId: GID, holeCount: 2,
  // First hole matches C16c caddie_golden.json h1_tee_0: 100/150/200 m.
  clubs: [{ name: '9I', m: 100, yd: 109 }, { name: '6I', m: 150, yd: 164 }, { name: '3W', m: 200, yd: 219 }],
  holes: [
    { hole: 1, par: 4, par_source: 'courseview', blue_yards: 328, route_len_m: 300, route: overlay.route, geometryCoverage: 'ready', geometryRevision: 'fixture-v1', map: { overlay }, landing_m: 150, tee_club: '6I', steps: [{ club: '6I', note: 'Centre line' }, { club: '6I', note: 'Green centre' }], cautions: [], hazards: { water_carry: [], bunkers: [] }, sourceRefs: [`course:${GID}`], missingData: [], candidateRoutes: [], carryTargets: [], yourShots: [] },
    { hole: 2, par: 4, par_source: 'courseview', blue_yards: 219, route_len_m: 200, route: secondOverlay.route, geometryCoverage: 'ready', geometryRevision: 'fixture-v1', map: { overlay: secondOverlay }, landing_m: 100, tee_club: '9I', steps: [{ club: '9I', note: 'Centre line' }], cautions: [], hazards: { water_carry: [], bunkers: [] }, sourceRefs: [`course:${GID}`], missingData: [], candidateRoutes: [], carryTargets: [], yourShots: [] },
  ],
}

const originalShots = [
  { id: 's1', start: [150, 450], end: [150, 250], club: '1D', lie: 'TeeBox', endLie: 'Fairway', shotType: 'TEE', order: 1, synthetic: false },
  { id: 's2', start: [150, 250], end: [150, 200], club: '7I', lie: 'Fairway', endLie: 'Fairway', shotType: 'APPROACH', order: 2, synthetic: false },
  { id: 's3', start: [150, 200], end: [150, 150], club: 'PW', lie: 'Fairway', endLie: 'Green', shotType: 'APPROACH', order: 3, synthetic: false },
]

// Independent, fixed post-edit snapshot: delete s2 and reconnect s3 to s1.
// Do not construct this from a submitted correction or the original array.
export const correctedShots = [
  { id: 's1', start: [150, 450], end: [150, 250], club: '1D', lie: 'TeeBox', endLie: 'Fairway', shotType: 'TEE', order: 1, synthetic: false },
  { id: 's3', start: [150, 250], end: [150, 150], club: 'PW', lie: 'Fairway', endLie: 'Green', shotType: 'APPROACH', order: 2, synthetic: false },
]

export interface Options {
  identity?: 'owner' | 'member' | 'player-link'
  diagnostics?: boolean
  imported?: boolean
  corrected?: boolean
  importRejected?: boolean
  correctionRejected?: boolean
  missingPhases?: boolean
}

export async function productApi(page: Page, options: Options = {}) {
  const identity = options.identity ?? 'owner'
  const records = {
    calls: [] as Array<{ path: string; method: string; auth?: string; admin?: string }>,
    imports: [] as unknown[], corrections: [] as unknown[],
    contexts: [] as URLSearchParams[], decisions: [] as Record<string, unknown>[],
    prepQueries: [] as URLSearchParams[], unexpected: [] as string[],
  }
  let imported = options.imported ?? true
  let corrected = options.corrected ?? false
  await page.addInitScript(({ identity, diagnostics }) => {
    localStorage.setItem('ai-caddie.diagnostics', diagnostics ? '1' : '0')
    if (identity === 'member') {
      localStorage.setItem('ai-caddie.session', JSON.stringify({ token: 'fixture-member-session', playerId: 'fixture-member', expiresAt: '2099-01-01T00:00:00Z' }))
    }
  }, { identity, diagnostics: options.diagnostics ?? false })

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) return route.continue()
    records.unexpected.push(`External request to ${url.origin}`)
    return route.abort('blockedbyclient')
  })
  // Block every API call, including unhandled writes, before it can reach Vite's
  // backend proxy. Unexpected endpoints fail the fixture instead of going live.
  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    records.calls.push({ path, method, auth: request.headers().authorization, admin: request.headers()['x-ai-caddie-admin-token'] })
    const json = (payload: unknown) => route.fulfill({ json: payload })
    if (path === '/api/v2/history/overview' && method === 'GET') return json({ schema: 'ai-caddie-history-overview-v2', metrics: summary, recentRounds: rounds, distribution: { total: 3, average: 81, best: 72, worst: 90, families: [], histogram: [] }, dataQuality: [], emptyState: null, currentPlayer: { id: identity === 'owner' ? 'me' : 'fixture-member', name: 'Fixture Player', avatar: null, isOwner: identity === 'owner' } })
    if (['/api/v2/history/stats', '/api/v2/history/stats/mobile'].includes(path) && method === 'GET') {
      const snapshot = corrected ? {
        ...stats, summary: { ...summary, shotCount: 8 },
        // Fixed projection after deleting one of three 7I shots (3 - 1 = 2).
        clubs: [stats.clubs[0], { ...stats.clubs[1], sampleCount: 2 }, { ...stats.clubs[2], p90: 100, max: 100 }],
      } : stats
      return json(options.missingPhases ? { ...snapshot, scoring: { ...stats.scoring, phaseStats: [], putting: {} } } : snapshot)
    }
    if (path === '/api/v2/history/summary' && method === 'GET') return json({ schema: 'ai-caddie-history-summary-v1', summary, topIssue: null })
    if (path === '/api/v2/history/rounds' && method === 'GET') return json({ schema: 'ai-caddie-history-rounds-v2', total: 3, groups: [{ key: '2026-05', label: 'May 2026', count: 3, average18: 81, bestScore: 72, rounds }], emptyState: null, availableYears: ['2026'], availableCourses: [{ key: 'fixture_orchard', label: COURSE }] })
    if (path === `/api/v2/history/rounds/${ROUND}` && method === 'GET') return json({ schema: 'ai-caddie-history-round-detail-v1', roundRef: ROUND, requestedRef: ROUND, found: true, title: `${COURSE} - 2026-05-20`, round: { id: ROUND, score: 72, toPar: 0, holesScored: 18, shotCount: 3, confidence: 'high', coverage: { scorecard: 'full', shots: 'partial', putts: 'full' } }, scorecard: rounds[0].scoreStrip.map((hole) => ({ ...hole, putts: 2, gir: true, fairway: 'hit', holeRef: `${ROUND}:${hole.hole}`, shotRefs: [], sourceRefs: [`${ROUND}:${hole.hole}`], status: 'complete' })), phaseSummary: [], holeDetails: [], relatedRefs: { roundRefs: [ROUND], holeRefs: [`${ROUND}:1`], shotRefs: [], sourceRefs: [] }, sourceFields: {}, missingData: [] })
    if (path === `/api/v2/history/rounds/${ROUND}/holes/1/shotmap` && method === 'GET') return json({ schema: 'ai-caddie-round-hole-shotmap-v1', found: true, roundRef: ROUND, hole: 1, par: 4, globalId: GID, localHole: 1, geometryRevision: 'fixture-v1', mapKind: 'prodgeometry', map: { overlay }, shots: corrected ? correctedShots : originalShots, missingData: [] })
    if (path === `/api/v2/history/rounds/${ROUND}/corrections` && method === 'POST' && identity !== 'player-link') {
      records.corrections.push(request.postDataJSON())
      if (options.correctionRejected) return route.fulfill({ status: 503, json: { detail: 'Fixture save unavailable' } })
      corrected = true
      return json({ schema: 'ai-caddie-round-correction-v1', stored: { clientMutationId: 'fixture-accepted' } })
    }
    if (new RegExp(`^/api/v2/courses/${GID}/holes/[12]/topo\\.png$`).test(path) && method === 'GET') return route.fulfill({ contentType: 'image/png', body: topo })
    if (path === '/api/v2/mobile/courses/options' && method === 'GET') return json({ schema: 'ai-caddie-mobile-course-options-v1', dataMode: 'fixture', total: 1, courses: [{ globalId: GID, courseKey: 'fixture_orchard', name: COURSE, roundCount: 3, latestRoundId: ROUND, latestRoundDate: '2026-05-20', templateRoundId: ROUND, suggestedLiveRoundId: 'fixture-live', holes: 18, teeBox: 'blue', geometryCoverage: 'ready', sourceRefs: [ROUND] }], emptyState: null })
    if (path === `/api/v2/mobile/courses/${GID}/package` && method === 'GET') return json({ schema: 'ai-caddie-live-round-package-v1', roundId: `web-prep-${GID}`, dataMode: 'fixture', holes: [{ number: 1, sourceGlobalId: GID, sourceLocalHole: 1, par: 4, yards: 328, geometryCoverage: 'ready' }, { number: 2, sourceGlobalId: GID, sourceLocalHole: 2, par: 4, yards: 219, geometryCoverage: 'ready' }] })
    if (path === `/api/v2/courses/${GID}/install/status` && method === 'GET') return json({ schema: 'ai-caddie-course-install-v1', globalId: GID, jobId: 'fixture-install', phase: 'ready', stage: 'complete', totalHoles: 2, geometryReady: 2, topoReady: 2, holes: [{ globalId: GID, localHole: 1, displayHole: 1, geometry: 'ready', topo: 'ready' }, { globalId: GID, localHole: 2, displayHole: 2, geometry: 'ready', topo: 'ready' }] })
    if (path === `/api/v2/courses/${GID}/topo/prewarm` && method === 'POST') return json({ schema: 'ai-caddie-topo-prewarm-v1', globalId: GID, holes: [1, 2], queued: 2 })
    if (path === `/api/v2/courses/${GID}/prep` && method === 'GET') {
      records.prepQueries.push(url.searchParams)
      return json(prep)
    }
    if (path === `/api/v2/courses/${GID}/prep-tips` && method === 'GET') return json({ schema: 'ai-caddie-prep-tips-v1', courseKey: 'fixture_orchard', tips: [] })
    if (path === '/api/v2/caddie/context' && method === 'GET') {
      records.contexts.push(url.searchParams)
      return json({ schema: 'ai-caddie-context-v1', sourceRef: url.searchParams.get('source_ref'), shotType: url.searchParams.get('shot_type'), context: { roundId: ROUND, sourceRef: url.searchParams.get('source_ref'), shotType: url.searchParams.get('shot_type'), distanceToPin_m: Number(url.searchParams.get('distance_to_pin_m')), ...(url.searchParams.has('strategy_mode') ? { strategyMode: url.searchParams.get('strategy_mode') } : {}) }, evidence: [], missingData: [] })
    }
    if (path === '/api/v2/caddie/decision' && method === 'POST') {
      const body = request.postDataJSON() as Record<string, unknown>
      records.decisions.push(body)
      const mode = (body.context as { strategyMode?: string })?.strategyMode
      return json({ schema: 'ai-caddie-decision-v2', decisionId: 'fixture-decision', sourceRef: `${ROUND}:1`, shotType: 'tee', options: [{ id: 'safe', label: 'Safe', recommendedClub: '9I', carry_m: 100, riskScore: 1 }, { id: 'stock', label: 'Stock', recommendedClub: '6I', carry_m: 150, riskScore: 2 }, { id: 'attack', label: 'Attack', recommendedClub: '3W', carry_m: 200, riskScore: 4 }], selectedOptionId: mode === 'attack' ? 'attack' : mode === 'protect_score' || mode === 'safe' ? 'safe' : 'stock', evidenceRefs: [`${ROUND}:1`], evidence: [], explanation: { narrative: 'Centre line' }, acceptableMiss: { direction: 'left' }, missingData: [], auditCriteria: [] })
    }
    if (path === '/api/v2/sync/status' && method === 'GET') return json(identity !== 'owner' ? { schema: 'ai-caddie-sync-status-v2', status: 'ready' } : { schema: 'ai-caddie-sync-status-v2', connector: { name: 'garmin_cn_web_session', state: imported ? 'ready' : 'reauth_required', detail: '', canSync: imported, reauthRequired: !imported, nextAction: imported ? 'review_history' : 'reauthenticate_garmin' }, snapshot: { dataMode: 'fixture', scorecardCount: 3, shotFileCount: 3, summaryPresent: true, lastSuccessfulSyncAt: null }, lastRun: null })
    if (path === '/api/v2/sync/garmin/session' && method === 'POST' && identity === 'owner') {
      records.imports.push(request.postDataJSON())
      if (options.importRejected) return route.fulfill({ status: 422, json: { detail: 'Fixture session rejected' } })
      imported = true
      return json({ schema: 'ai-caddie-garmin-session-import-v1', saved: true })
    }
    if (path === '/api/v2/sync/garmin' && method === 'POST' && identity === 'owner' && imported) return json({ schema: 'ai-caddie-sync-run-v2', state: 'ready', newRoundCount: 0, detail: 'Fixture complete' })
    if (path === '/api/v2/readiness' && method === 'GET') return json({ schema: 'ai-caddie-readiness-v1', status: 'ready', checks: [] })
    if (path === '/api/v2/annotations' && method === 'GET') return json({ schema: 'ai-caddie-annotations-v1', total: 0, annotations: [] })
    records.unexpected.push(`${method} ${path}`)
    return route.fulfill({ status: 403, json: { detail: 'Fixture denies this operation' } })
  })
  return records
}

// Every test fails on a browser exception or an API request missing from its
// scenario. The fixture is per-test, so import/correction state never leaks.
export const test = base.extend<{ api: Awaited<ReturnType<typeof productApi>>; scenario: Options }>({
  scenario: [{}, { option: true }],
  api: [async ({ page, scenario }, use) => {
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    const api = await productApi(page, scenario)
    await use(api)
    expect(errors, 'uncaught browser errors').toEqual([])
    expect(api.unexpected, 'unexpected API operations (all were intercepted)').toEqual([])
  }, { auto: true }],
})

export { expect }

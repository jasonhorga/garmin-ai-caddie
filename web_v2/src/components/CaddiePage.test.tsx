import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CaddiePage } from './CaddiePage'
import type {
  CaddieDecisionAuditRecord,
  CaddieContextResponse,
  CaddieDecisionResponse,
  MediaRecord,
  WeatherSnapshotResponse,
  VisionFindingRecord,
} from '../types'

const INTERACTION_TEST_TIMEOUT_MS = 10_000

const decision: CaddieDecisionResponse = {
  schema: 'ai-caddie-decision-v2',
  decisionId: 'fixture-links-4-approach',
  sourceRef: 'fixture-links:4',
  evidenceRefs: ['fixture-links:4'],
  shotType: 'approach',
  phase: 'Approach',
  context: { sourceRef: 'fixture-links:4', distanceToPin_m: 142 },
  options: [
    {
      id: 'safe',
      label: 'Safe',
      clubRecommendation: { source: 'club_profiles', clubs: [{ clubName: '9I', sampleSize: 24, median_m: 132 }] },
      carry_m: 132,
      riskScore: 0,
      coverage: { ready: 4, total: 4, pct: 100 },
      confidence: 'high',
      sourceRefs: ['fixture-links:4'],
    },
    {
      id: 'stock',
      label: 'Stock',
      clubRecommendation: { source: 'club_profiles', clubs: [{ clubName: '8I', sampleSize: 24, median_m: 144, p10_m: 132, p90_m: 153 }] },
      carry_m: 144,
      riskScore: 1,
      scoreImpact: {
        model: 'calibrated_history_club_v2',
        expectedStrokes: 1.24,
        expectedStrokesDelta: 0.24,
        components: { risk: 0.05, history: 0.12, hazardClearance: 0, dispersion: 0.02, clubSurfaceRisk: 0.03, clubConfidence: 0.02 },
        historyAdjustment: {
          expectedStrokesDelta: 0.12,
          sourceRefs: ['fixture-links:4:history'],
          factors: [
            {
              label: 'historical_hole_scoring',
              expectedStrokesDelta: 0.08,
              riskScoreDelta: 0.8,
              sourceRefs: ['fixture-links:4:history'],
            },
          ],
        },
        clubConfidence: {
          expectedStrokesDelta: 0.02,
          sampleSize: 24,
          carryWindow_m: 21,
          reason: 'club sample and dispersion are strong enough',
        },
      },
      historyAdjustment: { riskScoreDelta: 0.8, sourceRefs: ['fixture-links:4:history'] },
      hazardClearance: { minimumClearance_m: 16, criticalHazardId: 'water_front' },
      coverage: { ready: 4, total: 4, pct: 100 },
      confidence: 'high',
      sourceRefs: ['fixture-links:4', 'fixture-links:4:hazard'],
    },
    {
      id: 'attack',
      label: 'Attack',
      clubRecommendation: { source: 'club_profiles', clubs: [{ clubName: '7I', sampleSize: 24, median_m: 156 }] },
      carry_m: 156,
      riskScore: 3,
      coverage: { ready: 3, total: 4, pct: 75 },
      confidence: 'medium',
      missingData: [{ label: 'weather', reason: 'wind snapshot missing' }],
      sourceRefs: ['fixture-links:4'],
    },
  ],
  selected: { id: 'stock' },
  selectedOptionId: 'stock',
  selectedOption: {
    id: 'stock',
    clubRecommendation: { source: 'club_profiles', clubs: [{ clubName: '8I', sampleSize: 24, median_m: 144 }] },
    carry_m: 144,
  },
  sequences: [
    { id: 'safe', label: '3W-5I-54', expectedStrokes: 3, expectedRemaining_m: 40, riskScore: 1 },
    {
      id: 'stock',
      label: '1D-3W-58',
      expectedStrokes: 3,
      expectedRemaining_m: -21,
      riskScore: 2,
      coverage: { ready: 153, total: 153, pct: 100 },
      confidence: 'high',
      sourceRefs: ['club-sample-1d-0', 'club-sample-3w-0', 'club-sample-58-0'],
      clubs: [
        {
          clubName: '1D',
          role: 'advance',
          targetCarry_m: 245,
          expectedRemaining_m: 275,
          sampleSize: 80,
          confidence: 'high',
          sourceRefs: ['club-sample-1d-0'],
        },
        {
          clubName: '3W',
          role: 'position',
          targetCarry_m: 218,
          expectedRemaining_m: 57,
          sampleSize: 45,
          confidence: 'high',
          sourceRefs: ['club-sample-3w-0'],
        },
        {
          clubName: '58',
          role: 'scoring',
          targetCarry_m: 78,
          expectedRemaining_m: -21,
          sampleSize: 28,
          confidence: 'high',
          sourceRefs: ['club-sample-58-0'],
        },
      ],
    },
  ],
  selectedSequence: {
    id: 'stock',
    label: '1D-3W-58',
    expectedStrokes: 3,
    expectedRemaining_m: -21,
    riskScore: 2,
    coverage: { ready: 153, total: 153, pct: 100 },
    confidence: 'high',
    sourceRefs: ['club-sample-1d-0', 'club-sample-3w-0', 'club-sample-58-0'],
  },
  avoidZones: [{ kind: 'water', id: 'water_front' }],
  forbiddenZones: [],
  acceptableMiss: {
    direction: 'away_from_known_risks',
    selectedOptionId: 'stock',
    avoidRiskKinds: ['water'],
    rationale: "miss toward the side that avoids the selected route's known risk kinds",
  },
  evidence: [{ label: 'water_front', value: 'carry 126m' }, { kind: 'sequence', text: 'Normal three-shot plan: 1D-3W-58' }],
  confidence: { level: 'medium', reason: 'fixture data' },
  missingData: [{ label: 'wind', reason: 'not cached' }],
  auditCriteria: [{ label: 'first shot avoids water' }],
  explanation: {
    schema: 'ai-caddie-decision-explanation-v1',
    decisionId: 'fixture-links-4-approach',
    sourceRef: 'fixture-links:4',
    shotType: 'approach',
    provider: 'StaticProvider',
    model: 'static',
    factsUsed: [
      {
        label: 'selected_option',
        value: { id: 'stock', label: 'Stock', carry_m: 144, riskScore: 1, clubRecommendation: '8I' },
        sourceRefs: ['fixture-links:4'],
      },
      { label: 'avoid_zones', value: [{ id: 'water_front', kind: 'water', carryToClear_m: 126 }], refs: ['fixture-links:4:hazard'] },
      { label: 'confidence', value: { level: 'medium', reason: 'fixture data' }, sourceRefs: ['fixture-links:4'] },
    ],
    missingData: [{ label: 'wind', reason: 'not cached', missingDataRefs: ['fixture-links:4:weather'] }],
    unsupportedClaims: [{ category: 'scoring', claim: 'score outcome claim is not present in decision facts', sourceRefs: ['fixture-links:4'] }],
    sourceRefs: ['fixture-links:4'],
    factBinding: {
      state: 'needs_review',
      unsupportedClaimCount: 1,
      rule: 'narrative generated from factsUsed; deterministic decision fields remain authoritative',
    },
    narrative: 'Use Stock because the water carry and missing wind are visible in the structured facts.',
    confidence: 'medium',
  },
}

const auditRecord: CaddieDecisionAuditRecord = {
  id: 'audit-1',
  storedAt: '2026-05-25T00:00:00Z',
  decisionId: 'fixture-links-4-approach',
  sourceRef: 'fixture-links:4',
  selectedOptionId: 'stock',
  plannedOptionId: 'stock',
  actualOptionId: 'stock',
  actualShotRefs: ['fixture-links:4:1'],
  evidenceRefs: ['fixture-links:4'],
  classification: 'execution',
  audit: {
    schema: 'ai-caddie-decision-audit-v1',
    decisionId: 'fixture-links-4-approach',
    decisionSourceRef: 'fixture-links:4',
    phase: 'Approach',
    plannedOptionId: 'stock',
    selectedOptionId: 'stock',
    actualOptionId: 'stock',
    actualShotRefs: ['fixture-links:4:1'],
    evidenceRefs: ['fixture-links:4'],
    classification: 'execution',
    executionMatch: { hasFirstShot: true, clubMatch: true, distanceDelta_m: -1, riskTriggered: false },
    criteriaResults: [
      { label: 'club_match', status: 'pass', expected: ['8I'], actual: '8I' },
      { label: 'carry_window', status: 'pass', expected_m: 144, actual_m: 143, distanceDelta_m: -1 },
      { label: 'avoid_zones', status: 'pass', surface: 'green' },
      { label: 'penalty', status: 'pass', actual: false },
    ],
    result: { clubName: '8I', meters: 143, surface: 'green' },
    modelUpdateSuggestion: 'Keep the strategic option, but track whether this miss pattern repeats.',
  },
}

const weatherSnapshot: WeatherSnapshotResponse = {
  schema: 'ai-caddie-weather-snapshot-v1',
  state: 'ready',
  source: 'manual',
  roundId: '900001',
  hole: 7,
  capturedAt: '2026-05-25T08:00:00Z',
  location: { latitude: 22.279, longitude: 114.162 },
  windSpeedMps: 5.4,
  windDirectionDeg: 110,
  temperatureC: 28.5,
  precipitationMm: 0,
  confidence: 'medium',
  missingData: [],
}

const mediaRecord: MediaRecord = {
  id: 'media-1',
  createdAt: '2026-05-25T00:00:00Z',
  targetType: 'hole',
  targetId: '900001:7',
  mediaKind: 'photo',
  localPath: 'data/media/uploads/lie.jpg',
  capturedAt: '2026-05-25T08:00:00Z',
  privacyState: 'private_local',
  source: 'manual',
}

const visionFinding: VisionFindingRecord = {
  id: 'finding-1',
  createdAt: '2026-05-25T00:01:00Z',
  targetType: 'hole',
  targetId: '900001:7',
  mediaId: 'media-1',
  mediaKind: 'photo',
  findingType: 'visible_bunker',
  evidenceText: 'front bunker visible',
  confidence: 'medium',
  confirmationState: 'unconfirmed',
  missingInfo: [],
  provider: 'static',
  model: 'static',
  source: 'vision_model',
}

const caddieContext: CaddieContextResponse = {
  schema: 'ai-caddie-context-v1',
  sourceRef: '900001:7',
  shotType: 'approach',
  context: {
    source: 'history_drilldown',
    sourceRef: '900001:7',
    roundId: '900001',
    courseName: 'Black Knight B',
    hole: 7,
    globalId: 31795,
    localHole: 7,
    distanceToPin_m: 142,
    lie: 'fairway',
    geometry: { coverage: 'partial', hasHazards: true, hasMeshes: false, hazardCount: 1 },
    hazards: [{ kind: 'water', id: 'water-left' }],
    clubProfiles: { '8I': { clubName: '8I', sampleSize: 4, median: 144, p10: 132, p90: 153 } },
    historicalHoleIssues: [{ issue: 'double_or_worse', count: 1, phase: 'Course Management', refs: ['900002:7'] }],
    courseForm: { courseKey: 'black_knight', roundCount: 2, roundRefs: ['900001', '900002'] },
    manualNotes: [{ kind: 'strategy_note', note: 'Favor center green; short miss is playable.' }],
  },
  evidence: [{ label: 'history_ref', value: '900001:7' }],
  missingData: [{ label: 'meshes', reason: 'prodgeometry mesh file missing' }],
}

describe('CaddiePage', () => {
  it('blocks caddie plan requests until source-bound context is loaded', async () => {
    const onRequestDecision = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'idle' }}
        contextState={{ status: 'idle' }}
        onRequestDecision={onRequestDecision}
      />,
    )

    expect(screen.getByText('Load caddie context before requesting a source-bound plan.')).toBeInTheDocument()
    const requestButton = screen.getByRole('button', { name: 'Request caddie plan' })
    expect(requestButton).toBeDisabled()

    await userEvent.click(requestButton)

    expect(onRequestDecision).not.toHaveBeenCalled()
  })

  it('uses a selected history source ref when loading caddie context', async () => {
    const onLoadCaddieContext = vi.fn()
    const selectedProps = {
      decisionState: { status: 'idle' } as const,
      contextState: { status: 'idle' } as const,
      selectedSourceRef: '900002:5:4',
      onRequestDecision: vi.fn(),
      onLoadCaddieContext,
    }

    render(<CaddiePage {...selectedProps} />)

    expect(screen.getByLabelText('Source ref')).toHaveValue('900002:5:4')

    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))

    expect(onLoadCaddieContext).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceRef: '900002:5:4',
      }),
    )
  })

  it('keeps manual source ref overrides after the selected ref prefill', async () => {
    const onLoadCaddieContext = vi.fn()
    const selectedProps = {
      decisionState: { status: 'idle' } as const,
      contextState: { status: 'idle' } as const,
      selectedSourceRef: '900002:5:4',
      onRequestDecision: vi.fn(),
      onLoadCaddieContext,
    }

    render(<CaddiePage {...selectedProps} />)

    await userEvent.clear(screen.getByLabelText('Source ref'))
    await userEvent.type(screen.getByLabelText('Source ref'), 'manual-round:3')
    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))

    expect(onLoadCaddieContext).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceRef: 'manual-round:3',
      }),
    )
  })

  it('blocks plan requests when the loaded context belongs to a stale source ref', async () => {
    const onRequestDecision = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'idle' }}
        contextState={{ status: 'ready', data: caddieContext }}
        selectedSourceRef="900002:5:4"
        onRequestDecision={onRequestDecision}
      />,
    )

    expect(screen.getByLabelText('Source ref')).toHaveValue('900002:5:4')
    expect(screen.getByText('Load caddie context before requesting a source-bound plan.')).toBeInTheDocument()
    const requestButton = screen.getByRole('button', { name: 'Request caddie plan' })
    expect(requestButton).toBeDisabled()

    await userEvent.click(requestButton)

    expect(onRequestDecision).not.toHaveBeenCalled()
  })

  it('renders decision evidence and requests a source-bound plan', async () => {
    const onRequestDecision = vi.fn()
    const onCreateAudit = vi.fn()
    const onLoadWeather = vi.fn()
    const onLoadMediaContext = vi.fn()
    const onAttachMedia = vi.fn()
    const onAnalyzeMedia = vi.fn()
    const onRedactMedia = vi.fn()
    const onConfirmVisionFinding = vi.fn()
    const onLoadCaddieContext = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'ready', data: decision }}
        auditState={{ status: 'ready', data: auditRecord }}
        weatherState={{ status: 'ready', data: weatherSnapshot }}
        contextState={{ status: 'ready', data: caddieContext }}
        mediaState={{
          status: 'ready',
          targetType: 'hole',
          targetId: '900001:7',
          media: [mediaRecord],
          findings: [visionFinding],
        }}
        onRequestDecision={onRequestDecision}
        onCreateAudit={onCreateAudit}
        onLoadWeather={onLoadWeather}
        onLoadMediaContext={onLoadMediaContext}
        onAttachMedia={onAttachMedia}
        onAnalyzeMedia={onAnalyzeMedia}
        onRedactMedia={onRedactMedia}
        onConfirmVisionFinding={onConfirmVisionFinding}
        onLoadCaddieContext={onLoadCaddieContext}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Caddie' })).toBeInTheDocument()
    expect(screen.getByText('Stock')).toBeInTheDocument()
    expect(screen.getByText('8I')).toBeInTheDocument()
    expect(screen.getAllByText('sample 24').length).toBeGreaterThan(0)
    expect(screen.getAllByText('coverage 4/4').length).toBeGreaterThan(0)
    expect(screen.getAllByText('high option confidence').length).toBeGreaterThan(0)
    expect(screen.getByText('history +0.8 risk')).toBeInTheDocument()
    expect(screen.getAllByText('selected').length).toBeGreaterThan(0)
    expect(screen.getByText('144m - risk 1 - 1.24 exp - 16m clear')).toBeInTheDocument()
    expect(screen.getAllByText('water_front').length).toBeGreaterThan(0)
    expect(screen.getAllByText('wind').length).toBeGreaterThan(0)
    expect(screen.getAllByText('medium confidence').length).toBeGreaterThan(0)
    expect(screen.getByText('execution')).toHaveClass('audit-execution')
    expect(screen.getByText('planned stock -> actual stock')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source fixture-links:4:1' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source fixture-links:4' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Open source fixture-links:4:history' }).length).toBeGreaterThan(0)
    expect(screen.getByText('club match yes')).toBeInTheDocument()
    expect(screen.getByText('distance -1m')).toBeInTheDocument()
    expect(screen.getByText('risk no')).toBeInTheDocument()
    expect(screen.getByText('club_match')).toBeInTheDocument()
    expect(screen.getByText('carry_window')).toBeInTheDocument()
    expect(screen.getAllByText('pass').length).toBeGreaterThan(0)
    expect(screen.getByText('Keep the strategic option, but track whether this miss pattern repeats.')).toBeInTheDocument()
    const scoreImpact = screen.getByLabelText('Decision score impact')
    expect(within(scoreImpact).getByRole('heading', { name: 'Score Impact' })).toBeInTheDocument()
    expect(within(scoreImpact).getByText('calibrated_history_club_v2')).toBeInTheDocument()
    expect(within(scoreImpact).getByText('1.24')).toBeInTheDocument()
    expect(within(scoreImpact).getByText('+0.24 strokes')).toBeInTheDocument()
    expect(within(scoreImpact).getByText('History +0.12 strokes')).toBeInTheDocument()
    expect(within(scoreImpact).getByText('Club Confidence +0.02 strokes')).toBeInTheDocument()
    expect(within(scoreImpact).getByText('historical_hole_scoring')).toBeInTheDocument()
    expect(within(scoreImpact).getByText('club sample and dispersion are strong enough')).toBeInTheDocument()
    const acceptableMiss = screen.getByLabelText('Decision acceptable miss')
    expect(within(acceptableMiss).getByRole('heading', { name: 'Acceptable Miss' })).toBeInTheDocument()
    expect(within(acceptableMiss).getByText('Away From Known Risks')).toBeInTheDocument()
    expect(within(acceptableMiss).getByText('stock')).toBeInTheDocument()
    expect(within(acceptableMiss).getByText('avoid water')).toBeInTheDocument()
    expect(within(acceptableMiss).getByText("miss toward the side that avoids the selected route's known risk kinds")).toBeInTheDocument()
    const explanationPanel = screen.getByLabelText('Decision explanation')
    expect(within(explanationPanel).getByRole('heading', { name: 'Decision Explanation' })).toBeInTheDocument()
    expect(within(explanationPanel).getByText('Use Stock because the water carry and missing wind are visible in the structured facts.')).toBeInTheDocument()
    expect(within(explanationPanel).getByText('StaticProvider / static')).toBeInTheDocument()
    expect(within(explanationPanel).getByText('needs_review binding')).toBeInTheDocument()
    expect(within(explanationPanel).getByText('selected_option')).toBeInTheDocument()
    expect(within(explanationPanel).getByText(/carry_m 144/)).toBeInTheDocument()
    expect(within(explanationPanel).getByText(/riskScore 1/)).toBeInTheDocument()
    expect(within(explanationPanel).getByText(/clubRecommendation 8I/)).toBeInTheDocument()
    expect(within(explanationPanel).getByText('avoid_zones')).toBeInTheDocument()
    expect(within(explanationPanel).getByText(/carryToClear_m 126/)).toBeInTheDocument()
    expect(within(explanationPanel).getByText('score outcome claim is not present in decision facts')).toBeInTheDocument()
    expect(within(explanationPanel).getAllByRole('button', { name: 'Open source fixture-links:4' }).length).toBeGreaterThan(0)
    expect(within(explanationPanel).getAllByRole('button', { name: 'Open source fixture-links:4:hazard' }).length).toBeGreaterThan(0)
    expect(within(explanationPanel).getAllByRole('button', { name: 'Open source fixture-links:4:weather' }).length).toBeGreaterThan(0)
    const factsHeading = within(explanationPanel).getByRole('heading', { name: 'Facts' })
    const narrative = within(explanationPanel).getByText('Use Stock because the water carry and missing wind are visible in the structured facts.')
    expect(Boolean(factsHeading.compareDocumentPosition(narrative) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(screen.getByText('5.4 m/s')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Media Context' })).toBeInTheDocument()
    expect(screen.getByText('data/media/uploads/lie.jpg')).toBeInTheDocument()
    expect(screen.getByText('visible_bunker')).toBeInTheDocument()
    expect(screen.getByText('front bunker visible')).toBeInTheDocument()
    expect(screen.getByText('unconfirmed')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Club Sequences' })).toBeInTheDocument()
    expect(screen.getByText('1D-3W-58')).toBeInTheDocument()
    expect(screen.getAllByText(/3 shots/).length).toBeGreaterThan(0)
    expect(screen.getByText('coverage 153/153')).toBeInTheDocument()
    expect(screen.getByText('high sequence confidence')).toBeInTheDocument()
    expect(screen.getByText('advance 1D')).toBeInTheDocument()
    expect(screen.getByText('245m carry - 275m left')).toBeInTheDocument()
    expect(screen.getByText('80 samples')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source club-sample-1d-0' }).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Caddie Context' })).toBeInTheDocument()
    expect(screen.getByText('history_drilldown')).toBeInTheDocument()
    expect(screen.getByText('31795 H7')).toBeInTheDocument()
    expect(screen.getByText('double_or_worse')).toBeInTheDocument()
    expect(screen.getByText('Favor center green; short miss is playable.')).toBeInTheDocument()
    expect(screen.getByText('history_ref')).toBeInTheDocument()
    expect(screen.getByText('prodgeometry mesh file missing')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Load weather' }))
    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))
    await userEvent.click(screen.getByRole('button', { name: 'Load media context' }))
    await userEvent.click(screen.getByRole('button', { name: 'Analyze media media-1' }))
    await userEvent.click(screen.getByRole('button', { name: 'Redact media media-1' }))
    await userEvent.click(screen.getByRole('button', { name: 'Confirm finding finding-1' }))
    await userEvent.click(screen.getByRole('button', { name: 'Reject finding finding-1' }))
    await userEvent.upload(screen.getByLabelText('Media file'), new File(['lie-bytes'], 'lie.jpg', { type: 'image/jpeg' }))
    await userEvent.click(screen.getByRole('button', { name: 'Attach media' }))
    await userEvent.click(screen.getByRole('button', { name: 'Request caddie plan' }))
    expect(screen.queryByRole('button', { name: 'Audit with fixture outcome' })).not.toBeInTheDocument()
    await userEvent.clear(screen.getByLabelText('Actual club'))
    await userEvent.type(screen.getByLabelText('Actual club'), '9I')
    await userEvent.clear(screen.getByLabelText('Actual carry (m)'))
    await userEvent.type(screen.getByLabelText('Actual carry (m)'), '137')
    await userEvent.selectOptions(screen.getByLabelText('Result lie'), 'fringe')
    await userEvent.click(screen.getByRole('button', { name: 'Audit outcome' }))

    expect(onLoadWeather).toHaveBeenCalledWith(
      expect.objectContaining({
        source: 'manual',
        persist: true,
        roundId: '900001',
        hole: 7,
        capturedAt: expect.any(String),
      }),
    )
    expect(onLoadCaddieContext).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceRef: '900001:7',
        shotType: 'approach',
        distanceToPinM: 142,
        lie: 'fairway',
        capturedAt: expect.any(String),
      }),
    )
    expect(onLoadMediaContext).toHaveBeenCalledWith({ targetType: 'hole', targetId: '900001:7' })
    expect(onAnalyzeMedia).toHaveBeenCalledWith('media-1')
    expect(onRedactMedia).toHaveBeenCalledWith('media-1')
    expect(onConfirmVisionFinding).toHaveBeenNthCalledWith(1, 'finding-1', 'manual_confirmed')
    expect(onConfirmVisionFinding).toHaveBeenNthCalledWith(2, 'finding-1', 'rejected')
    expect(onAttachMedia).toHaveBeenCalledWith(
      expect.objectContaining({
        targetType: 'hole',
        targetId: '900001:7',
        mediaKind: 'photo',
        fileName: 'lie.jpg',
        contentBase64: 'bGllLWJ5dGVz',
        privacyState: 'private_local',
      }),
    )
    expect(onRequestDecision).toHaveBeenCalledWith({
      shotType: 'approach',
      context: expect.objectContaining({
        source: 'history_drilldown',
        sourceRef: '900001:7',
        historicalHoleIssues: [{ issue: 'double_or_worse', count: 1, phase: 'Course Management', refs: ['900002:7'] }],
        manualNotes: [{ kind: 'strategy_note', note: 'Favor center green; short miss is playable.' }],
        distanceToPin_m: 142,
        lie: 'fairway',
        weatherSnapshot,
        visionFindings: [visionFinding],
      }),
    })
    expect(onCreateAudit).toHaveBeenCalledWith(decision, {
      actualShot: {
        shotOrder: 1,
        clubName: '9I',
        meters: 137,
        end: { lie: 'fringe', feature: { surface: { kind: 'fringe' }, nearRisks: [] } },
      },
      actualShots: [
        {
          shotOrder: 1,
          clubName: '9I',
          meters: 137,
          end: { lie: 'fringe', feature: { surface: { kind: 'fringe' }, nearRisks: [] } },
        },
      ],
      penalty: false,
    })
  }, INTERACTION_TEST_TIMEOUT_MS)

  it('captures sequence audit shots, penalty, and score context', async () => {
    const onCreateAudit = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'ready', data: decision }}
        auditState={{ status: 'idle' }}
        contextState={{ status: 'ready', data: caddieContext }}
        onRequestDecision={vi.fn()}
        onCreateAudit={onCreateAudit}
      />,
    )

    await userEvent.clear(screen.getByLabelText('Actual club'))
    await userEvent.type(screen.getByLabelText('Actual club'), '1D')
    await userEvent.clear(screen.getByLabelText('Actual carry (m)'))
    await userEvent.type(screen.getByLabelText('Actual carry (m)'), '242')
    await userEvent.selectOptions(screen.getByLabelText('Result lie'), 'fairway')
    await userEvent.clear(screen.getByLabelText('Shot 2 club'))
    await userEvent.type(screen.getByLabelText('Shot 2 club'), '3W')
    await userEvent.type(screen.getByLabelText('Shot 2 carry (m)'), '211')
    await userEvent.selectOptions(screen.getByLabelText('Shot 2 result lie'), 'fairway')
    await userEvent.clear(screen.getByLabelText('Shot 3 club'))
    await userEvent.type(screen.getByLabelText('Shot 3 club'), '58')
    await userEvent.type(screen.getByLabelText('Shot 3 carry (m)'), '74')
    await userEvent.selectOptions(screen.getByLabelText('Shot 3 result lie'), 'green')
    await userEvent.type(screen.getByLabelText('Actual score to par'), '1')
    await userEvent.click(screen.getByLabelText('Penalty occurred'))
    await userEvent.click(screen.getByRole('button', { name: 'Audit outcome' }))

    expect(onCreateAudit).toHaveBeenCalledWith(decision, {
      actualShot: expect.objectContaining({ shotOrder: 1, clubName: '1D', meters: 242, penalty: true }),
      actualShots: [
        expect.objectContaining({ shotOrder: 1, clubName: '1D', meters: 242, penalty: true }),
        expect.objectContaining({ shotOrder: 2, clubName: '3W', meters: 211 }),
        expect.objectContaining({ shotOrder: 3, clubName: '58', meters: 74 }),
      ],
      actualScoreToPar: 1,
      penalty: true,
    })
  }, INTERACTION_TEST_TIMEOUT_MS)

  it('passes live coordinates and strategy mode when loading source-bound context', async () => {
    const onLoadCaddieContext = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'idle' }}
        contextState={{ status: 'idle' }}
        onRequestDecision={vi.fn()}
        onLoadCaddieContext={onLoadCaddieContext}
      />,
    )

    await userEvent.clear(screen.getByLabelText('Current latitude'))
    await userEvent.type(screen.getByLabelText('Current latitude'), '22.279')
    await userEvent.clear(screen.getByLabelText('Current longitude'))
    await userEvent.type(screen.getByLabelText('Current longitude'), '114.162')
    await userEvent.clear(screen.getByLabelText('Target latitude'))
    await userEvent.type(screen.getByLabelText('Target latitude'), '22.2799')
    await userEvent.clear(screen.getByLabelText('Target longitude'))
    await userEvent.type(screen.getByLabelText('Target longitude'), '114.162')
    await userEvent.selectOptions(screen.getByLabelText('Strategy mode'), 'protect_score')
    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))

    expect(onLoadCaddieContext).toHaveBeenCalledWith(
      expect.objectContaining({
        currentLatitude: 22.279,
        currentLongitude: 114.162,
        targetLatitude: 22.2799,
        targetLongitude: 114.162,
        strategyMode: 'protect_score',
      }),
    )
  })

  it('includes the current decision timestamp when loading source-bound context', async () => {
    const onLoadCaddieContext = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'idle' }}
        contextState={{ status: 'idle' }}
        onRequestDecision={vi.fn()}
        onLoadCaddieContext={onLoadCaddieContext}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))

    expect(onLoadCaddieContext).toHaveBeenCalledWith(
      expect.objectContaining({
        capturedAt: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/),
      }),
    )
  })

  it('passes route local coordinates when loading tee context', async () => {
    const onLoadCaddieContext = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'idle' }}
        contextState={{ status: 'idle' }}
        onRequestDecision={vi.fn()}
        onLoadCaddieContext={onLoadCaddieContext}
      />,
    )

    await userEvent.selectOptions(screen.getByLabelText('Shot type'), 'tee')
    await userEvent.clear(screen.getByLabelText('Route start X'))
    await userEvent.type(screen.getByLabelText('Route start X'), '0')
    await userEvent.clear(screen.getByLabelText('Route start Y'))
    await userEvent.type(screen.getByLabelText('Route start Y'), '0')
    await userEvent.clear(screen.getByLabelText('Route target X'))
    await userEvent.type(screen.getByLabelText('Route target X'), '0')
    await userEvent.clear(screen.getByLabelText('Route target Y'))
    await userEvent.type(screen.getByLabelText('Route target Y'), '182')
    await userEvent.click(screen.getByRole('button', { name: 'Load caddie context' }))

    expect(onLoadCaddieContext).toHaveBeenCalledWith(
      expect.objectContaining({
        shotType: 'tee',
        startX: 0,
        startY: 0,
        targetX: 0,
        targetY: 182,
        landingRadiusM: 18,
      }),
    )
  })

  it('does not send stale vision findings when media target no longer matches the selected source', async () => {
    const onRequestDecision = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'idle' }}
        contextState={{ status: 'ready', data: caddieContext }}
        mediaState={{
          status: 'ready',
          targetType: 'shot',
          targetId: 'fixture-round:4:approach',
          media: [mediaRecord],
          findings: [visionFinding],
        }}
        onRequestDecision={onRequestDecision}
      />,
    )

    expect(screen.getByText('Loaded media belongs to shot fixture-round:4:approach; reload media for hole 900001:7.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Request caddie plan' }))

    expect(onRequestDecision).toHaveBeenCalledWith({
      shotType: 'approach',
      context: expect.not.objectContaining({
        visionFindings: expect.anything(),
      }),
    })
  })

  it('renders history-aware acceptable miss bias', () => {
    const biasedDecision: CaddieDecisionResponse = {
      ...decision,
      acceptableMiss: {
        direction: 'history_depth_bias',
        selectedOptionId: 'stock',
        avoidRiskKinds: ['water'],
        preferredMiss: { depth: 'long' },
        avoidPatterns: ['approach_short'],
        sourceRefs: ['hist-approach-short'],
        rationale: 'historical miss patterns bias the acceptable miss away from repeated scoring-loss patterns',
      },
    }

    render(<CaddiePage decisionState={{ status: 'ready', data: biasedDecision }} contextState={{ status: 'ready', data: caddieContext }} onRequestDecision={vi.fn()} />)

    const acceptableMiss = screen.getByLabelText('Decision acceptable miss')
    expect(within(acceptableMiss).getByText('History Depth Bias')).toBeInTheDocument()
    expect(within(acceptableMiss).getByText('prefer depth long')).toBeInTheDocument()
    expect(within(acceptableMiss).getByText('avoid pattern approach_short')).toBeInTheDocument()
    expect(within(acceptableMiss).getByRole('button', { name: 'Open source hist-approach-short' })).toBeInTheDocument()
  })
})

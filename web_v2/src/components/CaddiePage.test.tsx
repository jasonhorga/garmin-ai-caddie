import { render, screen } from '@testing-library/react'
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

const decision: CaddieDecisionResponse = {
  schema: 'ai-caddie-decision-v2',
  shotType: 'approach',
  phase: 'Approach',
  context: { distanceToPin_m: 142 },
  options: [
    { id: 'safe', label: 'Safe', recommendedClub: '9I', carry_m: 132, riskScore: 0 },
    {
      id: 'stock',
      label: 'Stock',
      recommendedClub: '8I',
      carry_m: 144,
      riskScore: 1,
      scoreImpact: { expectedStrokes: 1.1, expectedStrokesDelta: 0.1 },
      hazardClearance: { minimumClearance_m: 16, criticalHazardId: 'water_front' },
    },
    { id: 'attack', label: 'Attack', recommendedClub: '7I', carry_m: 156, riskScore: 3 },
  ],
  selected: { id: 'stock' },
  selectedOptionId: 'stock',
  selectedOption: { id: 'stock' },
  sequences: [
    { id: 'safe', label: '3W-5I-54', expectedStrokes: 3, expectedRemaining_m: 40, riskScore: 1 },
    { id: 'stock', label: '1D-3W-58', expectedStrokes: 3, expectedRemaining_m: -21, riskScore: 2 },
  ],
  selectedSequence: { id: 'stock', label: '1D-3W-58', expectedStrokes: 3, expectedRemaining_m: -21, riskScore: 2 },
  avoidZones: [{ kind: 'water', id: 'water_front' }],
  forbiddenZones: [],
  acceptableMiss: { side: 'long' },
  evidence: [{ label: 'water_front', value: 'carry 126m' }, { kind: 'sequence', text: 'Normal three-shot plan: 1D-3W-58' }],
  confidence: { level: 'medium', reason: 'fixture data' },
  missingData: [{ label: 'wind', reason: 'not cached' }],
  auditCriteria: [{ label: 'first shot avoids water' }],
}

const auditRecord: CaddieDecisionAuditRecord = {
  id: 'audit-1',
  storedAt: '2026-05-25T00:00:00Z',
  decisionId: 'fixture-links-4-approach',
  audit: {
    schema: 'ai-caddie-decision-audit-v1',
    phase: 'Approach',
    plannedOptionId: 'stock',
    actualOptionId: 'stock',
    classification: 'execution',
    executionMatch: { hasFirstShot: true, clubMatch: true, distanceDelta_m: -1 },
    result: { clubName: '8I', meters: 143, surface: 'green' },
    modelUpdateSuggestion: { kind: 'none' },
  },
}

const weatherSnapshot: WeatherSnapshotResponse = {
  schema: 'ai-caddie-weather-snapshot-v1',
  state: 'ready',
  source: 'manual',
  roundId: 'fixture-round',
  hole: 4,
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
  targetType: 'shot',
  targetId: 'fixture-round:4:approach',
  mediaKind: 'photo',
  localPath: 'data/media/uploads/lie.jpg',
  capturedAt: '2026-05-25T08:00:00Z',
  privacyState: 'private_local',
  source: 'manual',
}

const visionFinding: VisionFindingRecord = {
  id: 'finding-1',
  createdAt: '2026-05-25T00:01:00Z',
  targetType: 'shot',
  targetId: 'fixture-round:4:approach',
  mediaId: 'media-1',
  mediaKind: 'photo',
  findingType: 'visible_bunker',
  evidenceText: 'front bunker visible',
  confidence: 'medium',
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

  it('renders decision evidence and requests a source-bound plan', async () => {
    const onRequestDecision = vi.fn()
    const onCreateAudit = vi.fn()
    const onLoadWeather = vi.fn()
    const onLoadMediaContext = vi.fn()
    const onAttachMedia = vi.fn()
    const onAnalyzeMedia = vi.fn()
    const onLoadCaddieContext = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'ready', data: decision }}
        auditState={{ status: 'ready', data: auditRecord }}
        weatherState={{ status: 'ready', data: weatherSnapshot }}
        contextState={{ status: 'ready', data: caddieContext }}
        mediaState={{
          status: 'ready',
          targetType: 'shot',
          targetId: 'fixture-round:4:approach',
          media: [mediaRecord],
          findings: [visionFinding],
        }}
        onRequestDecision={onRequestDecision}
        onCreateAudit={onCreateAudit}
        onLoadWeather={onLoadWeather}
        onLoadMediaContext={onLoadMediaContext}
        onAttachMedia={onAttachMedia}
        onAnalyzeMedia={onAnalyzeMedia}
        onLoadCaddieContext={onLoadCaddieContext}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Caddie' })).toBeInTheDocument()
    expect(screen.getByText('Stock')).toBeInTheDocument()
    expect(screen.getByText('8I')).toBeInTheDocument()
    expect(screen.getAllByText('selected').length).toBeGreaterThan(0)
    expect(screen.getByText('144m - risk 1 - 1.1 exp - 16m clear')).toBeInTheDocument()
    expect(screen.getAllByText('water_front').length).toBeGreaterThan(0)
    expect(screen.getByText('wind')).toBeInTheDocument()
    expect(screen.getAllByText('medium confidence').length).toBeGreaterThan(0)
    expect(screen.getByText('execution')).toHaveClass('audit-execution')
    expect(screen.getByText('planned stock -> actual stock')).toBeInTheDocument()
    expect(screen.getByText('5.4 m/s')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Media Context' })).toBeInTheDocument()
    expect(screen.getByText('data/media/uploads/lie.jpg')).toBeInTheDocument()
    expect(screen.getByText('visible_bunker')).toBeInTheDocument()
    expect(screen.getByText('front bunker visible')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Club Sequences' })).toBeInTheDocument()
    expect(screen.getByText('1D-3W-58')).toBeInTheDocument()
    expect(screen.getAllByText(/3 shots/).length).toBeGreaterThan(0)
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
    await userEvent.upload(screen.getByLabelText('Media file'), new File(['lie-bytes'], 'lie.jpg', { type: 'image/jpeg' }))
    await userEvent.click(screen.getByRole('button', { name: 'Attach media' }))
    await userEvent.click(screen.getByRole('button', { name: 'Request caddie plan' }))
    await userEvent.click(screen.getByRole('button', { name: 'Audit with fixture outcome' }))

    expect(onLoadWeather).toHaveBeenCalledTimes(1)
    expect(onLoadCaddieContext).toHaveBeenCalledWith({
      sourceRef: '900001:7',
      shotType: 'approach',
      distanceToPinM: 142,
      lie: 'fairway',
    })
    expect(onLoadMediaContext).toHaveBeenCalledWith({ targetType: 'shot', targetId: 'fixture-round:4:approach' })
    expect(onAnalyzeMedia).toHaveBeenCalledWith('media-1')
    expect(onAttachMedia).toHaveBeenCalledWith(
      expect.objectContaining({
        targetType: 'shot',
        targetId: 'fixture-round:4:approach',
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
    expect(onCreateAudit).toHaveBeenCalledWith(decision)
  })
})

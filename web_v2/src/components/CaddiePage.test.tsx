import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CaddiePage } from './CaddiePage'
import type { CaddieDecisionAuditRecord, CaddieDecisionResponse, WeatherSnapshotResponse } from '../types'

const decision: CaddieDecisionResponse = {
  schema: 'ai-caddie-decision-v2',
  shotType: 'approach',
  phase: 'Approach',
  context: { distanceToPin_m: 142 },
  options: [
    { id: 'safe', label: 'Safe', recommendedClub: '9I', carry_m: 132, riskScore: 0 },
    { id: 'stock', label: 'Stock', recommendedClub: '8I', carry_m: 144, riskScore: 1 },
    { id: 'attack', label: 'Attack', recommendedClub: '7I', carry_m: 156, riskScore: 3 },
  ],
  selected: { id: 'stock' },
  selectedOptionId: 'stock',
  selectedOption: { id: 'stock' },
  avoidZones: [{ kind: 'water', id: 'water_front' }],
  forbiddenZones: [],
  acceptableMiss: { side: 'long' },
  evidence: [{ label: 'water_front', value: 'carry 126m' }],
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

describe('CaddiePage', () => {
  it('renders decision evidence and requests a fixture-backed plan', async () => {
    const onRequestDecision = vi.fn()
    const onCreateAudit = vi.fn()
    const onLoadWeather = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'ready', data: decision }}
        auditState={{ status: 'ready', data: auditRecord }}
        weatherState={{ status: 'ready', data: weatherSnapshot }}
        onRequestDecision={onRequestDecision}
        onCreateAudit={onCreateAudit}
        onLoadWeather={onLoadWeather}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Caddie' })).toBeInTheDocument()
    expect(screen.getByText('Stock')).toBeInTheDocument()
    expect(screen.getByText('8I')).toBeInTheDocument()
    expect(screen.getByText('selected')).toBeInTheDocument()
    expect(screen.getAllByText('water_front').length).toBeGreaterThan(0)
    expect(screen.getByText('wind')).toBeInTheDocument()
    expect(screen.getAllByText('medium confidence').length).toBeGreaterThan(0)
    expect(screen.getByText('execution')).toHaveClass('audit-execution')
    expect(screen.getByText('planned stock -> actual stock')).toBeInTheDocument()
    expect(screen.getByText('5.4 m/s')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Load weather' }))
    await userEvent.click(screen.getByRole('button', { name: 'Request caddie plan' }))
    await userEvent.click(screen.getByRole('button', { name: 'Audit with fixture outcome' }))

    expect(onLoadWeather).toHaveBeenCalledTimes(1)
    expect(onRequestDecision).toHaveBeenCalledWith({
      shotType: 'approach',
      context: expect.objectContaining({ distanceToPin_m: 142, lie: 'fairway', weatherSnapshot }),
    })
    expect(onCreateAudit).toHaveBeenCalledWith(decision)
  })
})

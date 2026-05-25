import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CaddiePage } from './CaddiePage'
import type { CaddieDecisionAuditRecord, CaddieDecisionResponse } from '../types'

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

describe('CaddiePage', () => {
  it('renders decision evidence and requests a fixture-backed plan', async () => {
    const onRequestDecision = vi.fn()
    const onCreateAudit = vi.fn()

    render(
      <CaddiePage
        decisionState={{ status: 'ready', data: decision }}
        auditState={{ status: 'ready', data: auditRecord }}
        onRequestDecision={onRequestDecision}
        onCreateAudit={onCreateAudit}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Caddie' })).toBeInTheDocument()
    expect(screen.getByText('Stock')).toBeInTheDocument()
    expect(screen.getByText('8I')).toBeInTheDocument()
    expect(screen.getByText('selected')).toBeInTheDocument()
    expect(screen.getAllByText('water_front').length).toBeGreaterThan(0)
    expect(screen.getByText('wind')).toBeInTheDocument()
    expect(screen.getByText('medium confidence')).toBeInTheDocument()
    expect(screen.getByText('execution')).toHaveClass('audit-execution')
    expect(screen.getByText('planned stock -> actual stock')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Request caddie plan' }))
    await userEvent.click(screen.getByRole('button', { name: 'Audit with fixture outcome' }))

    expect(onRequestDecision).toHaveBeenCalledWith({
      shotType: 'approach',
      context: expect.objectContaining({ distanceToPin_m: 142, lie: 'fairway' }),
    })
    expect(onCreateAudit).toHaveBeenCalledWith(decision)
  })
})

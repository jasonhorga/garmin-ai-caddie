import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MobileReconciliationApplyResponse, MobileReconciliationResponse } from '../types'
import { MobileReconciliationPanel } from './MobileReconciliationPanel'

const reconciliation: MobileReconciliationResponse = {
  schema: 'ai-caddie-mobile-reconciliation-v1',
  roundId: '900001',
  summary: {
    eventCount: 3,
    matchedCount: 1,
    localOnlyCount: 1,
    garminOnlyCount: 0,
    conflictCount: 1,
    candidateDecisionAuditCount: 1,
    annotationSuggestionCount: 2,
  },
  matched: [{ eventId: 'club-match', kind: 'club', hole: 1, ref: '900001:1:1' }],
  localOnly: [{ eventId: 'penalty-local', kind: 'penalty', hole: 3, localValue: 1 }],
  garminOnly: [],
  conflicts: [{ eventId: 'score-conflict', kind: 'score', hole: 1, localValue: 5, garminValue: 4, ref: '900001:1' }],
  candidateDecisionAudits: [{ eventId: 'audit-1', decisionId: 'decision-1', hole: 1, actualShot: { clubName: '8I' } }],
  annotationSuggestions: [
    {
      id: 'score-conflict:score-correction',
      targetType: 'hole',
      targetId: '900001:1',
      kind: 'score_correction',
      payload: { from: 4, to: 5, sourceEventId: 'score-conflict' },
      reason: 'Local score input can correct the derived score for this hole.',
      confidence: 'medium',
    },
    {
      id: 'audit-1:caddie-feedback',
      targetType: 'decision',
      targetId: 'decision-1',
      kind: 'caddie_feedback',
      payload: { decisionId: 'decision-1', sourceEventId: 'audit-1' },
      reason: 'Offline live event includes an actual shot that can audit this caddie decision.',
      confidence: 'medium',
    },
  ],
}

const applyResponse: MobileReconciliationApplyResponse = {
  schema: 'ai-caddie-mobile-reconciliation-apply-v1',
  roundId: '900001',
  appliedCount: 1,
  skippedCount: 0,
  missingSuggestionIds: [],
  skippedSuggestionIds: [],
  annotations: [
    {
      id: 'ann-1',
      createdAt: '2026-05-25T11:00:00Z',
      targetType: 'hole',
      targetId: '900001:1',
      kind: 'score_correction',
      payload: { from: 4, to: 5 },
      source: 'manual',
    },
  ],
}

describe('MobileReconciliationPanel', () => {
  it('loads a round id from the review form', async () => {
    const onLoad = vi.fn()

    render(<MobileReconciliationPanel state={{ status: 'idle' }} applyState={{ status: 'idle' }} onLoad={onLoad} onApply={vi.fn()} />)

    await userEvent.clear(screen.getByLabelText('Round ID'))
    await userEvent.type(screen.getByLabelText('Round ID'), 'round:1')
    await userEvent.click(screen.getByRole('button', { name: 'Review offline events' }))

    expect(onLoad).toHaveBeenCalledWith('round:1')
  })

  it('renders reconciliation summary, suggestions, and applies selected rows', async () => {
    const onApply = vi.fn().mockResolvedValue(undefined)

    render(
      <MobileReconciliationPanel
        state={{ status: 'ready', data: reconciliation }}
        applyState={{ status: 'ready', data: applyResponse }}
        onLoad={vi.fn()}
        onApply={onApply}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Mobile Reconciliation' })).toBeInTheDocument()
    expect(screen.getByText('3 events')).toBeInTheDocument()
    expect(screen.getByText('1 conflict')).toBeInTheDocument()
    expect(screen.getByText('2 suggestions')).toBeInTheDocument()
    expect(screen.getAllByText('score_correction').length).toBeGreaterThan(0)
    expect(screen.getAllByText('900001:1').length).toBeGreaterThan(0)
    expect(screen.getByText('4 -> 5')).toBeInTheDocument()
    expect(screen.getByText('Offline live event includes an actual shot that can audit this caddie decision.')).toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('Select suggestion audit-1:caddie-feedback'))
    await userEvent.click(screen.getByRole('button', { name: 'Apply selected suggestions' }))

    expect(onApply).toHaveBeenCalledWith('900001', ['score-conflict:score-correction'])
    expect(screen.getByText('Applied 1 suggestions')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Applied annotations')).getByText('score_correction')).toBeInTheDocument()
  })

  it('shows an empty state when there are no annotation suggestions', () => {
    render(
      <MobileReconciliationPanel
        state={{ status: 'ready', data: { ...reconciliation, annotationSuggestions: [], summary: { ...reconciliation.summary, annotationSuggestionCount: 0 } } }}
        applyState={{ status: 'idle' }}
        onLoad={vi.fn()}
        onApply={vi.fn()}
      />,
    )

    expect(screen.getByText('No reconciliation suggestions')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Apply selected suggestions' })).toBeDisabled()
  })
})

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { MobileReconciliationApplyResponse, MobileReconciliationResponse } from '../types'
import { MobileReconciliationPanel } from './MobileReconciliationPanel'

const reconciliation: MobileReconciliationResponse = {
  schema: 'ai-caddie-mobile-reconciliation-v1',
  roundId: '900001',
  summary: {
    eventCount: 5,
    matchedCount: 1,
    localOnlyCount: 2,
    garminOnlyCount: 1,
    conflictCount: 1,
    candidateDecisionAuditCount: 1,
    annotationSuggestionCount: 4,
  },
  matched: [{ eventId: 'club-match', kind: 'club', hole: 1, ref: '900001:1:1' }],
  localOnly: [
    { eventId: 'penalty-local', kind: 'penalty', hole: 3, localValue: 1 },
    { eventId: 'note-local', kind: 'note', hole: 7, localValue: 'Wind hurting; favor center green.' },
  ],
  garminOnly: [{ kind: 'club', hole: 2, garminValue: '3W', ref: '900001:2:1' }],
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
      id: 'note-local:hole-note',
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'hole_note',
      payload: { text: 'Wind hurting; favor center green.', sourceEventId: 'note-local' },
      reason: 'Local mobile note can be preserved as an auditable hole note.',
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
    {
      id: 'photo-lie:media-context',
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'hole_note',
      payload: {
        mediaType: 'photo',
        mediaId: 'media-photo-1',
        text: 'Ball sitting down in rough.',
        sourceEventId: 'photo-lie',
      },
      reason: 'Offline photo context can be preserved as auditable media evidence for this hole.',
      confidence: 'medium',
    },
  ],
}

const applyResponse: MobileReconciliationApplyResponse = {
  schema: 'ai-caddie-mobile-reconciliation-apply-v1',
  roundId: '900001',
  appliedCount: 1,
  decisionAuditCount: 1,
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
  decisionAudits: [{ id: 'audit-1', decisionId: 'decision-1', classification: 'execution' }],
}

describe('MobileReconciliationPanel', () => {
  it('labels each restored hole replaced by a later Garmin card', () => {
    // J1.3: the local evidence explains why a formerly matched score is no longer in this round.
    const data = { ...reconciliation, localOnly: [
      { eventId: 'restored-score', kind: 'score', hole: 10, phoneHole: 10,
        localValue: 5, restoreSuperseded: true },
    ] }
    render(<MobileReconciliationPanel state={{ status: 'ready', data }} applyState={{ status: 'idle' }}
      onLoad={vi.fn()} onApply={vi.fn()} />)
    const evidence = screen.getByRole('region', { name: '仅本地移动事件' })
    expect(within(evidence).getByText('手机第 10 洞：补分已被后到 Garmin 球局替代')).toBeInTheDocument()
    expect(within(evidence).getByText('restored-score')).toBeInTheDocument()
  })

  it('uses mutually exclusive radios for conflict resolutions and leaves them unselected', async () => {
    const onApply = vi.fn().mockResolvedValue(undefined)
    const conflictData: MobileReconciliationResponse = {
      ...reconciliation,
      annotationSuggestions: [
        reconciliation.annotationSuggestions[1],
        {
          ...reconciliation.annotationSuggestions[0],
          id: 'score-conflict:score-correction-conflict:garmin:7:6',
          payload: { from: 6, to: 7, sourceEventId: 'score-conflict', resolution: 'garmin' },
        },
        {
          ...reconciliation.annotationSuggestions[0],
          id: 'score-conflict:score-correction-conflict:mobile:7:6',
          payload: { from: 7, to: 6, sourceEventId: 'score-conflict', resolution: 'mobile' },
        },
      ],
    }

    render(
      <MobileReconciliationPanel
        state={{ status: 'ready', data: conflictData }}
        applyState={{ status: 'idle' }}
        onLoad={vi.fn()}
        onApply={onApply}
      />,
    )

    const garmin = screen.getByLabelText('选择建议 score-conflict:score-correction-conflict:garmin:7:6')
    const mobile = screen.getByLabelText('选择建议 score-conflict:score-correction-conflict:mobile:7:6')
    expect(garmin).toHaveAttribute('type', 'radio')
    expect(mobile).toHaveAttribute('type', 'radio')
    expect(garmin).not.toBeChecked()
    expect(mobile).not.toBeChecked()
    expect(screen.getByLabelText('选择建议 note-local:hole-note')).toBeChecked()

    await userEvent.click(garmin)
    await userEvent.click(screen.getByRole('button', { name: '应用所选建议' }))
    expect(onApply).toHaveBeenCalledWith('900001', [
      'note-local:hole-note',
      'score-conflict:score-correction-conflict:garmin:7:6',
    ])
  })

  it('shows expired suggestions and reloads after an apply reports missing ids', async () => {
    const onLoad = vi.fn()
    const onApply = vi.fn().mockResolvedValue({
      ...applyResponse,
      appliedCount: 0,
      missingSuggestionIds: ['score-conflict:score-correction'],
    })

    render(
      <MobileReconciliationPanel
        state={{ status: 'ready', data: reconciliation }}
        applyState={{ status: 'idle' }}
        onLoad={onLoad}
        onApply={onApply}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: '应用所选建议' }))
    expect(await screen.findByText('建议已过期')).toBeInTheDocument()
    expect(onLoad).toHaveBeenCalledWith('900001')
    expect(screen.queryByText('未找到:score-conflict:score-correction')).not.toBeInTheDocument()
  })

  it('loads a round id from the review form', async () => {
    const onLoad = vi.fn()

    render(<MobileReconciliationPanel state={{ status: 'idle' }} applyState={{ status: 'idle' }} onLoad={onLoad} onApply={vi.fn()} />)

    await userEvent.clear(screen.getByLabelText('球局编号'))
    await userEvent.type(screen.getByLabelText('球局编号'), 'round:1')
    await userEvent.click(screen.getByRole('button', { name: '核对离线事件' }))

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

    expect(screen.getByRole('heading', { name: '离线对账' })).toBeInTheDocument()
    expect(screen.getByText('5 个事件')).toBeInTheDocument()
    expect(screen.getByText('1 处冲突')).toBeInTheDocument()
    expect(screen.getByText('4 条建议')).toBeInTheDocument()
    expect(screen.getAllByText('score_correction').length).toBeGreaterThan(0)
    expect(screen.getAllByText('hole_note').length).toBeGreaterThan(0)
    expect(screen.getAllByText('900001:1').length).toBeGreaterThan(0)
    expect(screen.getByText('4 → 5')).toBeInTheDocument()
    expect(screen.getByText('photo media-photo-1: Ball sitting down in rough.')).toBeInTheDocument()
    expect(screen.getAllByText('Wind hurting; favor center green.').length).toBeGreaterThan(0)
    expect(screen.getByText('Offline live event includes an actual shot that can audit this caddie decision.')).toBeInTheDocument()

    await userEvent.click(screen.getByLabelText('选择建议 audit-1:caddie-feedback'))
    await userEvent.click(screen.getByRole('button', { name: '应用所选建议' }))

    expect(onApply).toHaveBeenCalledWith('900001', ['score-conflict:score-correction', 'note-local:hole-note', 'photo-lie:media-context'])
    expect(screen.getByText('已应用 1 条建议，存档 1 条审计')).toBeInTheDocument()
    expect(within(screen.getByLabelText('已应用批注')).getByText('score_correction')).toBeInTheDocument()
    expect(within(screen.getByLabelText('已存档决策审计')).getByText('execution')).toBeInTheDocument()
  })

  it('renders local-only, Garmin-only, conflict, and audit evidence rows', () => {
    render(
      <MobileReconciliationPanel
        state={{ status: 'ready', data: reconciliation }}
        applyState={{ status: 'idle' }}
        onLoad={vi.fn()}
        onApply={vi.fn()}
      />,
    )

    expect(within(screen.getByLabelText('仅本地移动事件')).getByText('note-local')).toBeInTheDocument()
    expect(within(screen.getByLabelText('仅本地移动事件')).getByText('Wind hurting; favor center green.')).toBeInTheDocument()
    expect(within(screen.getByLabelText('仅 Garmin 事实')).getByText('900001:2:1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('对账冲突')).getByText('score-conflict')).toBeInTheDocument()
    expect(within(screen.getByLabelText('候选决策审计')).getByText('decision-1')).toBeInTheDocument()
  })

  it('shows skipped and missing apply results', () => {
    render(
      <MobileReconciliationPanel
        state={{ status: 'ready', data: reconciliation }}
        applyState={{
          status: 'ready',
          data: {
            ...applyResponse,
            appliedCount: 0,
            decisionAuditCount: 0,
            skippedCount: 1,
            skippedSuggestionIds: ['note-local:hole-note'],
            missingSuggestionIds: ['missing:hole-note'],
            annotations: [],
            decisionAudits: [],
          },
        }}
        onLoad={vi.fn()}
        onApply={vi.fn()}
      />,
    )

    expect(screen.getByText('已应用 0 条建议，跳过 1 条')).toBeInTheDocument()
    expect(screen.getByText('已跳过:note-local:hole-note')).toBeInTheDocument()
    expect(screen.getByText('未找到:missing:hole-note')).toBeInTheDocument()
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

    expect(screen.getByText('暂无对账建议')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '应用所选建议' })).toBeDisabled()
  })
})

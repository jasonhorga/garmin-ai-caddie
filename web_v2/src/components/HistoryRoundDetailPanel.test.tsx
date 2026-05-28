import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HistoryRoundDetailPanel } from './HistoryRoundDetailPanel'
import type { HistoryRoundDetailResponse } from '../types'

const payload: HistoryRoundDetailResponse = {
  schema: 'ai-caddie-history-round-detail-v1',
  roundRef: '700001',
  requestedRef: '700001',
  found: true,
  title: 'Scorecard Links - 2026-05-25',
  round: {
    id: '700001',
    courseName: 'Scorecard Links',
    score: 82,
    toPar: 10,
    holesScored: 18,
    shotCount: 42,
    coverage: { scorecard: 'ready', shots: 'ready', putts: 'partial' },
    confidence: 'high',
  },
  scorecard: [
    {
      hole: 1,
      par: 4,
      score: 4,
      toPar: 0,
      className: 'par',
      putts: 2,
      gir: true,
      fairway: 'hit',
      holeRef: '700001:1',
      shotRefs: ['700001:1:0', '700001:1:1'],
      sourceRefs: ['700001:1'],
      status: 'complete',
    },
    {
      hole: 2,
      par: 4,
      score: 5,
      toPar: 1,
      className: 'bogey',
      putts: 3,
      gir: false,
      fairway: 'right',
      holeRef: '700001:2',
      shotRefs: ['700001:2:2'],
      sourceRefs: ['700001:2'],
      status: 'complete',
    },
  ],
  phaseSummary: [
    { phase: 'Tee', state: 'ready', primary: '1/2 fairways', metrics: { fairwaysHit: 1 } },
    { phase: 'Putting', state: 'ready', primary: '5 putts', metrics: { totalPutts: 5 } },
  ],
  holeDetails: [
    { hole: 1, score: 4, toPar: 0, putts: 2, gir: true, fairway: 'hit', holeRef: '700001:1', shotRefs: ['700001:1:0', '700001:1:1'] },
    { hole: 2, score: 5, toPar: 1, putts: 3, gir: false, fairway: 'right', holeRef: '700001:2', shotRefs: ['700001:2:2'] },
  ],
  relatedRefs: {
    roundRefs: ['700001'],
    holeRefs: ['700001:1', '700001:2'],
    shotRefs: ['700001:1:0', '700001:1:1', '700001:2:2'],
    sourceRefs: ['garmin:scorecard:700001'],
  },
  sourceFields: { strokes: 82 },
  missingData: [{ label: 'putts', state: 'partial', reason: 'some holes missing putts' }],
  annotations: [
    { id: 'note-1', createdAt: '2026-05-25T12:00:00Z', targetType: 'round', targetId: '700001', kind: 'round_note', payload: { text: 'windy finish' }, source: 'manual' },
  ],
  corrections: [
    { id: 'correction-1', createdAt: '2026-05-25T12:00:00Z', targetType: 'round', targetId: '700001', kind: 'score_correction', payload: { from: 83, to: 82 }, source: 'manual' },
  ],
}

describe('HistoryRoundDetailPanel', () => {
  it('renders scorecard-first round review with phase and hole evidence', () => {
    render(<HistoryRoundDetailPanel state={{ status: 'ready', data: payload }} />)

    expect(screen.getByRole('heading', { name: 'Round Review' })).toBeInTheDocument()
    expect(screen.getByText('Scorecard Links - 2026-05-25')).toBeInTheDocument()
    expect(screen.getByLabelText('Round detail facts')).toHaveTextContent('Score')
    expect(screen.getByLabelText('Scorecard')).toHaveTextContent('H1')
    expect(screen.getByLabelText('Scorecard')).toHaveTextContent('3 putts')
    expect(screen.getByLabelText('Phase summary')).toHaveTextContent('1/2 fairways')
    expect(screen.getByLabelText('Hole details')).toHaveTextContent('700001:1:0')
    expect(screen.getByText('windy finish')).toBeInTheDocument()
    expect(screen.getByText('83 -> 82')).toBeInTheDocument()
    expect(screen.getAllByText('partial').length).toBeGreaterThan(0)
  })

  it('opens hole and shot source refs from the round detail', async () => {
    const onSelectRef = vi.fn()

    render(<HistoryRoundDetailPanel state={{ status: 'ready', data: payload }} onSelectRef={onSelectRef} />)

    await userEvent.click(screen.getByRole('button', { name: 'Open hole 1 detail 700001:1' }))
    const holeDetails = screen.getByLabelText('Hole details')
    await userEvent.click(within(holeDetails).getByRole('button', { name: 'Open source 700001:1:0' }))

    expect(onSelectRef).toHaveBeenCalledWith('700001:1')
    expect(onSelectRef).toHaveBeenCalledWith('700001:1:0')
  })

  it('supports retry and round correction actions', async () => {
    const onRetryRound = vi.fn()
    const onCreateAnnotationForRound = vi.fn()
    const onLoadRoundReport = vi.fn()
    const onGenerateRoundReport = vi.fn()

    render(<HistoryRoundDetailPanel state={{ status: 'error', roundRef: '700001', message: '401' }} onRetryRound={onRetryRound} />)
    await userEvent.click(screen.getByRole('button', { name: 'Retry round review' }))
    expect(onRetryRound).toHaveBeenCalledWith('700001')

    render(
      <HistoryRoundDetailPanel
        state={{ status: 'ready', data: payload }}
        onCreateAnnotationForRound={onCreateAnnotationForRound}
        onLoadRoundReport={onLoadRoundReport}
        onGenerateRoundReport={onGenerateRoundReport}
        reportState={{
          status: 'ready',
          data: {
            schema: 'ai-caddie-review-report-v1',
            kind: 'round',
            subjectId: '700001',
            sourceRefs: ['700001', '700001:1'],
            provider: 'StaticProvider',
            model: 'static',
            factsUsed: [
              {
                label: 'score',
                source: 'round',
                value: { score: 82, toPar: 10 },
                sourceRefs: ['700001'],
              },
              {
                label: 'putting',
                source: 'scorecard',
                value: '5 putts through fixture holes',
                holeRefs: ['700001:1', '700001:2'],
              },
            ],
            missingData: [
              {
                label: 'weather',
                state: 'missing',
                reason: 'no weather snapshot for this round',
                missingDataRefs: ['700001'],
              },
            ],
            inferencesMade: [
              {
                claim: 'Putting cost strokes late in the round.',
                factLabels: ['putting'],
                missingDataLabels: ['weather'],
                sourceRefs: ['700001:2'],
                confidence: 'medium',
              },
            ],
            unsupportedClaims: [
              {
                category: 'weather',
                claim: 'Wind caused the miss.',
                reason: 'weather snapshot is missing',
                missingDataRefs: ['700001'],
              },
            ],
            narrative: 'Round review from scorecard facts.',
            confidence: 'medium',
          },
        }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Add correction for round 700001' }))
    await userEvent.click(screen.getByRole('button', { name: 'Load AI Review' }))
    await userEvent.click(screen.getByRole('button', { name: 'Generate AI Review' }))
    expect(onCreateAnnotationForRound).toHaveBeenCalledWith({ targetType: 'round', targetId: '700001' })
    expect(onLoadRoundReport).toHaveBeenCalledWith('700001')
    expect(onGenerateRoundReport).toHaveBeenCalledWith('700001')
    expect(screen.getByText('Round review from scorecard facts.')).toBeInTheDocument()
    expect(screen.getByText('medium confidence')).toBeInTheDocument()
    expect(screen.getByLabelText('Round AI facts')).toHaveTextContent('score')
    expect(screen.getByLabelText('Round AI facts')).toHaveTextContent('score 82')
    expect(screen.getByLabelText('Round AI inferences')).toHaveTextContent('Putting cost strokes late in the round.')
    expect(screen.getByLabelText('Round AI missing data')).toHaveTextContent('weather')
    expect(screen.getByLabelText('Round AI unsupported claims')).toHaveTextContent('Wind caused the miss.')
  })
})

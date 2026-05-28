import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CorrectionsPage } from './CorrectionsPage'
import type { AnnotationCreateRequest, AnnotationCreateResponse, AnnotationKind, AnnotationTargetType } from '../types'

function responseFor(request: AnnotationCreateRequest): AnnotationCreateResponse {
  return {
    schema: 'ai-caddie-annotation-create-v1',
    annotation: {
      id: `ann-${request.kind}`,
      createdAt: '2026-05-25T10:40:00Z',
      targetType: request.targetType,
      targetId: request.targetId,
      kind: request.kind,
      payload: request.payload,
      source: 'manual',
    },
  }
}

function renderPage(
  onCreateAnnotation = vi.fn(async (request: AnnotationCreateRequest) => responseFor(request)),
  initialTarget?: { targetType: AnnotationTargetType; targetId: string },
) {
  render(
    <CorrectionsPage
      data={{ schema: 'ai-caddie-annotations-v1', total: 0, target: null, annotations: [] }}
      initialTarget={initialTarget}
      onCreateAnnotation={onCreateAnnotation}
    />,
  )
  return onCreateAnnotation
}

describe('CorrectionsPage', () => {
  it('summarizes correction impact without implying raw Garmin mutation', () => {
    render(
      <CorrectionsPage
        data={{
          schema: 'ai-caddie-annotations-v1',
          total: 4,
          target: null,
          annotations: [
            {
              id: 'ann-club',
              createdAt: '2026-05-25T10:40:00Z',
              targetType: 'shot',
              targetId: '900001:1:1',
              kind: 'club_correction',
              payload: { from: '8I', to: '7I' },
              source: 'manual',
            },
            {
              id: 'ann-score',
              createdAt: '2026-05-25T10:41:00Z',
              targetType: 'hole',
              targetId: '900001:1',
              kind: 'score_correction',
              payload: { from: 5, to: 4 },
              source: 'manual',
            },
            {
              id: 'ann-tag',
              createdAt: '2026-05-25T10:42:00Z',
              targetType: 'hole',
              targetId: '900001:1',
              kind: 'issue_tag',
              payload: { tag: 'approach_short' },
              source: 'manual',
            },
            {
              id: 'ann-note',
              createdAt: '2026-05-25T10:43:00Z',
              targetType: 'round',
              targetId: '900001',
              kind: 'round_note',
              payload: { text: 'Firm greens' },
              source: 'manual',
            },
          ],
        }}
        onCreateAnnotation={vi.fn()}
      />,
    )

    const impact = screen.getByLabelText('Correction impact')
    expect(within(impact).getByRole('heading', { name: 'Correction Impact' })).toBeInTheDocument()
    expect(within(impact).getByText('Manual records are overlays for derived stats; Garmin raw snapshots stay unchanged.')).toBeInTheDocument()
    expect(within(impact).getByText('Total annotations')).toBeInTheDocument()
    expect(within(impact).getByText('Stat overlays')).toBeInTheDocument()
    expect(within(impact).getByText('Corrections')).toBeInTheDocument()
    expect(within(impact).getByText('append-only audit log')).toBeInTheDocument()
    expect(within(impact).getByText('raw facts immutable')).toBeInTheDocument()
    expect(within(impact).getByText('history stats use explicit overlays')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Correction targets')).getByText('hole 2')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Correction targets')).getByText('round 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Correction targets')).getByText('shot 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Correction kinds')).getByText('Club correction 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Correction kinds')).getByText('Issue tag 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Correction kinds')).getByText('Round note 1')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Correction kinds')).getByText('Score correction 1')).toBeInTheDocument()
  })

  it.each([
    {
      option: 'Lie correction',
      targetType: 'shot',
      targetId: '900001:1:1',
      kind: 'lie_correction',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('Recorded lie'), 'rough')
        await userEvent.type(screen.getByLabelText('Corrected lie'), 'fairway')
      },
      payload: { from: 'rough', to: 'fairway' },
    },
    {
      option: 'Penalty correction',
      targetType: 'hole',
      targetId: '900001:2',
      kind: 'penalty_correction',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('Penalty strokes'), '1')
        await userEvent.type(screen.getByLabelText('Penalty reason'), 'water')
      },
      payload: { strokes: 1, reason: 'water' },
    },
    {
      option: 'Weather note',
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'weather_context_note',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('Note'), 'Strong headwind')
      },
      payload: { text: 'Strong headwind' },
    },
    {
      option: 'Strategy note',
      targetType: 'decision',
      targetId: '900001:7:2',
      kind: 'strategy_note',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('Note'), 'Layup was smarter')
      },
      payload: { text: 'Layup was smarter' },
    },
    {
      option: 'Caddie feedback',
      targetType: 'decision',
      targetId: '900001:7:2',
      kind: 'caddie_feedback',
      fill: async () => {
        await userEvent.selectOptions(screen.getByLabelText('Feedback rating'), 'too_aggressive')
        await userEvent.type(screen.getByLabelText('Note'), 'Water was too close')
      },
      payload: { rating: 'too_aggressive', note: 'Water was too close' },
    },
    {
      option: 'Remove issue tag',
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'issue_tag_removed',
      fill: async () => {
        await userEvent.type(screen.getByLabelText('Issue tag'), 'approach_short')
      },
      payload: { tag: 'approach_short' },
    },
  ])('submits $option payloads', async ({ option, targetType, targetId, kind, fill, payload }) => {
    const onCreateAnnotation = renderPage()

    expect(screen.getByRole('option', { name: option })).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Target type'), targetType)
    await userEvent.type(screen.getByLabelText('Target ID'), targetId)
    await userEvent.selectOptions(screen.getByLabelText('Correction type'), kind)
    await fill()
    await userEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

    expect(onCreateAnnotation).toHaveBeenCalledWith({
      targetType: targetType as AnnotationTargetType,
      targetId,
      kind: kind as AnnotationKind,
      payload,
    })
  })

  it.each([
    ['club_correction', 'Club corrections need both recorded and corrected clubs.'],
    ['issue_tag', 'Issue tag changes need an issue tag.'],
    ['note', 'Notes need text before saving.'],
  ])('prevents empty %s annotation payloads', async (kind, message) => {
    const onCreateAnnotation = renderPage()

    await userEvent.type(screen.getByLabelText('Target ID'), '900001:7')
    await userEvent.selectOptions(screen.getByLabelText('Correction type'), kind)
    await userEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

    expect(onCreateAnnotation).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent(message)
  })

  it('prevents non-numeric score corrections before calling the API', async () => {
    const onCreateAnnotation = renderPage()

    await userEvent.type(screen.getByLabelText('Target ID'), '900001:7')
    await userEvent.selectOptions(screen.getByLabelText('Correction type'), 'score_correction')
    await userEvent.type(screen.getByLabelText('Recorded score'), 'four')
    await userEvent.type(screen.getByLabelText('Corrected score'), '5')
    await userEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

    expect(onCreateAnnotation).not.toHaveBeenCalled()
    expect(screen.getByRole('status')).toHaveTextContent('Score corrections need numeric recorded and corrected scores.')
  })

  it('labels issue tag removal records in annotation history', () => {
    render(
      <CorrectionsPage
        data={{
          schema: 'ai-caddie-annotations-v1',
          total: 1,
          target: null,
          annotations: [
            {
              id: 'ann-remove',
              createdAt: '2026-05-25T10:40:00Z',
              targetType: 'hole',
              targetId: '900001:7',
              kind: 'issue_tag_removed' as AnnotationKind,
              payload: { tag: 'approach_short' },
              source: 'manual',
            },
          ],
        }}
        onCreateAnnotation={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Remove issue tag' })).toBeInTheDocument()
    expect(screen.getByText('approach_short')).toBeInTheDocument()
  })

  it('prefills a source-bound target and keeps it after saving', async () => {
    const onCreateAnnotation = renderPage(undefined, { targetType: 'hole', targetId: '900001:7' })

    expect(screen.getByLabelText('Target type')).toHaveValue('hole')
    expect(screen.getByLabelText('Target ID')).toHaveValue('900001:7')

    await userEvent.selectOptions(screen.getByLabelText('Correction type'), 'note')
    await userEvent.type(screen.getByLabelText('Note'), 'Pin was back right')
    await userEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

    expect(onCreateAnnotation).toHaveBeenCalledWith({
      targetType: 'hole',
      targetId: '900001:7',
      kind: 'hole_note',
      payload: { text: 'Pin was back right' },
    })
    expect(screen.getByLabelText('Target type')).toHaveValue('hole')
    expect(screen.getByLabelText('Target ID')).toHaveValue('900001:7')
  })

  it('restores the source-bound target type when saving after local target edits', async () => {
    const onCreateAnnotation = renderPage(undefined, { targetType: 'hole', targetId: '900001:7' })

    await userEvent.selectOptions(screen.getByLabelText('Target type'), 'shot')
    await userEvent.clear(screen.getByLabelText('Target ID'))
    await userEvent.type(screen.getByLabelText('Target ID'), '900001:7:1')
    await userEvent.selectOptions(screen.getByLabelText('Correction type'), 'note')
    await userEvent.type(screen.getByLabelText('Note'), 'Pin was back right')
    await userEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

    expect(onCreateAnnotation).toHaveBeenCalledWith({
      targetType: 'shot',
      targetId: '900001:7:1',
      kind: 'shot_note',
      payload: { text: 'Pin was back right' },
    })
    expect(screen.getByLabelText('Target type')).toHaveValue('hole')
    expect(screen.getByLabelText('Target ID')).toHaveValue('900001:7')
  })
})

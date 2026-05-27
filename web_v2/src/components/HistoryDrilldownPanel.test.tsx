import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { HistoryDrilldownPanel } from './HistoryDrilldownPanel'

describe('HistoryDrilldownPanel', () => {
  it('renders source detail with source fields and missing data', () => {
    render(
      <HistoryDrilldownPanel
        state={{
          status: 'ready',
          data: {
            schema: 'ai-caddie-history-drilldown-v1',
            ref: '900001:1:0',
            refType: 'shot',
            found: true,
            title: '1D on H1',
            round: { id: '900001', score: 77 },
            hole: { number: 1, par: 4, strokes: 4 },
            shot: { club: '1D', distance: 242, surface: 'fairway' },
            relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:1'], shotRefs: ['900001:1:0'] },
            sourceFields: { clubName: '1D', meters: 242, provenance: { confidence: 'high' } },
            missingData: [{ label: 'geometry', state: 'partial' }],
          },
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Source Detail' })).toBeInTheDocument()
    expect(screen.getByText('1D on H1')).toBeInTheDocument()
    expect(screen.getByText('shot')).toBeInTheDocument()
    expect(screen.getByText('clubName')).toBeInTheDocument()
    expect(screen.getByText('geometry')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Evidence Coverage' })).toBeInTheDocument()
    expect(screen.getByLabelText('Evidence coverage')).toHaveTextContent('Source fields3')
    expect(screen.getByLabelText('Evidence coverage')).toHaveTextContent('Related refs3')
    expect(screen.getByLabelText('Evidence coverage')).toHaveTextContent('Missing data1')
    expect(screen.getByLabelText('Evidence coverage')).toHaveTextContent('Confidencehigh')
  })

  it('renders related refs as drilldown buttons', async () => {
    const onSelectRef = vi.fn()
    const onCreateAnnotationForSource = vi.fn()

    render(
      <HistoryDrilldownPanel
        onSelectRef={onSelectRef}
        onCreateAnnotationForSource={onCreateAnnotationForSource}
        state={{
          status: 'ready',
          data: {
            schema: 'ai-caddie-history-drilldown-v1',
            ref: '900001:1:0',
            refType: 'shot',
            found: true,
            title: '1D on H1',
            round: { id: '900001', score: 77 },
            hole: { number: 1, par: 4, strokes: 4 },
            shot: { club: '1D', distance: 242, surface: 'fairway' },
            relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:1'], shotRefs: ['900001:1:0'] },
            sourceFields: { clubName: '1D', meters: 242 },
            missingData: [],
          },
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Related Sources' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Open source 900001:1' }))

    expect(onSelectRef).toHaveBeenCalledWith('900001:1')
    await userEvent.click(screen.getByRole('button', { name: 'Add correction for source 900001:1:0' }))

    expect(onCreateAnnotationForSource).toHaveBeenCalledWith({ targetType: 'shot', targetId: '900001:1:0' })
  })

  it('renders a retry action for protected drilldown errors', async () => {
    const onRetrySource = vi.fn()

    render(
      <HistoryDrilldownPanel
        onRetrySource={onRetrySource}
        state={{
          status: 'error',
          sourceRef: '900001:1:0',
          message: 'GET /api/v2/history/drilldown/900001%3A1%3A0 failed: 401 Unauthorized',
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Source Detail' })).toBeInTheDocument()
    expect(screen.getByText('900001:1:0')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Retry source detail' }))

    expect(onRetrySource).toHaveBeenCalledWith('900001:1:0')
  })

  it('creates corrections against canonical source targets when a drilldown ref is an alias', async () => {
    const onCreateAnnotationForSource = vi.fn()

    render(
      <HistoryDrilldownPanel
        onCreateAnnotationForSource={onCreateAnnotationForSource}
        state={{
          status: 'ready',
          data: {
            schema: 'ai-caddie-history-drilldown-v1',
            ref: 'garmin:shots:710001:hole10:shot0',
            refType: 'shot',
            found: true,
            title: '3W on H10',
            round: { id: 'merged_710001_710002', score: 82 },
            hole: { number: 10, par: 5, strokes: 5 },
            shot: { ref: 'merged_710001_710002:10:0', club: '3W', distance: 218, surface: 'fairway' },
            relatedRefs: {
              roundRefs: ['merged_710001_710002'],
              holeRefs: ['merged_710001_710002:10'],
              shotRefs: ['merged_710001_710002:10:0'],
            },
            sourceFields: { clubName: '3W', meters: 218 },
            missingData: [],
          },
        }}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Add correction for source garmin:shots:710001:hole10:shot0' }))

    expect(onCreateAnnotationForSource).toHaveBeenCalledWith({
      targetType: 'shot',
      targetId: 'merged_710001_710002:10:0',
    })
  })

  it('surfaces missing source reasons for unresolved refs', () => {
    render(
      <HistoryDrilldownPanel
        state={{
          status: 'ready',
          data: {
            schema: 'ai-caddie-history-drilldown-v1',
            ref: '900404:9',
            refType: 'hole',
            found: false,
            title: 'Source reference not found',
            round: null,
            hole: null,
            shot: null,
            relatedRefs: { roundRefs: [], holeRefs: [], shotRefs: [] },
            sourceFields: {},
            missingData: [{ label: 'source_ref', reason: '900404:9 was not found in loaded history data' }],
          },
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Source Unavailable' })).toBeInTheDocument()
    expect(screen.getByText('900404:9 was not found in loaded history data')).toBeInTheDocument()
  })

  it('renders manual annotations and corrections attached to the source', () => {
    render(
      <HistoryDrilldownPanel
        state={{
          status: 'ready',
          data: {
            schema: 'ai-caddie-history-drilldown-v1',
            ref: '900001:1:1',
            refType: 'shot',
            found: true,
            title: '8I on H1',
            round: { id: '900001', score: 77 },
            hole: { number: 1, par: 4, strokes: 4 },
            shot: { club: '8I', distance: 142, surface: 'green' },
            relatedRefs: { roundRefs: ['900001'], holeRefs: ['900001:1'], shotRefs: ['900001:1:1'] },
            sourceFields: { clubName: '8I', meters: 142 },
            missingData: [],
            annotations: [
              {
                id: 'ann-note',
                createdAt: '2026-05-25T10:40:00Z',
                targetType: 'shot',
                targetId: '900001:1:1',
                kind: 'shot_note',
                payload: { text: 'ball was above feet' },
                source: 'manual',
              },
              {
                id: 'ann-club',
                createdAt: '2026-05-25T10:41:00Z',
                targetType: 'shot',
                targetId: '900001:1:1',
                kind: 'club_correction',
                payload: { from: '8I', to: '7I' },
                source: 'manual',
              },
            ],
            corrections: [
              {
                id: 'ann-club',
                createdAt: '2026-05-25T10:41:00Z',
                targetType: 'shot',
                targetId: '900001:1:1',
                kind: 'club_correction',
                payload: { from: '8I', to: '7I' },
                source: 'manual',
              },
            ],
          },
        }}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Manual Annotations' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Applied Corrections' })).toBeInTheDocument()
    expect(screen.getByText('ball was above feet')).toBeInTheDocument()
    expect(screen.getAllByText('club_correction')).toHaveLength(2)
    expect(screen.getAllByText('8I -> 7I')).toHaveLength(2)
  })
})

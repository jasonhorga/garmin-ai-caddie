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
            sourceFields: { clubName: '1D', meters: 242 },
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
  })

  it('renders related refs as drilldown buttons', async () => {
    const onSelectRef = vi.fn()

    render(
      <HistoryDrilldownPanel
        onSelectRef={onSelectRef}
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
})

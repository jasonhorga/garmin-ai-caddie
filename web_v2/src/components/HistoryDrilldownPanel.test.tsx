import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
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
})

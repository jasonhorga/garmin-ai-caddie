import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DistributionPanel } from './DistributionPanel'
import type { ScoreDistribution } from '../types'

const distribution: ScoreDistribution = {
  total: 3,
  average: 88,
  best: 82,
  worst: 96,
  families: [
    { label: '70s', count: 0, pct: 0, className: 'eagle' },
    { label: '80s', count: 2, pct: 67, className: 'birdie' },
    { label: '90s', count: 1, pct: 33, className: 'bogey' },
  ],
  histogram: [
    { label: '80-84', start: 80, count: 0 },
    { label: '85-89', start: 85, count: 1 },
  ],
}

function barFor(label: string) {
  const row = screen.getByText(label).closest('div')
  const bar = row?.querySelector('i')

  if (!bar) {
    throw new Error(`Missing bar for ${label}`)
  }

  return bar
}

describe('DistributionPanel', () => {
  it('does not draw visible bars for zero-count distribution entries', () => {
    render(<DistributionPanel distribution={distribution} />)

    expect(barFor('70s')).toHaveStyle({ width: '0%' })
    expect(barFor('80s')).toHaveStyle({ width: '100%' })
    expect(barFor('80-84')).toHaveStyle({ width: '0%' })
    expect(barFor('85-89')).toHaveStyle({ width: '100%' })
  })

  it('does not render histogram bars when histogram data is empty', () => {
    const { container } = render(<DistributionPanel distribution={{ ...distribution, histogram: [] }} />)

    expect(container.querySelectorAll('.histogram-row i')).toHaveLength(0)
  })
})

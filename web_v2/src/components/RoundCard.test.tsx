import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RoundCard } from './RoundCard'
import type { RoundCard as RoundCardType } from '../types'

function baseRound(overrides: Partial<RoundCardType> = {}): RoundCardType {
  return {
    id: '900001',
    date: '2026-05-20T08:00:00',
    courseName: 'Black Knight B',
    courseKey: 'c_black',
    holesCompleted: 18,
    score: 82,
    par: 72,
    toPar: 10,
    scoreStrip: [{ hole: 1, par: 4, score: 4, toPar: 0, className: 'par' }],
    badges: [{ label: 'shots', state: 'good', value: 'ready', reason: 'ready' }],
    primaryIssue: null,
    ...overrides,
  }
}

describe('RoundCard', () => {
  it('tags a 手动 (manual) round with a chip', () => {
    render(<RoundCard round={baseRound({ source: 'manual' })} />)
    expect(screen.getByText('手动')).toBeInTheDocument()
    expect(screen.getByLabelText('手动录入的球局')).toBeInTheDocument()
  })

  it('does not tag Garmin-sourced rounds', () => {
    render(<RoundCard round={baseRound({ source: 'garmin' })} />)
    expect(screen.queryByText('手动')).not.toBeInTheDocument()
  })

  it('does not tag rounds with no source (legacy payloads)', () => {
    render(<RoundCard round={baseRound()} />)
    expect(screen.queryByText('手动')).not.toBeInTheDocument()
  })

  it('groups an 18-hole score strip into readable front and back nines', () => {
    const scoreStrip = Array.from({ length: 18 }, (_, index) => ({
      hole: index + 1,
      par: 4,
      score: 4,
      toPar: 0,
      className: 'par' as const,
    }))
    render(<RoundCard round={baseRound({ scoreStrip })} />)

    const front = screen.getByLabelText('前九成绩')
    const back = screen.getByLabelText('后九成绩')
    expect(within(front).getByText('1')).toBeInTheDocument()
    expect(within(front).getByText('9')).toBeInTheDocument()
    expect(within(front).queryByText('10')).not.toBeInTheDocument()
    expect(within(back).getByText('10')).toBeInTheDocument()
    expect(within(back).getByText('18')).toBeInTheDocument()
  })

  it('uses an under-par tone for a negative total instead of the over-par warning tone', () => {
    render(<RoundCard round={baseRound({ toPar: -3 })} />)
    expect(screen.getByText('-3')).toHaveClass('score-under')
  })
})

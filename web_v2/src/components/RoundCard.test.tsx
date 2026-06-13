import { render, screen } from '@testing-library/react'
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
})

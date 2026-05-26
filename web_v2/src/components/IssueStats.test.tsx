import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { IssueStats } from './IssueStats'

const statsFixture: HistoryStatsResponse = {
  schema: 'ai-caddie-history-stats-v1',
  dataMode: 'fixture',
  summary: {},
  time: {},
  scoring: {},
  courseDistribution: [],
  courses: [],
  holes: [],
  clubs: [],
  issues: [
    {
      issue: 'missing_shots',
      count: 2,
      refs: ['900002', '900003'],
      phase: 'Data Quality',
      source: 'deterministic',
      confidence: 'high',
    },
  ],
  dataQuality: [],
  drillDown: {},
}

describe('IssueStats', () => {
  it('renders issue counts and source refs', () => {
    render(<IssueStats data={statsFixture} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Issue Stats' })).toBeInTheDocument()
    expect(screen.getByText('missing_shots')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Data Quality')).toBeInTheDocument()
    expect(screen.getByText('deterministic')).toBeInTheDocument()
    expect(screen.getByText('high confidence')).toHaveClass('confidence-high')
    expect(screen.getByRole('button', { name: 'Open source 900002' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900003' })).toBeInTheDocument()
  })

  it('renders an empty state when no issue aggregates exist', () => {
    render(<IssueStats data={{ ...statsFixture, issues: [] }} />)

    expect(screen.getByText('No recurring issues yet')).toBeInTheDocument()
    expect(screen.getByText('Deterministic, AI-suggested, and manual issue tags will appear here after analysis.')).toBeInTheDocument()
  })
})

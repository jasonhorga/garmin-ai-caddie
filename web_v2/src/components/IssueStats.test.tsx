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
  records: {},
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
      coverage: { ready: 2, total: 3, pct: 66.7 },
    },
  ],
  diagnosis: {
    issueTrends: [
      {
        issue: 'three_putt',
        phase: 'Putting',
        direction: 'new',
        recentCount: 3,
        baselineCount: 0,
        deltaCount: 3,
        baselineRatePerRound: 0,
        recentRatePerRound: 1,
        estimatedStrokesLost: 3,
        actualToParImpact: 3,
        actualStrokesLost: 3,
        actualImpactCoverage: { ready: 3, total: 3, pct: 100 },
        recentAffectedHoleRefs: ['900004:7', '900005:7', '900006:7'],
        recentRefs: ['900004:7', '900005:7', '900006:7'],
        sourceRefs: ['900004:7', '900005:7', '900006:7'],
        coverage: { ready: 3, total: 3, pct: 100 },
        confidence: 'medium',
      },
    ],
    decisionAuditTrends: {
      classificationCounts: [
        {
          classification: 'execution',
          count: 2,
          pct: 66.7,
          sourceRefs: ['900001:7', '900002:8'],
          confidence: 'medium',
        },
      ],
      recentCostDrivers: [
        {
          classification: 'strategy',
          phase: 'tee_shot',
          direction: 'new',
          baselineCount: 0,
          recentCount: 1,
          baselineRatePerRound: 0,
          recentRatePerRound: 0.33,
          deltaCount: 1,
          estimatedStrokesLost: 1.2,
          recentRefs: ['900002:7'],
          sourceRefs: ['900002:7'],
          coverage: { ready: 1, total: 1, pct: 100 },
          confidence: 'low',
        },
      ],
    },
  },
  dataQuality: [],
  drillDown: {},
}

describe('IssueStats', () => {
  it('renders issue counts and source refs', () => {
    render(<IssueStats data={statsFixture} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Issue Stats' })).toBeInTheDocument()
    expect(screen.getByText('missing_shots')).toBeInTheDocument()
    expect(screen.getAllByText('2').length).toBeGreaterThan(0)
    expect(screen.getByText('Data Quality')).toBeInTheDocument()
    expect(screen.getByText('deterministic')).toBeInTheDocument()
    expect(screen.getByText('high confidence')).toHaveClass('confidence-high')
    expect(screen.getByText('coverage 2/3 66.7%')).toBeInTheDocument()
    expect(screen.getByText('Trend Diagnosis')).toBeInTheDocument()
    expect(screen.getByText('three_putt')).toBeInTheDocument()
    expect(screen.getAllByText('baseline 0').length).toBeGreaterThan(0)
    expect(screen.getByText('recent 3')).toBeInTheDocument()
    expect(screen.getByText('rate 0 -> 1/round')).toBeInTheDocument()
    expect(screen.getAllByText('medium confidence')[0]).toHaveClass('confidence-medium')
    expect(screen.getByText('coverage 3/3 100%')).toBeInTheDocument()
    expect(screen.getByText('+3')).toBeInTheDocument()
    expect(screen.getByText('3.0 est. strokes')).toBeInTheDocument()
    expect(screen.getByText('+3 actual to-par')).toBeInTheDocument()
    expect(screen.getByText('actual 3/3')).toBeInTheDocument()
    expect(screen.getByText('Caddie Audit')).toBeInTheDocument()
    expect(screen.getByText('execution')).toBeInTheDocument()
    expect(screen.getByText('66.7%')).toBeInTheDocument()
    expect(screen.getByText('strategy')).toBeInTheDocument()
    expect(screen.getByText('recent 1')).toBeInTheDocument()
    expect(screen.getByText('rate 0 -> 0.33/round')).toBeInTheDocument()
    expect(screen.getByText('low confidence')).toHaveClass('confidence-low')
    expect(screen.getByText('coverage 1/1 100%')).toBeInTheDocument()
    expect(screen.getByText('1.2 est. strokes')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900002' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900003' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900004:7' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900001:7' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 900002:7' })).toBeInTheDocument()
  })

  it('renders an empty state when no issue aggregates exist', () => {
    render(<IssueStats data={{ ...statsFixture, issues: [] }} />)

    expect(screen.getByText('No recurring issues yet')).toBeInTheDocument()
    expect(screen.getByText('Deterministic, AI-suggested, and manual issue tags will appear here after analysis.')).toBeInTheDocument()
  })
})

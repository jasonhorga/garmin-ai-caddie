import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { HistoryStatsResponse } from '../types'
import { DataQualityPage } from './DataQualityPage'

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
  issues: [],
  dataQuality: [
    {
      label: 'shots',
      state: 'partial',
      ready: 1,
      total: 3,
      refs: ['900003'],
      readyRefs: ['900001'],
      missingRefs: ['900002', '900003'],
      coverage: { ready: 1, total: 3, pct: 33.3 },
      confidence: 'low',
      reason: '1 of 3 scorecards have shot data',
      rowCount: 6,
    },
    { label: 'geometry', state: 'missing', ready: 0, total: 45, refs: ['900001:1'], missingRefs: ['900001:1'] },
    {
      label: 'reports',
      state: 'partial',
      ready: 1,
      total: 7,
      refs: ['900002', '900003'],
      readyRefs: ['900001'],
      missingRefs: ['900002', '900003', 'trend:recent_10', 'trend:year:2026'],
      roundReports: { ready: 1, total: 3, missingRefs: ['900002', '900003'] },
      trendReports: { ready: 0, total: 4, missingRefs: ['trend:recent_10', 'trend:year:2026'] },
    },
  ],
  drillDown: {},
}

describe('DataQualityPage', () => {
  it('renders data quality state and affected refs', () => {
    render(<DataQualityPage data={statsFixture} onSelectRef={vi.fn()} />)

    expect(screen.getByRole('heading', { name: '数据健康' })).toBeInTheDocument()
    expect(screen.getByText('shots')).toBeInTheDocument()
    expect(screen.getAllByText('部分')[0]).toHaveClass('quality-partial')
    expect(screen.getAllByText('1/3').length).toBeGreaterThan(0)
    expect(screen.getByText('coverage 1/3 33.3%')).toBeInTheDocument()
    expect(screen.getByText('low confidence')).toBeInTheDocument()
    expect(screen.getByText('1 of 3 scorecards have shot data')).toBeInTheDocument()
    expect(screen.getByText('行数 6')).toBeInTheDocument()
    expect(screen.getByText('缺失引用 2')).toBeInTheDocument()
    expect(screen.getByText('geometry')).toBeInTheDocument()
    expect(screen.getByText('缺失')).toHaveClass('quality-missing')
    expect(screen.getByText('0/45')).toBeInTheDocument()
    expect(screen.getByText('reports')).toBeInTheDocument()
    expect(screen.getByText('球局报告 1/3')).toBeInTheDocument()
    expect(screen.getByText('趋势报告 0/4')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Open source 900003' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Open source 900002' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Open source trend:recent_10' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'Open source 900001:1' }).length).toBeGreaterThan(0)
  })

  it('renders an empty state when no quality findings exist', () => {
    render(<DataQualityPage data={{ ...statsFixture, dataQuality: [] }} />)

    expect(screen.getByText('暂无数据健康发现')).toBeInTheDocument()
    expect(screen.getByText('载入历史、击球、几何、天气或报告数据后，这里会列出覆盖缺口。')).toBeInTheDocument()
  })
})

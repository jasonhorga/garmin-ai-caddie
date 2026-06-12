import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ReadinessPanel } from './ReadinessPanel'
import type { ReadinessResponse } from '../types'

const readinessFixture: ReadinessResponse = {
  schema: 'ai-caddie-readiness-v1',
  status: 'degraded',
  checks: [
    {
      label: 'service',
      state: 'ready',
      detail: 'API process is responding.',
      evidence: {},
    },
    {
      label: 'history',
      state: 'degraded',
      detail: 'No rounds are loaded for history review.',
      evidence: { dataMode: 'fixture', totalRounds: 0 },
    },
    {
      label: 'sync',
      state: 'degraded',
      detail: 'Garmin connector status is available.',
      evidence: { connectorState: 'reauth_required', scorecardCount: 12 },
    },
    {
      label: 'operations',
      state: 'ready',
      detail: 'Private trial run, smoke, backup, restore, deployment, and security docs are present.',
      evidence: {
        smokeCovers: ['readiness', 'reports'],
        lastBackup: {
          createdAt: '20260527T170000Z',
          sizeBytes: 2048,
          snapshot: '/Users/private/backups/ai-caddie-snapshot.tar.gz',
        },
      },
    },
  ],
}

describe('ReadinessPanel', () => {
  it('renders overall readiness and per-check evidence', () => {
    render(<ReadinessPanel readiness={readinessFixture} />)

    expect(screen.getByRole('heading', { name: '试运行就绪度' })).toBeInTheDocument()
    expect(screen.getByText('降级')).toHaveClass('readiness-degraded')
    expect(screen.getByText('service')).toBeInTheDocument()
    expect(screen.getByText('history')).toBeInTheDocument()
    expect(screen.getByText('dataMode: fixture')).toBeInTheDocument()
    expect(screen.getByText('scorecardCount: 12')).toBeInTheDocument()
    expect(screen.getByText('smokeCovers: readiness, reports')).toBeInTheDocument()
    expect(screen.getByText('lastBackup.createdAt: 20260527T170000Z')).toBeInTheDocument()
    expect(screen.getByText('lastBackup.sizeBytes: 2048')).toBeInTheDocument()
    expect(screen.queryByText(/Users\/private/)).not.toBeInTheDocument()
  })

  it('renders a compact unavailable state when readiness cannot load', () => {
    render(<ReadinessPanel readiness={null} error="GET /api/v2/readiness failed" />)

    expect(screen.getByRole('heading', { name: '试运行就绪度' })).toBeInTheDocument()
    const panel = screen.getByLabelText('试运行就绪度')
    expect(within(panel).getByText('不可用')).toHaveClass('readiness-error')
    expect(screen.getByText('GET /api/v2/readiness failed')).toBeInTheDocument()
  })
})

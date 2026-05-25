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
  ],
}

describe('ReadinessPanel', () => {
  it('renders overall readiness and per-check evidence', () => {
    render(<ReadinessPanel readiness={readinessFixture} />)

    expect(screen.getByRole('heading', { name: 'Private Trial Readiness' })).toBeInTheDocument()
    expect(screen.getByText('degraded')).toHaveClass('readiness-degraded')
    expect(screen.getByText('service')).toBeInTheDocument()
    expect(screen.getByText('history')).toBeInTheDocument()
    expect(screen.getByText('dataMode: fixture')).toBeInTheDocument()
    expect(screen.getByText('scorecardCount: 12')).toBeInTheDocument()
  })

  it('renders a compact unavailable state when readiness cannot load', () => {
    render(<ReadinessPanel readiness={null} error="GET /api/v2/readiness failed" />)

    expect(screen.getByRole('heading', { name: 'Private Trial Readiness' })).toBeInTheDocument()
    const panel = screen.getByLabelText('Private trial readiness')
    expect(within(panel).getByText('unavailable')).toHaveClass('readiness-error')
    expect(screen.getByText('GET /api/v2/readiness failed')).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SyncStatusPanel } from './SyncStatusPanel'
import type { SyncStatusResponse } from '../types'

const baseStatus: SyncStatusResponse = {
  schema: 'ai-caddie-sync-status-v2',
  connector: {
    name: 'garmin_cn_web_session',
    state: 'ready',
    detail: 'Local Garmin snapshots are available.',
    canSync: false,
    reauthRequired: false,
  },
  snapshot: {
    dataMode: 'local',
    scorecardCount: 12,
    shotFileCount: 8,
    summaryPresent: true,
    lastSuccessfulSyncAt: '2026-05-25T00:00:00Z',
  },
}

describe('SyncStatusPanel', () => {
  it('renders ready local snapshot counts', () => {
    render(<SyncStatusPanel status={baseStatus} />)

    expect(screen.getByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getByText('ready')).toBeInTheDocument()
    expect(screen.getByText('12 scorecards')).toBeInTheDocument()
    expect(screen.getByText('8 shot files')).toBeInTheDocument()
    expect(screen.getByText('local data')).toBeInTheDocument()
  })

  it('renders reauth required state', () => {
    render(
      <SyncStatusPanel
        status={{
          ...baseStatus,
          connector: {
            ...baseStatus.connector,
            state: 'reauth_required',
            detail: 'Garmin session expired.',
            reauthRequired: true,
          },
        }}
      />,
    )

    expect(screen.getByText('reauth required')).toBeInTheDocument()
    expect(screen.getByText('Garmin session expired.')).toBeInTheDocument()
  })
})

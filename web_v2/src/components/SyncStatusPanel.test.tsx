import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

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
  lastRun: null,
}

describe('SyncStatusPanel', () => {
  it('renders ready local snapshot counts', () => {
    render(<SyncStatusPanel status={baseStatus} onSync={vi.fn()} syncState="idle" />)

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
        onSync={vi.fn()}
        syncState="idle"
      />,
    )

    expect(screen.getByText('reauth required')).toBeInTheDocument()
    expect(screen.getByText('Garmin session expired.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sync now/i })).toBeDisabled()
  })

  it('runs sync from the button when connector can sync', async () => {
    const user = userEvent.setup()
    const onSync = vi.fn()

    render(<SyncStatusPanel status={{ ...baseStatus, connector: { ...baseStatus.connector, canSync: true } }} onSync={onSync} syncState="idle" />)

    await user.click(screen.getByRole('button', { name: /sync now/i }))

    expect(onSync).toHaveBeenCalledTimes(1)
  })

  it('shows sync running state', () => {
    render(<SyncStatusPanel status={{ ...baseStatus, connector: { ...baseStatus.connector, canSync: true } }} onSync={vi.fn()} syncState="running" />)

    expect(screen.getByRole('button', { name: /syncing/i })).toBeDisabled()
  })
})

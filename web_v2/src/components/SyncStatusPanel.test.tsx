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
  connectors: [
    {
      name: 'garmin_cn_web_session',
      state: 'ready',
      detail: 'Local Garmin snapshots are available.',
      canSync: false,
      reauthRequired: false,
    },
    {
      name: 'garmin_oauth_feasibility',
      state: 'not_available',
      detail: 'Official Garmin OAuth golf scorecard access is not proven.',
      canSync: false,
      reauthRequired: false,
      track: 'official_oauth',
      feasibilityQuestions: ['Can official OAuth access golf scorecards?'],
      capabilities: [
        {
          key: 'scorecards',
          label: 'Golf scorecards',
          state: 'unproven',
          evidence: 'OAuth access to Garmin golf scorecards is not documented for this build.',
          nextStep: 'Verify whether the official OAuth program can read scorecard records.',
          canReplaceCnConnector: false,
          migrationValue: true,
        },
        {
          key: 'identity',
          label: 'Identity',
          state: 'possible',
          evidence: 'OAuth can still provide an account migration path if golf data is unavailable.',
          nextStep: 'Keep the connector interface replaceable.',
          canReplaceCnConnector: false,
          migrationValue: true,
        },
      ],
      probe: {
        schema: 'ai-caddie-garmin-oauth-probe-v1',
        state: 'not_configured',
        liveProbeAllowed: false,
        configured: {
          clientId: false,
          clientCredential: false,
          redirectUri: false,
          consentEndpoint: false,
          exchangeEndpoint: false,
          scopes: false,
        },
        missing: ['client_id', 'redirect_uri', 'consent_endpoint', 'exchange_endpoint', 'scopes'],
        consentRequest: {
          method: 'GET',
          endpointConfigured: false,
          parameterKeys: ['response_type', 'client_id', 'redirect_uri', 'scope', 'state'],
          redactedPreview: null,
        },
        manualSteps: ['Register a Garmin OAuth client and redirect URI through the official developer path.'],
      },
    },
  ],
  snapshot: {
    dataMode: 'local',
    scorecardCount: 12,
    shotFileCount: 8,
    summaryPresent: true,
    lastSuccessfulSyncAt: '2026-05-25T00:00:00Z',
  },
  lastRun: {
    state: 'ready',
    detail: 'Garmin CN sync completed.',
    snapshotId: 'snap_123',
    errorCode: null,
    updatedAt: '2026-05-25T00:10:00Z',
  },
}

describe('SyncStatusPanel', () => {
  it('renders ready local snapshot counts', () => {
    render(
      <SyncStatusPanel
        status={{ ...baseStatus, connector: { ...baseStatus.connector, nextAction: 'review_history' } }}
        onSync={vi.fn()}
        syncState="idle"
      />,
    )

    expect(screen.getByText('Garmin CN')).toBeInTheDocument()
    expect(screen.getAllByText('ready').length).toBeGreaterThan(0)
    expect(screen.getByText('Review history')).toHaveClass('sync-next-action')
    expect(screen.getByText('12 scorecards')).toBeInTheDocument()
    expect(screen.getByText('8 shot files')).toBeInTheDocument()
    expect(screen.getByText('local data')).toBeInTheDocument()
    expect(screen.getByText('Last data update')).toBeInTheDocument()
    expect(screen.getByText('2026-05-25T00:00:00Z')).toBeInTheDocument()
    expect(screen.getByText('Last run')).toBeInTheDocument()
    expect(screen.getByText('snapshot snap_123')).toBeInTheDocument()
    expect(screen.getByText('Official OAuth')).toBeInTheDocument()
    expect(screen.getByText('not available')).toHaveClass('quality-missing')
    expect(screen.getByText('Can official OAuth access golf scorecards?')).toBeInTheDocument()
    expect(screen.getByText('Golf scorecards')).toBeInTheDocument()
    expect(screen.getByText('unproven')).toBeInTheDocument()
    expect(screen.getByText('Identity')).toBeInTheDocument()
    expect(screen.getByText('possible')).toBeInTheDocument()
    expect(screen.getByLabelText('OAuth probe readiness')).toHaveTextContent('OAuth probe')
    expect(screen.getByLabelText('OAuth probe readiness')).toHaveTextContent('not configured')
    expect(screen.getByLabelText('OAuth probe readiness')).toHaveTextContent('client_id, redirect_uri, consent_endpoint, exchange_endpoint, scopes')
    expect(screen.getByLabelText('OAuth probe readiness')).toHaveTextContent('dry-run only')
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
    expect(screen.getByText('Reauthenticate the Garmin CN session before running another sync.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sync now/i })).toBeDisabled()
  })

  it('runs sync from the button when connector can sync', async () => {
    const user = userEvent.setup()
    const onSync = vi.fn()

    render(<SyncStatusPanel status={{ ...baseStatus, connector: { ...baseStatus.connector, canSync: true } }} onSync={onSync} syncState="idle" />)

    await user.click(screen.getByRole('button', { name: /sync now/i }))

    expect(onSync).toHaveBeenCalledTimes(1)
  })

  it('passes an entered admin token to protected sync actions', async () => {
    const user = userEvent.setup()
    const onSync = vi.fn()

    render(<SyncStatusPanel status={{ ...baseStatus, connector: { ...baseStatus.connector, canSync: true } }} onSync={onSync} syncState="idle" />)

    await user.type(screen.getByLabelText('Admin token'), 'admin-secret')
    await user.click(screen.getByRole('button', { name: /sync now/i }))

    expect(onSync).toHaveBeenCalledWith('admin-secret')
  })

  it('shows sync running state', () => {
    render(<SyncStatusPanel status={{ ...baseStatus, connector: { ...baseStatus.connector, canSync: true } }} onSync={vi.fn()} syncState="running" />)

    expect(screen.getByRole('button', { name: /syncing/i })).toBeDisabled()
  })

  it('submits manually pasted Garmin session material', async () => {
    const user = userEvent.setup()
    const onSaveSession = vi.fn()

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
        onSaveSession={onSaveSession}
      />,
    )

    await user.type(screen.getByLabelText('Web session header'), 'Cookie: JWT_WEB=abc123')
    await user.type(screen.getByLabelText('Anti-forgery value'), 'connect-csrf-token: csrf-secret-value')
    await user.click(screen.getByRole('button', { name: 'Save session' }))

    expect(onSaveSession).toHaveBeenCalledWith({
      webSessionHeader: 'Cookie: JWT_WEB=abc123',
      antiForgeryValue: 'connect-csrf-token: csrf-secret-value',
      source: 'web_secure_paste',
    })
  })

  it('passes an entered admin token when saving Garmin session material', async () => {
    const user = userEvent.setup()
    const onSaveSession = vi.fn()

    render(<SyncStatusPanel status={baseStatus} onSaveSession={onSaveSession} />)

    await user.type(screen.getByLabelText('Admin token'), 'admin-secret')
    await user.type(screen.getByLabelText('Web session header'), 'Cookie: JWT_WEB=abc123')
    await user.type(screen.getByLabelText('Anti-forgery value'), 'connect-csrf-token: csrf-secret-value')
    await user.click(screen.getByRole('button', { name: 'Save session' }))

    expect(onSaveSession).toHaveBeenCalledWith(
      {
        webSessionHeader: 'Cookie: JWT_WEB=abc123',
        antiForgeryValue: 'connect-csrf-token: csrf-secret-value',
        source: 'web_secure_paste',
      },
      'admin-secret',
    )
  })

  it('clears pasted Garmin session material after a successful save', async () => {
    const user = userEvent.setup()
    const onSaveSession = vi.fn()
    const { rerender } = render(<SyncStatusPanel status={baseStatus} onSaveSession={onSaveSession} sessionSaveState="idle" />)

    await user.type(screen.getByLabelText('Web session header'), 'Cookie: JWT_WEB=abc123')
    await user.type(screen.getByLabelText('Anti-forgery value'), 'connect-csrf-token: csrf-secret-value')
    await user.click(screen.getByRole('button', { name: 'Save session' }))

    expect(onSaveSession).toHaveBeenCalledTimes(1)

    rerender(<SyncStatusPanel status={baseStatus} onSaveSession={onSaveSession} sessionSaveState="saved" />)

    expect(screen.getByLabelText('Web session header')).toHaveValue('')
    expect(screen.getByLabelText('Anti-forgery value')).toHaveValue('')
  })

  it('keeps pasted Garmin session material after a failed save', async () => {
    const user = userEvent.setup()
    const onSaveSession = vi.fn().mockRejectedValue(new Error('invalid session'))

    render(<SyncStatusPanel status={baseStatus} onSaveSession={onSaveSession} sessionSaveState="idle" />)

    await user.type(screen.getByLabelText('Web session header'), 'Cookie: JWT_WEB=abc123')
    await user.type(screen.getByLabelText('Anti-forgery value'), 'connect-csrf-token: csrf-secret-value')
    await user.click(screen.getByRole('button', { name: 'Save session' }))

    expect(onSaveSession).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('Web session header')).toHaveValue('Cookie: JWT_WEB=abc123')
    expect(screen.getByLabelText('Anti-forgery value')).toHaveValue('connect-csrf-token: csrf-secret-value')
  })
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SyncStatusPanel } from './SyncStatusPanel'
import type { ConnectorProbeStatus, SyncStatusResponse } from '../types'

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
        schema: 'ai-caddie-garmin-oauth-probe-v2',
        state: 'not_configured',
        liveProbeAllowed: false,
        configured: {
          clientId: false,
          clientCredential: false,
          redirectUri: false,
          consentEndpoint: true,
          exchangeEndpoint: true,
          apiBase: true,
          requestedScopes: false,
          authorizationCode: false,
          codeVerifier: false,
        },
        missing: ['client_id', 'redirect_uri'],
        consentRequest: {
          method: 'GET',
          endpoint: 'https://connect.garmin.com/oauth2Confirm',
          endpointConfigured: true,
          parameterKeys: ['response_type', 'client_id', 'redirect_uri', 'state', 'code_challenge', 'code_challenge_method'],
          redactedPreview:
            'https://connect.garmin.com/oauth2Confirm?response_type=code&client_id=<configured>&redirect_uri=<configured>&state=<generated>&code_challenge=<generated>&code_challenge_method=S256',
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
    expect(screen.getAllByText('就绪').length).toBeGreaterThan(0)
    expect(screen.getByText('查看历史')).toHaveClass('sync-next-action')
    expect(screen.getByText('12 张记分卡')).toBeInTheDocument()
    expect(screen.getByText('8 个击球文件')).toBeInTheDocument()
    expect(screen.getByText('本地数据')).toBeInTheDocument()
    expect(screen.getByText('最近数据更新')).toBeInTheDocument()
    expect(screen.getByText('2026-05-25T00:00:00Z')).toBeInTheDocument()
    expect(screen.getByText('最近运行')).toBeInTheDocument()
    expect(screen.getByText('快照 snap_123')).toBeInTheDocument()
    expect(screen.getByText('官方 OAuth')).toBeInTheDocument()
    expect(screen.getByText('不可用')).toHaveClass('quality-missing')
    expect(screen.getByText('Can official OAuth access golf scorecards?')).toBeInTheDocument()
    // capability label + nextStep map by key through the shared OAuth dictionary
    expect(screen.getByText('高尔夫记分卡')).toBeInTheDocument()
    expect(screen.getByText('验证官方授权能否读取高尔夫记分卡。')).toBeInTheDocument()
    expect(screen.getByText('未验证')).toBeInTheDocument()
    expect(screen.getByText('身份')).toBeInTheDocument()
    expect(screen.getByText('可行')).toBeInTheDocument()
    expect(screen.getByLabelText('OAuth 探测就绪度')).toHaveTextContent('OAuth 探测')
    expect(screen.getByLabelText('OAuth 探测就绪度')).toHaveTextContent('未配置')
    expect(screen.getByLabelText('OAuth 探测就绪度')).toHaveTextContent('client_id, redirect_uri')
    expect(screen.getByLabelText('OAuth 探测就绪度')).toHaveTextContent('仅试运行')
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

    expect(screen.getByText('需重新登录')).toBeInTheDocument()
    expect(screen.getByText('Garmin session expired.')).toBeInTheDocument()
    expect(screen.getByText('请先重新登录 Garmin CN 会话，再运行同步。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '立即同步' })).toBeDisabled()
  })

  it('maps the real expired-session detail sentence to zh', () => {
    render(
      <SyncStatusPanel
        status={{
          ...baseStatus,
          connector: {
            ...baseStatus.connector,
            state: 'reauth_required',
            detail: 'Garmin CN session expired or missing. Reconnect Garmin and retry.',
            reauthRequired: true,
          },
        }}
        onSync={vi.fn()}
        syncState="idle"
      />,
    )

    expect(screen.getByText('Garmin CN 会话已过期或缺失。请重新登录 Garmin 后再同步。')).toBeInTheDocument()
    expect(screen.queryByText('Garmin CN session expired or missing. Reconnect Garmin and retry.')).not.toBeInTheDocument()
  })

  it('runs sync from the button when connector can sync', async () => {
    const user = userEvent.setup()
    const onSync = vi.fn()

    render(<SyncStatusPanel status={{ ...baseStatus, connector: { ...baseStatus.connector, canSync: true } }} onSync={onSync} syncState="idle" />)

    await user.click(screen.getByRole('button', { name: '立即同步' }))

    expect(onSync).toHaveBeenCalledTimes(1)
  })

  it('shows sync running state', () => {
    render(<SyncStatusPanel status={{ ...baseStatus, connector: { ...baseStatus.connector, canSync: true } }} onSync={vi.fn()} syncState="running" />)

    expect(screen.getByRole('button', { name: '同步中' })).toBeDisabled()
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

    await user.type(screen.getByLabelText('网页会话头'), 'Cookie: JWT_WEB=abc123')
    await user.type(screen.getByLabelText('防伪令牌'), 'connect-csrf-token: csrf-secret-value')
    await user.click(screen.getByRole('button', { name: '保存会话' }))

    expect(onSaveSession).toHaveBeenCalledWith({
      webSessionHeader: 'Cookie: JWT_WEB=abc123',
      antiForgeryValue: 'connect-csrf-token: csrf-secret-value',
      source: 'web_secure_paste',
    })
  })

  it('clears pasted Garmin session material after a successful save', async () => {
    const user = userEvent.setup()
    const onSaveSession = vi.fn()
    const { rerender } = render(<SyncStatusPanel status={baseStatus} onSaveSession={onSaveSession} sessionSaveState="idle" />)

    await user.type(screen.getByLabelText('网页会话头'), 'Cookie: JWT_WEB=abc123')
    await user.type(screen.getByLabelText('防伪令牌'), 'connect-csrf-token: csrf-secret-value')
    await user.click(screen.getByRole('button', { name: '保存会话' }))

    expect(onSaveSession).toHaveBeenCalledTimes(1)

    rerender(<SyncStatusPanel status={baseStatus} onSaveSession={onSaveSession} sessionSaveState="saved" />)

    expect(screen.getByLabelText('网页会话头')).toHaveValue('')
    expect(screen.getByLabelText('防伪令牌')).toHaveValue('')
  })

  it('keeps pasted Garmin session material after a failed save', async () => {
    const user = userEvent.setup()
    const onSaveSession = vi.fn().mockRejectedValue(new Error('invalid session'))

    render(<SyncStatusPanel status={baseStatus} onSaveSession={onSaveSession} sessionSaveState="idle" />)

    await user.type(screen.getByLabelText('网页会话头'), 'Cookie: JWT_WEB=abc123')
    await user.type(screen.getByLabelText('防伪令牌'), 'connect-csrf-token: csrf-secret-value')
    await user.click(screen.getByRole('button', { name: '保存会话' }))

    expect(onSaveSession).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('网页会话头')).toHaveValue('Cookie: JWT_WEB=abc123')
    expect(screen.getByLabelText('防伪令牌')).toHaveValue('connect-csrf-token: csrf-secret-value')
  })

  it('renders without crash when probe has no missing array (real CN payload shape)', () => {
    // Real /api/v2/sync/status payloads for the CN connector omit `missing`
    // entirely. Fixtures always include it, so this gap is normally invisible.
    const probeWithoutMissing = {
      schema: 'ai-caddie-garmin-oauth-probe-v2',
      state: 'not_configured',
      liveProbeAllowed: false,
    } as unknown as ConnectorProbeStatus

    const statusWithCnProbe: SyncStatusResponse = {
      ...baseStatus,
      connectors: [
        {
          ...baseStatus.connectors![1],
          probe: probeWithoutMissing,
        },
      ],
    }

    render(<SyncStatusPanel status={statusWithCnProbe} onSync={vi.fn()} syncState="idle" />)

    expect(screen.getByText('同意请求已配置(参数已脱敏)。')).toBeInTheDocument()
  })

  it('renders the raw state string when probe state is not in the label map', () => {
    const probeUnknownState = {
      schema: 'ai-caddie-garmin-oauth-probe-v2',
      state: 'awaiting_redirect',
      liveProbeAllowed: true,
    } as unknown as ConnectorProbeStatus

    const statusWithUnknownProbeState: SyncStatusResponse = {
      ...baseStatus,
      connectors: [
        {
          ...baseStatus.connectors![1],
          probe: probeUnknownState,
        },
      ],
    }

    render(<SyncStatusPanel status={statusWithUnknownProbeState} onSync={vi.fn()} syncState="idle" />)

    expect(screen.getByText('awaiting_redirect')).toBeInTheDocument()
  })
})

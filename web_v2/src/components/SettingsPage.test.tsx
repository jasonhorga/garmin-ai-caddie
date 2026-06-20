import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ProductSettingsResponse } from '../types'
import { SettingsPage } from './SettingsPage'

const productSettings: ProductSettingsResponse = {
  schema: 'ai-caddie-product-settings-v1',
  dataSources: [
    {
      id: 'garmin_cn_web_session',
      label: 'Garmin CN Web Session',
      track: 'primary',
      state: 'available',
      credentialPolicy: 'session_material_only',
      capabilities: ['scorecards', 'shot_rows'],
    },
    {
      id: 'garmin_oauth',
      label: 'Official Garmin OAuth',
      track: 'feasibility',
      state: 'not_syncable',
      credentialPolicy: 'pkce_only_if_golf_data_is_proven',
      capabilities: ['identity_feasibility'],
      capabilityMatrix: [
        {
          key: 'scorecards',
          label: 'Golf scorecards',
          state: 'unproven',
          evidence: 'OAuth scorecard access is not proven.',
          nextStep: 'Verify scorecard access.',
          canReplaceCnConnector: false,
          migrationValue: true,
        },
        {
          key: 'identity',
          label: 'Identity',
          state: 'possible',
          evidence: 'OAuth identity may be useful later.',
          nextStep: 'Keep connector interface replaceable.',
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
        tokenExchange: {
          method: 'POST',
          endpoint: 'https://connectapi.garmin.com/di-oauth2-service/oauth/token',
          ready: false,
          missing: ['client_id', 'redirect_uri', 'client_credential', 'authorization_code', 'code_verifier'],
          parameterKeys: ['grant_type', 'client_id', 'client_credential', 'authorization_code', 'code_verifier', 'redirect_uri'],
        },
        resourceProbe: {
          userIdEndpoint: 'https://apis.garmin.com/wellness-api/rest/user/id',
          permissionsEndpoint: 'https://apis.garmin.com/wellness-api/rest/user/permissions',
          checks: ['user_id', 'permissions', 'golf_data_replacement_gap'],
        },
        manualSteps: [
          'Register a Garmin OAuth client and redirect URI through the official developer path.',
          'Generate a PKCE consent URL locally and keep the generated code verifier private.',
          'Exchange the one-time authorization code only when live probing is explicitly enabled.',
        ],
      },
    },
  ],
  aiProviders: {
    activeProvider: 'gemini_api_key',
    factBindingRequired: true,
    providers: [
      { id: 'static', label: 'Static', state: 'ready' },
      { id: 'gemini_api_key', label: 'Gemini API', state: 'configured' },
      {
        id: 'gemini_cli_oauth',
        label: 'Gemini CLI OAuth',
        state: 'configured',
        credentialPolicy: 'oauth_token_cache_with_refresh_client_credential',
        refreshRequiresClientCredential: true,
        productionUse: 'internal_only',
      },
    ],
  },
  liveApps: {
    ios: { state: 'contract_ready', offlineFirst: true, captures: ['gps', 'score', 'club', 'putt', 'penalty', 'note', 'photo', 'video'] },
    watch: { state: 'contract_ready', requiresIphoneBridge: true, inputs: ['club', 'distance', 'score', 'putt', 'penalty'] },
    vision: { state: 'bounded_context', confirmationRequired: true },
  },
  privacy: {
    noGarminPasswordStorage: true,
    adminProtectedWrites: true,
    mediaRedaction: true,
    localSnapshotsSurviveReauth: true,
    secretFreeStatusResponses: true,
  },
  endpoints: {
    syncStatus: '/api/v2/sync/status',
    caddieDecision: '/api/v2/caddie/decision',
    reports: '/api/v2/reports',
  },
}

describe('SettingsPage', () => {
  it('renders product control groups and navigates to owned surfaces', async () => {
    const onNavigate = vi.fn()
    const user = userEvent.setup()
    render(<SettingsPage onNavigate={onNavigate} />)

    expect(screen.getByRole('heading', { name: '后端配置' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '数据源' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI 引擎' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '实战应用' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '隐私与留存' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '人工订正' })).toBeInTheDocument()

    const dataSources = screen.getByLabelText('数据源配置')
    expect(within(dataSources).getByText('CN 网页会话')).toHaveClass('setting-primary')
    expect(within(dataSources).getByText('OAuth 可行性')).toHaveClass('setting-secondary')
    expect(within(dataSources).getByText('不存储 Garmin 密码')).toBeInTheDocument()

    const aiProviders = screen.getByLabelText('AI 引擎配置')
    expect(within(aiProviders).getByText('静态规则')).toBeInTheDocument()
    expect(within(aiProviders).getByText('NVIDIA NIM')).toBeInTheDocument()
    expect(within(aiProviders).getByText('Gemini API')).toBeInTheDocument()
    expect(within(aiProviders).getByText('Gemini CLI OAuth')).toBeInTheDocument()
    expect(within(aiProviders).getByText('仅本地开发')).toBeInTheDocument()
    expect(within(aiProviders).getByRole('checkbox', { name: '必须绑定事实' })).toBeChecked()

    const liveApps = screen.getByLabelText('实战应用配置')
    expect(within(liveApps).getByText('iOS 离线包')).toBeInTheDocument()
    expect(within(liveApps).getByText('手表桥接')).toBeInTheDocument()
    expect(within(liveApps).getByText('照片/视频上下文')).toBeInTheDocument()

    const privacy = screen.getByLabelText('隐私配置')
    expect(within(privacy).getByRole('checkbox', { name: '管理员保护写入' })).toBeChecked()
    expect(within(privacy).getByRole('checkbox', { name: '媒体脱敏' })).toBeChecked()
    expect(within(privacy).getByRole('checkbox', { name: '重新登录保留本地快照' })).toBeChecked()

    await user.click(screen.getByRole('button', { name: '打开同步控制' }))
    await user.click(screen.getByRole('button', { name: '打开实战准备' }))
    await user.click(screen.getByRole('button', { name: '打开报告控制' }))
    await user.click(screen.getByRole('button', { name: '打开订正' }))

    expect(onNavigate).toHaveBeenNthCalledWith(1, 'sync-quality')
    expect(onNavigate).toHaveBeenNthCalledWith(2, 'sync-quality')
    expect(onNavigate).toHaveBeenNthCalledWith(3, 'reports')
    expect(onNavigate).toHaveBeenNthCalledWith(4, 'corrections')
  })

  it('renders API-backed settings state when provided', () => {
    render(<SettingsPage onNavigate={vi.fn()} settings={productSettings} />)

    const dataSources = screen.getByLabelText('数据源配置')
    expect(within(dataSources).getByText('可用')).toHaveClass('setting-primary')
    expect(within(dataSources).getByText('不可同步')).toHaveClass('setting-secondary')
    const oauthProbe = screen.getByLabelText('OAuth 可行性探测')
    expect(within(oauthProbe).getByText('未配置')).toBeInTheDocument()
    expect(within(oauthProbe).getByText('缺失 client_id, redirect_uri')).toBeInTheDocument()
    expect(within(oauthProbe).getByText('授权码交换')).toBeInTheDocument()
    expect(within(oauthProbe).getByText('缺失 client_id, redirect_uri, client_credential, authorization_code, code_verifier')).toBeInTheDocument()
    expect(within(oauthProbe).getByText('user_id, permissions, golf_data_replacement_gap')).toBeInTheDocument()
    expect(within(screen.getByLabelText('OAuth 能力矩阵')).getByText('高尔夫记分卡: 未验证')).toBeInTheDocument()
    expect(within(screen.getByLabelText('OAuth 能力矩阵')).getByText('身份: 可行')).toBeInTheDocument()
    expect(within(oauthProbe).getByText('Register a Garmin OAuth client and redirect URI through the official developer path.')).toBeInTheDocument()

    const aiProviders = screen.getByLabelText('AI 引擎配置')
    expect(within(aiProviders).getByText('当前:Gemini API')).toHaveClass('setting-primary')
    expect(within(aiProviders).getByText('已配置')).toHaveClass('setting-primary')
    expect(within(aiProviders).getByText('令牌缓存 + 刷新需客户端凭据')).toBeInTheDocument()

    const liveApps = screen.getByLabelText('实战应用配置')
    expect(within(liveApps).getByText('iOS 契约就绪')).toBeInTheDocument()
    expect(within(liveApps).getByText('Watch 契约就绪')).toBeInTheDocument()
    expect(within(liveApps).getByText('GPS, score, club, putt, penalty, note, photo, video')).toBeInTheDocument()
    expect(within(liveApps).getByText('club, distance, score, putt, penalty')).toBeInTheDocument()

    const privacy = screen.getByLabelText('隐私配置')
    expect(within(privacy).getByRole('checkbox', { name: '状态响应不含密钥' })).toBeChecked()
  })
})

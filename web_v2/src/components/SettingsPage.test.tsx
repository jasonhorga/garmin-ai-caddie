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
        missing: ['client_id', 'redirect_uri'],
        consentRequest: {
          method: 'GET',
          endpointConfigured: false,
          parameterKeys: ['response_type', 'client_id', 'redirect_uri', 'scope', 'state'],
          redactedPreview: null,
        },
        manualSteps: [
          'Register a Garmin OAuth client and redirect URI through the official developer path.',
          'Run a manual consent probe with a private test account.',
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
      { id: 'gemini_cli_oauth', label: 'Gemini CLI OAuth', state: 'configured' },
    ],
  },
  liveApps: {
    ios: { state: 'contract_ready', offlineFirst: true, captures: ['gps', 'score', 'club', 'putt', 'penalty', 'note', 'photo', 'video'] },
    watch: { state: 'contract_ready', requiresIphoneBridge: true, inputs: ['club', 'score', 'putt', 'penalty'] },
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

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Data Sources' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'AI Providers' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Live Apps' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Privacy & Retention' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Manual Corrections' })).toBeInTheDocument()

    const dataSources = screen.getByLabelText('Data source settings')
    expect(within(dataSources).getByText('CN Web Session')).toHaveClass('setting-primary')
    expect(within(dataSources).getByText('OAuth feasibility')).toHaveClass('setting-secondary')
    expect(within(dataSources).getByText('No Garmin password storage')).toBeInTheDocument()

    const aiProviders = screen.getByLabelText('AI provider settings')
    expect(within(aiProviders).getByText('Static')).toBeInTheDocument()
    expect(within(aiProviders).getByText('NVIDIA NIM')).toBeInTheDocument()
    expect(within(aiProviders).getByText('Gemini API')).toBeInTheDocument()
    expect(within(aiProviders).getByText('Gemini CLI OAuth')).toBeInTheDocument()
    expect(within(aiProviders).getByRole('checkbox', { name: 'Fact binding required' })).toBeChecked()

    const liveApps = screen.getByLabelText('Live app settings')
    expect(within(liveApps).getByText('iOS offline package')).toBeInTheDocument()
    expect(within(liveApps).getByText('Watch bridge')).toBeInTheDocument()
    expect(within(liveApps).getByText('Photo / video context')).toBeInTheDocument()

    const privacy = screen.getByLabelText('Privacy settings')
    expect(within(privacy).getByRole('checkbox', { name: 'Admin protected writes' })).toBeChecked()
    expect(within(privacy).getByRole('checkbox', { name: 'Media redaction' })).toBeChecked()
    expect(within(privacy).getByRole('checkbox', { name: 'Local snapshots survive reauth' })).toBeChecked()

    await user.click(screen.getByRole('button', { name: 'Open sync controls' }))
    await user.click(screen.getByRole('button', { name: 'Open caddie controls' }))
    await user.click(screen.getByRole('button', { name: 'Open report controls' }))
    await user.click(screen.getByRole('button', { name: 'Open corrections' }))

    expect(onNavigate).toHaveBeenNthCalledWith(1, 'sync-quality')
    expect(onNavigate).toHaveBeenNthCalledWith(2, 'caddie')
    expect(onNavigate).toHaveBeenNthCalledWith(3, 'reports')
    expect(onNavigate).toHaveBeenNthCalledWith(4, 'corrections')
  })

  it('renders API-backed settings state when provided', () => {
    render(<SettingsPage onNavigate={vi.fn()} settings={productSettings} />)

    const dataSources = screen.getByLabelText('Data source settings')
    expect(within(dataSources).getByText('available')).toHaveClass('setting-primary')
    expect(within(dataSources).getByText('not_syncable')).toHaveClass('setting-secondary')
    const oauthProbe = screen.getByLabelText('OAuth feasibility probe')
    expect(within(oauthProbe).getByText('not configured')).toBeInTheDocument()
    expect(within(oauthProbe).getByText('Missing client_id, redirect_uri')).toBeInTheDocument()
    expect(within(screen.getByLabelText('OAuth capability matrix')).getByText('Golf scorecards: unproven')).toBeInTheDocument()
    expect(within(screen.getByLabelText('OAuth capability matrix')).getByText('Identity: possible')).toBeInTheDocument()
    expect(within(oauthProbe).getByText('Register a Garmin OAuth client and redirect URI through the official developer path.')).toBeInTheDocument()

    const aiProviders = screen.getByLabelText('AI provider settings')
    expect(within(aiProviders).getByText('active: Gemini API')).toHaveClass('setting-primary')
    expect(within(aiProviders).getByText('configured')).toHaveClass('setting-primary')

    const liveApps = screen.getByLabelText('Live app settings')
    expect(within(liveApps).getByText('iOS contract_ready')).toBeInTheDocument()
    expect(within(liveApps).getByText('Watch contract_ready')).toBeInTheDocument()
    expect(within(liveApps).getByText('GPS, score, club, putt, penalty, note, photo, video')).toBeInTheDocument()
    expect(within(liveApps).getByText('club, score, putt, penalty')).toBeInTheDocument()

    const privacy = screen.getByLabelText('Privacy settings')
    expect(within(privacy).getByRole('checkbox', { name: 'Secret-free status responses' })).toBeChecked()
  })
})

import type { ProductPage } from './ProductNav'
import type { ProductSettingsResponse } from '../types'

interface SettingsPageProps {
  onNavigate: (page: ProductPage) => void
  settings?: ProductSettingsResponse | null
  settingsError?: string | null
}

export function SettingsPage({ onNavigate, settings, settingsError }: SettingsPageProps) {
  const dataSources = Array.isArray(settings?.dataSources) ? settings.dataSources : []
  const providers = Array.isArray(settings?.aiProviders?.providers) ? settings.aiProviders.providers : []
  const cnSession = dataSources.find((source) => asString(source.id) === 'garmin_cn_web_session')
  const oauth = dataSources.find((source) => asString(source.id) === 'garmin_oauth')
  const oauthProbe = asRecord(oauth?.probe)
  const oauthExchange = asRecord(oauthProbe.tokenExchange)
  const oauthResourceProbe = asRecord(oauthProbe.resourceProbe)
  const oauthMissing = asStringList(oauthProbe.missing)
  const oauthExchangeMissing = asStringList(oauthExchange.missing)
  const oauthResourceChecks = asStringList(oauthResourceProbe.checks)
  const oauthCapabilities = asRecords(oauth?.capabilityMatrix).slice(0, 3)
  const oauthSteps = asStringList(oauthProbe.manualSteps).slice(0, 3)
  const activeProvider = providers.find((provider) => asString(provider.id) === settings?.aiProviders?.activeProvider)
  const ios = asRecord(settings?.liveApps?.ios)
  const watch = asRecord(settings?.liveApps?.watch)
  const privacy = asRecord(settings?.privacy)
  const iosCaptures = formatSettingList(ios.captures, ['gps', 'club', 'score'])
  const watchInputs = formatSettingList(watch.inputs, ['club', 'distance', 'score', 'putt', 'penalty'])

  return (
    <section className="settings-page" aria-label="Settings workspace">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Control Surface</p>
          <h1>Settings</h1>
          <p>Connector, provider, live app, privacy, and correction controls.</p>
        </div>
        {settingsError ? <span className="semantic-chip quality-missing">{settingsError}</span> : null}
      </div>

      <div className="settings-grid">
        <article className="settings-item" aria-label="Data source settings">
          <div className="settings-item-main">
            <h2>Data Sources</h2>
            <div className="setting-chip-row">
              <span className="setting-chip setting-primary">CN Web Session</span>
              <span className="setting-chip setting-secondary">OAuth feasibility</span>
              <span className="setting-chip">Local snapshots</span>
              {cnSession ? <span className="setting-chip setting-primary">{asString(cnSession.state) ?? 'unknown'}</span> : null}
              {oauth ? <span className="setting-chip setting-secondary">{asString(oauth.state) ?? 'unknown'}</span> : null}
            </div>
            <div className="settings-fact-grid">
              <span>Scorecards</span>
              <b>session connector</b>
              <span>Shot rows</span>
              <b>normalized snapshot</b>
              <span>Geometry</span>
              <b>prodgeometry</b>
              <span>Credential policy</span>
              <b>No Garmin password storage</b>
            </div>
            {oauthProbe.schema ? (
              <div className="settings-oauth-probe" aria-label="OAuth feasibility probe">
                <div>
                  <span>OAuth probe</span>
                  <b>{asString(oauthProbe.state) === 'ready_for_manual_consent' ? 'ready for manual consent' : 'not configured'}</b>
                </div>
                {oauthMissing.length ? <p>Missing {oauthMissing.join(', ')}</p> : <p>Consent request uses redacted configured parameters.</p>}
                <div className="settings-oauth-probe-grid">
                  <span>Code exchange</span>
                  <b>{asBoolean(oauthExchange.ready, false) ? 'ready' : oauthExchangeMissing.length ? `missing ${oauthExchangeMissing.join(', ')}` : 'not ready'}</b>
                  <span>Resource checks</span>
                  <b>{oauthResourceChecks.length ? oauthResourceChecks.join(', ') : 'user_id, permissions'}</b>
                </div>
                {oauthCapabilities.length ? (
                  <div className="settings-oauth-capabilities" aria-label="OAuth capability matrix">
                    {oauthCapabilities.map((capability) => (
                      <span key={asString(capability.key) ?? asString(capability.label) ?? 'capability'}>
                        {asString(capability.label) ?? 'Capability'}: {asString(capability.state) ?? 'unknown'}
                      </span>
                    ))}
                  </div>
                ) : null}
                {oauthSteps.length ? (
                  <ol>
                    {oauthSteps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                ) : null}
              </div>
            ) : null}
          </div>
          <button type="button" onClick={() => onNavigate('sync-quality')}>
            Review privacy controls
          </button>
        </article>

        <article className="settings-item" aria-label="AI provider settings">
          <div className="settings-item-main">
            <h2>AI Providers</h2>
            <div className="setting-chip-row">
              {activeProvider ? <span className="setting-chip setting-primary">active: {asString(activeProvider.label) ?? settings?.aiProviders.activeProvider}</span> : null}
              <span className="setting-chip setting-primary">Static</span>
              <span className={providerChipClass(settings, 'nvidia_nim')}>NVIDIA NIM</span>
              <span className={providerChipClass(settings, 'gemini_api_key')}>Gemini API</span>
              <span className={providerChipClass(settings, 'gemini_cli_oauth')}>Gemini CLI OAuth</span>
              <span className="setting-chip">Anthropic</span>
              {activeProvider ? <span className="setting-chip setting-primary">{asString(activeProvider.state) ?? 'unknown'}</span> : null}
            </div>
            <label className="setting-check">
              <input type="checkbox" checked={settings?.aiProviders?.factBindingRequired ?? true} readOnly />
              <span>Fact binding required</span>
            </label>
            <div className="settings-fact-grid">
              <span>Reports</span>
              <b>factsUsed + missingData</b>
              <span>Caddie explanation</span>
              <b>decision facts only</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('reports')}>
            Open report controls
          </button>
        </article>

        <article className="settings-item" aria-label="Live app settings">
          <div className="settings-item-main">
            <h2>Live Apps</h2>
            <div className="setting-chip-row">
              <span className="setting-chip setting-primary">iOS offline package</span>
              <span className="setting-chip setting-secondary">Watch bridge</span>
              <span className="setting-chip">Photo / video context</span>
              {asString(ios.state) ? <span className="setting-chip">iOS {asString(ios.state)}</span> : null}
              {asString(watch.state) ? <span className="setting-chip">Watch {asString(watch.state)}</span> : null}
            </div>
            <div className="settings-fact-grid">
              <span>Round start</span>
              <b>cached package</b>
              <span>On-course input</span>
              <b>{iosCaptures}</b>
              <span>Watch input</span>
              <b>{watchInputs}</b>
              <span>Post-round</span>
              <b>event reconciliation</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('sync-quality')}>
            Open live prep
          </button>
        </article>

        <article className="settings-item" aria-label="Privacy settings">
          <div className="settings-item-main">
            <h2>Privacy & Retention</h2>
            <div className="setting-check-grid">
              <label className="setting-check">
                <input type="checkbox" checked={asBoolean(privacy.adminProtectedWrites, true)} readOnly />
                <span>Admin protected writes</span>
              </label>
              <label className="setting-check">
                <input type="checkbox" checked={asBoolean(privacy.mediaRedaction, true)} readOnly />
                <span>Media redaction</span>
              </label>
              <label className="setting-check">
                <input type="checkbox" checked={asBoolean(privacy.localSnapshotsSurviveReauth, true)} readOnly />
                <span>Local snapshots survive reauth</span>
              </label>
              <label className="setting-check">
                <input type="checkbox" checked={asBoolean(privacy.secretFreeStatusResponses, true)} readOnly />
                <span>Secret-free status responses</span>
              </label>
            </div>
            <div className="settings-fact-grid">
              <span>Session material</span>
              <b>secret storage only</b>
              <span>Media bytes</span>
              <b>redactable</b>
              <span>API responses</span>
              <b>private paths removed</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('sync-quality')}>
            Open sync controls
          </button>
        </article>

        <article className="settings-item">
          <div className="settings-item-main">
            <h2>Manual Corrections</h2>
            <div className="setting-chip-row">
              <span className="setting-chip">Issue tags</span>
              <span className="setting-chip">Score fixes</span>
              <span className="setting-chip">Caddie feedback</span>
              <span className="setting-chip">Weather notes</span>
            </div>
            <div className="settings-fact-grid">
              <span>Raw facts</span>
              <b>immutable</b>
              <span>Derived stats</span>
              <b>correction-aware</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('corrections')}>
            Open corrections
          </button>
        </article>
      </div>
    </section>
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(asString).filter((item): item is string => Boolean(item)) : []
}

function asRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => item !== null && typeof item === 'object' && !Array.isArray(item)) : []
}

function asBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}

function formatSettingList(value: unknown, fallback: string[]): string {
  const rawValues = Array.isArray(value) ? value : fallback
  return rawValues
    .map(asString)
    .filter((item): item is string => Boolean(item))
    .map((item) => (item.toLowerCase() === 'gps' ? 'GPS' : item))
    .join(', ')
}

function providerChipClass(settings: ProductSettingsResponse | null | undefined, providerId: string): string {
  const providers = Array.isArray(settings?.aiProviders?.providers) ? settings.aiProviders.providers : []
  const provider = providers.find((row) => asString(row.id) === providerId)
  return asString(provider?.state) === 'configured' ? 'setting-chip setting-primary' : 'setting-chip'
}

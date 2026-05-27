import type { ProductPage } from './ProductNav'

interface SettingsPageProps {
  onNavigate: (page: ProductPage) => void
}

export function SettingsPage({ onNavigate }: SettingsPageProps) {
  return (
    <section className="settings-page" aria-label="Settings workspace">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">Control Surface</p>
          <h1>Settings</h1>
          <p>Connector, provider, live app, privacy, and correction controls.</p>
        </div>
      </div>

      <div className="settings-grid">
        <article className="settings-item" aria-label="Data source settings">
          <div className="settings-item-main">
            <h2>Data Sources</h2>
            <div className="setting-chip-row">
              <span className="setting-chip setting-primary">CN Web Session</span>
              <span className="setting-chip setting-secondary">OAuth feasibility</span>
              <span className="setting-chip">Local snapshots</span>
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
          </div>
          <button type="button" onClick={() => onNavigate('sync-quality')}>
            Review privacy controls
          </button>
        </article>

        <article className="settings-item" aria-label="AI provider settings">
          <div className="settings-item-main">
            <h2>AI Providers</h2>
            <div className="setting-chip-row">
              <span className="setting-chip setting-primary">Static</span>
              <span className="setting-chip">NVIDIA NIM</span>
              <span className="setting-chip">Gemini API</span>
              <span className="setting-chip">Anthropic</span>
            </div>
            <label className="setting-check">
              <input type="checkbox" checked readOnly />
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
            </div>
            <div className="settings-fact-grid">
              <span>Round start</span>
              <b>cached package</b>
              <span>On-course input</span>
              <b>GPS, club, score</b>
              <span>Post-round</span>
              <b>event reconciliation</b>
            </div>
          </div>
          <button type="button" onClick={() => onNavigate('caddie')}>
            Open caddie controls
          </button>
        </article>

        <article className="settings-item" aria-label="Privacy settings">
          <div className="settings-item-main">
            <h2>Privacy & Retention</h2>
            <div className="setting-check-grid">
              <label className="setting-check">
                <input type="checkbox" checked readOnly />
                <span>Admin protected writes</span>
              </label>
              <label className="setting-check">
                <input type="checkbox" checked readOnly />
                <span>Media redaction</span>
              </label>
              <label className="setting-check">
                <input type="checkbox" checked readOnly />
                <span>Local snapshots survive reauth</span>
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

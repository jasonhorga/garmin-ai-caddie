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
          <p>Connector preferences, review tools, and manual data controls.</p>
        </div>
      </div>

      <div className="settings-grid">
        <article className="settings-item">
          <div>
            <h2>Manual corrections</h2>
            <p>Audit notes, club fixes, issue tags, weather context, and caddie feedback.</p>
          </div>
          <button type="button" onClick={() => onNavigate('corrections')}>
            Open corrections
          </button>
        </article>
      </div>
    </section>
  )
}

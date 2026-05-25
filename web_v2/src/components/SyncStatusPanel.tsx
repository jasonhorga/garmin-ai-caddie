import type { SyncStatusResponse } from '../types'

const stateLabel = {
  ready: 'ready',
  no_data: 'no data',
  reauth_required: 'reauth required',
  error: 'error',
  not_available: 'not available',
}

const connectorLabel = {
  garmin_cn_web_session: 'Garmin CN Web Session',
  garmin_oauth_feasibility: 'Official OAuth',
}

interface SyncStatusPanelProps {
  status: SyncStatusResponse
  onSync?: () => void
  syncState?: 'idle' | 'running' | 'error'
}

export function SyncStatusPanel({ status, onSync, syncState = 'idle' }: SyncStatusPanelProps) {
  const isRunning = syncState === 'running'
  const canRun = Boolean(onSync) && status.connector.canSync && !status.connector.reauthRequired && !isRunning
  const connectors = status.connectors && status.connectors.length ? status.connectors : [status.connector]

  return (
    <section className="sync-panel" aria-label="Garmin sync status">
      <div>
        <p className="eyebrow">Garmin CN</p>
        <h2>{stateLabel[status.connector.state]}</h2>
        <p>{status.connector.detail}</p>
        {status.lastRun ? <p>Last run: {stateLabel[status.lastRun.state]}</p> : null}
      </div>
      <div className="sync-panel__facts">
        <span>{status.snapshot.scorecardCount} scorecards</span>
        <span>{status.snapshot.shotFileCount} shot files</span>
        <span>{status.snapshot.dataMode} data</span>
      </div>
      <div className="sync-connectors" aria-label="Connector tracks">
        {connectors.map((connector) => (
          <article key={connector.name} className="sync-connector">
            <div>
              <strong>{connectorLabel[connector.name]}</strong>
              <p>{connector.detail}</p>
              {connector.feasibilityQuestions?.[0] ? <p>{connector.feasibilityQuestions[0]}</p> : null}
            </div>
            <span className={`semantic-chip ${connector.state === 'ready' ? 'quality-good' : 'quality-missing'}`}>
              {stateLabel[connector.state]}
            </span>
          </article>
        ))}
      </div>
      <button className="sync-action" type="button" onClick={onSync} disabled={!canRun}>
        {isRunning ? 'Syncing' : 'Sync now'}
      </button>
    </section>
  )
}

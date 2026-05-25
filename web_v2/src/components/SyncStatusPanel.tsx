import type { SyncStatusResponse } from '../types'

const stateLabel = {
  ready: 'ready',
  no_data: 'no data',
  reauth_required: 'reauth required',
  error: 'error',
}

interface SyncStatusPanelProps {
  status: SyncStatusResponse
  onSync?: () => void
  syncState?: 'idle' | 'running' | 'error'
}

export function SyncStatusPanel({ status, onSync, syncState = 'idle' }: SyncStatusPanelProps) {
  const isRunning = syncState === 'running'
  const canRun = Boolean(onSync) && status.connector.canSync && !status.connector.reauthRequired && !isRunning

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
      <button className="sync-action" type="button" onClick={onSync} disabled={!canRun}>
        {isRunning ? 'Syncing' : 'Sync now'}
      </button>
    </section>
  )
}

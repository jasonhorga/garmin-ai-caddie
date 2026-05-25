import type { SyncStatusResponse } from '../types'

const stateLabel = {
  ready: 'ready',
  no_data: 'no data',
  reauth_required: 'reauth required',
  error: 'error',
}

interface SyncStatusPanelProps {
  status: SyncStatusResponse
}

export function SyncStatusPanel({ status }: SyncStatusPanelProps) {
  return (
    <section className="sync-panel" aria-label="Garmin sync status">
      <div>
        <p className="eyebrow">Garmin CN</p>
        <h2>{stateLabel[status.connector.state]}</h2>
        <p>{status.connector.detail}</p>
      </div>
      <div className="sync-panel__facts">
        <span>{status.snapshot.scorecardCount} scorecards</span>
        <span>{status.snapshot.shotFileCount} shot files</span>
        <span>{status.snapshot.dataMode} data</span>
      </div>
    </section>
  )
}

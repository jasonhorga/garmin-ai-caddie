import { useState, type FormEvent } from 'react'
import type { GarminSessionImportRequest, SyncStatusResponse } from '../types'

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
  onSaveSession?: (request: GarminSessionImportRequest) => void | Promise<void>
  sessionSaveState?: 'idle' | 'saving' | 'saved' | 'error'
  sessionSaveError?: string | null
}

export function SyncStatusPanel({
  status,
  onSync,
  syncState = 'idle',
  onSaveSession,
  sessionSaveState = 'idle',
  sessionSaveError = null,
}: SyncStatusPanelProps) {
  const [webSessionHeader, setWebSessionHeader] = useState('')
  const [antiForgeryValue, setAntiForgeryValue] = useState('')
  const isRunning = syncState === 'running'
  const canRun = Boolean(onSync) && status.connector.canSync && !status.connector.reauthRequired && !isRunning
  const connectors = status.connectors && status.connectors.length ? status.connectors : [status.connector]
  const canSaveSession =
    Boolean(onSaveSession) &&
    sessionSaveState !== 'saving' &&
    webSessionHeader.trim().length > 0 &&
    antiForgeryValue.trim().length > 0

  function handleSessionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSaveSession || !onSaveSession) return
    void onSaveSession({
      webSessionHeader,
      antiForgeryValue,
    })
  }

  return (
    <section className="sync-panel" aria-label="Garmin sync status">
      <div>
        <p className="eyebrow">Garmin CN</p>
        <h2>{stateLabel[status.connector.state]}</h2>
        <p>{status.connector.detail}</p>
        {status.connector.reauthRequired ? (
          <p className="sync-guidance">Reauthenticate the Garmin CN session before running another sync.</p>
        ) : null}
      </div>
      <div className="sync-panel__facts">
        <span>{status.snapshot.scorecardCount} scorecards</span>
        <span>{status.snapshot.shotFileCount} shot files</span>
        <span>{status.snapshot.dataMode} data</span>
      </div>
      <div className="sync-run-meta" aria-label="Sync run metadata">
        <article>
          <span>Last data update</span>
          <strong>{status.snapshot.lastSuccessfulSyncAt ?? 'not recorded'}</strong>
        </article>
        <article>
          <span>Last run</span>
          <strong>{status.lastRun ? stateLabel[status.lastRun.state] : 'not run'}</strong>
          {status.lastRun?.snapshotId ? <em>snapshot {status.lastRun.snapshotId}</em> : null}
          {status.lastRun?.errorCode ? <em>error {status.lastRun.errorCode}</em> : null}
        </article>
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
      {onSaveSession ? (
        <form className="sync-session-form" aria-label="Garmin session import" onSubmit={handleSessionSubmit}>
          <label htmlFor="web-session-header">Web session header</label>
          <textarea
            id="web-session-header"
            value={webSessionHeader}
            onChange={(event) => setWebSessionHeader(event.target.value)}
            rows={2}
            spellCheck={false}
          />
          <label htmlFor="anti-forgery-value">Anti-forgery value</label>
          <input
            id="anti-forgery-value"
            value={antiForgeryValue}
            onChange={(event) => setAntiForgeryValue(event.target.value)}
            spellCheck={false}
          />
          <button type="submit" disabled={!canSaveSession}>
            {sessionSaveState === 'saving' ? 'Saving session' : 'Save session'}
          </button>
          {sessionSaveState === 'saved' ? <span className="sync-session-state">session saved</span> : null}
          {sessionSaveState === 'error' ? <span className="sync-session-error">{sessionSaveError ?? 'session save failed'}</span> : null}
        </form>
      ) : null}
    </section>
  )
}

import { useState, type FormEvent } from 'react'
import type { GarminSessionImportRequest, SyncStatusResponse } from '../types'
import { dataModeZh, oauthCapabilityZh, stateZh } from '../zhLabels'

const connectorLabel = {
  garmin_cn_web_session: 'Garmin CN 网页会话',
  garmin_oauth_feasibility: '官方 OAuth',
}

// connector.detail closed sentences: three from server_v2/sync_status.py
// (:117-124) plus the fixed OAuth feasibility sentence (garmin_oauth.py
// build_oauth_feasibility_status). Free-form persisted details fall through raw.
const CONNECTOR_DETAIL_ZH: Record<string, string> = {
  'Garmin connector needs attention.': 'Garmin 连接器需要处理。',
  'Local Garmin snapshots are available.': '本地 Garmin 快照已就绪。',
  'No local Garmin snapshots are loaded. Connect Garmin or use fixture mode.':
    '尚未载入本地 Garmin 快照。请连接 Garmin 或使用示例数据。',
  'Official Garmin OAuth is tracked as a replaceable connector path, but golf scorecard and shot access are not proven for this product yet.':
    '官方 Garmin OAuth 作为可替换的连接器路径在跟踪,但高尔夫记分卡与击球数据访问尚未验证。',
  // ai_caddie/connectors/garmin_cn.py emits these two on the reauth/error paths —
  // the expired one is the most common state the user ever sees here.
  'Garmin CN session expired or missing. Reconnect Garmin and retry.':
    'Garmin CN 会话已过期或缺失。请重新登录 Garmin 后再同步。',
  'Garmin CN sync failed before a complete snapshot was written.':
    'Garmin CN 同步在写出完整快照前失败。',
}

function connectorDetailZh(raw: string): string {
  return CONNECTOR_DETAIL_ZH[raw] ?? raw
}

const capabilityStateLabel = {
  unproven: '未验证',
  not_available: '不可用',
  possible: '可行',
  proven: '已验证',
  needs_golf_fit_validation: '需 FIT 验证',
  not_replacement: '非替代方案',
}

const probeStateLabel = {
  not_configured: '未配置',
  ready_for_manual_consent: '可手动授权',
}

const nextActionLabel = {
  connect_garmin: '连接 Garmin',
  review_history: '查看历史',
  reauthenticate_garmin: '重新登录 Garmin',
  inspect_sync_error: '检查同步错误',
}

interface SyncStatusPanelProps {
  status: SyncStatusResponse
  onSync?: (adminToken?: string) => void
  syncState?: 'idle' | 'running' | 'error'
  onSaveSession?: (request: GarminSessionImportRequest, adminToken?: string) => void | Promise<void>
  sessionSaveState?: 'idle' | 'saving' | 'saved' | 'error'
  sessionSaveError?: string | null
}

// Owner diagnostics surface (off the consumer nav). The admin-token entry field
// was removed in the consumer de-engineer pass — the owner now authenticates via
// the baked/`?admin=` token plumbing (adminTokenStore), so protected sync actions
// call the parent handlers with no token and rely on that fallback.
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

  async function handleSessionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSaveSession || !onSaveSession) return
    const request = {
      webSessionHeader,
      antiForgeryValue,
      source: 'web_secure_paste' as const,
    }
    try {
      await onSaveSession(request)
      setWebSessionHeader('')
      setAntiForgeryValue('')
    } catch {
      // Parent state owns the visible failure; keep pasted credentials available for correction.
    }
  }

  function handleSyncClick() {
    if (!canRun || !onSync) return
    onSync()
  }

  return (
    <section className="sync-panel" aria-label="Garmin 同步状态">
      <div>
        <p className="eyebrow">Garmin CN</p>
        <h2>{stateZh(status.connector.state)}</h2>
        <p>{connectorDetailZh(status.connector.detail)}</p>
        {status.connector.nextAction ? (
          <span className="sync-next-action">{nextActionLabel[status.connector.nextAction]}</span>
        ) : null}
        {status.connector.reauthRequired ? (
          <p className="sync-guidance">请先重新登录 Garmin CN 会话，再运行同步。</p>
        ) : null}
      </div>
      <div className="sync-panel__facts">
        <span>{status.snapshot.scorecardCount} 张记分卡</span>
        <span>{status.snapshot.shotFileCount} 个击球文件</span>
        <span>{dataModeZh(status.snapshot.dataMode)}数据</span>
      </div>
      <div className="sync-run-meta" aria-label="同步运行记录">
        <article>
          <span>最近数据更新</span>
          <strong>{status.snapshot.lastSuccessfulSyncAt ?? '未记录'}</strong>
        </article>
        <article>
          <span>最近运行</span>
          <strong>{status.lastRun ? stateZh(status.lastRun.state) : '未运行'}</strong>
          {status.lastRun?.snapshotId ? <em>快照 {status.lastRun.snapshotId}</em> : null}
          {status.lastRun?.errorCode ? <em>错误 {status.lastRun.errorCode}</em> : null}
        </article>
      </div>
      <div className="sync-connectors" aria-label="连接器">
        {connectors.map((connector) => (
          <article key={connector.name} className="sync-connector">
            <div>
              <strong>{connectorLabel[connector.name]}</strong>
              <p>{connectorDetailZh(connector.detail)}</p>
              {connector.feasibilityQuestions?.[0] ? <p>{connector.feasibilityQuestions[0]}</p> : null}
              {connector.capabilities?.length ? (
                <div className="sync-capabilities" aria-label={`${connectorLabel[connector.name]} 能力矩阵`}>
                  {connector.capabilities.map((capability) => (
                    <div key={capability.key} className="sync-capability-row">
                      <span>
                        <strong>{oauthCapabilityZh(capability.key)?.label ?? capability.label}</strong>
                        <em>{oauthCapabilityZh(capability.key)?.nextStep ?? capability.nextStep}</em>
                      </span>
                      <b className={`semantic-chip ${capability.state === 'possible' || capability.state === 'proven' ? 'quality-good' : 'quality-missing'}`}>
                        {capabilityStateLabel[capability.state]}
                      </b>
                    </div>
                  ))}
                </div>
              ) : null}
              {connector.probe ? (
                <div className="sync-oauth-probe" aria-label="OAuth 探测就绪度">
                  <span>
                    <strong>OAuth 探测</strong>
                    <em>{connector.probe.liveProbeAllowed ? '允许实测' : '仅试运行'}</em>
                  </span>
                  <b className={`semantic-chip ${connector.probe.state === 'ready_for_manual_consent' ? 'quality-good' : 'quality-missing'}`}>
                    {probeStateLabel[connector.probe.state] ?? connector.probe.state}
                  </b>
                  {(connector.probe.missing?.length ?? 0) > 0 ? (
                    <p>缺失:{connector.probe.missing?.join(', ')}</p>
                  ) : (
                    <p>同意请求已配置(参数已脱敏)。</p>
                  )}
                </div>
              ) : null}
            </div>
            <span className={`semantic-chip ${connector.state === 'ready' ? 'quality-good' : 'quality-missing'}`}>
              {stateZh(connector.state)}
            </span>
          </article>
        ))}
      </div>
      <button className="sync-action" type="button" onClick={handleSyncClick} disabled={!canRun}>
        {isRunning ? '同步中' : '立即同步'}
      </button>
      {onSaveSession ? (
        <form className="sync-session-form" aria-label="Garmin 会话导入" onSubmit={handleSessionSubmit}>
          <label htmlFor="web-session-header">网页会话头</label>
          <textarea
            id="web-session-header"
            value={webSessionHeader}
            onChange={(event) => setWebSessionHeader(event.target.value)}
            rows={2}
            spellCheck={false}
          />
          <label htmlFor="anti-forgery-value">防伪令牌</label>
          <input
            id="anti-forgery-value"
            value={antiForgeryValue}
            onChange={(event) => setAntiForgeryValue(event.target.value)}
            spellCheck={false}
          />
          <button type="submit" disabled={!canSaveSession}>
            {sessionSaveState === 'saving' ? '保存中' : '保存会话'}
          </button>
          {sessionSaveState === 'saved' ? <span className="sync-session-state">会话已保存</span> : null}
          {sessionSaveState === 'error' ? <span className="sync-session-error">{sessionSaveError ?? '会话保存失败'}</span> : null}
        </form>
      ) : null}
    </section>
  )
}

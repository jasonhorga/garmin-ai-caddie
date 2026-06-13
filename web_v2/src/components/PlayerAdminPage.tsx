import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { createAdminPlayer, deleteAdminPlayer, fetchAdminPlayers, rotateAdminPlayerToken } from '../api'
import type { AdminPlayer } from '../types'

// Owner-only player management (multiplayer foundation, stage 1).
//
// This page manages players and their per-player capability links ONLY. It never
// renders anyone's score analysis — it holds no HistoryData/stats and only ever
// sees the admin registry view (name + tokenLast4 + optional aggregate counts).
// Plaintext links are returned once by create/rotate and shown in a one-time
// banner; the list never carries token material. The whole page is gated behind
// the owner admin token and is unreachable from a per-player link.

interface PlayerAdminPageProps {
  adminToken?: string
  onNavigate?: (page: 'sync-quality') => void
}

type ListState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; players: AdminPlayer[] }
  | { status: 'error'; message: string }

interface IssuedLink {
  id: string
  name: string
  url: string
  reason: 'created' | 'rotated'
}

const SOURCE_LABEL: Record<string, string> = { garmin: 'Garmin', manual: '手动' }

function sourceLabel(key: string): string {
  return SOURCE_LABEL[key] ?? key
}

function formatSources(sources?: Record<string, number> | null): string | null {
  if (!sources) return null
  const entries = Object.entries(sources).filter(([, value]) => typeof value === 'number' && value > 0)
  const total = entries.reduce((sum, [, value]) => sum + value, 0)
  if (!total) return null
  return entries.map(([key, value]) => `${sourceLabel(key)} ${Math.round((value / total) * 100)}%`).join(' · ')
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '未知错误'
}

export function PlayerAdminPage({ adminToken, onNavigate }: PlayerAdminPageProps) {
  const token = adminToken?.trim() ?? ''
  const [listState, setListState] = useState<ListState>(() =>
    adminToken?.trim() ? { status: 'loading' } : { status: 'idle' },
  )
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null)
  const [issued, setIssued] = useState<IssuedLink | null>(null)
  const [copied, setCopied] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!token) return
    setListState({ status: 'loading' })
    try {
      const data = await fetchAdminPlayers(token)
      setListState({ status: 'ready', players: data.players })
    } catch (error: unknown) {
      setListState({ status: 'error', message: errorMessage(error) })
    }
  }, [token])

  useEffect(() => {
    // No admin token → render the gate (below) and issue no request. The stale
    // list state stays hidden because the gate branch is keyed on `token`.
    // setState happens only in the async resolution (never synchronously in the
    // effect body) so a token change can't trigger a cascading render.
    if (!token) return
    let cancelled = false
    fetchAdminPlayers(token)
      .then((data) => {
        if (!cancelled) setListState({ status: 'ready', players: data.players })
      })
      .catch((error: unknown) => {
        if (!cancelled) setListState({ status: 'error', message: errorMessage(error) })
      })
    return () => {
      cancelled = true
    }
  }, [token])

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed || creating) return
    setCreating(true)
    setActionError(null)
    try {
      const created = await createAdminPlayer({ name: trimmed }, token)
      setIssued({ id: created.id, name: created.name, url: created.url, reason: 'created' })
      setCopied(false)
      setName('')
      await load()
    } catch (error: unknown) {
      setActionError(errorMessage(error))
    } finally {
      setCreating(false)
    }
  }

  async function handleRotate(player: AdminPlayer) {
    setBusyId(player.id)
    setActionError(null)
    try {
      const rotated = await rotateAdminPlayerToken(player.id, token)
      setIssued({ id: player.id, name: player.name, url: rotated.url, reason: 'rotated' })
      setCopied(false)
      await load()
    } catch (error: unknown) {
      setActionError(errorMessage(error))
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(player: AdminPlayer) {
    if (confirmingDeleteId !== player.id) {
      setConfirmingDeleteId(player.id)
      return
    }
    setBusyId(player.id)
    setActionError(null)
    try {
      await deleteAdminPlayer(player.id, token)
      setConfirmingDeleteId(null)
      if (issued?.id === player.id) setIssued(null)
      await load()
    } catch (error: unknown) {
      setActionError(errorMessage(error))
    } finally {
      setBusyId(null)
    }
  }

  async function handleCopy(url: string) {
    try {
      await navigator.clipboard?.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section className="player-admin-page" aria-label="球员管理工作区">
      <div className="section-head stats-head">
        <div>
          <p className="eyebrow">多球员</p>
          <h1>球员管理</h1>
          <p>为好友发放专属链接;此页只管理球员与链接,不展示任何人的成绩。</p>
        </div>
        {actionError ? <span className="semantic-chip quality-missing">{actionError}</span> : null}
      </div>

      {!token ? (
        <section className="panel empty-state" aria-label="需要管理令牌">
          <h2>需要管理令牌</h2>
          <p className="empty-state-hint">请先在「设置 → 同步与数据健康」中输入令牌后,再来管理球员。</p>
          {onNavigate ? (
            <button type="button" onClick={() => onNavigate('sync-quality')}>
              去输入令牌
            </button>
          ) : null}
        </section>
      ) : (
        <>
          <form className="panel player-admin-create" aria-label="新建球员" onSubmit={handleCreate}>
            <label htmlFor="player-admin-name">球员名字</label>
            <input
              id="player-admin-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如:老王"
              autoComplete="off"
              spellCheck={false}
            />
            <button className="sync-action" type="submit" disabled={!name.trim() || creating}>
              {creating ? '创建中' : '新建球员'}
            </button>
          </form>

          {issued ? (
            <section className="panel player-admin-issued" aria-label="一次性专属链接">
              <div>
                <p className="eyebrow">{issued.reason === 'rotated' ? '已重发链接' : '新链接已生成'}</p>
                <h2>{issued.name} 的专属链接</h2>
                <p className="empty-state-hint">
                  仅显示一次,请立即复制并发给该球员。
                  {issued.reason === 'rotated' ? '旧链接已失效。' : ''}
                </p>
              </div>
              <code className="player-admin-url">{issued.url}</code>
              <div className="player-admin-issued-actions">
                <button className="sync-action" type="button" onClick={() => void handleCopy(issued.url)}>
                  复制链接
                </button>
                {copied ? <span className="sync-session-state">已复制</span> : null}
                <button type="button" onClick={() => setIssued(null)}>
                  知道了
                </button>
              </div>
            </section>
          ) : null}

          {listState.status === 'loading' ? (
            <section className="panel empty-state">
              <h2>球员加载中</h2>
            </section>
          ) : null}

          {listState.status === 'error' ? (
            <section className="panel empty-state">
              <h2>加载球员失败</h2>
              <p>{listState.message}</p>
              <button type="button" onClick={() => void load()}>
                重试
              </button>
            </section>
          ) : null}

          {listState.status === 'ready' ? (
            <ul className="player-admin-list" aria-label="球员列表">
              {listState.players.map((player) => {
                const sourceText = formatSources(player.sources)
                const confirming = confirmingDeleteId === player.id
                const rowBusy = busyId === player.id
                return (
                  <li key={player.id} className="panel player-admin-row">
                    <div className="player-admin-row-main">
                      <div className="player-admin-identity">
                        <strong>{player.name}</strong>
                        {player.isOwner ? <span className="semantic-chip quality-good">本人</span> : null}
                      </div>
                      <div className="player-admin-meta">
                        <span className="player-admin-token">
                          {player.tokenLast4 ? `链接尾号 …${player.tokenLast4}` : '用管理令牌登录'}
                        </span>
                        {player.roundCount != null ? (
                          <span className="player-admin-stat">
                            {player.roundCount} 局{sourceText ? ` · ${sourceText}` : ''}
                          </span>
                        ) : (
                          <span className="player-admin-stat player-admin-muted">暂无数据</span>
                        )}
                      </div>
                    </div>
                    <div className="player-admin-actions">
                      {player.isOwner ? null : (
                        <button
                          type="button"
                          className="sync-action"
                          aria-label={`重发 ${player.name} 的专属链接`}
                          disabled={rowBusy}
                          onClick={() => void handleRotate(player)}
                        >
                          {rowBusy && !confirming ? '处理中' : '重发链接'}
                        </button>
                      )}
                      {confirming ? (
                        <button
                          type="button"
                          className="player-admin-danger"
                          aria-label={`确认删除球员 ${player.name}`}
                          disabled={rowBusy}
                          onClick={() => void handleDelete(player)}
                        >
                          确认删除
                        </button>
                      ) : (
                        <button
                          type="button"
                          aria-label={`删除球员 ${player.name}`}
                          disabled={player.isOwner || rowBusy}
                          onClick={() => void handleDelete(player)}
                        >
                          删除
                        </button>
                      )}
                      {confirming ? (
                        <button type="button" onClick={() => setConfirmingDeleteId(null)}>
                          取消
                        </button>
                      ) : null}
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : null}
        </>
      )}
    </section>
  )
}

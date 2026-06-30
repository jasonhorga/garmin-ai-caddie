import { afterEach, describe, expect, it } from 'vitest'
import { clearSession, currentSession, currentSessionPlayerId, currentSessionToken, saveSession } from './sessionStore'

describe('sessionStore', () => {
  afterEach(() => clearSession())

  const live = (token: string, playerId: string) => ({
    token,
    playerId,
    expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
  })

  it('saves and reads a live session', () => {
    saveSession(live('t1', 'me'))
    expect(currentSession()?.playerId).toBe('me')
    expect(currentSessionToken()).toBe('t1')
    expect(currentSessionPlayerId()).toBe('me')
  })

  it('drops an expired session (never vends a stale token)', () => {
    saveSession({ token: 't2', playerId: 'p_x', expiresAt: new Date(Date.now() - 1000).toISOString() })
    expect(currentSession()).toBeNull()
    expect(currentSessionToken()).toBeNull()
  })

  it('clear removes the session', () => {
    saveSession(live('t3', 'p_y'))
    clearSession()
    expect(currentSession()).toBeNull()
  })

  it('ignores corrupt stored JSON', () => {
    window.sessionStorage.setItem('ai-caddie.session', '{not json')
    expect(currentSession()).toBeNull()
  })
})

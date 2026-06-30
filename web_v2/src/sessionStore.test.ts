import { afterEach, describe, expect, it } from 'vitest'
import { clearSession, currentSession, currentSessionPlayerId, currentSessionToken, saveSession } from './sessionStore'

const ADMIN_TOKEN_KEY = 'ai-caddie.admin-token'

describe('sessionStore', () => {
  afterEach(() => {
    clearSession()
    try {
      window.localStorage.removeItem(ADMIN_TOKEN_KEY)
    } catch {
      /* storage may be unavailable in the test env */
    }
  })

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

  it('persists the session in localStorage so it survives a browser/tab close', () => {
    // The session must outlive the tab (localStorage, NOT sessionStorage) so users
    // aren't forced to re-login every time they reopen the browser.
    saveSession(live('persisted', 'me'))
    expect(window.localStorage.getItem('ai-caddie.session')).not.toBeNull()
    expect(window.sessionStorage.getItem('ai-caddie.session')).toBeNull()
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
    window.localStorage.setItem('ai-caddie.session', '{not json')
    expect(currentSession()).toBeNull()
  })

  it('clears a stored owner admin token when a MEMBER session is saved', () => {
    // SECURITY: a member browser must not retain a stray/shared owner admin token.
    window.localStorage.setItem(ADMIN_TOKEN_KEY, 'admin-secret')
    saveSession(live('member-bearer', 'p_member'))
    expect(window.localStorage.getItem(ADMIN_TOKEN_KEY)).toBeNull()
  })

  it('keeps the stored admin token when the OWNER session is saved (bare-URL owner UX)', () => {
    window.localStorage.setItem(ADMIN_TOKEN_KEY, 'admin-secret')
    saveSession(live('owner-bearer', 'me'))
    expect(window.localStorage.getItem(ADMIN_TOKEN_KEY)).toBe('admin-secret')
  })
})

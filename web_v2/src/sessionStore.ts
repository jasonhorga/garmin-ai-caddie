// Apple Sign-in session (consumer auth). Everyone signs in with Apple; the
// owner is just the session whose playerId is the backend OWNER_ID ("me").
//
// Stored in sessionStorage (NOT localStorage) to limit XSS blast radius — the
// bearer lives only for the tab session. api.ts reads `currentSessionToken()`
// and attaches it as `Authorization: Bearer`. Never log the token.

export const OWNER_PLAYER_ID = 'me'

const SESSION_KEY = 'ai-caddie.session'

export interface AppSession {
  token: string
  playerId: string
  expiresAt: string // ISO8601
}

function isExpired(session: AppSession): boolean {
  const t = Date.parse(session.expiresAt)
  return Number.isFinite(t) && t <= Date.now()
}

/** The live (non-expired) session, or null. An expired session is dropped. */
export function currentSession(): AppSession | null {
  let raw: string | null
  try {
    raw = window.sessionStorage.getItem(SESSION_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as AppSession
    if (!parsed || typeof parsed.token !== 'string' || !parsed.token) return null
    if (isExpired(parsed)) {
      clearSession()
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function currentSessionToken(): string | null {
  return currentSession()?.token ?? null
}

export function currentSessionPlayerId(): string | null {
  return currentSession()?.playerId ?? null
}

export function saveSession(session: AppSession): void {
  try {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
  } catch {
    /* sessionStorage unavailable (private mode / SSR) — sign-in just won't persist */
  }
}

export function clearSession(): void {
  try {
    window.sessionStorage.removeItem(SESSION_KEY)
  } catch {
    /* ignore */
  }
}

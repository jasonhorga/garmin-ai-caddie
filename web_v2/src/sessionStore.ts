// Apple Sign-in session (consumer auth). Everyone signs in with Apple; the
// owner is just the session whose playerId is the backend OWNER_ID ("me").
//
// Stored in localStorage so the session SURVIVES a browser/tab close — users
// stay signed in across restarts instead of re-logging-in every visit (the
// backend TTL, default 30 days, still bounds the bearer's lifetime). The
// tradeoff vs sessionStorage: a stored XSS could now read the bearer; that's
// the accepted consumer call (re-login-every-launch is worse UX). api.ts reads
// `currentSessionToken()` and attaches it as `Authorization: Bearer`. Never log
// the token.

import { writeStoredAdminToken } from './adminTokenStore'

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
    raw = window.localStorage.getItem(SESSION_KEY)
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
  // SECURITY: a MEMBER browser must not retain a stray/shared owner admin token.
  // Clear any stored admin token whenever a non-owner session is established, so a
  // member is authenticated ONLY by their own Apple Bearer (and never re-hydrates a
  // leftover admin token on reload). The owner session (playerId === OWNER_PLAYER_ID)
  // keeps its typed/bookmarked admin token — the bare-URL owner UX depends on it.
  // Mirrors api.ts suppressing the admin header for member sessions.
  if (session.playerId !== OWNER_PLAYER_ID) {
    writeStoredAdminToken('')
  }
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  } catch {
    /* localStorage unavailable (private mode / disabled / SSR) — sign-in just won't persist */
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(SESSION_KEY)
  } catch {
    /* ignore */
  }
}

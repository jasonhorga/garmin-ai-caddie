// Owner admin-token persistence (owner/homeserver deployment).
//
// In owner mode the app is opened at the bare URL with no per-player link, so
// the only credential that reaches the private owner profile is the admin token
// the owner types into the sync panel. Persisting it in localStorage (the same
// tradeoff the player bearer makes by living in the URL) lets a fresh page load
// hydrate the token and carry it on the very first boot fetch, instead of
// 401-ing and stranding the owner on the recovery panel. Never log the token.

const ADMIN_TOKEN_KEY = 'ai-caddie.admin-token'

/** Read the persisted admin token, or '' when none is stored / storage is unavailable. */
export function readStoredAdminToken(): string {
  try {
    return window.localStorage.getItem(ADMIN_TOKEN_KEY)?.trim() ?? ''
  } catch {
    return ''
  }
}

/** Persist a non-empty admin token; clearing it (empty/whitespace) removes the key. */
export function writeStoredAdminToken(token: string): void {
  try {
    const trimmed = token.trim()
    if (trimmed) window.localStorage.setItem(ADMIN_TOKEN_KEY, trimmed)
    else window.localStorage.removeItem(ADMIN_TOKEN_KEY)
  } catch {
    // Storage can be unavailable (private mode / disabled); a failed persist is
    // non-fatal — the in-memory token still works for the current session.
  }
}

interface AdminLocationLike {
  readonly search: string
}

/**
 * Read an owner admin token carried in the URL (`?admin=<token>`), mirroring the
 * player bearer that lives in `/p/<token>`. Lets the owner bookmark ONE URL and
 * never retype the token — durable even when iOS Safari clears localStorage. The
 * secret stays in the owner's bookmark (their device), never in the shipped JS.
 */
export function readAdminTokenFromUrl(loc: AdminLocationLike = window.location): string {
  try {
    return new URLSearchParams(loc.search).get('admin')?.trim() ?? ''
  } catch {
    return ''
  }
}

/**
 * Build-time default admin token, inlined by Vite from
 * `VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN`. Set ONLY in the owner's private homeserver
 * build so the bare URL auto-loads the owner profile with no entry. Empty in the
 * repo / CI build. NOTE: this inlines the token into the shipped JS — enable it only
 * for a deployment whose URL is the owner's alone (it is readable by anyone who
 * loads that URL).
 */
export function readBakedAdminToken(): string {
  return String(import.meta.env.VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN ?? '').trim()
}

/**
 * Resolve the admin token to hydrate at app boot, in priority order:
 *   URL `?admin=` (memory-only)  →  previously-stored (typed)  →  build-time baked default.
 *
 * P1-1 N2: a URL token is returned but deliberately NOT persisted to localStorage — the
 * high-privilege admin token shouldn't be left at rest (XSS-readable, surviving the session)
 * when it was only ever meant to ride in the owner's bookmarked URL. A reload re-reads it from
 * the URL; an in-session SPA navigation keeps it in React state. A token the owner TYPES into the
 * sync panel is still persisted by the caller (writeStoredAdminToken) for the bare-URL owner UX.
 */
export function resolveInitialAdminToken(loc: AdminLocationLike = window.location): string {
  const fromUrl = readAdminTokenFromUrl(loc)
  if (fromUrl) {
    return fromUrl
  }
  return readStoredAdminToken() || readBakedAdminToken()
}

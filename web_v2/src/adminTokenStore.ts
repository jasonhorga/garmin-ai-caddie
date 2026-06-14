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

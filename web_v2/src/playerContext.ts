// Player capability-token context (multiplayer foundation, stage 1).
//
// The whole web app is scoped to a single player by a per-player bearer
// token carried in the URL. There is no in-app switcher: whoever opens the
// link only ever sees that one player. The token is read once from the
// location and injected as `Authorization: Bearer <token>` on every API
// request (see api.ts). Never log or persist the token.

/** Minimal subset of `window.location` needed to resolve the player token. */
export interface LocationLike {
  pathname: string
  search: string
}

/**
 * Resolve the active player's capability token from the current location.
 *
 * Resolution order:
 *  1. Path form `/p/<token>` (the canonical shareable URL).
 *  2. Query form `?key=<token>` (fallback / convenience form).
 *  3. Neither present → `null` (no player scope; owner/admin behavior applies).
 */
export function readPlayerToken(loc: LocationLike = window.location): string | null {
  const pathMatch = loc.pathname.match(/^\/p\/([^/?#]+)/)
  if (pathMatch) {
    const fromPath = pathMatch[1].trim()
    if (fromPath) return fromPath
  }

  const fromQuery = new URLSearchParams(loc.search).get('key')?.trim()
  if (fromQuery) return fromQuery

  return null
}

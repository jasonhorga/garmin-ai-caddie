// Owner-only "diagnostics mode" persistence.
//
// The web ships one build for both the owner (homeserver, baked admin token) and
// any per-player share link. By default the product hides all internal plumbing —
// raw refs/IDs, source-trace panels, data-quality / coverage / confidence chips,
// AI evidence chains — so it reads like a real product. The owner can flip
// "diagnostics mode" ON to reveal that plumbing when debugging data or preparing a
// correction (which needs the underlying refs). Default OFF; never offered to a
// player link. Mirrors adminTokenStore's localStorage tradeoff.

const DIAGNOSTICS_KEY = 'ai-caddie.diagnostics'

/** Read the persisted diagnostics-mode flag (default false / off). */
export function readStoredDiagnostics(): boolean {
  try {
    return window.localStorage.getItem(DIAGNOSTICS_KEY) === '1'
  } catch {
    return false
  }
}

/** Persist diagnostics-mode on/off (removes the key when off). */
export function writeStoredDiagnostics(on: boolean): void {
  try {
    if (on) window.localStorage.setItem(DIAGNOSTICS_KEY, '1')
    else window.localStorage.removeItem(DIAGNOSTICS_KEY)
  } catch {
    // Storage can be unavailable (private mode / disabled); the in-memory toggle
    // still applies for the current session.
  }
}

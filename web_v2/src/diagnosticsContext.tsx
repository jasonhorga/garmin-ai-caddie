import { createContext, useContext } from 'react'

// Whether owner "diagnostics mode" is on. Default false everywhere — player
// links, tests, and the owner's default view — so every engineering surface that
// reads it (raw refs, source-trace panels, data-quality / evidence chips) stays
// hidden unless the owner explicitly turns diagnostics on. Components read it via
// useDiagnostics() instead of prop-drilling through the whole tree.
const DiagnosticsContext = createContext(false)

export const DiagnosticsProvider = DiagnosticsContext.Provider

/** True only when the owner has diagnostics mode on. False by default. */
export function useDiagnostics(): boolean {
  return useContext(DiagnosticsContext)
}

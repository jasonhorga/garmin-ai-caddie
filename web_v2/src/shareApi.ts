import type { SharedRoundResponse } from './types'

function apiUrl(path: string): string {
  const baseUrl = String(import.meta.env.VITE_AI_CADDIE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')
  if (!baseUrl) return path
  return `${baseUrl}${path.startsWith('/') ? path : `/${path}`}`
}

/** Anonymous read-only fetch. This module intentionally has no session/admin-token imports. */
export async function fetchSharedRound(token: string): Promise<SharedRoundResponse> {
  const response = await fetch(apiUrl(`/api/v2/share/${encodeURIComponent(token)}`), {
    credentials: 'omit',
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error('share link not found')
  return response.json() as Promise<SharedRoundResponse>
}

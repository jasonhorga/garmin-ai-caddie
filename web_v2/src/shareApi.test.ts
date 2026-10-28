import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchSharedRound } from './shareApi'

describe('shareApi', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('uses an anonymous no-store request with no bearer or admin credential', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ found: true }), { status: 200 }))
    await fetchSharedRound('token_abc')
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/share/token_abc', {
      credentials: 'omit',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    })
  })

  it('normalizes any failed response to the neutral not-found error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 404 }))
    await expect(fetchSharedRound('expired')).rejects.toThrow('share link not found')
  })
})

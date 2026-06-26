import { afterEach, describe, expect, it, vi } from 'vitest'
import { readAdminTokenFromUrl, readBakedAdminToken, readStoredAdminToken, resolveInitialAdminToken } from './adminTokenStore'

describe('readAdminTokenFromUrl', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads the owner admin token from the ?admin= query param', () => {
    expect(readAdminTokenFromUrl({ search: '?admin=tok123' })).toBe('tok123')
  })

  it('trims surrounding whitespace', () => {
    expect(readAdminTokenFromUrl({ search: '?admin=%20%20abc%20' })).toBe('abc')
  })

  it('reads the token when other query params are present', () => {
    expect(readAdminTokenFromUrl({ search: '?foo=1&admin=tok&bar=2' })).toBe('tok')
  })

  it('returns empty string for an empty ?admin= param', () => {
    expect(readAdminTokenFromUrl({ search: '?admin=' })).toBe('')
  })

  it('returns empty string when no ?admin= param is present', () => {
    expect(readAdminTokenFromUrl({ search: '' })).toBe('')
    expect(readAdminTokenFromUrl({ search: '?key=playertok' })).toBe('')
  })

  it('defaults to window.location when no argument is provided', () => {
    vi.stubGlobal('location', { search: '?admin=windowtok' })
    expect(readAdminTokenFromUrl()).toBe('windowtok')
  })
})

describe('readBakedAdminToken', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('is empty when the build-time env var is unset', () => {
    expect(readBakedAdminToken()).toBe('')
  })

  it('returns the trimmed build-time token when set', () => {
    vi.stubEnv('VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN', '  baked-tok  ')
    expect(readBakedAdminToken()).toBe('baked-tok')
  })
})

describe('resolveInitialAdminToken', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    try {
      window.localStorage.clear()
    } catch {
      /* storage may be unavailable in the test env */
    }
  })

  it('returns a URL ?admin= token WITHOUT persisting it to localStorage (P1-1 N2)', () => {
    window.localStorage.clear()
    expect(resolveInitialAdminToken({ search: '?admin=urltok' })).toBe('urltok')
    // the high-privilege admin token must NOT be left at rest in localStorage
    expect(readStoredAdminToken()).toBe('')
  })

  it('falls back to the stored token when the URL carries none', () => {
    window.localStorage.setItem('ai-caddie.admin-token', 'stored-tok')
    expect(resolveInitialAdminToken({ search: '' })).toBe('stored-tok')
  })

  it('falls back to the baked default when neither URL nor storage has a token', () => {
    window.localStorage.clear()
    vi.stubEnv('VITE_AI_CADDIE_DEFAULT_ADMIN_TOKEN', 'baked-tok')
    expect(resolveInitialAdminToken({ search: '' })).toBe('baked-tok')
  })
})

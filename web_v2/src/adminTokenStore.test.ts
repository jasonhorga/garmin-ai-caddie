import { afterEach, describe, expect, it, vi } from 'vitest'
import { readAdminTokenFromUrl } from './adminTokenStore'

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

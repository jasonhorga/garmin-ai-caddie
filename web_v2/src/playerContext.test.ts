import { afterEach, describe, expect, it, vi } from 'vitest'
import { readPlayerToken } from './playerContext'

describe('readPlayerToken', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads the token from a /p/<token> path', () => {
    expect(readPlayerToken({ pathname: '/p/abc123', search: '' })).toBe('abc123')
  })

  it('reads the token from a /p/<token> path with trailing segments', () => {
    expect(readPlayerToken({ pathname: '/p/abc123/history', search: '' })).toBe('abc123')
  })

  it('preserves base64url token characters from the path', () => {
    expect(readPlayerToken({ pathname: '/p/aB3-_dEf', search: '' })).toBe('aB3-_dEf')
  })

  it('falls back to the ?key= query param when there is no /p/ path', () => {
    expect(readPlayerToken({ pathname: '/', search: '?key=xyz789' })).toBe('xyz789')
  })

  it('prefers the /p/ path over the ?key= query param', () => {
    expect(readPlayerToken({ pathname: '/p/frompath', search: '?key=fromquery' })).toBe('frompath')
  })

  it('returns null when neither a /p/ path nor a ?key= param is present', () => {
    expect(readPlayerToken({ pathname: '/', search: '' })).toBeNull()
  })

  it('returns null for an empty /p/ segment', () => {
    expect(readPlayerToken({ pathname: '/p/', search: '' })).toBeNull()
  })

  it('returns null for an empty ?key= param', () => {
    expect(readPlayerToken({ pathname: '/', search: '?key=' })).toBeNull()
  })

  it('defaults to window.location when no argument is provided', () => {
    vi.stubGlobal('location', { pathname: '/p/windowtok', search: '' })
    expect(readPlayerToken()).toBe('windowtok')
  })

  it('returns null on the default app location', () => {
    vi.stubGlobal('location', { pathname: '/', search: '' })
    expect(readPlayerToken()).toBeNull()
  })
})

import { describe, expect, it } from 'vitest'
import { assertNoConsumerAdminToken, isConsumerBuildWithBakedAdminToken } from './buildGuards'

describe('consumer admin-token build guard', () => {
  it('flags (and throws on) a consumer build that bakes the owner admin token', () => {
    expect(isConsumerBuildWithBakedAdminToken({ bakedAdminToken: 'secret', requireLink: 'true' })).toBe(true)
    expect(() => assertNoConsumerAdminToken({ bakedAdminToken: 'secret', requireLink: 'true' })).toThrow(/never bake/i)
  })

  it('trims and lower-cases the REQUIRE_LINK flag', () => {
    expect(isConsumerBuildWithBakedAdminToken({ bakedAdminToken: 'secret', requireLink: '  TRUE  ' })).toBe(true)
  })

  it('allows the owner homeserver build: baked token but REQUIRE_LINK unset/false', () => {
    expect(isConsumerBuildWithBakedAdminToken({ bakedAdminToken: 'secret' })).toBe(false)
    expect(() => assertNoConsumerAdminToken({ bakedAdminToken: 'secret' })).not.toThrow()
    expect(() => assertNoConsumerAdminToken({ bakedAdminToken: 'secret', requireLink: 'false' })).not.toThrow()
  })

  it('allows a consumer build with no (or blank) baked token', () => {
    expect(isConsumerBuildWithBakedAdminToken({ requireLink: 'true' })).toBe(false)
    expect(() => assertNoConsumerAdminToken({ requireLink: 'true' })).not.toThrow()
    expect(() => assertNoConsumerAdminToken({ bakedAdminToken: '   ', requireLink: 'true' })).not.toThrow()
  })

  it('allows a dev/CI build that sets neither variable', () => {
    expect(() => assertNoConsumerAdminToken({})).not.toThrow()
  })
})

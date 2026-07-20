import { describe, expect, it } from 'vitest'
import {
  canonicalContractSourceSHA256,
  canonicalObjectDescriptors,
  reasonCodes,
  roundEventKinds,
  roundEventSubmissionClasses,
  roundTransportLimits,
} from './generated'

describe('generated canonical declarations', () => {
  it('starts schema-owner gated and still generates shared descriptors', () => {
    expect(roundEventKinds).toEqual([])
    expect(roundEventSubmissionClasses).toEqual({})
    expect(reasonCodes).toContain('round_binding_mismatch')
    expect(reasonCodes).toContain('event_envelope_limit_exceeded')
    expect(reasonCodes).toContain('invalid_device_proof')
    expect(roundTransportLimits.maxEventsPerBatch).toBe(64)
    expect(roundTransportLimits.maxEventCanonicalBytes).toBe(65536)
    expect(canonicalContractSourceSHA256).toMatch(/^[0-9a-f]{64}$/)
    expect(canonicalObjectDescriptors.CanonicalFixtureAlpha.domainTag)
      .toBe('CanonicalFixtureAlpha/v1')
  })
})

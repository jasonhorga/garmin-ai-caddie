import { describe, expect, it } from 'vitest'
import {
  canonicalContractSourceSHA256,
  canonicalObjectDescriptors,
  reasonCodes,
  roundEventKinds,
  roundEventSubmissionClasses,
  roundTransportLimits,
} from './generated'

const expectedReasonCodes = [
  'account_principal_conflict',
  'actor_not_authorized',
  'binding_not_established',
  'bootstrap_required',
  'consumer_ack_ahead_of_stream',
  'dead_letter_quota_exceeded',
  'entity_base_revision_conflict',
  'event_batch_too_large',
  'event_envelope_limit_exceeded',
  'flag_position_not_player_set',
  'green_surface_quarantined',
  'idempotency_key_body_mismatch',
  'identity_envelope_mismatch',
  'illegal_lifecycle_transition',
  'invalid_device_proof',
  'legacy_migration_invalid_payload',
  'legacy_migration_malformed',
  'legacy_migration_unmappable',
  'merge_control_not_ready',
  'merge_semantic_binding_mismatch',
  'missing_event_receipt',
  'payload_schema_invalid',
  'peer_ledger_bundle_invalid',
  'player_cancelled_target',
  'projection_dependency_cycle',
  'replay_gap_detected',
  'request_body_too_large',
  'resolution_commit_conflict',
  'resolution_commit_invalid_bundle',
  'resolution_commit_required',
  'resolution_episode_conflict',
  'resolution_episode_terminal',
  'resolution_required_cause_missing',
  'round_binding_mismatch',
  'round_start_authority_unavailable',
  'round_start_binding_rejected',
  'round_start_intent_conflict',
  'shot_identity_conflict',
  'shot_location_unavailable',
  'shot_target_not_player_confirmed',
  'shot_target_orphaned',
  'transport_receipt_hash_mismatch',
  'unknown_event_kind',
  'unsupported_client_version',
] as const

const expectedRoundTransportLimits = {
  maxConsumerEpochCharacters: 128,
  maxDeadLetterPageSize: 100,
  maxDeadLetterRetainedBytes: 16384,
  maxDeadLettersPerRound: 2048,
  maxEventCanonicalBytes: 65536,
  maxEventJsonDepth: 16,
  maxEventsPerBatch: 64,
  maxHttpBodyBytes: 1048576,
  maxJsonKeyCharacters: 128,
  maxJsonStringCharacters: 4096,
  maxMergeSourceIncarnations: 8,
  maxRawJsonDepth: 64,
  maxReplayPageSize: 500,
  maxSyncPathIdCharacters: 128,
} as const

describe('generated canonical declarations', () => {
  it('starts schema-owner gated and matches the complete frozen registries', () => {
    expect(roundEventKinds).toEqual([])
    expect(roundEventSubmissionClasses).toEqual({})
    expect(reasonCodes).toEqual(expectedReasonCodes)
    expect(roundTransportLimits).toEqual(expectedRoundTransportLimits)
    expect(canonicalContractSourceSHA256).toMatch(/^[0-9a-f]{64}$/)
    expect(canonicalObjectDescriptors.CanonicalFixtureAlpha.domainTag)
      .toBe('CanonicalFixtureAlpha/v1')
  })
})

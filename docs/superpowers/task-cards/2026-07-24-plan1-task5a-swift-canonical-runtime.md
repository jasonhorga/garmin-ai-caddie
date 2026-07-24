# Plan 1 Task 5A Swift Canonical Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` to implement this card. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide the one auditable Swift RFC 8785 + AI-Caddie-v1 canonical
JSON and typed-ID runtime required by every later Task 5 storage/transport
packet.

**Architecture:** The shared `AICaddieDomain` target owns a typed `JSONValue`
and a small validation wrapper around a pinned, vendored SwiftJCS serializer.
The wrapper rejects non-NFC strings, negative zero, non-finite numbers, and
integral values outside JavaScript's safe range before serialization. Domain
tests run in the normal iOS Native CI scheme; Python asset tests independently
pin provenance, vectors, resources, and test routing.

**Tech Stack:** Swift 5.9, Foundation, CryptoKit, minacle/swift-jcs commit
`1e69befe76f5445696e821811402c586dd2186d8`, Python 3.12/rfc8785 for fixed
test vectors, XcodeGen, GitHub `macos-15` Native CI.

---

## Authority, outcome, and exclusions

- Packet routing authority:
  `2026-07-24-plan1-task5-packet-map.md`.
- Normative algorithms: Task 5 historical identity code and the Task 11 pinned
  JCS provenance/runtime section in
  `../plans/2026-07-18-phase0-canonical-round-runtime.md`.
- Baseline: docs commit `f39a025266010c762328d71fb6d28811b9d29649`.

5A is complete only when the exact candidate runs the Domain tests in Native
CI and the homeserver provenance/vector/mechanical tests are green. It does not
define `DomainRoundEvent`, storage-v1, a ledger owner, sequence reservation,
legacy wire IDs, prepared batches, receipts, iOS lifecycle, or Watch behavior.

## Owned files

Create:

- `mobile/ios/AICaddieDomain/JSONValue.swift`
- `mobile/ios/AICaddieDomain/CanonicalJSON.swift`
- `mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS/JSONCanonicalization.swift`
- `mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS/NumberSerializer.swift`
- `mobile/ios/AICaddieDomain/ThirdParty/SwiftJCS/StringSerializer.swift`
- `mobile/ios/ThirdPartyLicenses/swift-jcs-UNLICENSE`
- `mobile/ios/ThirdPartyLicenses/swift-jcs-provenance.json`
- `mobile/ios/AICaddieDomainTests/CanonicalJSONTests.swift`
- `mobile/ios/AICaddieDomainTests/Fixtures/rfc8785_number_vectors.json`
- `tools/contracts/generate_rfc8785_vectors.py`
- `tests/test_swift_canonical_runtime_assets.py`

Modify:

- `Package.swift` — copy Domain fixtures byte-for-byte.
- `mobile/ios/project.yml` — include `AICaddieDomainTests` in the normal iOS
  test scheme.

No canonical registry or generated declaration changes belong to 5A.

## Frozen implementation contract

1. `JSONValue` has distinct `integer(Int64)` and `number(Double)` cases plus
   null, Boolean, string, array, and object. Codable decoding must not collapse
   a JSON integer into Double and must reject unsupported/non-finite values.
2. `CanonicalJSON.data(JSONValue)` and its generic Encodable overload produce
   RFC 8785 bytes after recursively checking all object keys/string values for
   NFC, every integer/integral Double for the inclusive safe range
   `-9_007_199_254_740_991...9_007_199_254_740_991`, and every Double for
   finiteness and negative zero.
3. `TypedID.make(domain:value:)` hashes exact
   `UTF8(domain) + 0x00 + canonicalBytes` with SHA-256 and emits lowercase
   hexadecimal. Empty/non-NFC domain tags are rejected rather than creating a
   second ambiguous namespace.
4. The vendored files and Unlicense are exact bytes from commit
   `1e69befe76f5445696e821811402c586dd2186d8`. Provenance pins:

   - `JSONCanonicalization.swift`:
     `22a38cf5cda61062cf3a61688474e4dba796a8eea1bfb2ca8c977587deddbc9c`
   - `NumberSerializer.swift`:
     `acdedc57a40e8ceb66ff640a82d84b7e340617670aff955b4679df43b3816502`
   - `StringSerializer.swift`:
     `cbb40f06dbb35c43ca9db9e0637cb6baaaf82844d673476363c548556ec91464`
   - `swift-jcs-UNLICENSE`:
     `b5065838cbac452dfc855ba6e6e031481ad2c68406f70d21ead9321374653e6c`

5. `rfc8785_number_vectors.json` starts with the official Appendix B roster,
   then uses the frozen `0xA1CADD1E5EED1234` LCG sequence until the complete
   roster contains exactly 2,048 finite, non-negative-zero IEEE-754 samples.
   The checked-in Python tool canonicalizes them with the already-locked Python
   `rfc8785` dependency. Tests consume checked-in bytes; they never rewrite the
   fixture.
6. The existing root golden value `{"z":1,"a":"球场"}` canonicalizes to
   UTF-8 hex `7b2261223a22e79083e59cba222c227a223a317d`. Typed IDs for that canonical
   value are fixed as:

   - `CanonicalFixtureAlpha/v1` →
     `a2fcc54ce2819d6ae58a7f40ffc9d6837ca3104c222eb391c8e7c204282309b3`
   - `CanonicalFixtureBeta/v1` →
     `f65b7f4bfaf68ad4a2005ebfd6c4a163b351c39fc0c59efb8ec83aace6295b44`

7. The generated Xcode scheme must execute `AICaddieDomainTests` on the iOS
   simulator. A green app test job that never ran `CanonicalJSONTests` is not
   5A evidence.

## TDD execution

- [ ] **Step 1: Add only behavioral tests and asset checks**

Add `CanonicalJSONTests` covering the fixed bytes/typed IDs, integer-vs-number
round-trip, nested ordering/escaping, NFC rejection for keys and values,
negative zero through both the typed and generic Encodable overloads,
infinities/NaN, both safe-integer boundaries, every checked-in number vector,
and deterministic repeated output. Add the Python asset test for
the four vendored digests, exact provenance keys/values, deterministic vector
regeneration into a temporary directory, Package resource mode, and Xcode
scheme inclusion.

- [ ] **Step 2: Observe RED before production files exist**

Push a test-only evidence ref and run Native Mobile CI at that exact SHA.
Initial compile failure for the wished-for API is only the first RED. Add the
smallest compile-safe test seam if needed and continue until at least the
canonical byte/validation/vector assertions fail for their intended behavior.
On homeserver run:

```text
/home/jason/.local/bin/uv run python -m unittest \
  tests.test_swift_canonical_runtime_assets -v
```

Record exact SHA, commands, exit codes, and expected failure reasons. Do not
claim a missing test target/import as complete behavioral RED evidence.

- [ ] **Step 3: Vendor pinned sources and implement the wrapper minimally**

Acquire only the four pinned upstream files, verify their bytes before adding
them, then implement `JSONValue`, `CanonicalJSON`, and `TypedID` to satisfy the
frozen contract. Do not add ledger, transport, registry, or application APIs.
Use `apply_patch` for repository files; network download output is input, not a
write path.

- [ ] **Step 4: Generate the fixed vector asset on homeserver**

Run the checked-in generator in a dedicated homeserver clone, compare its
output byte-for-byte to the committed fixture, and leave the clone clean. The
test suite may validate regeneration into a temporary path but may not rewrite
the committed fixture.

- [ ] **Step 5: Verify GREEN at one exact candidate SHA**

Homeserver gates:

```text
/home/jason/.local/bin/uv run python -m unittest \
  tests.test_swift_canonical_runtime_assets \
  tests.test_contract_codegen tests.test_contract_authority -v

git diff --no-renames --name-only -z f39a025..HEAD |
  /home/jason/.local/bin/uv run python tools/contracts/check_authority.py

git diff --check f39a025..HEAD
git status --porcelain=v1
```

Native Mobile CI at the same SHA must show `CanonicalJSONTests` executed with
zero failures and must keep the iOS and Watch targets green.

The mechanically generated 2,048-vector fixture is reviewed by deterministic
regeneration and SHA/byte equality, not by asking a quality reviewer to inspect
thousands of JSON lines manually. Production wrapper and tests remain the
human review surface.

- [ ] **Step 6: Independent reviews and integration**

Run specification review against only this card and exact packet diff, then
quality review only after specification PASS. Critical/Important findings are
fixed by the same implementation channel, retested, and re-reviewed. Minor
adjacent Task 5 requirements go to their named packet. Integrate one exact
candidate commit and write the 5A verification record before marking 5A
`VERIFIED` and activating 5B.

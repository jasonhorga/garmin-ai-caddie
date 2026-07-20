from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_pairs)


def _source_digest(registry_root: Path) -> str:
    repo_root = registry_root.parents[1]
    paths = sorted(registry_root.rglob("*.json")) + [repo_root / "tools/contracts/generate_contracts.py"]
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(repo_root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        raw = path.read_bytes()
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _swift_name(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def _swift_array(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def generate_all(registry_root: Path, output_root: Path) -> dict[str, str]:
    del output_root
    canonical = _load(registry_root / "canonical_object_registry.json")
    events = _load(registry_root / "event_kind_registry.json")
    reasons = _load(registry_root / "reason_codes.json")
    descriptors = dict(sorted(canonical["objects"].items()))
    source_digest = _source_digest(registry_root)
    kinds = sorted(events["kinds"])
    submission_classes = {
        kind: events["kinds"][kind].get("submissionClass", "ordinary_event")
        for kind in kinds
    }
    reason_codes = sorted(reasons["codes"])
    limits = reasons["roundTransportLimits"]

    python = (
        "# generated; do not edit\n"
        f"CANONICAL_CONTRACT_SOURCE_SHA256 = {source_digest!r}\n"
        f"CANONICAL_OBJECT_DESCRIPTORS = {descriptors!r}\n"
        "EVENT_KINDS = " + repr(tuple(kinds)) + "\n"
        "EVENT_SUBMISSION_CLASSES = " + repr(submission_classes) + "\n"
        "REASON_CODES = " + repr(tuple(reason_codes)) + "\n"
        "ROUND_TRANSPORT_LIMITS = " + repr(dict(sorted(limits.items()))) + "\n"
    )
    swift_descriptor_rows = "\n".join(
        "        " + json.dumps(raw["domainTag"]) + ": CanonicalObjectDescriptor("
        + "objectName: " + json.dumps(name)
        + ", domainTag: " + json.dumps(raw["domainTag"])
        + ", schemaRef: " + json.dumps(raw["schemaRef"])
        + ", includedFields: " + _swift_array(raw["includedFields"])
        + ", excludedFields: " + _swift_array(raw["excludedFields"]) + "),"
        for name, raw in descriptors.items()
    )
    swift_kind_declarations = "".join(
        f'\n    public static let {_swift_name(value)} = RoundEventKind(rawValue: "{value}")'
        for value in kinds
    )
    swift_reasons = "\n".join(
        f'    public static let {_swift_name(value)} = ReasonCode(rawValue: "{value}")'
        for value in reason_codes
    )
    swift_known_kinds = _swift_array(kinds)
    if submission_classes:
        swift_submission_classes = "[\n" + "\n".join(
            f'        {json.dumps(kind)}: .{_swift_name(value)},'
            for kind, value in submission_classes.items()
        ) + "\n    ]"
    else:
        swift_submission_classes = "[:]"
    swift = f"""// generated; do not edit
public let canonicalContractSourceSHA256 = {json.dumps(source_digest)}

public struct CanonicalObjectDescriptor: Sendable, Equatable {{
    public let objectName: String
    public let domainTag: String
    public let schemaRef: String
    public let includedFields: [String]
    public let excludedFields: [String]
}}

public enum GeneratedCanonicalObjects {{
    public static let byDomain: [String: CanonicalObjectDescriptor] = [
{swift_descriptor_rows}
    ]
}}

public enum RoundEventSubmissionClass: String, Codable, Sendable {{
    case ordinaryEvent = "ordinary_event"
    case resolutionPrerequisite = "resolution_prerequisite"
    case ordinaryOrResolutionCommit = "ordinary_or_resolution_commit"
    case resolutionCommitOnly = "resolution_commit_only"
}}

public struct RoundEventKind: RawRepresentable, Codable, Hashable, Sendable {{
    public let rawValue: String
    public init(rawValue: String) {{ self.rawValue = rawValue }}
    public init(from decoder: Decoder) throws {{
        self.rawValue = try decoder.singleValueContainer().decode(String.self)
    }}
    public func encode(to encoder: Encoder) throws {{
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }}
    public static let knownValues: Set<String> = {swift_known_kinds}
    public static let submissionClasses: [String: RoundEventSubmissionClass] = {swift_submission_classes}{swift_kind_declarations}
}}

public struct ReasonCode: RawRepresentable, Codable, Hashable, Sendable {{
    public let rawValue: String
    public init(rawValue: String) {{ self.rawValue = rawValue }}
    public init(from decoder: Decoder) throws {{
        self.rawValue = try decoder.singleValueContainer().decode(String.self)
    }}
    public func encode(to encoder: Encoder) throws {{
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }}
{swift_reasons}
}}

public enum RoundTransportLimits {{
    public static let maxHttpBodyBytes = {limits["maxHttpBodyBytes"]}
    public static let maxEventsPerBatch = {limits["maxEventsPerBatch"]}
    public static let maxEventCanonicalBytes = {limits["maxEventCanonicalBytes"]}
    public static let maxEventJsonDepth = {limits["maxEventJsonDepth"]}
    public static let maxRawJsonDepth = {limits["maxRawJsonDepth"]}
    public static let maxJsonKeyCharacters = {limits["maxJsonKeyCharacters"]}
    public static let maxJsonStringCharacters = {limits["maxJsonStringCharacters"]}
    public static let maxDeadLetterRetainedBytes = {limits["maxDeadLetterRetainedBytes"]}
    public static let maxDeadLettersPerRound = {limits["maxDeadLettersPerRound"]}
    public static let maxDeadLetterPageSize = {limits["maxDeadLetterPageSize"]}
    public static let maxConsumerEpochCharacters = {limits["maxConsumerEpochCharacters"]}
    public static let maxMergeSourceIncarnations = {limits["maxMergeSourceIncarnations"]}
    public static let maxSyncPathIdCharacters = {limits["maxSyncPathIdCharacters"]}
    public static let maxReplayPageSize = {limits["maxReplayPageSize"]}
}}
"""
    typescript = (
        "// generated; do not edit\n"
        + f"export const canonicalContractSourceSHA256 = {json.dumps(source_digest)} as const\n"
        + "export const canonicalObjectDescriptors = "
        + json.dumps(descriptors, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + " as const\n"
        + "export const roundEventKinds = " + json.dumps(kinds) + " as const\n"
        + "export const roundEventSubmissionClasses = "
        + json.dumps(submission_classes, sort_keys=True)
        + " as const\n"
        + "export const reasonCodes = " + json.dumps(reason_codes) + " as const\n"
        + "export const roundTransportLimits = "
        + json.dumps(limits, sort_keys=True)
        + " as const\n"
        + "export type RoundEventKind = typeof roundEventKinds[number] | (string & {})\n"
    )
    return {
        "ai_caddie/contracts/generated.py": python,
        "mobile/ios/AICaddieDomain/GeneratedContracts.swift": swift,
        "web_v2/src/contracts/generated.ts": typescript,
    }


if __name__ == "__main__":
    for relative, content in generate_all(Path("contracts/canonical"), Path(".")).items():
        target = Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))

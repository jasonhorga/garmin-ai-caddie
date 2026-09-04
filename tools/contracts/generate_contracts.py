from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


_EVENT_KIND_REGISTRY_SCHEMA = "ai-caddie-event-kind-registry-v1"
_REASON_CODE_REGISTRY_SCHEMA = "ai-caddie-reason-code-registry-v1"
_EVENT_KIND_REGISTRY_KEYS = frozenset({"schema", "kinds"})
_REASON_CODE_REGISTRY_KEYS = frozenset({"schema", "codes", "roundTransportLimits"})
_MOBILE_EVENT_SANITIZER_FIXTURE = "fixtures/mobile_event_sanitizer_golden.json"
_MOBILE_EVENT_SANITIZER_SWIFT_RESOURCE = (
    "mobile/ios/AICaddieTests/Fixtures/mobile_event_sanitizer_golden.json"
)
_SUBMISSION_CLASSES = frozenset(
    {
        "ordinary_event",
        "resolution_prerequisite",
        "ordinary_or_resolution_commit",
        "resolution_commit_only",
    }
)
_ROUND_TRANSPORT_LIMIT_KEYS = (
    "maxHttpBodyBytes",
    "maxEventsPerBatch",
    "maxEventCanonicalBytes",
    "maxEventJsonDepth",
    "maxRawJsonDepth",
    "maxJsonKeyCharacters",
    "maxJsonStringCharacters",
    "maxDeadLetterRetainedBytes",
    "maxDeadLettersPerRound",
    "maxDeadLetterPageSize",
    "maxConsumerEpochCharacters",
    "maxMergeSourceIncarnations",
    "maxSyncPathIdCharacters",
    "maxReplayPageSize",
)
_JAVASCRIPT_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_RAW_NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", re.ASCII)
_SWIFT_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)
_SWIFT_RESERVED_WORDS = frozenset(
    {
        "Self",
        "Type",
        "actor",
        "any",
        "as",
        "associatedtype",
        "associativity",
        "async",
        "await",
        "borrowing",
        "break",
        "case",
        "catch",
        "class",
        "consume",
        "consuming",
        "continue",
        "convenience",
        "copy",
        "default",
        "defer",
        "deinit",
        "didSet",
        "discard",
        "distributed",
        "do",
        "dynamic",
        "each",
        "else",
        "enum",
        "extension",
        "fallthrough",
        "false",
        "fileprivate",
        "final",
        "for",
        "func",
        "get",
        "guard",
        "if",
        "import",
        "in",
        "indirect",
        "infix",
        "init",
        "inout",
        "internal",
        "is",
        "isolated",
        "lazy",
        "left",
        "let",
        "macro",
        "mutating",
        "nil",
        "none",
        "nonisolated",
        "nonmutating",
        "open",
        "operator",
        "optional",
        "override",
        "package",
        "postfix",
        "precedence",
        "precedencegroup",
        "prefix",
        "private",
        "protocol",
        "public",
        "repeat",
        "required",
        "rethrows",
        "return",
        "right",
        "self",
        "sending",
        "set",
        "some",
        "static",
        "struct",
        "subscript",
        "super",
        "switch",
        "throw",
        "throws",
        "true",
        "try",
        "typealias",
        "unowned",
        "var",
        "weak",
        "where",
        "while",
        "willSet",
    }
)
_ROUND_EVENT_KIND_MEMBERS = frozenset(
    {"rawValue", "init", "encode", "knownValues", "submissionClasses"}
)
_REASON_CODE_MEMBERS = frozenset({"rawValue", "init", "encode"})


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
    # The authority manifest describes ownership and audit pins; it is not a
    # contract input and must not invalidate the generated declaration digest.
    paths = sorted(
        path
        for path in registry_root.rglob("*.json")
        if path != registry_root / "authority.json"
    ) + [repo_root / "tools/contracts/generate_contracts.py"]
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


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_exact_keys(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"{label} keys must be exactly {sorted(expected)!r}; "
            f"missing={missing!r}; extra={extra!r}"
        )


def _validate_raw_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or _RAW_NAME.fullmatch(value) is None:
        raise ValueError(
            f"{label} must match ASCII lower snake case "
            f"[a-z][a-z0-9]*(?:_[a-z0-9]+)*; got {value!r}"
        )
    return value


def _validate_swift_names(
    raw_values: list[str],
    type_name: str,
    existing_members: frozenset[str],
) -> dict[str, str]:
    by_raw: dict[str, str] = {}
    by_identifier: dict[str, str] = {}
    for raw_value in sorted(raw_values):
        identifier = _swift_name(raw_value)
        if _SWIFT_IDENTIFIER.fullmatch(identifier) is None:
            raise ValueError(
                f"invalid Swift identifier in {type_name}: {identifier!r} from {raw_value!r}"
            )
        if identifier in _SWIFT_RESERVED_WORDS:
            raise ValueError(
                f"Swift reserved word in {type_name}: {identifier} from {raw_value!r}"
            )
        if identifier in existing_members:
            raise ValueError(
                f"{type_name} member collision: {identifier} from {raw_value!r}"
            )
        previous = by_identifier.get(identifier)
        if previous is not None:
            raise ValueError(
                f"Swift identifier collision in {type_name}: {identifier} "
                f"from {previous!r} and {raw_value!r}"
            )
        by_raw[raw_value] = identifier
        by_identifier[identifier] = raw_value
    return by_raw


def _validate_event_registry(
    raw_registry: Any,
) -> tuple[list[str], dict[str, str], dict[str, str]]:
    registry = _require_object(raw_registry, "event kind registry")
    _require_exact_keys(registry, _EVENT_KIND_REGISTRY_KEYS, "event kind registry")
    if registry["schema"] != _EVENT_KIND_REGISTRY_SCHEMA:
        raise ValueError(
            f"event kind registry schema must be {_EVENT_KIND_REGISTRY_SCHEMA!r}; "
            f"got {registry['schema']!r}"
        )
    kinds_object = registry["kinds"]
    if not isinstance(kinds_object, dict):
        raise ValueError("event kind registry kinds must be an object")

    kinds = sorted(kinds_object)
    submission_classes: dict[str, str] = {}
    for kind in kinds:
        _validate_raw_name(kind, "event kind name")
        rule = kinds_object[kind]
        if not isinstance(rule, dict):
            raise ValueError(f"event rule for {kind} must be an object")
        submission_class = rule.get("submissionClass", "ordinary_event")
        if not isinstance(submission_class, str) or submission_class not in _SUBMISSION_CLASSES:
            raise ValueError(
                f"submissionClass for {kind} must be one of {sorted(_SUBMISSION_CLASSES)!r}; "
                f"got {submission_class!r}"
            )
        submission_classes[kind] = submission_class

    swift_names = _validate_swift_names(kinds, "RoundEventKind", _ROUND_EVENT_KIND_MEMBERS)
    return kinds, submission_classes, swift_names


def _validate_reason_registry(
    raw_registry: Any,
) -> tuple[list[str], dict[str, int], dict[str, str]]:
    registry = _require_object(raw_registry, "reason code registry")
    _require_exact_keys(registry, _REASON_CODE_REGISTRY_KEYS, "reason code registry")
    if registry["schema"] != _REASON_CODE_REGISTRY_SCHEMA:
        raise ValueError(
            f"reason code registry schema must be {_REASON_CODE_REGISTRY_SCHEMA!r}; "
            f"got {registry['schema']!r}"
        )
    codes_value = registry["codes"]
    if not isinstance(codes_value, list):
        raise ValueError("reason code registry codes must be a list")

    codes: list[str] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for raw_code in codes_value:
        code = _validate_raw_name(raw_code, "reason code name")
        if code in seen:
            duplicates.add(code)
        seen.add(code)
        codes.append(code)
    if duplicates:
        raise ValueError(f"reason codes must be unique; duplicates={sorted(duplicates)!r}")

    limits_object = registry["roundTransportLimits"]
    if not isinstance(limits_object, dict):
        raise ValueError("roundTransportLimits must be an object")
    expected_limit_keys = frozenset(_ROUND_TRANSPORT_LIMIT_KEYS)
    _require_exact_keys(limits_object, expected_limit_keys, "roundTransportLimits")
    limits: dict[str, int] = {}
    for key in sorted(expected_limit_keys):
        value = limits_object[key]
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            or value > _JAVASCRIPT_MAX_SAFE_INTEGER
        ):
            raise ValueError(
                f"roundTransportLimits.{key} must be a positive integer no greater than "
                f"{_JAVASCRIPT_MAX_SAFE_INTEGER}; got {value!r}"
            )
        limits[key] = value

    sorted_codes = sorted(codes)
    swift_names = _validate_swift_names(sorted_codes, "ReasonCode", _REASON_CODE_MEMBERS)
    return sorted_codes, limits, swift_names


def _swift_array(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def generate_all(registry_root: Path, output_root: Path) -> dict[str, str]:
    del output_root
    canonical = _load(registry_root / "canonical_object_registry.json")
    events = _load(registry_root / "event_kind_registry.json")
    reasons = _load(registry_root / "reason_codes.json")
    descriptors = dict(sorted(canonical["objects"].items()))
    kinds, submission_classes, swift_kind_names = _validate_event_registry(events)
    reason_codes, limits, swift_reason_names = _validate_reason_registry(reasons)
    source_digest = _source_digest(registry_root)

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
        f'\n    public static let {swift_kind_names[value]} = RoundEventKind(rawValue: "{value}")'
        for value in kinds
    )
    swift_reasons = "\n".join(
        f'    public static let {swift_reason_names[value]} = ReasonCode(rawValue: "{value}")'
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


def generate_shared_resource_outputs(registry_root: Path) -> dict[str, bytes]:
    source = registry_root / _MOBILE_EVENT_SANITIZER_FIXTURE
    raw = source.read_bytes()
    corpus = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    if (
        not isinstance(corpus, dict)
        or set(corpus) != {"schema", "cases"}
        or corpus.get("schema") != "ai-caddie-mobile-event-sanitizer-golden-v1"
        or not isinstance(corpus.get("cases"), list)
        or not corpus["cases"]
    ):
        raise ValueError("mobile event sanitizer golden corpus is invalid")
    return {_MOBILE_EVENT_SANITIZER_SWIFT_RESOURCE: raw}


if __name__ == "__main__":
    registry_root = Path("contracts/canonical")
    generated_bytes = {
        relative: content.encode("utf-8")
        for relative, content in generate_all(registry_root, Path(".")).items()
    }
    generated_bytes.update(generate_shared_resource_outputs(registry_root))
    for relative, content in generated_bytes.items():
        target = Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterator


_SCHEMA = "ai-caddie-storage-v1-shapes-v1"
_OUTPUT = "mobile/ios/AICaddieDomain/GeneratedStorageV1Shape.swift"
_GENERATOR = "tools/contracts/generate_storage_v1_shape.py"
_TOP_KEYS = frozenset({"schema", "roots", "types", "policies", "profiles"})
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*", re.ASCII)

_ROOT_TARGETS = (
    ("storageDocument", "DomainLedgerStateV1"),
    ("legacyV1EventBatchBody", "LegacyV1EventBatchBody"),
)
_TYPE_ORDER = (
    "StoredEventV1",
    "OriginSequenceState",
    "CanonicalStringSet",
    "DomainLedgerStateV1",
    "LegacyDomainAlias",
    "LegacyWireBinding",
    "PreparedLegacyV1Slot",
    "PreparedLegacyV1Batch",
    "LegacyV1TerminalStatus",
    "LegacyV1EventReceipt",
    "LegacyV1OutboxRecord",
    "LegacyV1TransportAnomaly",
    "WatchTerminalReceiptRelayObligation",
    "WatchTerminalReceiptRelayConfirmation",
    "LegacyV1EventBatchBody",
    "RoundEventKind",
    "JSONValue",
)
_TYPE_KINDS = {
    "StoredEventV1": "record",
    "OriginSequenceState": "record",
    "CanonicalStringSet": "collection",
    "DomainLedgerStateV1": "record",
    "LegacyDomainAlias": "record",
    "LegacyWireBinding": "record",
    "PreparedLegacyV1Slot": "record",
    "PreparedLegacyV1Batch": "record",
    "LegacyV1TerminalStatus": "closedEnum",
    "LegacyV1EventReceipt": "record",
    "LegacyV1OutboxRecord": "record",
    "LegacyV1TransportAnomaly": "record",
    "WatchTerminalReceiptRelayObligation": "record",
    "WatchTerminalReceiptRelayConfirmation": "record",
    "LegacyV1EventBatchBody": "record",
    "RoundEventKind": "openString",
    "JSONValue": "recursiveJSONValue",
}
_RECORD_MEMBERS = {
    "StoredEventV1": (
        "eventId",
        "originDeviceId",
        "originEpoch",
        "clientSequence",
        "roundId",
        "kind",
        "payload",
        "occurredAt",
    ),
    "OriginSequenceState": (
        "originDeviceId",
        "originEpoch",
        "lastReservedClientSequence",
    ),
    "DomainLedgerStateV1": (
        "storageVersion",
        "origin",
        "events",
        "outbox",
        "deadLetters",
        "receipts",
        "legacyWireBindings",
        "preparedLegacyV1Batches",
        "watchTerminalReceiptRelayObligations",
        "watchTerminalReceiptRelayConfirmations",
        "migrationMarkers",
        "transportAnomalies",
    ),
    "LegacyDomainAlias": ("eventIdentity", "eventHash"),
    "LegacyWireBinding": (
        "roundId",
        "wireClientId",
        "wireEventId",
        "canonicalDomainIdentity",
        "canonicalDomainEventHash",
        "normalizedWireEnvelopeHash",
        "legacyAliases",
    ),
    "PreparedLegacyV1Slot": (
        "bindingKey",
        "exactNormalizedEnvelope",
        "exactNormalizedEnvelopeHash",
    ),
    "PreparedLegacyV1Batch": (
        "roundId",
        "orderedSlots",
        "exactRequestBody",
        "requestBodySha256",
        "idempotencyKey",
    ),
    "LegacyV1EventReceipt": (
        "eventIdentity",
        "eventHash",
        "status",
        "serverSequence",
    ),
    "LegacyV1OutboxRecord": (
        "eventIdentity",
        "eventHash",
        "receipt",
        "deadLetterReason",
    ),
    "LegacyV1TransportAnomaly": ("roundId", "code", "evidence"),
    "WatchTerminalReceiptRelayObligation": (
        "obligationId",
        "eventIdentity",
        "eventHash",
        "status",
    ),
    "WatchTerminalReceiptRelayConfirmation": (
        "confirmationId",
        "obligationId",
        "eventIdentity",
        "eventHash",
        "status",
    ),
    "LegacyV1EventBatchBody": ("roundId", "events"),
}
_POLICY_PROFILES = (
    ("rootCollection", "rootCollection"),
    ("preparedSlots", "preparedSlots"),
    ("requestBody", "requestBody"),
    ("eventOrEnvelope", "eventOrEnvelope"),
)
_PROFILE_KINDS = (
    ("ordinaryString", "stringScalars"),
    ("rootCollection", "count"),
    ("preparedSlots", "count"),
    ("requestBody", "base64"),
    ("eventOrEnvelope", "canonicalJSON"),
)
_EXPECTED_POLICY_PATHS = frozenset(
    {
        ("rootCollection", "events"),
        ("rootCollection", "outbox"),
        ("rootCollection", "deadLetters"),
        ("rootCollection", "receipts"),
        ("rootCollection", "legacyWireBindings"),
        ("rootCollection", "preparedLegacyV1Batches"),
        ("rootCollection", "watchTerminalReceiptRelayObligations"),
        ("rootCollection", "watchTerminalReceiptRelayConfirmations"),
        ("rootCollection", "migrationMarkers"),
        ("rootCollection", "transportAnomalies"),
        ("preparedSlots", "preparedLegacyV1Batches[*].orderedSlots"),
        ("requestBody", "preparedLegacyV1Batches[*].exactRequestBody"),
        ("eventOrEnvelope", "events[*]"),
        (
            "eventOrEnvelope",
            "preparedLegacyV1Batches[*].orderedSlots[*].exactNormalizedEnvelope",
        ),
    }
)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def _load(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_nonfinite,
    )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str] | frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != frozenset(expected):
        raise ValueError(
            f"{label} keys must be exactly {sorted(expected)!r}; "
            f"got {sorted(actual)!r}"
        )


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be an ASCII identifier")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _unique_order(names: list[str], expected: tuple[str, ...], label: str) -> None:
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate {label} name")
    if tuple(names) != expected:
        raise ValueError(f"{label} roster must be exactly {expected!r}")


def _limit_reference(
    value: Any,
    label: str,
    *,
    swift: str | None = None,
    literal: bool = False,
) -> dict[str, Any]:
    raw = _object(value, label)
    if len(raw) != 1 or not set(raw).issubset({"literal", "swift"}):
        raise ValueError(f"{label} must contain exactly one limit authority")
    if "literal" in raw:
        number = _integer(raw["literal"], f"{label}.literal")
        if not literal or number < 0:
            raise ValueError(f"{label} literal is not allowed")
    else:
        symbol = _string(raw["swift"], f"{label}.swift")
        if swift is None or symbol != swift:
            raise ValueError(f"{label} has an unknown Swift limit authority")
    return raw


def _validate_profile(value: Any, expected_name: str, expected_kind: str) -> dict[str, Any]:
    raw = _object(value, f"profile {expected_name}")
    name = _identifier(raw.get("name"), "profile name")
    kind = _identifier(raw.get("kind"), f"profile {name} kind")
    if name != expected_name or kind != expected_kind:
        raise ValueError(f"profile {expected_name} has an unknown declaration")
    if kind == "stringScalars":
        _exact_keys(raw, {"name", "kind", "maximum"}, f"profile {name}")
        _limit_reference(
            raw["maximum"],
            f"profile {name} maximum",
            swift="RoundTransportLimits.maxJsonStringCharacters",
        )
    elif name == "rootCollection":
        _exact_keys(raw, {"name", "kind", "maximum"}, f"profile {name}")
        maximum = _limit_reference(
            raw["maximum"],
            f"profile {name} maximum",
            literal=True,
        )
        if maximum["literal"] != 65_536:
            raise ValueError(f"profile {name} has an incompatible maximum")
    elif name == "preparedSlots":
        _exact_keys(
            raw,
            {"name", "kind", "minimum", "maximum"},
            f"profile {name}",
        )
        minimum = _limit_reference(
            raw["minimum"],
            f"profile {name} minimum",
            literal=True,
        )
        if minimum["literal"] != 1:
            raise ValueError(f"profile {name} has an incompatible minimum")
        _limit_reference(
            raw["maximum"],
            f"profile {name} maximum",
            swift="RoundTransportLimits.maxEventsPerBatch",
        )
    elif kind == "base64":
        _exact_keys(
            raw,
            {
                "name",
                "kind",
                "alphabet",
                "padding",
                "maximumTextScalars",
                "maximumDecodedBytes",
            },
            f"profile {name}",
        )
        if raw["alphabet"] != "standard" or raw["padding"] != "required":
            raise ValueError(f"profile {name} Base64 declaration is malformed")
        _limit_reference(
            raw["maximumTextScalars"],
            f"profile {name} maximumTextScalars",
            swift="StorageV1RawJSONGate.maximumStringScalars",
        )
        _limit_reference(
            raw["maximumDecodedBytes"],
            f"profile {name} maximumDecodedBytes",
            swift="RoundTransportLimits.maxHttpBodyBytes",
        )
    elif kind == "canonicalJSON":
        _exact_keys(
            raw,
            {"name", "kind", "maximumBytes", "maximumDepth"},
            f"profile {name}",
        )
        _limit_reference(
            raw["maximumBytes"],
            f"profile {name} maximumBytes",
            swift="RoundTransportLimits.maxEventCanonicalBytes",
        )
        _limit_reference(
            raw["maximumDepth"],
            f"profile {name} maximumDepth",
            swift="RoundTransportLimits.maxEventJsonDepth",
        )
    else:
        raise ValueError(f"unknown profile kind: {kind}")
    return raw


def _validate_policy_target(policy: str, value: dict[str, Any], label: str) -> None:
    kind = value.get("kind")
    valid = False
    if policy == "rootCollection":
        valid = kind in {"array", "dynamicMap"} or (
            kind == "ref" and value.get("name") == "CanonicalStringSet"
        )
    elif policy == "preparedSlots":
        valid = kind == "array"
    elif policy == "requestBody":
        valid = kind == "scalar" and value.get("name") == "base64Data"
    elif policy == "eventOrEnvelope":
        valid = kind == "ref" and value.get("name") in {
            "StoredEventV1",
            "JSONValue",
        }
    if not valid:
        raise ValueError(f"{label} has a wrong-shaped policy target")


def _validate_shape(
    value: Any,
    label: str,
    *,
    type_names: frozenset[str],
    policy_names: frozenset[str],
    profile_names: frozenset[str],
    used_policies: set[str],
    used_profiles: set[str],
) -> dict[str, Any]:
    raw = _object(value, label)
    kind = _identifier(raw.get("kind"), f"{label} kind")
    if kind == "scalar":
        scalar = _identifier(raw.get("name"), f"{label} scalar")
        if scalar == "string":
            _exact_keys(raw, {"kind", "name", "profile"}, label)
            profile = _identifier(raw["profile"], f"{label} profile")
            if profile not in profile_names:
                raise ValueError(f"{label} references unknown profile {profile}")
            used_profiles.add(profile)
        elif scalar in {"int", "base64Data"}:
            _exact_keys(raw, {"kind", "name"}, label)
        else:
            raise ValueError(f"{label} has unknown scalar {scalar}")
    elif kind == "ref":
        _exact_keys(raw, {"kind", "name"}, label)
        name = _identifier(raw["name"], f"{label} reference")
        if name not in type_names:
            raise ValueError(f"{label} has dangling reference {name}")
    elif kind == "array":
        _exact_keys(raw, {"kind", "items"}, label)
        _validate_shape(
            raw["items"],
            f"{label} items",
            type_names=type_names,
            policy_names=policy_names,
            profile_names=profile_names,
            used_policies=used_policies,
            used_profiles=used_profiles,
        )
    elif kind == "dynamicMap":
        _exact_keys(raw, {"kind", "values"}, label)
        _validate_shape(
            raw["values"],
            f"{label} values",
            type_names=type_names,
            policy_names=policy_names,
            profile_names=profile_names,
            used_policies=used_policies,
            used_profiles=used_profiles,
        )
    elif kind == "nullable":
        _exact_keys(raw, {"kind", "value"}, label)
        _validate_shape(
            raw["value"],
            f"{label} nullable value",
            type_names=type_names,
            policy_names=policy_names,
            profile_names=profile_names,
            used_policies=used_policies,
            used_profiles=used_profiles,
        )
    elif kind == "constrained":
        _exact_keys(raw, {"kind", "policy", "value"}, label)
        policy = _identifier(raw["policy"], f"{label} policy")
        if policy not in policy_names:
            raise ValueError(f"{label} references unknown policy {policy}")
        target = _object(raw["value"], f"{label} constrained value")
        _validate_policy_target(policy, target, label)
        used_policies.add(policy)
        _validate_shape(
            target,
            f"{label} constrained value",
            type_names=type_names,
            policy_names=policy_names,
            profile_names=profile_names,
            used_policies=used_policies,
            used_profiles=used_profiles,
        )
    elif kind == "literal":
        _exact_keys(raw, {"kind", "scalar", "value"}, label)
        if raw["scalar"] != "int":
            raise ValueError(f"{label} has unknown literal scalar")
        _integer(raw["value"], f"{label} literal")
    elif kind == "record":
        _exact_keys(raw, {"kind", "members"}, label)
        members = _array(raw["members"], f"{label} members")
        member_names: list[str] = []
        for index, member_value in enumerate(members):
            member = _object(member_value, f"{label} member {index}")
            _exact_keys(member, {"name", "shape"}, f"{label} member {index}")
            member_name = _identifier(member["name"], f"{label} member {index} name")
            member_names.append(member_name)
            _validate_shape(
                member["shape"],
                f"{label}.{member_name}",
                type_names=type_names,
                policy_names=policy_names,
                profile_names=profile_names,
                used_policies=used_policies,
                used_profiles=used_profiles,
            )
        if len(member_names) != len(set(member_names)):
            raise ValueError(f"{label} has duplicate record members")
    elif kind == "collection":
        _exact_keys(raw, {"kind", "representation", "items"}, label)
        if raw["representation"] != "sortedUniqueArray":
            raise ValueError(f"{label} has unknown collection representation")
        _validate_shape(
            raw["items"],
            f"{label} items",
            type_names=type_names,
            policy_names=policy_names,
            profile_names=profile_names,
            used_policies=used_policies,
            used_profiles=used_profiles,
        )
    elif kind == "openString":
        _exact_keys(raw, {"kind", "profile"}, label)
        profile = _identifier(raw["profile"], f"{label} profile")
        if profile not in profile_names:
            raise ValueError(f"{label} references unknown profile {profile}")
        used_profiles.add(profile)
    elif kind == "closedEnum":
        _exact_keys(raw, {"kind", "values"}, label)
        values = _array(raw["values"], f"{label} values")
        normalized = [_string(item, f"{label} value") for item in values]
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError(f"{label} closed enum values must be unique and non-empty")
    elif kind == "recursiveJSONValue":
        _exact_keys(raw, {"kind", "stringProfile"}, label)
        profile = _identifier(raw["stringProfile"], f"{label} string profile")
        if profile not in profile_names:
            raise ValueError(f"{label} references unknown profile {profile}")
        used_profiles.add(profile)
    else:
        raise ValueError(f"{label} has unknown descriptor kind {kind}")
    return raw


def _child_shapes(shape: dict[str, Any]) -> Iterator[dict[str, Any]]:
    kind = shape["kind"]
    if kind == "record":
        for member in shape["members"]:
            yield member["shape"]
    elif kind in {"array", "collection"}:
        yield shape["items"]
    elif kind == "dynamicMap":
        yield shape["values"]
    elif kind in {"nullable", "constrained"}:
        yield shape["value"]


def _reachable_types(
    roots: list[dict[str, Any]],
    types: dict[str, dict[str, Any]],
) -> set[str]:
    reachable: set[str] = set()

    def visit(shape: dict[str, Any]) -> None:
        if shape["kind"] == "ref":
            name = shape["name"]
            if name in reachable:
                return
            reachable.add(name)
            visit(types[name])
            return
        for child in _child_shapes(shape):
            visit(child)

    for root in roots:
        visit(root["shape"])
    return reachable


def _flatten_policy_paths(
    roots: list[dict[str, Any]],
    types: dict[str, dict[str, Any]],
) -> frozenset[tuple[str, str]]:
    result: set[tuple[str, str]] = set()

    def append(path: str, component: str) -> str:
        return f"{path}.{component}" if path else component

    def visit(shape: dict[str, Any], path: str, resolving: frozenset[str]) -> None:
        kind = shape["kind"]
        if kind == "constrained":
            occurrence = (shape["policy"], path)
            if occurrence in result:
                raise ValueError(
                    "duplicate contextual policy occurrence: "
                    f"{occurrence!r}"
                )
            result.add(occurrence)
            visit(shape["value"], path, resolving)
        elif kind == "record":
            for member in shape["members"]:
                visit(member["shape"], append(path, member["name"]), resolving)
        elif kind in {"array", "collection"}:
            visit(shape["items"], f"{path}[*]", resolving)
        elif kind == "dynamicMap":
            visit(shape["values"], f"{path}[*]", resolving)
        elif kind == "nullable":
            visit(shape["value"], path, resolving)
        elif kind == "ref":
            name = shape["name"]
            if name not in resolving:
                visit(types[name], path, resolving | {name})

    for root in roots:
        visit(root["shape"], "", frozenset())
    return frozenset(result)


def _validate(document: Any) -> dict[str, Any]:
    raw = _object(document, "storage-v1 descriptor")
    _exact_keys(raw, _TOP_KEYS, "storage-v1 descriptor")
    if raw["schema"] != _SCHEMA:
        raise ValueError("unknown storage-v1 descriptor schema")

    profile_values = _array(raw["profiles"], "profiles")
    profile_names: list[str] = []
    if len(profile_values) != len(_PROFILE_KINDS):
        raise ValueError("profile roster has the wrong size")
    for value, (expected_name, expected_kind) in zip(profile_values, _PROFILE_KINDS):
        profile = _validate_profile(value, expected_name, expected_kind)
        profile_names.append(profile["name"])
    _unique_order(profile_names, tuple(name for name, _ in _PROFILE_KINDS), "profile")

    policy_values = _array(raw["policies"], "policies")
    policy_names: list[str] = []
    used_profiles: set[str] = set()
    if len(policy_values) != len(_POLICY_PROFILES):
        raise ValueError("policy roster has the wrong size")
    for value, (expected_name, expected_profile) in zip(
        policy_values,
        _POLICY_PROFILES,
    ):
        policy = _object(value, f"policy {expected_name}")
        _exact_keys(policy, {"name", "profile"}, f"policy {expected_name}")
        name = _identifier(policy["name"], "policy name")
        profile = _identifier(policy["profile"], f"policy {name} profile")
        if name != expected_name or profile != expected_profile:
            raise ValueError(f"policy {expected_name} has an unknown declaration")
        policy_names.append(name)
        used_profiles.add(profile)
    _unique_order(policy_names, tuple(name for name, _ in _POLICY_PROFILES), "policy")

    type_values = _array(raw["types"], "types")
    definitions: list[dict[str, Any]] = []
    type_names: list[str] = []
    for index, value in enumerate(type_values):
        definition = _object(value, f"type definition {index}")
        _exact_keys(definition, {"name", "shape"}, f"type definition {index}")
        name = _identifier(definition["name"], f"type definition {index} name")
        definitions.append(definition)
        type_names.append(name)
    _unique_order(type_names, _TYPE_ORDER, "type")

    type_name_set = frozenset(type_names)
    policy_name_set = frozenset(policy_names)
    profile_name_set = frozenset(profile_names)
    used_policies: set[str] = set()
    types: dict[str, dict[str, Any]] = {}
    for definition in definitions:
        name = definition["name"]
        shape = _object(definition["shape"], f"type {name} shape")
        if shape.get("kind") != _TYPE_KINDS[name]:
            raise ValueError(f"type {name} has an unknown definition kind")
        validated = _validate_shape(
            shape,
            f"type {name}",
            type_names=type_name_set,
            policy_names=policy_name_set,
            profile_names=profile_name_set,
            used_policies=used_policies,
            used_profiles=used_profiles,
        )
        if name in _RECORD_MEMBERS:
            members = tuple(member["name"] for member in validated["members"])
            if members != _RECORD_MEMBERS[name]:
                raise ValueError(f"type {name} has unknown or malformed members")
        types[name] = validated

    root_values = _array(raw["roots"], "roots")
    roots: list[dict[str, Any]] = []
    root_names: list[str] = []
    for index, value in enumerate(root_values):
        root = _object(value, f"root definition {index}")
        _exact_keys(root, {"name", "shape"}, f"root definition {index}")
        name = _identifier(root["name"], f"root definition {index} name")
        root_names.append(name)
        roots.append(root)
    _unique_order(root_names, tuple(name for name, _ in _ROOT_TARGETS), "root")
    for root, (_, target) in zip(roots, _ROOT_TARGETS):
        if root["shape"] != {"kind": "ref", "name": target}:
            raise ValueError(f"root {root['name']} has a malformed reference")
        _validate_shape(
            root["shape"],
            f"root {root['name']}",
            type_names=type_name_set,
            policy_names=policy_name_set,
            profile_names=profile_name_set,
            used_policies=used_policies,
            used_profiles=used_profiles,
        )

    reachable = _reachable_types(roots, types)
    if reachable != type_name_set:
        raise ValueError(
            f"unreachable type definitions: {sorted(type_name_set - reachable)!r}"
        )
    if used_policies != policy_name_set:
        raise ValueError(
            f"unused policies: {sorted(policy_name_set - used_policies)!r}"
        )
    if used_profiles != profile_name_set:
        raise ValueError(
            f"unused profiles: {sorted(profile_name_set - used_profiles)!r}"
        )
    policy_paths = _flatten_policy_paths(roots, types)
    if policy_paths != _EXPECTED_POLICY_PATHS:
        raise ValueError("contextual policy paths do not match the closed roster")
    return raw


def _source_digest(registry_root: Path) -> str:
    repo_root = registry_root.parents[1]
    paths = sorted(registry_root.rglob("*.json"))
    generator = repo_root / _GENERATOR
    if not paths or not generator.is_file():
        raise ValueError("storage-v1 source set is incomplete")
    digest = hashlib.sha256()
    for path in [*paths, generator]:
        relative = path.relative_to(repo_root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _swift_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _emit_shape(shape: dict[str, Any]) -> str:
    kind = shape["kind"]
    if kind == "scalar":
        if shape["name"] == "string":
            return f".scalar(.string(profile: .{shape['profile']}))"
        return f".scalar(.{shape['name']})"
    if kind == "ref":
        return f".reference({_swift_string(shape['name'])})"
    if kind == "array":
        return f".array({_emit_shape(shape['items'])})"
    if kind == "dynamicMap":
        return f".dynamicMap({_emit_shape(shape['values'])})"
    if kind == "nullable":
        return f".nullable({_emit_shape(shape['value'])})"
    if kind == "constrained":
        return (
            f".constrained(policy: .{shape['policy']}, "
            f"value: {_emit_shape(shape['value'])})"
        )
    if kind == "literal":
        return f".literalInt({shape['value']})"
    if kind == "record":
        members = ", ".join(
            ".init(name: "
            + _swift_string(member["name"])
            + ", shape: "
            + _emit_shape(member["shape"])
            + ")"
            for member in shape["members"]
        )
        return f".record([{members}])"
    if kind == "collection":
        return (
            f".collection(representation: .{shape['representation']}, "
            f"items: {_emit_shape(shape['items'])})"
        )
    if kind == "openString":
        return f".openString(profile: .{shape['profile']})"
    if kind == "closedEnum":
        values = ", ".join(_swift_string(value) for value in shape["values"])
        return f".closedEnum([{values}])"
    if kind == "recursiveJSONValue":
        return f".recursiveJSONValue(stringProfile: .{shape['stringProfile']})"
    raise ValueError(f"cannot emit unknown shape kind {kind}")


def _emit_limit(value: dict[str, Any]) -> str:
    if "literal" in value:
        return f".literal({value['literal']})"
    symbol = value["swift"]
    return f".authority(name: {_swift_string(symbol)}, value: {symbol})"


def _emit_profile(profile: dict[str, Any]) -> str:
    name = profile["name"]
    kind = profile["kind"]
    if kind == "stringScalars":
        descriptor = f".stringScalars(maximum: {_emit_limit(profile['maximum'])})"
    elif kind == "count":
        minimum = (
            _emit_limit(profile["minimum"])
            if "minimum" in profile
            else "nil"
        )
        descriptor = (
            f".count(minimum: {minimum}, "
            f"maximum: {_emit_limit(profile['maximum'])})"
        )
    elif kind == "base64":
        descriptor = (
            f".base64(alphabet: .{profile['alphabet']}, "
            f"padding: .{profile['padding']}, "
            f"maximumTextScalars: {_emit_limit(profile['maximumTextScalars'])}, "
            f"maximumDecodedBytes: {_emit_limit(profile['maximumDecodedBytes'])})"
        )
    else:
        descriptor = (
            f".canonicalJSON(maximumBytes: {_emit_limit(profile['maximumBytes'])}, "
            f"maximumDepth: {_emit_limit(profile['maximumDepth'])})"
        )
    return f"    .init(name: .{name}, descriptor: {descriptor}),"


_SWIFT_DECLARATIONS = """// generated; do not edit
internal enum StorageV1ProfileName {
    case ordinaryString
    case rootCollection
    case preparedSlots
    case requestBody
    case eventOrEnvelope
}

internal enum StorageV1PolicyName {
    case rootCollection
    case preparedSlots
    case requestBody
    case eventOrEnvelope
}

internal enum StorageV1CollectionRepresentation {
    case sortedUniqueArray
}

internal enum StorageV1Base64Alphabet {
    case standard
}

internal enum StorageV1Base64Padding {
    case required
}

internal enum StorageV1LimitReference {
    case literal(Int)
    case authority(name: String, value: Int)
}

internal enum StorageV1LimitProfileDescriptor {
    case stringScalars(maximum: StorageV1LimitReference)
    case count(minimum: StorageV1LimitReference?, maximum: StorageV1LimitReference)
    case base64(
        alphabet: StorageV1Base64Alphabet,
        padding: StorageV1Base64Padding,
        maximumTextScalars: StorageV1LimitReference,
        maximumDecodedBytes: StorageV1LimitReference
    )
    case canonicalJSON(
        maximumBytes: StorageV1LimitReference,
        maximumDepth: StorageV1LimitReference
    )
}

internal enum StorageV1ScalarDescriptor {
    case string(profile: StorageV1ProfileName)
    case int
    case base64Data
}

internal indirect enum StorageV1ShapeDescriptor {
    case scalar(StorageV1ScalarDescriptor)
    case reference(String)
    case array(StorageV1ShapeDescriptor)
    case dynamicMap(StorageV1ShapeDescriptor)
    case nullable(StorageV1ShapeDescriptor)
    case constrained(policy: StorageV1PolicyName, value: StorageV1ShapeDescriptor)
    case literalInt(Int)
    case record([StorageV1MemberDescriptor])
    case collection(
        representation: StorageV1CollectionRepresentation,
        items: StorageV1ShapeDescriptor
    )
    case openString(profile: StorageV1ProfileName)
    case closedEnum([String])
    case recursiveJSONValue(stringProfile: StorageV1ProfileName)
}

internal struct StorageV1MemberDescriptor {
    internal let name: String
    internal let shape: StorageV1ShapeDescriptor
}

internal struct StorageV1RootDescriptor {
    internal let name: String
    internal let shape: StorageV1ShapeDescriptor
}

internal struct StorageV1TypeDescriptor {
    internal let name: String
    internal let shape: StorageV1ShapeDescriptor
}

internal struct StorageV1PolicyDescriptor {
    internal let name: StorageV1PolicyName
    internal let profile: StorageV1ProfileName
}

internal struct StorageV1NamedLimitProfile {
    internal let name: StorageV1ProfileName
    internal let descriptor: StorageV1LimitProfileDescriptor
}

"""


def _emit(document: dict[str, Any], source_digest: str) -> str:
    profiles = "\n".join(_emit_profile(profile) for profile in document["profiles"])
    policies = "\n".join(
        f"    .init(name: .{policy['name']}, profile: .{policy['profile']}),"
        for policy in document["policies"]
    )
    roots = "\n".join(
        f"    .init(name: {_swift_string(root['name'])}, "
        f"shape: {_emit_shape(root['shape'])}),"
        for root in document["roots"]
    )
    types = "\n".join(
        f"    .init(name: {_swift_string(definition['name'])}, "
        f"shape: {_emit_shape(definition['shape'])}),"
        for definition in document["types"]
    )
    referenced_types = "\n".join(f"    {name}.self," for name in _TYPE_ORDER)
    return (
        _SWIFT_DECLARATIONS
        + f'internal let storageV1ShapeSourceSHA256 = "{source_digest}"\n\n'
        + "internal let storageV1ReferencedDomainTypes: [Any.Type] = [\n"
        + referenced_types
        + "\n]\n\n"
        + "internal let storageV1LimitProfiles: [StorageV1NamedLimitProfile] = [\n"
        + profiles
        + "\n]\n\n"
        + "internal let storageV1Policies: [StorageV1PolicyDescriptor] = [\n"
        + policies
        + "\n]\n\n"
        + "internal let storageV1Roots: [StorageV1RootDescriptor] = [\n"
        + roots
        + "\n]\n\n"
        + "internal let storageV1Types: [StorageV1TypeDescriptor] = [\n"
        + types
        + "\n]\n"
    )


def generate_all(registry_root: Path, output_root: Path) -> dict[str, str]:
    del output_root
    sources = sorted(registry_root.rglob("*.json"))
    if len(sources) != 1:
        raise ValueError("storage-v1 requires exactly one descriptor JSON source")
    document = _validate(_load(sources[0]))
    return {_OUTPUT: _emit(document, _source_digest(registry_root))}


if __name__ == "__main__":
    generated = generate_all(Path("contracts/storage-v1"), Path("."))
    for relative, content in generated.items():
        target = Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))

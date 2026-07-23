from __future__ import annotations

import json
import math
import unicodedata
from typing import Any

import rfc8785


class CanonicalJSONError(ValueError):
    pass


MAX_SAFE_INTEGER = 9_007_199_254_740_991


class _NegativeZeroInteger(int):
    pass


_NEGATIVE_ZERO_INTEGER = _NegativeZeroInteger(0)


def _validate(value: Any) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise CanonicalJSONError("strings must not contain surrogate code points")
        if unicodedata.normalize("NFC", value) != value:
            raise CanonicalJSONError("strings must be NFC")
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, _NegativeZeroInteger):
        raise CanonicalJSONError("integer negative zero is forbidden")
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalJSONError("integer exceeds safe range")
        return
    if isinstance(value, float):
        if not math.isfinite(value) or (value == 0.0 and math.copysign(1.0, value) < 0):
            raise CanonicalJSONError("non-finite and negative zero are forbidden")
        if value.is_integer() and abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalJSONError("integral float exceeds safe integer range")
        return
    if isinstance(value, list):
        for item in value:
            _validate(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError("object keys must be strings")
            _validate(key)
            _validate(item)
        return
    raise CanonicalJSONError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    _validate(value)
    try:
        return rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise CanonicalJSONError(str(exc)) from exc


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise CanonicalJSONError(f"duplicate object key: {key}")
        value[key] = child
    return value


def _parse_integer(token: str) -> int:
    if token == "-0":
        return _NEGATIVE_ZERO_INTEGER
    return int(token)


def _parse_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise CanonicalJSONError(f"non-finite number: {token}")
    return value


def parse_canonical_json(raw: str | bytes) -> Any:
    value = parse_unique_json(raw)
    _validate(value)
    return value


def parse_unique_json(raw: str | bytes) -> Any:
    """Decode transport JSON without collapsing duplicate keys.

    Canonical-value validation is deliberately separate so a syntactically
    unique batch can produce one durable reject for only the invalid event.
    Integer negative zero is retained as an internal int sentinel for that
    later validation step.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CanonicalJSONError(f"JSON bytes must be UTF-8: {exc}") from exc
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_int=_parse_integer,
            parse_float=_parse_float,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CanonicalJSONError(f"non-finite number: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalJSONError(str(exc)) from exc

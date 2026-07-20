from __future__ import annotations

import json
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pathspec


class AuthorityViolation(RuntimeError):
    pass


_AUTHORITY_SCHEMA = "ai-caddie-contract-authority-v1"
_AUTHORITY_KEYS = {
    "schema",
    "authoritativeInputs",
    "evidenceInputs",
    "canonicalRoots",
    "legacyAdapters",
    "forbiddenSymbols",
    "generatedGroups",
}
_REGISTRY_SCHEMA = "ai-caddie-canonical-object-registry-v1"
_LEGACY_ADAPTER_MODES = {
    "mobile/contracts/watch_input_event.schema.json": "adapter_only",
    "mobile/contracts/live_round_event.schema.json": "v1_compatibility_only",
}


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise AuthorityViolation(f"duplicate JSON key: {key}")
        value[key] = child
    return value


def _load_unique_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorityViolation(f"invalid JSON: {path}: {exc}") from exc


def _string_list(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AuthorityViolation(f"invalid {label}: expected string list")
    return value


def _validate_authority_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _AUTHORITY_KEYS:
        raise AuthorityViolation("invalid authority manifest top-level structure")
    if value["schema"] != _AUTHORITY_SCHEMA:
        raise AuthorityViolation(f"invalid authority manifest schema: {value['schema']!r}")

    for key in _AUTHORITY_KEYS - {"schema"}:
        if not isinstance(value[key], list):
            raise AuthorityViolation(f"invalid authority manifest field: {key}")

    for key in ("authoritativeInputs", "evidenceInputs"):
        allowed_keys = (
            {frozenset({"path", "sourceCommit", "gitBlobOid", "sha256"})}
            if key == "authoritativeInputs"
            else {
                frozenset({"path", "gitBlobOid", "sha256"}),
                frozenset({"path", "sourceCommit", "gitBlobOid", "sha256"}),
            }
        )
        for item in value[key]:
            if (
                not isinstance(item, dict)
                or frozenset(item) not in allowed_keys
                or not isinstance(item["path"], str)
                or not isinstance(item["gitBlobOid"], str)
                or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", item["gitBlobOid"])
                or not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                or (
                    "sourceCommit" in item
                    and (
                        not isinstance(item["sourceCommit"], str)
                        or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", item["sourceCommit"])
                    )
                )
            ):
                raise AuthorityViolation(f"invalid {key} declaration")

    _string_list(value["canonicalRoots"], label="canonicalRoots")
    for adapter in value["legacyAdapters"]:
        if not isinstance(adapter, dict) or set(adapter) != {
            "path", "mode", "allowedProperties", "forbiddenEnumValues",
        }:
            raise AuthorityViolation("invalid legacy adapter declaration")
        if (
            not isinstance(adapter["mode"], str)
            or adapter["mode"] not in set(_LEGACY_ADAPTER_MODES.values())
        ):
            raise AuthorityViolation(f"invalid legacy adapter mode: {adapter['mode']!r}")
        if not isinstance(adapter["path"], str):
            raise AuthorityViolation("invalid legacy adapter declaration")
        _string_list(adapter["allowedProperties"], label="legacy adapter allowedProperties")
        _string_list(adapter["forbiddenEnumValues"], label="legacy adapter forbiddenEnumValues")

    for rule in value["forbiddenSymbols"]:
        if not isinstance(rule, dict) or set(rule) != {"paths", "values"}:
            raise AuthorityViolation("invalid forbidden symbol declaration")
        _string_list(rule["paths"], label="forbidden symbol paths")
        _string_list(rule["values"], label="forbidden symbol values")

    for group in value["generatedGroups"]:
        if (
            not isinstance(group, dict)
            or set(group) != {"name", "sources", "outputs"}
            or not isinstance(group["name"], str)
            or not group["name"]
        ):
            raise AuthorityViolation("invalid generated group declaration")
        _string_list(group["sources"], label="generated group sources")
        _string_list(group["outputs"], label="generated group outputs")
    return value


def _validate_registry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema", "canonicalization", "typedIdAlgorithm", "objects",
    }:
        raise AuthorityViolation("invalid canonical object registry structure")
    if value["schema"] != _REGISTRY_SCHEMA:
        raise AuthorityViolation(f"invalid canonical object registry schema: {value['schema']!r}")
    if (
        not isinstance(value["canonicalization"], str)
        or not isinstance(value["typedIdAlgorithm"], str)
        or not isinstance(value["objects"], dict)
    ):
        raise AuthorityViolation("invalid canonical object registry structure")
    return value


def _git_output(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise AuthorityViolation(f"git pin lookup failed ({' '.join(args)}): {detail}") from exc


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    if isinstance(value, dict):
        return [item for key, child in value.items() for item in [key, *_strings(child)]]
    return []


def _json_pointer_exists(path: Path, fragment: str) -> bool:
    value: Any = _load_unique_json(path)
    if fragment == "":
        return True
    if not fragment.startswith("/"):
        return False
    try:
        for raw in fragment[1:].split("/"):
            token = raw.replace("~1", "/").replace("~0", "~")
            value = value[int(token)] if isinstance(value, list) else value[token]
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    return True


def _repo_relative_path(
    root: Path, value: Any, *, label: str, allow_gitwildmatch: bool = False,
) -> str:
    if not isinstance(value, str):
        raise AuthorityViolation(f"invalid {label}: expected string")
    body = value[1:] if allow_gitwildmatch and value.startswith("!") else value
    if allow_gitwildmatch and value.startswith("!!"):
        raise AuthorityViolation(f"invalid {label}: {value!r}")
    segments = body.split("/")
    if (
        not body
        or body.startswith("/")
        or "\\" in body
        or "\x00" in body
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise AuthorityViolation(f"invalid {label}: {value!r}")

    static_segments: list[str] = []
    for segment in segments:
        if allow_gitwildmatch and any(marker in segment for marker in "*?["):
            break
        static_segments.append(segment)
    resolved = root.joinpath(*static_segments).resolve()
    if resolved != root and root not in resolved.parents:
        raise AuthorityViolation(f"invalid {label}: {value!r}")
    return value


def check_authority(root: Path, *, changed_paths: list[str]) -> list[str]:
    root = root.resolve()
    manifest_path = root / "contracts/canonical/authority.json"
    manifest = _validate_authority_manifest(_load_unique_json(manifest_path))
    violations: list[str] = []
    legacy_adapters: list[tuple[dict[str, Any], str]] = []
    for adapter in manifest["legacyAdapters"]:
        relative = _repo_relative_path(root, adapter["path"], label="legacy adapter path")
        if _LEGACY_ADAPTER_MODES.get(relative) != adapter["mode"]:
            raise AuthorityViolation(f"legacy adapter mode mismatch: {relative}")
        legacy_adapters.append((adapter, relative))
    changed = {
        _repo_relative_path(root, value, label="changed path") for value in changed_paths
    }
    manifest_relative = manifest_path.relative_to(root).as_posix()
    roots = tuple(
        (root / _repo_relative_path(root, value, label="canonical root path")).resolve()
        for value in manifest["canonicalRoots"]
    )

    for collection, label in (
        (manifest["authoritativeInputs"], "authoritative input path"),
        (manifest["evidenceInputs"], "evidence input path"),
    ):
        for item in collection:
            relative = _repo_relative_path(root, item["path"], label=label)
            path = root / relative
            if not path.is_file():
                violations.append(f"declared authority input missing: {relative}")
                continue
            actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_sha != item["sha256"]:
                violations.append(f"pinned input sha256 mismatch: {relative}")
            current_blob = _git_output(root, "hash-object", "--", relative)
            if item.get("sourceCommit"):
                resolved_commit = _git_output(root, "rev-parse", f"{item['sourceCommit']}^{{commit}}")
                if resolved_commit != item["sourceCommit"]:
                    violations.append(f"pinned input commit mismatch: {relative}")
                source_blob = _git_output(root, "rev-parse", f"{item['sourceCommit']}:{relative}")
                pinned_blob = item.get("gitBlobOid")
                if current_blob != source_blob:
                    if current_blob == pinned_blob:
                        violations.append(f"pinned input sourceCommit content mismatch: {relative}")
                    elif source_blob == pinned_blob:
                        violations.append(f"pinned input current-vs-commit content mismatch: {relative}")
                    else:
                        violations.append(f"pinned input provenance mismatch: {relative}")
                elif source_blob != pinned_blob:
                    violations.append(f"pinned input gitBlobOid mismatch: {relative}")
            elif item.get("gitBlobOid"):
                if current_blob != item["gitBlobOid"]:
                    violations.append(f"pinned input working blob mismatch: {relative}")

    for adapter, relative in legacy_adapters:
        if relative not in changed or not (root / relative).is_file():
            continue
        payload = _load_unique_json(root / relative)
        properties = set(payload.get("properties") or {})
        unexpected = properties - set(adapter["allowedProperties"])
        if unexpected:
            violations.append(f"legacy contract expanded: {relative}: {sorted(unexpected)}")
        forbidden = set(adapter["forbiddenEnumValues"]) & set(_strings(payload))
        if forbidden:
            violations.append(f"legacy forbidden enum value: {relative}: {sorted(forbidden)}")

    for rule in manifest["forbiddenSymbols"]:
        patterns = [
            _repo_relative_path(
                root, value, label="forbidden symbol pattern", allow_gitwildmatch=True,
            )
            for value in rule["paths"]
        ]
        matcher = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
        for relative in changed:
            if relative == manifest_relative:
                continue
            if not matcher.match_file(relative):
                continue
            path = root / relative
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            for symbol in rule["values"]:
                token = rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])"
                if re.search(token, content):
                    violations.append(f"forbidden symbol {symbol}: {relative}")

    generated_groups: list[tuple[dict[str, Any], list[str], list[str]]] = []
    for group in manifest["generatedGroups"]:
        sources = [
            _repo_relative_path(
                root, value, label="generated source pattern", allow_gitwildmatch=True,
            )
            for value in group["sources"]
        ]
        outputs = [
            _repo_relative_path(root, value, label="generated output path")
            for value in group["outputs"]
        ]
        generated_groups.append((group, sources, outputs))

    generated_output_owners: dict[str, str] = {}
    for group, sources, outputs in generated_groups:
        if len(outputs) != len(set(outputs)):
            violations.append(f"duplicate generated output inside group {group['name']}")
        source_matcher = pathspec.PathSpec.from_lines("gitwildmatch", sources)
        for output in outputs:
            if source_matcher.match_file(output):
                violations.append(
                    f"generated output also matches a source in {group['name']}: {output}"
                )
        for output in outputs:
            previous = generated_output_owners.setdefault(output, group["name"])
            if previous != group["name"]:
                violations.append(
                    f"multiple generated owners for {output}: {previous}, {group['name']}"
                )

    for group, sources, outputs in generated_groups:
        source_matcher = pathspec.PathSpec.from_lines("gitwildmatch", sources)
        changed_sources = {relative for relative in changed if source_matcher.match_file(relative)}
        changed_outputs = changed & set(outputs)
        if changed_sources and not changed_outputs:
            violations.append(
                f"generated group {group['name']} changed a source without an owned output"
            )
        if changed_outputs and not changed_sources:
            violations.append(
                f"generated group {group['name']} changed an output without a source"
            )

    registry_path = root / "contracts/canonical/canonical_object_registry.json"
    if registry_path.is_file():
        registry = _validate_registry(_load_unique_json(registry_path))
        if registry.get("canonicalization") != "RFC8785+AI-Caddie-v1":
            violations.append("canonical object registry has wrong canonicalization")
        if registry.get("typedIdAlgorithm") != (
            "lowercaseHex(SHA-256(ASCII(domainTag+'\\u0000')||canonicalBytes))"
        ):
            violations.append("canonical object registry has wrong typedIdAlgorithm")
        seen_names: set[str] = set()
        seen_domains: set[str] = set()
        for name, descriptor in registry["objects"].items():
            if not isinstance(descriptor, dict) or set(descriptor) != {
                "domainTag", "schemaRef", "includedFields", "excludedFields"
            }:
                violations.append(f"invalid canonical descriptor keys: {name}")
                continue
            domain_tag = descriptor["domainTag"]
            if not isinstance(domain_tag, str):
                violations.append(f"invalid canonical object registry domainTag: {name}")
                continue
            if name in seen_names or domain_tag in seen_domains:
                violations.append(f"duplicate canonical object/domain: {name}")
                continue
            seen_names.add(name); seen_domains.add(domain_tag)
            if not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9.-]*/v[1-9][0-9]*", domain_tag, flags=re.ASCII
            ):
                violations.append(f"invalid canonical object registry domainTag: {name}")
            included = descriptor["includedFields"]
            excluded = descriptor["excludedFields"]
            if (
                not isinstance(included, list) or not included
                or not all(isinstance(value, str) for value in included)
                or ("*" in included and included != ["*"])
                or not isinstance(excluded, list)
                or not all(isinstance(value, str) for value in excluded)
                or set(included) & set(excluded)
            ):
                violations.append(f"invalid canonical field projection: {name}")
            if not isinstance(descriptor["schemaRef"], str):
                violations.append(f"invalid canonical schemaRef: {name}")
                continue
            schema_path, _, fragment = descriptor["schemaRef"].partition("#")
            schema_path = _repo_relative_path(
                root, schema_path, label=f"canonical schemaRef path for {name}"
            )
            resolved = (root / schema_path).resolve()
            if not any(resolved == value or value in resolved.parents for value in roots):
                violations.append(f"schemaRef escapes canonical roots: {name}")
                continue
            if not resolved.is_file() or not _json_pointer_exists(resolved, fragment):
                violations.append(f"unresolved canonical schemaRef: {name}")

    if violations:
        raise AuthorityViolation("; ".join(violations))
    return violations


if __name__ == "__main__":
    repo = Path.cwd()
    raw_paths = sys.stdin.buffer.read()
    if raw_paths and not raw_paths.endswith(b"\0"):
        raise AuthorityViolation("changed path input is not NUL-terminated")
    changed_paths = [os.fsdecode(value) for value in raw_paths[:-1].split(b"\0")] if raw_paths else []
    check_authority(repo, changed_paths=changed_paths)

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes

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


def _reject_non_finite_constant(value: str) -> Any:
    raise AuthorityViolation(f"non-finite JSON constant: {value}")


def _load_unique_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_non_finite_constant,
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

    canonical_roots = _string_list(value["canonicalRoots"], label="canonicalRoots")
    if not canonical_roots:
        raise AuthorityViolation("invalid canonicalRoots: expected a non-empty string list")
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
        paths = _string_list(rule["paths"], label="forbidden symbol paths")
        if not paths:
            raise AuthorityViolation(
                "invalid forbidden symbol paths: expected a non-empty string list"
            )
        _string_list(rule["values"], label="forbidden symbol values")

    generated_names: set[str] = set()
    for group in value["generatedGroups"]:
        if (
            not isinstance(group, dict)
            or set(group) != {"name", "sources", "outputs"}
            or not isinstance(group["name"], str)
            or not group["name"]
        ):
            raise AuthorityViolation("invalid generated group declaration")
        if group["name"] in generated_names:
            raise AuthorityViolation(f"duplicate generated group name: {group['name']}")
        generated_names.add(group["name"])
        sources = _string_list(group["sources"], label="generated group sources")
        outputs = _string_list(group["outputs"], label="generated group outputs")
        if not sources:
            raise AuthorityViolation(
                "invalid generated group sources: expected a non-empty string list"
            )
        if not outputs:
            raise AuthorityViolation(
                "invalid generated group outputs: expected a non-empty string list"
            )
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
    if re.search(r"%(?![0-9A-Fa-f]{2})", fragment):
        return False
    try:
        fragment = unquote_to_bytes(fragment).decode("utf-8")
    except UnicodeDecodeError:
        return False
    if fragment == "":
        return True
    if not fragment.startswith("/"):
        return False
    try:
        for raw in fragment[1:].split("/"):
            if re.search(r"~(?:[^01]|$)", raw):
                return False
            token = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", token, flags=re.ASCII):
                    return False
                value = value[int(token)]
            elif isinstance(value, dict):
                value = value[token]
            else:
                return False
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
    if allow_gitwildmatch and body.startswith("#"):
        raise AuthorityViolation(f"invalid {label}: comment-only pattern {value!r}")
    if allow_gitwildmatch and body != body.strip():
        raise AuthorityViolation(f"invalid {label}: non-normalized pattern {value!r}")
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
    try:
        resolved = root.joinpath(*static_segments).resolve()
    except (OSError, RuntimeError) as exc:
        raise AuthorityViolation(f"invalid {label}: {value!r}: {exc}") from exc
    if resolved != root and root not in resolved.parents:
        raise AuthorityViolation(f"invalid {label}: {value!r}")
    return value


def _compile_gitwildmatch(patterns: list[str], *, label: str) -> pathspec.PathSpec:
    try:
        matcher = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    except (ValueError, re.error) as exc:
        raise AuthorityViolation(f"invalid {label}: {exc}") from exc
    if not any(pattern.include is True for pattern in matcher.patterns):
        raise AuthorityViolation(f"invalid {label}: expected a positive include pattern")
    return matcher


def _existing_regular_file(path: Path, *, label: str) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
            return False
        raise AuthorityViolation(f"cannot inspect {label}: {path}: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise AuthorityViolation(f"{label} is not a regular file: {path}")
    return True


def _require_readable_file(path: Path, *, label: str) -> None:
    try:
        with path.open("rb") as stream:
            stream.read(1)
    except OSError as exc:
        raise AuthorityViolation(f"cannot read {label}: {path}: {exc}") from exc


def _read_bytes(path: Path, *, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise AuthorityViolation(f"cannot read {label}: {path}: {exc}") from exc


def _read_utf8_text(path: Path, *, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AuthorityViolation(f"cannot read {label}: {path}: {exc}") from exc


def _require_directory(path: Path, *, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise AuthorityViolation(f"{label} is not a directory: {path}: {exc}") from exc
    if not stat.S_ISDIR(mode):
        raise AuthorityViolation(f"{label} is not a directory: {path}")


def check_authority(root: Path, *, changed_paths: list[str]) -> list[str]:
    root = root.resolve()
    manifest_path = root / "contracts/canonical/authority.json"
    if not _existing_regular_file(manifest_path, label="authority manifest"):
        raise AuthorityViolation(f"authority manifest is missing: {manifest_path}")
    manifest = _validate_authority_manifest(_load_unique_json(manifest_path))
    violations: list[str] = []
    legacy_adapters: list[tuple[dict[str, Any], str]] = []
    for adapter in manifest["legacyAdapters"]:
        relative = _repo_relative_path(root, adapter["path"], label="legacy adapter path")
        if _LEGACY_ADAPTER_MODES.get(relative) != adapter["mode"]:
            raise AuthorityViolation(f"legacy adapter mode mismatch: {relative}")
        legacy_adapters.append((adapter, relative))
    changed: set[str] = set()
    for value in changed_paths:
        relative = _repo_relative_path(root, value, label="changed path")
        changed_path = root / relative
        changed_label = f"changed path {relative!r}"
        if _existing_regular_file(changed_path, label=changed_label):
            _require_readable_file(changed_path, label=changed_label)
        changed.add(relative)
    manifest_relative = manifest_path.relative_to(root).as_posix()
    roots_list: list[Path] = []
    for value in manifest["canonicalRoots"]:
        relative = _repo_relative_path(root, value, label="canonical root path")
        canonical_root = root / relative
        _require_directory(canonical_root, label=f"canonical root {relative!r}")
        roots_list.append(canonical_root.resolve())
    roots = tuple(roots_list)

    for collection, label in (
        (manifest["authoritativeInputs"], "authoritative input path"),
        (manifest["evidenceInputs"], "evidence input path"),
    ):
        for item in collection:
            relative = _repo_relative_path(root, item["path"], label=label)
            path = root / relative
            input_label = f"{label.removesuffix(' path')} {relative!r}"
            if not _existing_regular_file(path, label=input_label):
                violations.append(f"declared authority input missing: {relative}")
                continue
            actual_sha = hashlib.sha256(_read_bytes(path, label=input_label)).hexdigest()
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
        if relative not in changed:
            continue
        if not _existing_regular_file(
            root / relative, label=f"legacy adapter {relative!r}"
        ):
            continue
        payload = _load_unique_json(root / relative)
        if not isinstance(payload, dict):
            raise AuthorityViolation(f"malformed legacy contract: {relative}: expected object")
        raw_properties = payload.get("properties", {})
        if not isinstance(raw_properties, dict):
            raise AuthorityViolation(
                f"malformed legacy contract: {relative}: properties must be an object"
            )
        properties = set(raw_properties)
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
        matcher = _compile_gitwildmatch(patterns, label="forbidden symbol pattern")
        for relative in changed:
            if relative == manifest_relative:
                continue
            if not matcher.match_file(relative):
                continue
            path = root / relative
            if not _existing_regular_file(path, label=f"protected path {relative!r}"):
                continue
            content = _read_utf8_text(path, label=f"protected path {relative!r}")
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
    generated_source_matchers: dict[str, pathspec.PathSpec] = {}
    for group, sources, outputs in generated_groups:
        if len(sources) != len(set(sources)):
            violations.append(f"duplicate generated source inside group {group['name']}")
        if len(outputs) != len(set(outputs)):
            violations.append(f"duplicate generated output inside group {group['name']}")
        generated_source_matchers[group["name"]] = _compile_gitwildmatch(
            sources, label=f"generated source pattern for {group['name']}"
        )
        for output in outputs:
            previous = generated_output_owners.setdefault(output, group["name"])
            if previous != group["name"]:
                violations.append(
                    f"multiple generated owners for {output}: {previous}, {group['name']}"
                )

    for _, _, outputs in generated_groups:
        for output in outputs:
            for source_group, source_matcher in generated_source_matchers.items():
                if source_matcher.match_file(output):
                    violations.append(
                        "generated output also matches a source in "
                        f"{source_group}: {output}"
                    )

    for group, sources, outputs in generated_groups:
        source_matcher = generated_source_matchers[group["name"]]
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
    if _existing_regular_file(registry_path, label="canonical object registry"):
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
                or not all(included)
                or len(included) != len(set(included))
                or ("*" in included and included != ["*"])
                or not isinstance(excluded, list)
                or not all(isinstance(value, str) for value in excluded)
                or not all(excluded)
                or len(excluded) != len(set(excluded))
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
            schema_file = root / schema_path
            if not _existing_regular_file(
                schema_file, label=f"canonical schemaRef for {name}"
            ):
                violations.append(f"unresolved canonical schemaRef: {name}")
                continue
            resolved = schema_file.resolve()
            if not any(resolved == value or value in resolved.parents for value in roots):
                violations.append(f"schemaRef escapes canonical roots: {name}")
                continue
            if not _json_pointer_exists(resolved, fragment):
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

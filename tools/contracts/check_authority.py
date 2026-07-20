from __future__ import annotations

import json
import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

import pathspec


class AuthorityViolation(RuntimeError):
    pass


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
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthorityViolation(f"invalid JSON: {path}: {exc}") from exc


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


def check_authority(root: Path, *, changed_paths: list[str]) -> list[str]:
    manifest_path = root / "contracts/canonical/authority.json"
    manifest = _load_unique_json(manifest_path)
    violations: list[str] = []
    changed = set(changed_paths)
    manifest_relative = manifest_path.relative_to(root).as_posix()

    for item in manifest["authoritativeInputs"] + manifest["evidenceInputs"]:
        relative = item["path"]
        path = root / relative
        if not path.is_file():
            violations.append(f"declared authority input missing: {relative}")
            continue
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha != item["sha256"]:
            violations.append(f"pinned input sha256 mismatch: {relative}")
        if item.get("sourceCommit"):
            resolved_commit = _git_output(root, "rev-parse", f"{item['sourceCommit']}^{{commit}}")
            if resolved_commit != item["sourceCommit"]:
                violations.append(f"pinned input commit mismatch: {relative}")
            actual_blob = _git_output(root, "rev-parse", f"{item['sourceCommit']}:{relative}")
            if actual_blob != item.get("gitBlobOid"):
                violations.append(f"pinned input git blob mismatch: {relative}")
        elif item.get("gitBlobOid"):
            actual_blob = _git_output(root, "hash-object", relative)
            if actual_blob != item["gitBlobOid"]:
                violations.append(f"pinned input working blob mismatch: {relative}")

    for adapter in manifest["legacyAdapters"]:
        relative = adapter["path"]
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
        matcher = pathspec.PathSpec.from_lines("gitwildmatch", rule["paths"])
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

    generated_output_owners: dict[str, str] = {}
    for group in manifest["generatedGroups"]:
        if len(group["outputs"]) != len(set(group["outputs"])):
            violations.append(f"duplicate generated output inside group {group['name']}")
        source_matcher = pathspec.PathSpec.from_lines("gitwildmatch", group["sources"])
        for output in group["outputs"]:
            if source_matcher.match_file(output):
                violations.append(
                    f"generated output also matches a source in {group['name']}: {output}"
                )
        for output in group["outputs"]:
            previous = generated_output_owners.setdefault(output, group["name"])
            if previous != group["name"]:
                violations.append(
                    f"multiple generated owners for {output}: {previous}, {group['name']}"
                )

    for group in manifest["generatedGroups"]:
        source_matcher = pathspec.PathSpec.from_lines("gitwildmatch", group["sources"])
        changed_sources = {relative for relative in changed if source_matcher.match_file(relative)}
        changed_outputs = changed & set(group["outputs"])
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
        registry = _load_unique_json(registry_path)
        if registry.get("canonicalization") != "RFC8785+AI-Caddie-v1":
            violations.append("canonical object registry has wrong canonicalization")
        if registry.get("typedIdAlgorithm") != (
            "lowercaseHex(SHA-256(ASCII(domainTag+'\\u0000')||canonicalBytes))"
        ):
            violations.append("canonical object registry has wrong typedIdAlgorithm")
        roots = tuple((root / value).resolve() for value in manifest["canonicalRoots"])
        seen_names: set[str] = set()
        seen_domains: set[str] = set()
        for name, descriptor in registry["objects"].items():
            if set(descriptor) != {
                "domainTag", "schemaRef", "includedFields", "excludedFields"
            }:
                violations.append(f"invalid canonical descriptor keys: {name}")
                continue
            if name in seen_names or descriptor["domainTag"] in seen_domains:
                violations.append(f"duplicate canonical object/domain: {name}")
                continue
            seen_names.add(name); seen_domains.add(descriptor["domainTag"])
            domain_tag = descriptor["domainTag"]
            if not isinstance(domain_tag, str) or not re.fullmatch(
                r"[A-Za-z][A-Za-z0-9.-]*/v[1-9][0-9]*", domain_tag, flags=re.ASCII
            ):
                violations.append(f"invalid canonical domainTag: {name}")
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
            schema_path, _, fragment = descriptor["schemaRef"].partition("#")
            if Path(schema_path).is_absolute():
                violations.append(f"absolute canonical schemaRef: {name}")
                continue
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
    check_authority(repo, changed_paths=[line.strip() for line in __import__("sys").stdin if line.strip()])

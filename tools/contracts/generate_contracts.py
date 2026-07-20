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


def _swift_array(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def generate_all(registry_root: Path, output_root: Path) -> dict[str, str]:
    del output_root
    registry = _load(registry_root / "canonical_object_registry.json")
    descriptors = dict(sorted(registry["objects"].items()))
    source_digest = _source_digest(registry_root)

    python = (
        "# generated; do not edit\n"
        f"CANONICAL_CONTRACT_SOURCE_SHA256 = {source_digest!r}\n"
        f"CANONICAL_OBJECT_DESCRIPTORS = {descriptors!r}\n"
    )
    swift_rows = "\n".join(
        "        " + json.dumps(raw["domainTag"]) + ": CanonicalObjectDescriptor("
        + "objectName: " + json.dumps(name)
        + ", domainTag: " + json.dumps(raw["domainTag"])
        + ", schemaRef: " + json.dumps(raw["schemaRef"])
        + ", includedFields: " + _swift_array(raw["includedFields"])
        + ", excludedFields: " + _swift_array(raw["excludedFields"]) + "),"
        for name, raw in descriptors.items()
    )
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
{swift_rows}
    ]
}}
"""
    typescript = (
        "// generated; do not edit\n"
        + f"export const canonicalContractSourceSHA256 = {json.dumps(source_digest)} as const\n"
        + "export const canonicalObjectDescriptors = "
        + json.dumps(descriptors, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + " as const\n"
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
        target.write_text(content, encoding="utf-8")

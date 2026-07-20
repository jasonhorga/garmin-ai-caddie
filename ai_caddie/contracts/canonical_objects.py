from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .canonical_json import parse_unique_json
from .generated import CANONICAL_OBJECT_DESCRIPTORS


class CanonicalObjectError(ValueError):
    pass


@lru_cache(maxsize=1)
def _schema_registry() -> Registry:
    repo_root = Path(__file__).resolve().parents[2]
    registry = Registry()
    for path in sorted((repo_root / "contracts/canonical").rglob("*.schema.json")):
        document = parse_unique_json(path.read_bytes())
        registry = registry.with_resource(
            path.resolve().as_uri(),
            Resource.from_contents(document, default_specification=DRAFT202012),
        )
    return registry


@dataclass(frozen=True)
class CanonicalObjectDescriptor:
    object_name: str
    domain_tag: str
    schema_ref: str
    included_fields: tuple[str, ...]
    excluded_fields: frozenset[str]

    def validate_and_project(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise CanonicalObjectError(f"{self.domain_tag} payload must be an object")
        repo_root = Path(__file__).resolve().parents[2]
        schema_path, separator, fragment = self.schema_ref.partition("#")
        absolute_ref = (repo_root / schema_path).resolve().as_uri()
        if separator:
            absolute_ref += f"#{fragment}"
        validator = Draft202012Validator(
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": absolute_ref},
            registry=_schema_registry(),
        )
        errors = sorted(validator.iter_errors(dict(payload)), key=lambda item: list(item.path))
        if errors:
            first = errors[0]
            location = "/".join(str(item) for item in first.absolute_path) or "<root>"
            raise CanonicalObjectError(
                f"schema validation failed for {self.domain_tag} at {location}: {first.message}"
            )

        keys = set(payload)
        if self.included_fields == ("*",):
            return {key: payload[key] for key in payload if key not in self.excluded_fields}
        included = set(self.included_fields)
        unclassified = keys - included - self.excluded_fields
        if unclassified:
            raise CanonicalObjectError(
                f"unclassified fields for {self.domain_tag}: {sorted(unclassified)}"
            )
        return {key: payload[key] for key in self.included_fields if key in payload}


class CanonicalObjectTable:
    def __init__(self, generated: Mapping[str, Mapping[str, Any]]) -> None:
        by_domain: dict[str, CanonicalObjectDescriptor] = {}
        for object_name, raw in generated.items():
            descriptor = CanonicalObjectDescriptor(
                object_name=object_name,
                domain_tag=str(raw["domainTag"]),
                schema_ref=str(raw["schemaRef"]),
                included_fields=tuple(raw["includedFields"]),
                excluded_fields=frozenset(raw["excludedFields"]),
            )
            if descriptor.domain_tag in by_domain:
                raise CanonicalObjectError(
                    f"duplicate generated canonical domain: {descriptor.domain_tag}"
                )
            by_domain[descriptor.domain_tag] = descriptor
        self._by_domain = by_domain

    def require_domain(self, domain_tag: str) -> CanonicalObjectDescriptor:
        try:
            return self._by_domain[domain_tag]
        except KeyError as exc:
            raise CanonicalObjectError(
                f"unregistered canonical domain: {domain_tag}"
            ) from exc


GENERATED_CANONICAL_OBJECTS = CanonicalObjectTable(CANONICAL_OBJECT_DESCRIPTORS)

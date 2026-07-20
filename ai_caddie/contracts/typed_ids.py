from __future__ import annotations

import hashlib
from typing import Any

from .canonical_json import canonical_json_bytes
from .canonical_objects import GENERATED_CANONICAL_OBJECTS


def _typed_digest(domain_tag: str, semantic_payload: Any) -> str:
    prefix = domain_tag.encode("ascii") + b"\0"
    return hashlib.sha256(prefix + canonical_json_bytes(semantic_payload)).hexdigest()


def typed_id(domain_tag: str, payload: Any) -> str:
    descriptor = GENERATED_CANONICAL_OBJECTS.require_domain(domain_tag)
    semantic = descriptor.validate_and_project(payload)
    return _typed_digest(descriptor.domain_tag, semantic)

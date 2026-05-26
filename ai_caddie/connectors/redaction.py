from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"\b(cookie\w*|csrf\w*|token\w*|secret\w*|authorization\w*)\b[^,;\n]*", re.IGNORECASE),
]


def sanitize_secret_text(message: object, *, limit: int = 240) -> str:
    text = str(message).replace(".garmin_tokens", "<credential-dir>")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<redacted>", text)
    return text[:limit]

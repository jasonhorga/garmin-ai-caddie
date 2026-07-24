from __future__ import annotations

import json
import math
import struct
from pathlib import Path

import rfc8785


OFFICIAL = [
    0x0000000000000000,
    0x0000000000000001,
    0x8000000000000001,
    0x7FEFFFFFFFFFFFFF,
    0xFFEFFFFFFFFFFFFF,
    0x4340000000000000,
    0xC340000000000000,
    0x4430000000000000,
    0x44B52D02C7E14AF5,
    0x44B52D02C7E14AF6,
    0x44B52D02C7E14AF7,
    0x444B1AE4D6E2EF4E,
    0x444B1AE4D6E2EF4F,
    0x444B1AE4D6E2EF50,
    0x3EB0C6F7A0B5ED8C,
    0x3EB0C6F7A0B5ED8D,
    0x41B3DE4355555553,
    0x41B3DE4355555554,
    0x41B3DE4355555555,
    0x41B3DE4355555556,
    0x41B3DE4355555557,
    0xBECBF647612F3696,
    0x43143FF3C1CB0959,
]


def as_double(bits: int) -> float:
    return struct.unpack(">d", bits.to_bytes(8, "big"))[0]


def build() -> list[dict[str, str]]:
    bits = list(OFFICIAL)
    state = 0xA1CADD1E5EED1234
    while len(bits) < 2_048:
        state = (
            state * 6364136223846793005 + 1442695040888963407
        ) & ((1 << 64) - 1)
        value = as_double(state)
        if math.isfinite(value) and not (
            value == 0.0 and math.copysign(1.0, value) < 0
        ):
            bits.append(state)
    return [
        {
            "bitPatternHex": f"{item:016x}",
            "expected": rfc8785.dumps(as_double(item)).decode("ascii"),
        }
        for item in bits
    ]


if __name__ == "__main__":
    target = Path(
        "mobile/ios/AICaddieDomainTests/Fixtures/"
        "rfc8785_number_vectors.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")

"""Entry point for one isolated server worker task."""

from __future__ import annotations

import pickle
import struct
import sys


def _read_exact(size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sys.stdin.buffer.read(remaining)
        if not chunk:
            raise EOFError
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def main() -> int:
    while True:
        try:
            size = struct.unpack("!Q", _read_exact(8))[0]
        except EOFError:
            return 0
        function, args, kwargs = pickle.loads(_read_exact(size))
        try:
            payload = ("ok", function(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - transport domain exceptions to the parent
            try:
                pickle.dumps(exc, protocol=5)
            except Exception:
                exc = RuntimeError(f"{type(exc).__name__}: {exc}")
            payload = ("error", exc)
        encoded = pickle.dumps(payload, protocol=5)
        sys.stdout.buffer.write(struct.pack("!Q", len(encoded)) + encoded)
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

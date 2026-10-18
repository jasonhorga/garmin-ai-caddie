"""Collect readiness runtime resources and verify them inside a built image."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


SCHEMA = "ai-caddie-readiness-runtime-paths-v1"
TRACE_MARKER = "CARD432-TRACE:"

# Keep tracing in a fresh interpreter: readiness helpers can cache filesystem reads.
_TRACE_SCRIPT = r'''
import json
import os
import sys
from pathlib import Path
from server_v2 import readiness

root = Path.cwd().resolve()
observed = set()
paths_by_label = {}
active = True
recording = False

def record(value):
    global recording
    if not active or recording or isinstance(value, int):
        return
    recording = True
    try:
        try:
            raw = os.fsdecode(os.fspath(value))
        except TypeError:
            return
        absolute = os.path.realpath(raw if os.path.isabs(raw) else os.path.join(os.getcwd(), raw))
        root_text = os.path.realpath(os.fspath(root))
        try:
            relative = os.path.relpath(absolute, root_text)
        except ValueError:
            return
        if relative in (os.curdir, os.pardir) or relative.startswith(os.pardir + os.sep):
            return
        observed.add(Path(relative).as_posix())
    finally:
        recording = False

original_path_methods = {
    name: getattr(Path, name)
    for name in ("exists", "is_file", "is_symlink", "is_dir", "stat", "lstat", "open", "read_text", "read_bytes")
}
original_os_methods = {name: getattr(os, name) for name in ("stat", "lstat", "access")}

def wrap_path(name):
    original = original_path_methods[name]
    def traced(path, *args, **kwargs):
        record(path)
        return original(path, *args, **kwargs)
    return traced

def wrap_os(name):
    original = original_os_methods[name]
    def traced(path, *args, **kwargs):
        record(path)
        return original(path, *args, **kwargs)
    return traced

def audit_hook(event, args):
    if event in {"open", "os.listdir", "os.scandir", "os.walk"} and args:
        record(args[0] if args[0] is not None else os.getcwd())

sys.addaudithook(audit_hook)
original_check = readiness._check

def traced_check(label, *args, **kwargs):
    paths_by_label.setdefault(label, set()).update(observed)
    observed.clear()
    return original_check(label, *args, **kwargs)

for name in original_path_methods:
    setattr(Path, name, wrap_path(name))
for name in original_os_methods:
    setattr(os, name, wrap_os(name))
readiness._check = traced_check
try:
    readiness.build_readiness_response()
finally:
    active = False
    readiness._check = original_check
    for name, original in original_path_methods.items():
        setattr(Path, name, original)
    for name, original in original_os_methods.items():
        setattr(os, name, original)

if observed:
    paths_by_label.setdefault("<after-final-check>", set()).update(observed)

print("CARD432-TRACE:" + json.dumps({
    "labels": {label: sorted(paths) for label, paths in paths_by_label.items()},
    "packaging": sorted(readiness.PACKAGING_LABELS),
}))
'''


def _valid_path(path: object) -> bool:
    return (
        isinstance(path, str)
        and path not in {"", "."}
        and not path.startswith("/")
        and "\\" not in path
        and "\x00" not in path
        and all(part not in {"", ".", ".."} for part in path.split("/"))
    )


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _classify(root: Path, recording: dict) -> dict:
    packaging_labels = set(recording["packaging"])
    labels_by_path: dict[str, set[str]] = {}
    for label, paths in recording["labels"].items():
        for path in paths:
            if _valid_path(path):
                labels_by_path.setdefault(path, set()).add(label)
    manifest = {
        "schema": SCHEMA,
        "packagingLabels": sorted(packaging_labels),
        "runtime": [],
        "packaging": [],
        "absent": [],
        "excluded": [],
    }
    private_roots = {"data", ".garmin_tokens", "output", "logs", "backups", "clubs.json"}
    for path, labels in sorted(labels_by_path.items()):
        parts = path.split("/")
        reason = None
        if parts[0] in private_roots:
            reason = "private_root"
        elif any(part in {".venv", "node_modules"} for part in parts):
            reason = "build_environment"
        elif "__pycache__" in parts or path.endswith(".pyc"):
            reason = "bytecode"
        if reason:
            manifest["excluded"].append({"path": path, "reason": reason})
            continue
        entry = {"path": path, "labels": sorted(labels)}
        if not labels - packaging_labels:
            manifest["packaging"].append(entry)
            continue
        target = root / path
        if not target.exists():
            manifest["absent"].append(entry)
            continue
        if target.is_file():
            entry.update(kind="file", sha256=_digest(target))
        elif target.is_dir():
            entry["kind"] = "dir"
        else:
            raise ValueError(f"unsupported runtime resource kind: {path}")
        manifest["runtime"].append(entry)
    return manifest


def _collect(root: Path) -> dict:
    root = root.resolve()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(part for part in (str(root), env.get("PYTHONPATH", "")) if part)
    env["AI_CADDIE_DATA_MODE"] = "fixture"
    env.pop("AI_CADDIE_PRIVATE_ROOT", None)
    try:
        child = subprocess.run(
            [sys.executable, "-c", _TRACE_SCRIPT],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired as exc:
        tail = exc.stderr or b""
        if isinstance(tail, bytes):
            tail = tail.decode("utf-8", errors="replace")
        raise ValueError(f"readiness trace child timed out: {tail[-4000:]}") from exc
    results = [line[len(TRACE_MARKER):] for line in child.stdout.splitlines() if line.startswith(TRACE_MARKER)]
    if child.returncode or not results:
        status = f"exited {child.returncode}" if child.returncode else "produced no result"
        raise ValueError(f"readiness trace child {status}: {child.stderr[-4000:]}")
    return _classify(root, json.loads(results[-1]))


def _validate_manifest(manifest: object) -> list[dict]:
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("invalid manifest: unsupported schema")
    runtime = manifest.get("runtime")
    if not isinstance(runtime, list) or not runtime:
        raise ValueError("invalid manifest: runtime must be a nonempty list")
    for entry in runtime:
        if not isinstance(entry, dict) or "path" not in entry:
            raise ValueError("invalid manifest: runtime entry needs a path")
        path = entry["path"]
        if not _valid_path(path):
            raise ValueError(f"invalid manifest path: {path}")
        if entry.get("kind") not in {"file", "dir"}:
            raise ValueError(f"invalid manifest: unknown kind for {path}")
        if entry["kind"] == "file" and (
            not isinstance(entry.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
        ):
            raise ValueError(f"invalid manifest: file needs a SHA-256 digest: {path}")
    return sorted(runtime, key=lambda entry: entry["path"])


def _verify(runtime: list[dict], image_root: Path) -> int:
    problems = []
    print(f"Verifying {len(runtime)} readiness runtime paths against {image_root}", file=sys.stderr)
    for entry in runtime:
        path = entry["path"]
        target = image_root / path
        try:
            correct_kind = target.is_file() if entry["kind"] == "file" else target.is_dir()
            if not correct_kind:
                problems.append(f"missing from image: {path}")
            elif entry["kind"] == "file" and _digest(target) != entry["sha256"]:
                problems.append(f"differs in image: {path}")
            else:
                print(f"checked in image: {path}", file=sys.stderr)
        except OSError:
            problems.append(f"missing from image: {path}")
    for problem in problems:
        print(problem, file=sys.stderr)
    return int(bool(problems))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect")
    collect.add_argument("--root", type=Path)
    collect.add_argument("--output", default="-")
    verify = commands.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--image-root", required=True, type=Path)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    if args.command == "verify":
        try:
            text = sys.stdin.read() if args.manifest == "-" else Path(args.manifest).read_text(encoding="utf-8")
            runtime = _validate_manifest(json.loads(text))
        except (OSError, ValueError, TypeError) as exc:
            message = str(exc)
            print(message if message.startswith("invalid manifest") else f"invalid manifest: {message}", file=sys.stderr)
            return 1
        return _verify(runtime, args.image_root)
    try:
        # Do not create or truncate output until the child and classification succeed.
        root = args.root if args.root is not None else Path(__file__).resolve().parents[1]
        manifest = _collect(root)
        payload = json.dumps(manifest, indent=2, ensure_ascii=True) + "\n"
        if args.output == "-":
            sys.stdout.write(payload)
        else:
            Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Collected {len(manifest['runtime'])} readiness runtime paths", file=sys.stderr)
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print(f"readiness collection failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

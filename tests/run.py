"""Thin layer entry point over tests.check_isolation (docs/test-plan.md 3.3).

    python -m tests.run --layer fast   # small + medium (+ legacy until K13): the host CD command
    python -m tests.run --layer slow   # tests/large only
    python -m tests.run --layer all    # fast + large

``--changed`` and ``--shard`` belong to C401 (K12).
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from tests.support.layers import LAYER_ENV, SLOW

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = {
    "fast": ("tests", False),
    "slow": ("tests/large", True),
    "all": ("tests", True),
}


def plan(layer, environ):
    """Return (command, environment) for ``layer``; the caller's environ is not modified."""
    start, slow = DISCOVERY[layer]
    env = {key: value for key, value in environ.items() if key != LAYER_ENV}
    if slow:
        env[LAYER_ENV] = SLOW
    return [sys.executable, "-m", "tests.check_isolation", "discover", "-s", start, "-t", "."], env


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m tests.run", description=__doc__.splitlines()[0])
    parser.add_argument("--layer", required=True, choices=sorted(DISCOVERY))
    parser.add_argument("-v", "--verbose", action="store_true")
    options = parser.parse_args(argv)
    command, env = plan(options.layer, os.environ)
    if options.verbose:
        command.append("-v")
    return subprocess.run(command, cwd=ROOT, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())

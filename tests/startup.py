"""Process start-up choices made before the tests package imports the backend.

Standard library only: this runs first in every test process, including the
outer isolation runner, which must stay light.
"""
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ISOLATION_RUNNER = "tests.check_isolation"
CHILD_FLAG = "--logging-child"
# Interpreter options whose value is the next argument.
_OPTIONS_WITH_VALUE = {"-X", "-W", "--check-hash-based-pycs"}


def isolation_parent(argv):
    """True for ``python [options] -m tests.check_isolation`` without the child flag.

    That parent only snapshots git and runs its child, so it skips the offline
    install (and with it the backend import). Every other process keeps it.
    """
    arguments = iter(argv[1:])
    for argument in arguments:
        if argument == "-m":
            module = next(arguments, None)
            return module == ISOLATION_RUNNER and next(arguments, None) != CHILD_FLAG
        if argument in _OPTIONS_WITH_VALUE:
            next(arguments, None)
        elif not argument.startswith("-") or argument == "-" or argument.startswith("-c"):
            return False
    return False


def bytecode_prefix(root, writable, temporary_root):
    """Where bytecode goes: beside the source, or one shared directory when it is read-only."""
    if writable(root):
        return None
    return os.path.join(temporary_root, "caddie-pycache")


def share_bytecode_cache():
    """In a read-only checkout, cache bytecode under TMPDIR for this and every child process."""
    if sys.pycache_prefix:
        return
    prefix = bytecode_prefix(ROOT, lambda path: os.access(path, os.W_OK), tempfile.gettempdir())
    if prefix:
        sys.pycache_prefix = prefix
        os.environ["PYTHONPYCACHEPREFIX"] = prefix

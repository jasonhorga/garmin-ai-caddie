"""Medium layer: in-process HTTP, $TMPDIR files, local subprocesses (test-plan 3.1).

No hermetic guard; the runner enforces a 30 s per-test limit and a 135 s layer
budget (tests/check_isolation.py).
"""

"""Thin layer entry point (interface stub)."""
import sys


def plan(layer, environ):
    return ([sys.executable, "-m", "tests.check_isolation", "discover", "-s", "tests", "-t", "."],
            dict(environ))

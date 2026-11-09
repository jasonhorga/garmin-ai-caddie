"""Install offline defaults before importing any backend test module."""
import sys

from tests import startup

startup.share_bytecode_cache()
# The outer isolation runner only runs git and its child; the child installs.
if not startup.isolation_parent(sys.orig_argv):
    from tests.offline import install

    install()

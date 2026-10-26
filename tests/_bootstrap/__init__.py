"""Install defaults even when discovery treats tests/ as the top-level directory.

unittest visits packages regardless of its file pattern, in sorted order. This
package precedes acceptance/, product/ and test_*.py, including with ``-p``.
Import through tests so both discovery modes share one guard and one cache.
"""
from tests.offline import install

install()

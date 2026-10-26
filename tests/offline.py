"""Suite-wide Garmin HTTP guard and disposable provider caches.

Explicit transport fakes take precedence over these defaults. A live integration
test must opt in with ``allow_garmin_network``; the opt-in is local to its context
and does not enable background threads. Never use it with a real player account.
"""
import atexit
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import URLError
from urllib.parse import urlsplit
import urllib.request

import requests

_allowed = ContextVar("test_garmin_network_allowed", default=False)
_installed = False


class GarminNetworkBlocked(URLError):
    """An implicit Garmin request was stopped before opening a connection."""


def _blocked(url):
    hostname = (urlsplit(url).hostname or "").lower().rstrip(".")
    return not _allowed.get() and any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in ("garmin.cn", "garmin.com")
    )


@contextmanager
def allow_garmin_network():
    """Explicit opt-in for an intentionally live, separately selected test."""
    token = _allowed.set(True)
    try:
        yield
    finally:
        _allowed.reset(token)


def install():
    global _installed
    if _installed:
        return
    _installed = True

    # Guard below urlopen aliases and Session.get/post, but above actual I/O.
    # Existing tests can still fake urlopen, Session.send or an HTTP adapter.
    original_open = urllib.request.OpenerDirector.open

    @wraps(original_open)
    def offline_open(self, fullurl, *args, **kwargs):
        url = fullurl.full_url if isinstance(fullurl, urllib.request.Request) else fullurl
        if _blocked(url):
            raise GarminNetworkBlocked("Garmin HTTP disabled by tests.offline; use a fixture")
        return original_open(self, fullurl, *args, **kwargs)

    urllib.request.OpenerDirector.open = offline_open
    original_send = requests.adapters.HTTPAdapter.send

    @wraps(original_send)
    def offline_send(self, request, *args, **kwargs):
        if _blocked(request.url):
            raise requests.ConnectionError("Garmin HTTP disabled by tests.offline; use a fixture")
        return original_send(self, request, *args, **kwargs)

    requests.adapters.HTTPAdapter.send = offline_send

    # A browser (or an xvfb child process) would bypass Python's HTTP clients.
    # Guard the two launch boundaries; FakePage-based login tests stay offline.
    from ai_caddie.garmin import garmin_playwright_login

    def guard_browser(function):
        @wraps(function)
        def guarded(*args, **kwargs):
            if not _allowed.get():
                raise GarminNetworkBlocked("Garmin browser login disabled by tests.offline")
            return function(*args, **kwargs)
        return guarded

    garmin_playwright_login._login_once = guard_browser(garmin_playwright_login._login_once)
    garmin_playwright_login._reexec_under_xvfb = guard_browser(
        garmin_playwright_login._reexec_under_xvfb
    )

    # Keep the actual repo ROOT intact for fixtures, scripts and root-resolution
    # tests. A child directory also preserves batch export's relative_to(ROOT)
    # path contract, while never reading/writing the repository's provider cache.
    from ai_caddie.core import data as disk
    ROOT = disk.ROOT

    temporary = TemporaryDirectory(prefix=".test-cache-", dir=ROOT)
    atexit.register(temporary.cleanup)
    cache_root = Path(temporary.name)
    courseview = cache_root / "data" / "courseview"

    # Set reader anchors before importing consumers which snapshot these paths.
    disk.MESH_DIR = cache_root / "output" / "prodgeometry"
    disk.HAZARD_DIR = cache_root / "output" / "prodgeometry_hazards"
    from ai_caddie.courses import course_reference, courseview_core, prep_cache
    from ai_caddie.geometry import inspect_courseview_release, batch_prodgeometry_course
    from ai_caddie.geometry import geometry_sync, garmin_raster

    original_dir = course_reference._courseview_dir

    def courseview_dir(root=ROOT):
        return original_dir(cache_root if Path(root).resolve() == ROOT else root)

    course_reference._courseview_dir = courseview_dir
    original_course_dir = course_reference._course_dir

    def course_dir(root=ROOT):
        return original_course_dir(cache_root if Path(root).resolve() == ROOT else root)

    course_reference._course_dir = course_dir
    course_reference.COURSE_DIR = course_dir()
    prep_cache._COURSES_DIR = course_dir()
    original_path = courseview_core.course_data_cache_path

    @wraps(original_path)
    def course_data_path(*args, root=ROOT, **kwargs):
        return original_path(
            *args, root=cache_root if Path(root).resolve() == ROOT else root, **kwargs
        )

    courseview_core.course_data_cache_path = course_data_path
    inspect_courseview_release.COURSEVIEW = courseview
    geometry_sync.COURSEVIEW = courseview
    prep_cache._COURSEVIEW_DIR = courseview
    batch_prodgeometry_course.PROD_ROOT = courseview / "prodgeometry"
    batch_prodgeometry_course.OUT_ROOT = disk.MESH_DIR
    batch_prodgeometry_course.HAZARD_ROOT = disk.HAZARD_DIR
    batch_prodgeometry_course.SUMMARY_ROOT = cache_root / "output" / "prodgeometry_batch"
    garmin_raster.RASTER_CACHE_DIR = cache_root / "output" / "garmin_raster"

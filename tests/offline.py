"""Suite-wide Garmin HTTP guard and disposable provider caches.

Explicit transport fakes take precedence over these defaults. A live integration
test must opt in with ``allow_garmin_network``; the opt-in is local to its context
and does not enable background threads. Never use it with a real player account.
"""
import atexit
import os
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

    # Lifespan workers outlive TestClient and can consume later tests' mocks. Read at
    # startup (not import time); wiring tests explicitly opt in and fake the entry point.
    os.environ["AI_CADDIE_BOOT_BACKGROUND_WORK"] = "0"

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

    # Keep core.data.ROOT intact as the fixture/source anchor. Batch and topo
    # runtime roots below are redirected; production-root tests use clean children.
    # SIGKILL can bypass cleanup, so disposable files must live outside the repo.
    from ai_caddie.core import data as disk
    ROOT = disk.ROOT

    temporary = TemporaryDirectory(prefix=".test-cache-")
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

    from ai_caddie.courses import vector_prep
    from ai_caddie.geometry import overlay_prodgeometry_on_raster as overlay, topo_render

    overlay.RASTER_CACHE = cache_root / "output" / "hole_overlays"
    overlay.OUT_DIR = cache_root / "output" / "prodgeometry_overlay"
    vector_prep._CACHE_DIR = cache_root / "output" / "vector-prep"
    topo_render.ROOT = cache_root

    # batch's ROOT also anchors relative_to() and its hard-coded staging path.
    # SCRIPT_DIR / DEFAULT_SNAPSHOT still point at the real source tree. Its
    # Python exporter children run from this disposable cwd, so expose the source
    # only in batch's subprocess environment, leaving the parent and other children
    # unchanged. Both run() and interruptible Popen() need the same environment.
    batch_prodgeometry_course.ROOT = cache_root
    original_subprocess = batch_prodgeometry_course.subprocess

    class BatchSubprocess:
        def __getattr__(self, name):
            return getattr(original_subprocess, name)

        def child_kwargs(self, kwargs):
            inherited = kwargs.get("env")
            env = dict(os.environ if inherited is None else inherited)
            env["PYTHONPATH"] = os.pathsep.join(
                [str(ROOT), *filter(None, env.get("PYTHONPATH", "").split(os.pathsep))]
            )
            return {**kwargs, "env": env}

        def run(self, *args, **kwargs):
            return original_subprocess.run(*args, **self.child_kwargs(kwargs))

        def Popen(self, *args, **kwargs):
            return original_subprocess.Popen(*args, **self.child_kwargs(kwargs))

    batch_prodgeometry_course.subprocess = BatchSubprocess()

    from ai_caddie.caddie import decision, mobile_live

    def disposable_root(root):
        return cache_root if Path(root or ".").resolve() == ROOT else root

    # Patch application defaults before main snapshots them or constructs its job
    # store. Explicit test roots and database URL overrides keep their scope.
    from ai_caddie.connectors import snapshot, sync_lock
    from ai_caddie.reports import reports
    from ai_caddie.rounds import players
    from server_v2 import db, reports as report_routes, sync_jobs

    # Expose the disposable anchor for callers inspecting ROOT / STATUS_FILE. This assignment
    # cannot change root=ROOT defaults already bound at definition time: the write/read status
    # wrappers below perform the actual default-root redirection.
    snapshot.ROOT = cache_root
    players.ROOT = cache_root
    db.ROOT = cache_root
    report_routes.REPORT_ROOT = cache_root
    sync_jobs.ROOT = cache_root

    # SYNC_DIR/STATUS_FILE remain relative: explicit root / STATUS_FILE is part
    # of snapshot's API. Redirect the default root rather than making that suffix
    # absolute (which would silently discard explicit per-test roots).
    def redirect_snapshot_root(function):
        @wraps(function)
        def redirected(*args, root=ROOT, **kwargs):
            return function(*args, root=disposable_root(root), **kwargs)
        return redirected

    snapshot.write_connector_status = redirect_snapshot_root(snapshot.write_connector_status)
    snapshot.read_connector_status = redirect_snapshot_root(snapshot.read_connector_status)
    original_lock_path = sync_lock.sync_lock_path

    @wraps(original_lock_path)
    def sync_lock_path(root):
        return original_lock_path(disposable_root(root))

    sync_lock.sync_lock_path = sync_lock_path
    original_report_path = reports.report_store_file

    @wraps(original_report_path)
    def report_store_file(root=None):
        return original_report_path(disposable_root(root))

    reports.report_store_file = report_store_file
    original_report_root = reports.evidence_root

    @wraps(original_report_root)
    def report_evidence_root(player_id, *, root=None):
        return original_report_root(player_id, root=disposable_root(root))

    reports.evidence_root = report_evidence_root
    original_job_init = sync_jobs.GarminSyncJobStore.__init__

    @wraps(original_job_init)
    def job_store_init(self, *, root=ROOT):
        original_job_init(self, root=disposable_root(root))

    sync_jobs.GarminSyncJobStore.__init__ = job_store_init

    original_evidence_root = decision.evidence_root

    @wraps(original_evidence_root)
    def evidence_root(player_id, *, root=None):
        return original_evidence_root(player_id, root=disposable_root(root))

    decision.evidence_root = evidence_root

    def redirect_mobile_path(function):
        @wraps(function)
        def path(root=None, **kwargs):
            return function(disposable_root(root), **kwargs)
        return path

    mobile_live.mobile_event_log = redirect_mobile_path(mobile_live.mobile_event_log)
    mobile_live.mobile_event_ack_store = redirect_mobile_path(mobile_live.mobile_event_ack_store)

    # Set route defaults too: event-store locks and the cross-worker package lock
    # use MOBILE_ROOT directly, while decision routes supply explicit roots.
    from server_v2 import caddie, mobile

    caddie.DECISION_LEDGER_ROOT = cache_root
    caddie.DECISION_AUDIT_ROOT = cache_root
    mobile.MOBILE_ROOT = cache_root
    mobile.DECISION_LEDGER_ROOT = cache_root
    mobile.DECISION_AUDIT_ROOT = cache_root

    from server_v2 import main

    main.SYNC_ROOT = cache_root

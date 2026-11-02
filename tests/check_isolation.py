"""Run unittest arguments and reject new/changed data or output git status.

CI/local usage: python -m tests.check_isolation tests.test_offline_followups
Full CI usage: python -m tests.check_isolation discover -s tests -t . -v
"""
import logging
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


def repository_artifacts():
    """Include ignored files, which normal git status would hide."""
    return subprocess.check_output(
        ["git", "status", "--porcelain", "--ignored", "--untracked-files=all",
         "--", "data/", "output/"], cwd=ROOT, text=True,
    )


def artifact_files():
    """Catch rewritten ignored files even when their git status stays '!!'."""
    files = {}
    for directory in (ROOT / "data", ROOT / "output"):
        for path in directory.rglob("*"):
            if path.is_file() or path.is_symlink():
                stat = path.lstat()
                files[path.relative_to(ROOT).as_posix()] = (stat.st_size, stat.st_mtime_ns, stat.st_mode)
    return files


class LoggingIsolationSuite(unittest.TestSuite):
    """Check each module after tearDownModule and unittest module cleanups.

    The child runner captures pristine methods before importing test modules.
    Report leaks at their source and restore the methods so subsequent modules
    still run with independent results.
    """

    original_methods = (logging.Logger.addHandler, logging.Logger.callHandlers)

    def _handleModuleTearDown(self, result):
        previous = self._get_previous_module(result)
        super()._handleModuleTearDown(result)
        if previous is None:
            return
        changed = [name for name, original in zip(
            ("addHandler", "callHandlers"), self.original_methods)
            if getattr(logging.Logger, name) is not original]
        if not changed:
            return
        try:
            raise AssertionError("; ".join(f"{previous} leaked Logger.{name}" for name in changed))
        except AssertionError:
            # Use a real assertion failure, attributed to the completed module.
            witness = unittest.FunctionTestCase(lambda: None,
                                                description=previous + " logging isolation")
            result.addFailure(witness, sys.exc_info())
        finally:
            handle = getattr(logging.Logger.addHandler, "_privacy_handle", None)
            if handle is not None:
                handle.close()
            logging.Logger.addHandler, logging.Logger.callHandlers = self.original_methods


def run_logging_checked_tests(arguments):
    loader = unittest.TestLoader()
    loader.suiteClass = LoggingIsolationSuite
    program = unittest.main(module=None, argv=[sys.argv[0], *arguments],
                            testLoader=loader, exit=False)
    return 0 if program.result.wasSuccessful() else 1


def main():
    if len(sys.argv) == 1:
        raise SystemExit("Pass unittest modules or discovery arguments")
    before = repository_artifacts()
    before_files = artifact_files()
    result = subprocess.run([sys.executable, "-m", "tests.check_isolation",
                             "--logging-child", *sys.argv[1:]], cwd=ROOT)
    after = repository_artifacts()
    after_files = artifact_files()
    changed = {
        path for path in before_files.keys() | after_files.keys()
        if before_files.get(path) != after_files.get(path)
    }
    # Retain the git-status check too (e.g. an index/status change without a file
    # metadata change), and report only the differing entries from this run.
    changed.update(line[3:] for line in set(before.splitlines()) ^ set(after.splitlines()))
    if changed:
        print("Repository artifacts changed:\nNew/changed repository artifacts:", file=sys.stderr)
        for path in sorted(changed):
            print(f"  {path}", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--logging-child":
        raise SystemExit(run_logging_checked_tests(sys.argv[2:]))
    raise SystemExit(main())

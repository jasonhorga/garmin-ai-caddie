"""Run unittest arguments and reject new/changed data or output git status.

CI/local usage: python -m tests.check_isolation tests.test_offline_followups
Full CI usage: python -m tests.check_isolation discover -s tests -t . -v
"""
from pathlib import Path
import subprocess
import sys


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


def main():
    if len(sys.argv) == 1:
        raise SystemExit("Pass unittest modules or discovery arguments")
    before = repository_artifacts()
    before_files = artifact_files()
    result = subprocess.run([sys.executable, "-m", "unittest", *sys.argv[1:]], cwd=ROOT)
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
    raise SystemExit(main())

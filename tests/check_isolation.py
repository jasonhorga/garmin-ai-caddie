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


def main():
    if len(sys.argv) == 1:
        raise SystemExit("Pass unittest modules or discovery arguments")
    before = repository_artifacts()
    result = subprocess.run([sys.executable, "-m", "unittest", *sys.argv[1:]], cwd=ROOT)
    after = repository_artifacts()
    if after != before:
        print(f"Repository artifacts changed:\nBEFORE:\n{before}AFTER:\n{after}", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())

"""What was run: the code commit and the library versions, for the deterministic JSON reports (no timestamps)."""
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CODE_PATHS = ("episode_three", "scripts", "requirements.txt")
LIBRARIES = ("numpy", "pandas", "scikit-learn", "scipy", "joblib")


def code_commit():
    """The last commit that changed code (not reports, docs or devlogs), plus -dirty if code has uncommitted edits.

    Not plain HEAD: committing the report itself would move HEAD, and re-running would then change the file.
    """
    def git(*args):
        return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True).stdout.strip()
    commit = git("log", "-1", "--format=%H", "--", *CODE_PATHS)
    dirty = git("status", "--porcelain", "--", *CODE_PATHS)
    return commit + ("-dirty" if dirty else "")


def versions(libraries=LIBRARIES):
    return {"python": ".".join(map(str, sys.version_info[:3])), **{name: version(name) for name in libraries}}

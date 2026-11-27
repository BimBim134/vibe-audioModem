"""Which Vibe AudioModem this is: the release number, and the git state of a source checkout."""

import importlib.metadata
import subprocess
from pathlib import Path

GIT_SECONDS = 3.0  # git is only asked, never waited for long


def version() -> str:
    """The release number (from `pyproject.toml`, kept in the package's metadata)."""
    try:
        return importlib.metadata.version("vibemodem")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _git(root: Path, *arguments: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            timeout=GIT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = done.stdout.strip()
    return text if done.returncode == 0 and text else None


def git_description() -> str | None:
    """`v1.0-15-gabc1234-dirty on dev` when run from a git checkout (the tag it is after, the
    commits since, the commit, uncommitted changes, the branch); None otherwise, as in a
    packaged application or without git."""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return None
    described = _git(root, "describe", "--tags", "--always", "--dirty")
    if described is None:
        return None
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return f"{described} on {branch}" if branch and branch != "HEAD" else described


def describe() -> dict:
    return {"version": version(), "git": git_description()}

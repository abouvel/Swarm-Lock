"""All git subprocess operations for the Swarm Lock Manager.

No other module should call git directly — everything goes through here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised on unexpected git failures."""

    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


def _run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as e:
        raise GitError(f"Git command timed out: git {' '.join(args)}") from e
    except FileNotFoundError as e:
        raise GitError("git is not installed or not on PATH") from e

    if check and result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}",
            stderr=result.stderr,
        )
    return result


def pull_rebase(repo_dir: Path) -> bool:
    """Run git pull --rebase. Returns True on success."""
    _run_git(["pull", "--rebase"], cwd=repo_dir)
    return True


def add_and_commit(repo_dir: Path, paths: list[str], message: str) -> bool:
    """Stage specific paths and commit. Returns True on success."""
    _run_git(["add"] + paths, cwd=repo_dir)
    _run_git(["commit", "-m", message], cwd=repo_dir)
    return True


def push(repo_dir: Path) -> bool:
    """Push to remote. Returns False on rejection (not an exception)."""
    result = _run_git(["push", "--force-with-lease"], cwd=repo_dir, check=False)
    if result.returncode != 0:
        # Check if it's a rejection vs a real error
        stderr = result.stderr.lower()
        if "rejected" in stderr or "failed to push" in stderr or "non-fast-forward" in stderr:
            return False
        raise GitError(
            f"git push failed unexpectedly: {result.stderr.strip()}",
            stderr=result.stderr,
        )
    return True


def reset_last_commit(repo_dir: Path) -> bool:
    """Reset the last commit (soft reset HEAD~1). Returns True on success."""
    _run_git(["reset", "HEAD~1"], cwd=repo_dir)
    return True


def get_repo_root(start_dir: Path | None = None) -> Path:
    """Find the root of the git repository."""
    cwd = start_dir or Path.cwd()
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(result.stdout.strip())


def has_dirty_tree(repo_dir: Path) -> bool:
    """Check if working tree has uncommitted changes (staged or unstaged)."""
    result = _run_git(["status", "--porcelain"], cwd=repo_dir)
    return bool(result.stdout.strip())


def commit_all(repo_dir: Path, message: str) -> bool:
    """Stage all changes and commit. Returns True on success, False if nothing to commit."""
    result = _run_git(["status", "--porcelain"], cwd=repo_dir)
    if not result.stdout.strip():
        return False
    _run_git(["add", "."], cwd=repo_dir)
    _run_git(["commit", "-m", message], cwd=repo_dir)
    return True


def current_branch(repo_dir: Path) -> str:
    """Get the current branch name."""
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    return result.stdout.strip()


def push_branch(repo_dir: Path, branch: str | None = None) -> bool:
    """Push current branch (with -u for tracking). Returns False on rejection."""
    cmd = ["push", "-u", "origin"]
    if branch:
        cmd.append(branch)
    else:
        cmd.append(_run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir).stdout.strip())
    result = _run_git(cmd, cwd=repo_dir, check=False)
    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "rejected" in stderr or "failed to push" in stderr or "non-fast-forward" in stderr:
            return False
        raise GitError(
            f"git push failed unexpectedly: {result.stderr.strip()}",
            stderr=result.stderr,
        )
    return True

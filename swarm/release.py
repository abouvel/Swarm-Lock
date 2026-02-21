"""The distributed release flow.

1. Acquire filelock
2. git pull --rebase
3. Read lock file (missing → fail, wrong agent → fail)
4. Delete lock file, append log
5. git add + commit, git push
6. Push rejected → re-write lock file, reset HEAD~1, report failure
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout

from swarm import git
from swarm.locks import (
    CLAIMED_DIR,
    LOG_FILE,
    append_log,
    delete_lock,
    lock_file_path,
    read_lock,
    write_lock,
)
from swarm.types import LockRecord, ReleaseResult, get_agent_id

FILELOCK_TIMEOUT = 30


def release(
    repo_dir: Path,
    task_id: str,
    summary: str = "",
    agent_id: str | None = None,
) -> ReleaseResult:
    """Execute the full distributed release flow."""
    agent = agent_id or get_agent_id()
    lock_path = repo_dir / CLAIMED_DIR / ".claim.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with FileLock(lock_path, timeout=FILELOCK_TIMEOUT):
            return _release_inner(repo_dir, task_id, summary, agent)
    except Timeout:
        return ReleaseResult(
            success=False,
            task_id=task_id,
            message="Could not acquire local filelock within 30s",
        )


def _release_inner(
    repo_dir: Path,
    task_id: str,
    summary: str,
    agent: str,
) -> ReleaseResult:
    """Inner release logic, called while holding the filelock."""
    # Step 2: Pull latest
    try:
        git.pull_rebase(repo_dir)
    except git.GitError as e:
        return ReleaseResult(
            success=False, task_id=task_id,
            message=f"Git pull failed: {e}",
        )

    # Step 3: Read lock file
    lf_path = lock_file_path(repo_dir, task_id)
    if not lf_path.exists():
        return ReleaseResult(
            success=False, task_id=task_id,
            message=f"No lock file found for task {task_id}",
        )

    try:
        record = read_lock(lf_path)
    except Exception as e:
        return ReleaseResult(
            success=False, task_id=task_id,
            message=f"Could not read lock file: {e}",
        )

    if record.claimed_by != agent:
        return ReleaseResult(
            success=False, task_id=task_id,
            message=f"Lock owned by {record.claimed_by}, not {agent}. Cannot release another agent's lock.",
        )

    # Step 3.5: Auto-commit any dirty changes before releasing
    try:
        if git.has_dirty_tree(repo_dir):
            commit_msg = f"feat: work on {task_id} — {summary}" if summary else f"feat: work on {task_id}"
            git.commit_all(repo_dir, commit_msg)
            git.push_branch(repo_dir)
    except git.GitError as e:
        return ReleaseResult(
            success=False, task_id=task_id,
            message=f"Failed to commit/push working changes: {e}",
        )

    # Step 4: Delete lock file and append log
    relative_lock = str(lf_path.relative_to(repo_dir))
    delete_lock(repo_dir, task_id)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_summary = summary or "no summary"
    append_log(repo_dir, f"[{now}] RELEASED | {task_id} | {log_summary} | {agent}")

    # Step 5: Commit and push
    commit_summary = f" — {summary}" if summary else ""
    try:
        git.add_and_commit(
            repo_dir,
            [relative_lock, LOG_FILE],
            f"swarm: release {task_id}{commit_summary}",
        )
    except git.GitError as e:
        # Commit failed — re-create lock file
        write_lock(repo_dir, record)
        return ReleaseResult(
            success=False, task_id=task_id,
            message=f"Git commit failed: {e}",
        )

    # Step 6: Push
    try:
        pushed = git.push(repo_dir)
    except git.GitError as e:
        _rollback_release(repo_dir, record)
        return ReleaseResult(
            success=False, task_id=task_id,
            message=f"Git push error: {e}",
        )

    if not pushed:
        _rollback_release(repo_dir, record)
        return ReleaseResult(
            success=False, task_id=task_id,
            message="Push rejected. Lock file restored.",
        )

    return ReleaseResult(
        success=True, task_id=task_id, summary=summary,
        message=f"Released task {task_id} ({record.scope}) as {agent}",
    )


def _rollback_release(repo_dir: Path, record: LockRecord) -> None:
    """Roll back a failed release: reset commit and re-create lock file."""
    try:
        git.reset_last_commit(repo_dir)
    except git.GitError:
        pass
    write_lock(repo_dir, record)

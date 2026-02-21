"""The distributed claim flow.

Order of operations must never change:
1. Acquire filelock on .claim.lock (30s timeout)
2. git pull --rebase
3. Read all existing locks
4. Check conflict (HARD → abort, SOFT without force → abort)
5. Build LockRecord, write to disk
6. Append to SWARM_LOG.md
7. git add + commit (lock file + log)
8. git push — success: done. Rejected: reset HEAD~1, delete lock file, report failure
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout

from swarm import git
from swarm.conflicts import check_conflict
from swarm.locks import (
    CLAIMED_DIR,
    LOG_FILE,
    append_log,
    delete_lock,
    lock_file_path,
    read_all_locks,
    write_lock,
)
from swarm.types import (
    ClaimResult,
    ConflictResult,
    LockRecord,
    LockStatus,
    get_agent_id,
)

FILELOCK_TIMEOUT = 30


def claim(
    repo_dir: Path,
    task_id: str,
    scope: str,
    agent_id: str | None = None,
    force: bool = False,
    notes: str = "",
) -> ClaimResult:
    """Execute the full distributed claim flow."""
    agent = agent_id or get_agent_id()
    lock_path = repo_dir / CLAIMED_DIR / ".claim.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with FileLock(lock_path, timeout=FILELOCK_TIMEOUT):
            return _claim_inner(repo_dir, task_id, scope, agent, force, notes)
    except Timeout:
        return ClaimResult(
            success=False,
            task_id=task_id,
            scope=scope,
            message="Could not acquire local filelock within 30s — another agent may be claiming on this machine",
        )


def _claim_inner(
    repo_dir: Path,
    task_id: str,
    scope: str,
    agent: str,
    force: bool,
    notes: str,
) -> ClaimResult:
    """Inner claim logic, called while holding the filelock."""
    # Step 2: Pull latest
    try:
        git.pull_rebase(repo_dir)
    except git.GitError as e:
        return ClaimResult(
            success=False, task_id=task_id, scope=scope,
            message=f"Git pull failed: {e}",
        )

    # Step 3: Read existing locks
    existing = read_all_locks(repo_dir)

    # Step 4: Conflict check
    conflict = check_conflict(scope, existing)
    if conflict.result == ConflictResult.HARD:
        _log_conflict(repo_dir, task_id, scope, agent, conflict)
        return ClaimResult(
            success=False, task_id=task_id, scope=scope,
            conflict=conflict, message=conflict.message,
        )
    if conflict.result == ConflictResult.SOFT and not force:
        _log_conflict(repo_dir, task_id, scope, agent, conflict)
        return ClaimResult(
            success=False, task_id=task_id, scope=scope,
            conflict=conflict,
            message=f"{conflict.message}. Use --force to override.",
        )

    # Step 5: Build and write lock
    now = datetime.now(timezone.utc)
    record = LockRecord(
        task_id=task_id,
        scope=scope,
        claimed_by=agent,
        claimed_at=now,
        last_updated=now,
        status=LockStatus.ACTIVE,
        notes=notes,
    )
    written_path = write_lock(repo_dir, record)

    # Step 6: Append log
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    append_log(repo_dir, f"[{timestamp}] CLAIMED | {task_id} | {scope} | {agent}")

    # Step 7: Commit and push
    relative_lock = str(written_path.relative_to(repo_dir))
    try:
        git.add_and_commit(
            repo_dir,
            [relative_lock, LOG_FILE],
            f"swarm: claim {task_id} on {scope}",
        )
    except git.GitError as e:
        # Commit failed — clean up
        delete_lock(repo_dir, task_id)
        return ClaimResult(
            success=False, task_id=task_id, scope=scope,
            message=f"Git commit failed: {e}",
        )

    # Step 8: Push
    try:
        pushed = git.push(repo_dir)
    except git.GitError as e:
        _rollback(repo_dir, task_id)
        return ClaimResult(
            success=False, task_id=task_id, scope=scope,
            message=f"Git push error: {e}",
        )

    if not pushed:
        _rollback(repo_dir, task_id)
        return ClaimResult(
            success=False, task_id=task_id, scope=scope,
            message="Push rejected (another agent won the race). Rolled back.",
        )

    return ClaimResult(
        success=True, task_id=task_id, scope=scope,
        message=f"Claimed '{scope}' for task {task_id} as {agent}",
    )


def _rollback(repo_dir: Path, task_id: str) -> None:
    """Roll back a failed push: reset commit and delete lock file."""
    try:
        git.reset_last_commit(repo_dir)
    except git.GitError:
        pass
    delete_lock(repo_dir, task_id)


def _log_conflict(repo_dir, task_id, scope, agent, conflict):
    """Log a conflict to SWARM_LOG.md."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blocking = conflict.blocking_lock
    blocker = f"blocked by {blocking.task_id}" if blocking else "unknown blocker"
    append_log(repo_dir, f"[{now}] CONFLICT | {task_id} | {blocker} | {agent}")

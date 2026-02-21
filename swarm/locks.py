"""Lock file I/O and SWARM_LOG.md appending.

No git calls — this module only handles filesystem operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from swarm.types import LockRecord, LockStatus


CLAIMED_DIR = Path("current_tasks") / "claimed"
LOG_FILE = "SWARM_LOG.md"


def lock_file_path(repo_dir: Path, task_id: str) -> Path:
    """Return the path where a lock file should live."""
    return repo_dir / CLAIMED_DIR / f"{task_id}.json"


def write_lock(repo_dir: Path, record: LockRecord) -> Path:
    """Write a lock record to disk. Returns the path written."""
    path = lock_file_path(repo_dir, record.task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2))
    return path


def read_lock(path: Path) -> LockRecord:
    """Read a lock record from a file path."""
    return LockRecord.model_validate_json(path.read_text())


def read_all_locks(repo_dir: Path) -> list[LockRecord]:
    """Read all active lock files from the claimed directory."""
    claimed = repo_dir / CLAIMED_DIR
    if not claimed.exists():
        return []
    locks = []
    for f in claimed.glob("*.json"):
        try:
            record = read_lock(f)
            if record.status == LockStatus.ACTIVE:
                locks.append(record)
        except Exception:
            # Skip malformed lock files
            continue
    return locks


def delete_lock(repo_dir: Path, task_id: str) -> bool:
    """Delete a lock file. Returns True if it existed and was deleted."""
    path = lock_file_path(repo_dir, task_id)
    if path.exists():
        path.unlink()
        return True
    return False


def append_log(repo_dir: Path, entry: str) -> None:
    """Append a line to SWARM_LOG.md."""
    log_path = repo_dir / LOG_FILE
    with log_path.open("a") as f:
        f.write(entry + "\n")

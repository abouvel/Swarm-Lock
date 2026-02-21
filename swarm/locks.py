"""Lock file I/O.

No git calls — this module only handles filesystem operations.
"""

from __future__ import annotations

from pathlib import Path

from swarm.types import LockRecord

CLAIMED_DIR = Path("current_tasks") / "claimed"


def lock_file_path(repo_dir: Path, keyword: str) -> Path:
    """Return the path where a lock file should live."""
    return repo_dir / CLAIMED_DIR / f"{keyword}.lock.json"


def write_lock(repo_dir: Path, record: LockRecord) -> Path:
    """Write a lock record to disk. Returns the path written."""
    path = lock_file_path(repo_dir, record.keyword)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2))
    return path


def read_lock(path: Path) -> LockRecord:
    """Read a lock record from a file path."""
    return LockRecord.model_validate_json(path.read_text())


def read_all_locks(repo_dir: Path) -> list[LockRecord]:
    """Read all lock files from the claimed directory."""
    claimed = repo_dir / CLAIMED_DIR
    if not claimed.exists():
        return []
    locks = []
    for f in claimed.glob("*.lock.json"):
        try:
            locks.append(read_lock(f))
        except Exception:
            continue
    return locks


def delete_lock(repo_dir: Path, keyword: str) -> bool:
    """Delete a lock file. Returns True if it existed and was deleted."""
    path = lock_file_path(repo_dir, keyword)
    if path.exists():
        path.unlink()
        return True
    return False

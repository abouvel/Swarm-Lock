"""Tests for swarm/locks.py — real filesystem, no git."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from swarm.locks import (
    append_log,
    delete_lock,
    lock_file_path,
    read_all_locks,
    read_lock,
    write_lock,
)
from swarm.types import LockRecord, LockStatus


class TestLockFilePath:
    def test_returns_correct_path(self, tmp_path):
        p = lock_file_path(tmp_path, "task-1")
        assert p == tmp_path / "current_tasks" / "claimed" / "task-1.json"


class TestWriteAndReadLock:
    def test_round_trip(self, tmp_repo, sample_lock):
        path = write_lock(tmp_repo, sample_lock)
        assert path.exists()
        loaded = read_lock(path)
        assert loaded.task_id == sample_lock.task_id
        assert loaded.scope == sample_lock.scope
        assert loaded.claimed_by == sample_lock.claimed_by
        assert loaded.status == LockStatus.ACTIVE

    def test_write_creates_dirs(self, tmp_path, sample_lock):
        # Even without pre-existing dirs, write_lock creates them
        path = write_lock(tmp_path, sample_lock)
        assert path.exists()


class TestReadAllLocks:
    def test_reads_active_locks(self, tmp_repo, sample_lock):
        write_lock(tmp_repo, sample_lock)

        # Add a second lock
        lock2 = sample_lock.model_copy(update={"task_id": "feat-456", "scope": "src/other.py"})
        write_lock(tmp_repo, lock2)

        locks = read_all_locks(tmp_repo)
        assert len(locks) == 2
        task_ids = {l.task_id for l in locks}
        assert task_ids == {"feature-123", "feat-456"}

    def test_skips_released_locks(self, tmp_repo, sample_lock):
        released = sample_lock.model_copy(update={"status": LockStatus.RELEASED})
        write_lock(tmp_repo, released)
        locks = read_all_locks(tmp_repo)
        assert len(locks) == 0

    def test_empty_dir(self, tmp_repo):
        locks = read_all_locks(tmp_repo)
        assert locks == []

    def test_skips_malformed_files(self, tmp_repo, sample_lock):
        write_lock(tmp_repo, sample_lock)
        # Write a bad file
        bad = tmp_repo / "current_tasks" / "claimed" / "bad.json"
        bad.write_text("not json")
        locks = read_all_locks(tmp_repo)
        assert len(locks) == 1


class TestDeleteLock:
    def test_delete_existing(self, tmp_repo, sample_lock):
        write_lock(tmp_repo, sample_lock)
        assert delete_lock(tmp_repo, sample_lock.task_id) is True
        assert not lock_file_path(tmp_repo, sample_lock.task_id).exists()

    def test_delete_nonexistent(self, tmp_repo):
        assert delete_lock(tmp_repo, "nope") is False


class TestAppendLog:
    def test_appends_line(self, tmp_repo):
        append_log(tmp_repo, "[2026-02-20] CLAIMED | task-1 | src/a.py | agent-1")
        append_log(tmp_repo, "[2026-02-20] RELEASED | task-1 | done | agent-1")
        log = (tmp_repo / "SWARM_LOG.md").read_text()
        lines = log.strip().split("\n")
        assert len(lines) == 2
        assert "CLAIMED" in lines[0]
        assert "RELEASED" in lines[1]

    def test_creates_file_if_missing(self, tmp_path):
        # No SWARM_LOG.md exists yet
        append_log(tmp_path, "first entry")
        assert (tmp_path / "SWARM_LOG.md").exists()

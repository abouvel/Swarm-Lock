"""Tests for swarm/status.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from swarm.locks import write_lock
from swarm.status import STALE_THRESHOLD, format_status, get_status
from swarm.types import LockRecord, LockStatus


def _make_lock(task_id: str, minutes_ago: int = 5) -> LockRecord:
    now = datetime.now(timezone.utc)
    ts = now - timedelta(minutes=minutes_ago)
    return LockRecord(
        task_id=task_id,
        scope=f"src/{task_id}.py",
        claimed_by="agent-1",
        claimed_at=ts,
        last_updated=ts,
        status=LockStatus.ACTIVE,
    )


class TestGetStatus:
    def test_empty(self, tmp_repo):
        status = get_status(tmp_repo)
        assert status["total"] == 0
        assert status["active"] == []
        assert status["stale"] == []

    def test_active_lock(self, tmp_repo):
        lock = _make_lock("task-1", minutes_ago=5)
        write_lock(tmp_repo, lock)
        status = get_status(tmp_repo)
        assert status["total"] == 1
        assert len(status["active"]) == 1
        assert len(status["stale"]) == 0

    def test_stale_lock(self, tmp_repo):
        lock = _make_lock("task-1", minutes_ago=45)
        write_lock(tmp_repo, lock)
        status = get_status(tmp_repo)
        assert status["total"] == 1
        assert len(status["active"]) == 0
        assert len(status["stale"]) == 1

    def test_mixed_locks(self, tmp_repo):
        write_lock(tmp_repo, _make_lock("fresh", minutes_ago=5))
        write_lock(tmp_repo, _make_lock("stale", minutes_ago=60))
        status = get_status(tmp_repo)
        assert status["total"] == 2
        assert len(status["active"]) == 1
        assert len(status["stale"]) == 1


class TestFormatStatus:
    def test_empty_status(self, tmp_repo):
        status = get_status(tmp_repo)
        output = format_status(status)
        assert "No active locks" in output

    def test_with_locks(self, tmp_repo):
        write_lock(tmp_repo, _make_lock("task-1", minutes_ago=5))
        status = get_status(tmp_repo)
        output = format_status(status)
        assert "task-1" in output
        assert "Active Locks" in output

    def test_stale_section(self, tmp_repo):
        write_lock(tmp_repo, _make_lock("old-task", minutes_ago=60))
        status = get_status(tmp_repo)
        output = format_status(status)
        assert "old-task" in output
        assert "Stale" in output

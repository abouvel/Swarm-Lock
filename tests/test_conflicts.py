"""Tests for swarm/conflicts.py — pure logic, no I/O."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from swarm.conflicts import check_conflict
from swarm.types import ConflictResult, LockRecord, LockStatus


def _make_lock(scope: str, task_id: str = "task-1", agent: str = "agent-1") -> LockRecord:
    now = datetime.now(timezone.utc)
    return LockRecord(
        task_id=task_id,
        scope=scope,
        claimed_by=agent,
        claimed_at=now,
        last_updated=now,
        status=LockStatus.ACTIVE,
    )


class TestExactMatch:
    def test_same_file(self):
        locks = [_make_lock("src/auth/session.py")]
        result = check_conflict("src/auth/session.py", locks)
        assert result.result == ConflictResult.HARD

    def test_same_function(self):
        locks = [_make_lock("src/auth/session.py:validate_token")]
        result = check_conflict("src/auth/session.py:validate_token", locks)
        assert result.result == ConflictResult.HARD

    def test_same_directory(self):
        locks = [_make_lock("src/auth/")]
        result = check_conflict("src/auth/", locks)
        assert result.result == ConflictResult.HARD


class TestDirectoryContainment:
    def test_file_inside_locked_directory(self):
        locks = [_make_lock("src/auth/")]
        result = check_conflict("src/auth/session.py", locks)
        assert result.result == ConflictResult.SOFT

    def test_directory_contains_locked_file(self):
        locks = [_make_lock("src/auth/session.py")]
        result = check_conflict("src/auth/", locks)
        assert result.result == ConflictResult.SOFT

    def test_function_inside_locked_directory(self):
        locks = [_make_lock("src/auth/")]
        result = check_conflict("src/auth/session.py:validate_token", locks)
        assert result.result == ConflictResult.SOFT

    def test_nested_directory_containment(self):
        locks = [_make_lock("src/")]
        result = check_conflict("src/auth/", locks)
        assert result.result == ConflictResult.SOFT

    def test_child_dir_claims_parent(self):
        locks = [_make_lock("src/auth/")]
        result = check_conflict("src/", locks)
        assert result.result == ConflictResult.SOFT


class TestSameFileDifferentFunction:
    def test_different_functions(self):
        locks = [_make_lock("src/auth/session.py:validate_token")]
        result = check_conflict("src/auth/session.py:refresh_token", locks)
        assert result.result == ConflictResult.SOFT

    def test_file_vs_function_is_soft(self):
        # Claiming whole file when a function is locked — overlapping but not exact
        locks = [_make_lock("src/auth/session.py:validate_token")]
        result = check_conflict("src/auth/session.py", locks)
        assert result.result == ConflictResult.SOFT


class TestNoConflict:
    def test_disjoint_files(self):
        locks = [_make_lock("src/auth/session.py")]
        result = check_conflict("src/db/models.py", locks)
        assert result.result == ConflictResult.NONE

    def test_disjoint_directories(self):
        locks = [_make_lock("src/auth/")]
        result = check_conflict("src/db/", locks)
        assert result.result == ConflictResult.NONE

    def test_empty_locks(self):
        result = check_conflict("src/anything.py", [])
        assert result.result == ConflictResult.NONE

    def test_similar_prefix_but_different_dir(self):
        # src/auth-utils/ should NOT conflict with src/auth/
        locks = [_make_lock("src/auth/")]
        result = check_conflict("src/auth-utils/foo.py", locks)
        assert result.result == ConflictResult.NONE


class TestPriority:
    def test_hard_takes_priority_over_soft(self):
        locks = [
            _make_lock("src/auth/", task_id="t1"),  # SOFT with incoming
            _make_lock("src/auth/session.py", task_id="t2"),  # HARD with incoming
        ]
        result = check_conflict("src/auth/session.py", locks)
        assert result.result == ConflictResult.HARD
        assert result.blocking_lock.task_id == "t2"

    def test_first_soft_returned(self):
        locks = [
            _make_lock("src/auth/session.py:validate_token", task_id="t1"),
            _make_lock("src/auth/session.py:refresh_token", task_id="t2"),
        ]
        result = check_conflict("src/auth/session.py:other_func", locks)
        assert result.result == ConflictResult.SOFT
        assert result.blocking_lock.task_id == "t1"

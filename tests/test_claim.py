"""Tests for swarm/claim.py."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from swarm.claim import claim
from swarm.locks import lock_file_path, read_lock, write_lock
from swarm.types import ConflictResult, LockRecord, LockStatus


@pytest.fixture
def mock_git_ops():
    """Patch all git operations for claim tests."""
    with patch("swarm.claim.git") as mock:
        mock.pull_rebase = MagicMock(return_value=True)
        mock.add_and_commit = MagicMock(return_value=True)
        mock.push = MagicMock(return_value=True)
        mock.reset_last_commit = MagicMock(return_value=True)
        mock.GitError = __import__("swarm.git", fromlist=["GitError"]).GitError
        yield mock


class TestClaimSuccess:
    def test_basic_claim(self, tmp_repo, mock_git_ops):
        result = claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1")
        assert result.success is True
        assert result.task_id == "task-1"
        assert "Claimed" in result.message

        # Lock file should exist
        lf = lock_file_path(tmp_repo, "task-1")
        assert lf.exists()
        record = read_lock(lf)
        assert record.scope == "src/main.py"
        assert record.claimed_by == "agent-1"

        # Git should have been called
        mock_git_ops.pull_rebase.assert_called_once()
        mock_git_ops.add_and_commit.assert_called_once()
        mock_git_ops.push.assert_called_once()

    def test_log_entry_written(self, tmp_repo, mock_git_ops):
        claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1")
        log = (tmp_repo / "SWARM_LOG.md").read_text()
        assert "CLAIMED" in log
        assert "task-1" in log
        assert "agent-1" in log


class TestClaimConflict:
    def test_hard_conflict_blocks(self, tmp_repo, mock_git_ops):
        # Pre-existing lock
        now = datetime.now(timezone.utc)
        existing = LockRecord(
            task_id="task-0", scope="src/main.py", claimed_by="agent-0",
            claimed_at=now, last_updated=now, status=LockStatus.ACTIVE,
        )
        write_lock(tmp_repo, existing)

        result = claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1")
        assert result.success is False
        assert result.conflict is not None
        assert result.conflict.result == ConflictResult.HARD

        # Should NOT have committed or pushed
        mock_git_ops.add_and_commit.assert_not_called()

    def test_soft_conflict_blocks_without_force(self, tmp_repo, mock_git_ops):
        now = datetime.now(timezone.utc)
        existing = LockRecord(
            task_id="task-0", scope="src/", claimed_by="agent-0",
            claimed_at=now, last_updated=now, status=LockStatus.ACTIVE,
        )
        write_lock(tmp_repo, existing)

        result = claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1")
        assert result.success is False
        assert result.conflict.result == ConflictResult.SOFT
        assert "--force" in result.message

    def test_soft_conflict_passes_with_force(self, tmp_repo, mock_git_ops):
        now = datetime.now(timezone.utc)
        existing = LockRecord(
            task_id="task-0", scope="src/", claimed_by="agent-0",
            claimed_at=now, last_updated=now, status=LockStatus.ACTIVE,
        )
        write_lock(tmp_repo, existing)

        result = claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1", force=True)
        assert result.success is True


class TestClaimPushRejection:
    def test_push_rejected_rolls_back(self, tmp_repo, mock_git_ops):
        mock_git_ops.push.return_value = False

        result = claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1")
        assert result.success is False
        assert "rejected" in result.message.lower()

        # Lock file should have been cleaned up
        assert not lock_file_path(tmp_repo, "task-1").exists()
        mock_git_ops.reset_last_commit.assert_called_once()


class TestClaimGitFailures:
    def test_pull_failure(self, tmp_repo, mock_git_ops):
        from swarm.git import GitError
        mock_git_ops.pull_rebase.side_effect = GitError("network error")

        result = claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1")
        assert result.success is False
        assert "pull failed" in result.message.lower()

    def test_commit_failure_cleans_up(self, tmp_repo, mock_git_ops):
        from swarm.git import GitError
        mock_git_ops.add_and_commit.side_effect = GitError("commit failed")

        result = claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1")
        assert result.success is False
        assert not lock_file_path(tmp_repo, "task-1").exists()


class TestClaimFilelock:
    def test_filelock_timeout(self, tmp_repo):
        from filelock import FileLock

        # Hold the lock so claim times out
        lock_path = tmp_repo / "current_tasks" / "claimed" / ".claim.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        with patch("swarm.claim.FILELOCK_TIMEOUT", 0):
            with FileLock(lock_path):
                result = claim(tmp_repo, "task-1", "src/main.py", agent_id="agent-1")
                assert result.success is False
                assert "filelock" in result.message.lower()

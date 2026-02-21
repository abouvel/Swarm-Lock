"""Tests for swarm/release.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from swarm.locks import lock_file_path, write_lock
from swarm.release import release
from swarm.types import LockRecord, LockStatus


@pytest.fixture
def mock_git_ops():
    """Patch all git operations for release tests."""
    with patch("swarm.release.git") as mock:
        mock.pull_rebase = MagicMock(return_value=True)
        mock.add_and_commit = MagicMock(return_value=True)
        mock.push = MagicMock(return_value=True)
        mock.reset_last_commit = MagicMock(return_value=True)
        mock.GitError = __import__("swarm.git", fromlist=["GitError"]).GitError
        yield mock


@pytest.fixture
def locked_repo(tmp_repo):
    """A tmp repo with an existing active lock."""
    now = datetime.now(timezone.utc)
    record = LockRecord(
        task_id="task-1", scope="src/main.py", claimed_by="agent-1",
        claimed_at=now, last_updated=now, status=LockStatus.ACTIVE,
    )
    write_lock(tmp_repo, record)
    return tmp_repo


class TestReleaseSuccess:
    def test_basic_release(self, locked_repo, mock_git_ops):
        result = release(locked_repo, "task-1", summary="done", agent_id="agent-1")
        assert result.success is True
        assert result.task_id == "task-1"
        assert result.summary == "done"

        # Lock file should be gone
        assert not lock_file_path(locked_repo, "task-1").exists()

        # Git should have been called
        mock_git_ops.pull_rebase.assert_called_once()
        mock_git_ops.add_and_commit.assert_called_once()
        mock_git_ops.push.assert_called_once()

    def test_log_entry_written(self, locked_repo, mock_git_ops):
        release(locked_repo, "task-1", summary="testing complete", agent_id="agent-1")
        log = (locked_repo / "SWARM_LOG.md").read_text()
        assert "RELEASED" in log
        assert "task-1" in log
        assert "testing complete" in log


class TestReleaseValidation:
    def test_missing_lock_file(self, tmp_repo, mock_git_ops):
        result = release(tmp_repo, "nonexistent", agent_id="agent-1")
        assert result.success is False
        assert "No lock file" in result.message

    def test_wrong_agent(self, locked_repo, mock_git_ops):
        result = release(locked_repo, "task-1", agent_id="agent-2")
        assert result.success is False
        assert "agent-1" in result.message
        assert "Cannot release" in result.message

        # Lock should still exist
        assert lock_file_path(locked_repo, "task-1").exists()


class TestReleasePushRejection:
    def test_push_rejected_restores_lock(self, locked_repo, mock_git_ops):
        mock_git_ops.push.return_value = False

        result = release(locked_repo, "task-1", agent_id="agent-1")
        assert result.success is False
        assert "rejected" in result.message.lower()

        # Lock file should have been restored
        assert lock_file_path(locked_repo, "task-1").exists()
        mock_git_ops.reset_last_commit.assert_called_once()


class TestReleaseGitFailures:
    def test_pull_failure(self, locked_repo, mock_git_ops):
        from swarm.git import GitError
        mock_git_ops.pull_rebase.side_effect = GitError("network error")

        result = release(locked_repo, "task-1", agent_id="agent-1")
        assert result.success is False
        assert "pull failed" in result.message.lower()

    def test_commit_failure_restores_lock(self, locked_repo, mock_git_ops):
        from swarm.git import GitError
        mock_git_ops.add_and_commit.side_effect = GitError("commit failed")

        result = release(locked_repo, "task-1", agent_id="agent-1")
        assert result.success is False

        # Lock should have been re-created
        assert lock_file_path(locked_repo, "task-1").exists()

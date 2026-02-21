"""Tests for swarm/git.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from swarm.git import (
    GitError,
    add_and_commit,
    get_repo_root,
    pull_rebase,
    push,
    reset_last_commit,
)


@pytest.fixture
def mock_run():
    with patch("swarm.git.subprocess.run") as m:
        m.return_value = MagicMock(returncode=0, stdout="", stderr="")
        yield m


class TestPullRebase:
    def test_success(self, mock_run, tmp_path):
        assert pull_rebase(tmp_path) is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["git", "pull", "--rebase"]

    def test_failure_raises(self, mock_run, tmp_path):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "conflict"
        with pytest.raises(GitError):
            pull_rebase(tmp_path)


class TestAddAndCommit:
    def test_success(self, mock_run, tmp_path):
        assert add_and_commit(tmp_path, ["file.json", "LOG.md"], "msg") is True
        assert mock_run.call_count == 2
        # First call: git add
        assert mock_run.call_args_list[0][0][0] == ["git", "add", "file.json", "LOG.md"]
        # Second call: git commit
        assert mock_run.call_args_list[1][0][0] == ["git", "commit", "-m", "msg"]


class TestPush:
    def test_success(self, mock_run, tmp_path):
        assert push(tmp_path) is True

    def test_rejection_returns_false(self, mock_run, tmp_path):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "! [rejected] main -> main (non-fast-forward)"
        assert push(tmp_path) is False

    def test_unexpected_error_raises(self, mock_run, tmp_path):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "fatal: could not read from remote repository"
        with pytest.raises(GitError):
            push(tmp_path)


class TestResetLastCommit:
    def test_success(self, mock_run, tmp_path):
        assert reset_last_commit(tmp_path) is True
        args = mock_run.call_args[0][0]
        assert args == ["git", "reset", "HEAD~1"]


class TestGetRepoRoot:
    def test_success(self, mock_run):
        mock_run.return_value.stdout = "/home/user/repo\n"
        root = get_repo_root(Path("/home/user/repo/sub"))
        assert root == Path("/home/user/repo")

    def test_not_a_repo(self, mock_run):
        mock_run.return_value.returncode = 128
        mock_run.return_value.stderr = "fatal: not a git repository"
        with pytest.raises(GitError):
            get_repo_root(Path("/tmp"))


class TestGitTimeout:
    def test_timeout_raises_git_error(self, tmp_path):
        import subprocess as sp

        with patch("swarm.git.subprocess.run", side_effect=sp.TimeoutExpired("git", 30)):
            with pytest.raises(GitError, match="timed out"):
                pull_rebase(tmp_path)

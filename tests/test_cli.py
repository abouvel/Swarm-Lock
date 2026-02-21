"""Tests for swarm/cli.py."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from swarm.cli import app
from swarm.locks import lock_file_path, write_lock
from swarm.types import LockRecord

runner = CliRunner(mix_stderr=False)


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.git.pull_rebase", return_value=True)
@patch("swarm.cli.git.add_and_commit", return_value=True)
@patch("swarm.cli.git.push", return_value=True)
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_start_success(mock_id, mock_push, mock_commit, mock_pull, mock_root, tmp_repo):
    mock_root.return_value = tmp_repo
    result = runner.invoke(app, ["start", "auth"])
    assert result.exit_code == 0
    assert "locked 'auth'" in result.output
    assert lock_file_path(tmp_repo, "auth").exists()


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.git.pull_rebase", return_value=True)
@patch("swarm.cli.get_agent_id", return_value="agent-2")
def test_start_already_locked(mock_id, mock_pull, mock_root, tmp_repo):
    mock_root.return_value = tmp_repo
    # Pre-create lock
    now = datetime.now(timezone.utc)
    write_lock(tmp_repo, LockRecord(keyword="auth", claimed_by="agent-1", claimed_at=now))
    result = runner.invoke(app, ["start", "auth"])
    assert result.exit_code == 1
    assert "already locked by agent-1" in result.output


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.git.pull_rebase", return_value=True)
@patch("swarm.cli.git.add_and_commit", return_value=True)
@patch("swarm.cli.git.push", return_value=False)
@patch("swarm.cli.git.reset_last_commit", return_value=True)
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_start_push_rejected(mock_id, mock_reset, mock_push, mock_commit, mock_pull, mock_root, tmp_repo):
    mock_root.return_value = tmp_repo
    result = runner.invoke(app, ["start", "auth"])
    assert result.exit_code == 1
    assert "conflict" in result.output
    assert not lock_file_path(tmp_repo, "auth").exists()


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.git._run_git")
@patch("swarm.cli.git.push", return_value=True)
def test_done_success(mock_push, mock_git, mock_root, tmp_repo):
    mock_root.return_value = tmp_repo
    now = datetime.now(timezone.utc)
    write_lock(tmp_repo, LockRecord(keyword="auth", claimed_by="agent-1", claimed_at=now))
    result = runner.invoke(app, ["done", "auth"])
    assert result.exit_code == 0
    assert "unlocked 'auth'" in result.output


@patch("swarm.cli.git.get_repo_root")
def test_done_no_lock(mock_root, tmp_repo):
    mock_root.return_value = tmp_repo
    result = runner.invoke(app, ["done", "auth"])
    assert result.exit_code == 1
    assert "no active lock" in result.output


@patch("swarm.cli.git.get_repo_root")
def test_status_empty(mock_root, tmp_repo):
    mock_root.return_value = tmp_repo
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "no active locks" in result.output


@patch("swarm.cli.git.get_repo_root")
def test_status_with_lock(mock_root, tmp_repo):
    mock_root.return_value = tmp_repo
    now = datetime.now(timezone.utc)
    write_lock(tmp_repo, LockRecord(keyword="auth", claimed_by="agent-1", claimed_at=now))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "auth" in result.output
    assert "agent-1" in result.output


# --- Phase B: idempotent start + check ---

@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.git.pull_rebase", return_value=True)
@patch("swarm.cli.git.add_and_commit", return_value=True)
@patch("swarm.cli.git.push", return_value=True)
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_start_idempotent(mock_id, mock_push, mock_commit, mock_pull, mock_root, tmp_repo):
    """start --if-not-held when already holding → exit 0, no git calls."""
    mock_root.return_value = tmp_repo
    now = datetime.now(timezone.utc)
    write_lock(tmp_repo, LockRecord(keyword="auth", claimed_by="agent-1", claimed_at=now))
    result = runner.invoke(app, ["start", "--if-not-held", "auth"])
    assert result.exit_code == 0
    mock_pull.assert_not_called()
    mock_commit.assert_not_called()
    mock_push.assert_not_called()


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_check_free(mock_id, mock_root, tmp_repo):
    """No lock file → exit 0."""
    mock_root.return_value = tmp_repo
    result = runner.invoke(app, ["check", "auth"])
    assert result.exit_code == 0


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_check_own(mock_id, mock_root, tmp_repo):
    """Lock exists, same agent → exit 0."""
    mock_root.return_value = tmp_repo
    now = datetime.now(timezone.utc)
    write_lock(tmp_repo, LockRecord(keyword="auth", claimed_by="agent-1", claimed_at=now))
    result = runner.invoke(app, ["check", "auth"])
    assert result.exit_code == 0


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_check_blocked(mock_id, mock_root, tmp_repo):
    """Lock exists, different agent → exit 2, BLOCKED in output."""
    mock_root.return_value = tmp_repo
    now = datetime.now(timezone.utc)
    write_lock(tmp_repo, LockRecord(keyword="auth", claimed_by="agent-2", claimed_at=now))
    result = runner.invoke(app, ["check", "auth"])
    assert result.exit_code == 2
    assert "BLOCKED" in result.output


# --- Phase D: hook pre-edit ---

@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.git.pull_rebase", return_value=True)
@patch("swarm.cli.git.add_and_commit", return_value=True)
@patch("swarm.cli.git.push", return_value=True)
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_hook_pre_edit_free_keyword(mock_id, mock_push, mock_commit, mock_pull, mock_root, tmp_repo):
    """No lock → auto-claims, exit 0."""
    mock_root.return_value = tmp_repo
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/auth/login.py"}})
    result = runner.invoke(app, ["hook", "pre-edit"], input=payload)
    assert result.exit_code == 0
    assert lock_file_path(tmp_repo, "src").exists()


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_hook_pre_edit_own_keyword(mock_id, mock_root, tmp_repo):
    """Already held by this agent → no-op, exit 0."""
    mock_root.return_value = tmp_repo
    now = datetime.now(timezone.utc)
    write_lock(tmp_repo, LockRecord(keyword="src", claimed_by="agent-1", claimed_at=now))
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/auth/login.py"}})
    result = runner.invoke(app, ["hook", "pre-edit"], input=payload)
    assert result.exit_code == 0


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_hook_pre_edit_blocked(mock_id, mock_root, tmp_repo):
    """Held by another → exit 2, BLOCKED in output."""
    mock_root.return_value = tmp_repo
    now = datetime.now(timezone.utc)
    write_lock(tmp_repo, LockRecord(keyword="src", claimed_by="agent-2", claimed_at=now))
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/auth/login.py"}})
    result = runner.invoke(app, ["hook", "pre-edit"], input=payload)
    assert result.exit_code == 2
    assert "BLOCKED" in result.output


@patch("swarm.cli.git.get_repo_root")
def test_hook_pre_edit_no_file_path(mock_root, tmp_repo):
    """Empty payload → exit 0 (pass-through)."""
    mock_root.return_value = tmp_repo
    payload = json.dumps({"tool_name": "Edit", "tool_input": {}})
    result = runner.invoke(app, ["hook", "pre-edit"], input=payload)
    assert result.exit_code == 0


@patch("swarm.cli.git.get_repo_root")
@patch("swarm.cli.git.pull_rebase", return_value=True)
@patch("swarm.cli.git.add_and_commit", return_value=True)
@patch("swarm.cli.git.push", return_value=True)
@patch("swarm.cli.get_agent_id", return_value="agent-1")
def test_hook_pre_edit_uses_index(mock_id, mock_push, mock_commit, mock_pull, mock_root, tmp_repo):
    """Index maps file to keyword, claims that keyword."""
    from datetime import datetime, timezone
    from swarm.index import SwarmIndex, write_index

    mock_root.return_value = tmp_repo
    now = datetime.now(timezone.utc)
    index = SwarmIndex(
        created_at=now,
        last_updated=now,
        terms={"auth": ["src/auth/"]},
    )
    write_index(tmp_repo, index)

    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/auth/login.py"}})
    result = runner.invoke(app, ["hook", "pre-edit"], input=payload)
    assert result.exit_code == 0
    assert lock_file_path(tmp_repo, "auth").exists()

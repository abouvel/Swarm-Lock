"""Tests for cli.py — thin entry point tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from cli import app
from swarm.types import ClaimResult, ConflictDetail, ConflictResult, LockRecord, LockStatus, ReleaseResult

runner = CliRunner()


@pytest.fixture(autouse=True)
def mock_repo_root(tmp_path):
    with patch("cli.git.get_repo_root", return_value=tmp_path):
        yield tmp_path


class TestClaimCommand:
    def test_success(self, mock_repo_root):
        result_obj = ClaimResult(success=True, task_id="t1", scope="src/a.py", message="Claimed 'src/a.py'")
        with patch("cli.do_claim", return_value=result_obj):
            with patch("cli.get_agent_id", return_value="agent-1"):
                result = runner.invoke(app, ["claim", "t1", "src/a.py"])
                assert result.exit_code == 0
                assert "Claimed" in result.output

    def test_failure(self, mock_repo_root):
        result_obj = ClaimResult(success=False, task_id="t1", scope="src/a.py", message="Hard conflict")
        with patch("cli.do_claim", return_value=result_obj):
            with patch("cli.get_agent_id", return_value="agent-1"):
                result = runner.invoke(app, ["claim", "t1", "src/a.py"])
                assert result.exit_code == 1

    def test_force_flag(self, mock_repo_root):
        result_obj = ClaimResult(success=True, task_id="t1", scope="src/a.py", message="ok")
        with patch("cli.do_claim", return_value=result_obj) as mock_claim:
            with patch("cli.get_agent_id", return_value="agent-1"):
                runner.invoke(app, ["claim", "t1", "src/a.py", "--force"])
                mock_claim.assert_called_once()
                assert mock_claim.call_args.kwargs["force"] is True


class TestReleaseCommand:
    def test_success(self, mock_repo_root):
        result_obj = ReleaseResult(success=True, task_id="t1", summary="done", message="Released")
        with patch("cli.do_release", return_value=result_obj):
            with patch("cli.get_agent_id", return_value="agent-1"):
                result = runner.invoke(app, ["release", "t1", "done"])
                assert result.exit_code == 0
                assert "Released" in result.output

    def test_failure(self, mock_repo_root):
        result_obj = ReleaseResult(success=False, task_id="t1", message="No lock file")
        with patch("cli.do_release", return_value=result_obj):
            with patch("cli.get_agent_id", return_value="agent-1"):
                result = runner.invoke(app, ["release", "t1"])
                assert result.exit_code == 1


class TestStatusCommand:
    def test_empty(self, mock_repo_root):
        with patch("cli.get_status", return_value={"active": [], "stale": [], "total": 0}):
            with patch("cli.format_status", return_value="No active locks."):
                result = runner.invoke(app, ["status"])
                assert result.exit_code == 0
                assert "No active locks" in result.output


class TestCheckConflictCommand:
    def test_no_conflict(self, mock_repo_root):
        with patch("cli.read_all_locks", return_value=[]):
            result = runner.invoke(app, ["check-conflict", "src/a.py"])
            assert result.exit_code == 0
            assert "No conflicts" in result.output

    def test_hard_conflict(self, mock_repo_root):
        now = datetime.now(timezone.utc)
        lock = LockRecord(
            task_id="t1", scope="src/a.py", claimed_by="agent-1",
            claimed_at=now, last_updated=now, status=LockStatus.ACTIVE,
        )
        with patch("cli.read_all_locks", return_value=[lock]):
            result = runner.invoke(app, ["check-conflict", "src/a.py"])
            assert result.exit_code == 1
            assert "Hard conflict" in result.output


class TestOracleCommand:
    def test_success(self, mock_repo_root):
        from swarm.oracle import OracleResult
        oracle_result = OracleResult(success=True, summary="5 passed")
        with patch("cli.run_oracle", return_value=oracle_result):
            result = runner.invoke(app, ["oracle"])
            assert result.exit_code == 0
            assert "passed" in result.output

    def test_failure(self, mock_repo_root):
        from swarm.oracle import OracleResult
        oracle_result = OracleResult(success=False, summary="2 failed")
        with patch("cli.run_oracle", return_value=oracle_result):
            result = runner.invoke(app, ["oracle"])
            assert result.exit_code == 1

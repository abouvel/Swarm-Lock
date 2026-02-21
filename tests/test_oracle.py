"""Tests for swarm/oracle.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from swarm.oracle import OracleResult, run_oracle


@pytest.fixture
def mock_subprocess():
    with patch("swarm.oracle.subprocess.run") as m:
        m.return_value = MagicMock(returncode=0, stdout="all good", stderr="")
        yield m


class TestRunOracle:
    def test_all_pass(self, tmp_path, mock_subprocess):
        result = run_oracle(tmp_path)
        assert result.success is True
        assert len(result.commands_run) == 2  # pytest + ruff

    def test_failure_detected(self, tmp_path, mock_subprocess):
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stdout = "FAILED test_foo.py"
        result = run_oracle(tmp_path)
        assert result.success is False

    def test_custom_commands(self, tmp_path, mock_subprocess):
        result = run_oracle(tmp_path, commands=[["echo", "hello"]])
        assert result.success is True
        assert len(result.commands_run) == 1
        assert "echo hello" in result.commands_run[0]

    def test_summary_contains_output(self, tmp_path, mock_subprocess):
        mock_subprocess.return_value.stdout = "5 passed"
        result = run_oracle(tmp_path)
        assert "5 passed" in result.summary

    def test_command_not_found(self, tmp_path):
        with patch("swarm.oracle.subprocess.run", side_effect=FileNotFoundError):
            result = run_oracle(tmp_path, commands=[["nonexistent"]])
            assert result.success is False
            assert "not found" in result.outputs["nonexistent"].lower()

    def test_timeout(self, tmp_path):
        import subprocess as sp
        with patch("swarm.oracle.subprocess.run", side_effect=sp.TimeoutExpired("cmd", 120)):
            result = run_oracle(tmp_path, commands=[["slow"]])
            assert result.success is False
            assert "timed out" in result.outputs["slow"].lower()

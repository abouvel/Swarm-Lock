"""Tests for swarm/types.py."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from swarm.types import (
    ClaimResult,
    ConflictDetail,
    ConflictResult,
    LockRecord,
    LockStatus,
    ReleaseResult,
    ScopeType,
    get_agent_id,
    parse_scope,
)


class TestLockRecord:
    def test_create_lock_record(self):
        now = datetime.now(timezone.utc)
        rec = LockRecord(
            task_id="feat-1",
            scope="src/main.py",
            claimed_by="agent-1",
            claimed_at=now,
            last_updated=now,
        )
        assert rec.status == LockStatus.ACTIVE
        assert rec.notes == ""
        assert rec.task_id == "feat-1"

    def test_lock_record_serialization(self):
        now = datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc)
        rec = LockRecord(
            task_id="feat-1",
            scope="src/main.py",
            claimed_by="agent-1",
            claimed_at=now,
            last_updated=now,
        )
        data = rec.model_dump()
        assert data["status"] == "active"
        assert data["task_id"] == "feat-1"

        # Round-trip through JSON
        json_str = rec.model_dump_json()
        rec2 = LockRecord.model_validate_json(json_str)
        assert rec2 == rec


class TestParseScope:
    def test_file_scope(self):
        assert parse_scope("src/auth/session.py") == ScopeType.FILE

    def test_function_scope(self):
        assert parse_scope("src/auth/session.py:validate_token") == ScopeType.FUNCTION

    def test_directory_scope(self):
        assert parse_scope("src/auth/") == ScopeType.DIRECTORY

    def test_root_directory(self):
        assert parse_scope("src/") == ScopeType.DIRECTORY

    def test_nested_colons(self):
        # Edge case: multiple colons still treated as function
        assert parse_scope("src/file.py:Class:method") == ScopeType.FUNCTION


class TestGetAgentId:
    def test_env_var_takes_priority(self):
        with patch.dict("os.environ", {"AGENT_ID": "agent-42"}):
            assert get_agent_id() == "agent-42"

    def test_git_config_fallback(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "git-user\n"
                result = get_agent_id()
                # Only assert if AGENT_ID wasn't set
                if "AGENT_ID" not in __import__("os").environ:
                    assert result == "git-user"

    def test_fallback_to_unknown(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stdout = ""
                assert get_agent_id() == "agent-unknown"

    def test_env_var_empty_string_uses_fallback(self):
        # Empty string is falsy, should fall through
        with patch.dict("os.environ", {"AGENT_ID": ""}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stdout = ""
                assert get_agent_id() == "agent-unknown"


class TestClaimResult:
    def test_success(self):
        r = ClaimResult(success=True, task_id="t1", scope="src/a.py", message="ok")
        assert r.success
        assert r.conflict is None

    def test_with_conflict(self):
        conflict = ConflictDetail(result=ConflictResult.HARD, message="exact match")
        r = ClaimResult(
            success=False, task_id="t1", scope="src/a.py", conflict=conflict
        )
        assert not r.success
        assert r.conflict.result == ConflictResult.HARD


class TestReleaseResult:
    def test_success(self):
        r = ReleaseResult(success=True, task_id="t1", summary="done", message="ok")
        assert r.success

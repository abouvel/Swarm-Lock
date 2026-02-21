"""Tests for swarm/types.py."""

from datetime import datetime, timezone
from unittest.mock import patch

from swarm.types import LockRecord, get_agent_id


class TestLockRecord:
    def test_create(self):
        now = datetime.now(timezone.utc)
        rec = LockRecord(keyword="auth", claimed_by="agent-1", claimed_at=now)
        assert rec.keyword == "auth"
        assert rec.status == "active"

    def test_roundtrip_json(self):
        now = datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc)
        rec = LockRecord(keyword="auth", claimed_by="agent-1", claimed_at=now)
        rec2 = LockRecord.model_validate_json(rec.model_dump_json())
        assert rec2 == rec


class TestGetAgentId:
    def test_env_var(self):
        with patch.dict("os.environ", {"AGENT_ID": "agent-42"}):
            assert get_agent_id() == "agent-42"

    def test_fallback(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run") as m:
                m.return_value.returncode = 1
                m.return_value.stdout = ""
                assert get_agent_id() == "agent-unknown"

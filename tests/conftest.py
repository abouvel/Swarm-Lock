"""Shared test fixtures for swarm lock manager tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from swarm.types import LockRecord, LockStatus, ScopeType


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temporary directory mimicking a repo with current_tasks/claimed/."""
    claimed = tmp_path / "current_tasks" / "claimed"
    claimed.mkdir(parents=True)
    (claimed / ".gitkeep").touch()
    (tmp_path / "SWARM_LOG.md").touch()
    return tmp_path


@pytest.fixture
def sample_lock() -> LockRecord:
    """A sample active lock record."""
    return LockRecord(
        task_id="feature-123",
        scope="src/auth/session.py:validate_token",
        claimed_by="agent-1",
        claimed_at=datetime(2026, 2, 20, 14, 23, 0, tzinfo=timezone.utc),
        last_updated=datetime(2026, 2, 20, 14, 23, 0, tzinfo=timezone.utc),
        status=LockStatus.ACTIVE,
        notes="",
    )


@pytest.fixture
def sample_lock_file(tmp_repo: Path, sample_lock: LockRecord) -> Path:
    """Write a sample lock file to the tmp repo and return its path."""
    lock_dir = tmp_repo / "current_tasks" / "claimed"
    lock_path = lock_dir / f"{sample_lock.task_id}.json"
    lock_path.write_text(sample_lock.model_dump_json(indent=2))
    return lock_path


@pytest.fixture
def mock_git():
    """Mock git module functions. Returns a namespace with configurable mocks."""
    mock = MagicMock()
    mock.pull_rebase = MagicMock(return_value=True)
    mock.add_and_commit = MagicMock(return_value=True)
    mock.push = MagicMock(return_value=True)
    mock.reset_last_commit = MagicMock(return_value=True)
    mock.get_repo_root = MagicMock()
    return mock

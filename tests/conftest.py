"""Shared test fixtures."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from swarm.types import LockRecord


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temporary directory mimicking a repo with current_tasks/claimed/."""
    claimed = tmp_path / "current_tasks" / "claimed"
    claimed.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_lock() -> LockRecord:
    """A sample active lock record."""
    return LockRecord(
        keyword="auth",
        claimed_by="agent-1",
        claimed_at=datetime(2026, 2, 20, 14, 23, 0, tzinfo=timezone.utc),
    )

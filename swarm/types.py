"""Foundation types for the Swarm Lock Manager."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class LockStatus(str, Enum):
    ACTIVE = "active"
    RELEASED = "released"


class ScopeType(str, Enum):
    FILE = "file"
    FUNCTION = "function"
    DIRECTORY = "directory"


class LockRecord(BaseModel):
    task_id: str
    scope: str
    claimed_by: str
    claimed_at: datetime
    last_updated: datetime
    status: LockStatus = LockStatus.ACTIVE
    notes: str = ""


class ConflictResult(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    NONE = "none"


class ConflictDetail(BaseModel):
    result: ConflictResult
    blocking_lock: Optional[LockRecord] = None
    message: str = ""


class ClaimResult(BaseModel):
    success: bool
    task_id: str
    scope: str
    conflict: Optional[ConflictDetail] = None
    message: str = ""


class ReleaseResult(BaseModel):
    success: bool
    task_id: str
    summary: str = ""
    message: str = ""


def parse_scope(scope: str) -> ScopeType:
    """Determine scope type from string format.

    - Trailing slash → directory
    - Contains colon → function
    - Otherwise → file
    """
    if scope.endswith("/"):
        return ScopeType.DIRECTORY
    if ":" in scope:
        return ScopeType.FUNCTION
    return ScopeType.FILE


def get_agent_id() -> str:
    """Resolve agent identity.

    Priority: AGENT_ID env var → git config user.name → 'agent-unknown'
    """
    agent_id = os.environ.get("AGENT_ID")
    if agent_id:
        return agent_id

    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return "agent-unknown"

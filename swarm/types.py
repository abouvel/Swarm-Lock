"""Foundation types for the Swarm Lock Manager."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

from pydantic import BaseModel


class LockRecord(BaseModel):
    keyword: str
    claimed_by: str
    claimed_at: datetime
    status: str = "active"


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

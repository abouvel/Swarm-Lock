"""Status display — reads lock files and categorizes them."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from swarm.locks import read_all_locks
from swarm.types import LockRecord

STALE_THRESHOLD = timedelta(minutes=30)


def get_status(repo_dir: Path) -> dict:
    """Categorize locks as active or stale.

    Returns dict with keys: 'active', 'stale', 'total'.
    """
    locks = read_all_locks(repo_dir)
    now = datetime.now(timezone.utc)

    active = []
    stale = []

    for lock in locks:
        age = now - lock.last_updated
        if age > STALE_THRESHOLD:
            stale.append(lock)
        else:
            active.append(lock)

    return {
        "active": active,
        "stale": stale,
        "total": len(locks),
    }


def format_status(status: dict) -> str:
    """Format status as a rich table string."""
    console = Console(record=True, width=120)

    if status["total"] == 0:
        console.print("[green]No active locks.[/green]")
        return console.export_text()

    if status["active"]:
        table = Table(title="Active Locks", show_lines=True)
        table.add_column("Task ID", style="cyan")
        table.add_column("Scope", style="white")
        table.add_column("Agent", style="green")
        table.add_column("Claimed At", style="dim")
        table.add_column("Notes", style="dim")

        for lock in status["active"]:
            table.add_row(
                lock.task_id,
                lock.scope,
                lock.claimed_by,
                lock.claimed_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                lock.notes or "",
            )
        console.print(table)

    if status["stale"]:
        table = Table(title="⚠ Stale Locks (>30min)", show_lines=True)
        table.add_column("Task ID", style="red")
        table.add_column("Scope", style="white")
        table.add_column("Agent", style="yellow")
        table.add_column("Last Updated", style="dim")

        for lock in status["stale"]:
            table.add_row(
                lock.task_id,
                lock.scope,
                lock.claimed_by,
                lock.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC"),
            )
        console.print(table)

    return console.export_text()

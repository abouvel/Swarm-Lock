"""Thin CLI entry point for the Swarm Lock Manager.

No business logic here — delegates to swarm modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from swarm import git
from swarm.claim import claim as do_claim
from swarm.conflicts import check_conflict
from swarm.locks import read_all_locks
from swarm.oracle import run_oracle
from swarm.release import release as do_release
from swarm.status import format_status, get_status
from swarm.types import get_agent_id

app = typer.Typer(help="Swarm Lock Manager — distributed file locking for multi-agent workflows")
console = Console()


def _resolve_repo() -> Path:
    """Find the git repo root from CWD."""
    try:
        return git.get_repo_root()
    except git.GitError:
        console.print("[red]Error: not inside a git repository.[/red]")
        raise typer.Exit(code=1)


@app.command()
def claim(
    task_id: str = typer.Argument(help="Unique task identifier"),
    scope: str = typer.Argument(help="Scope to claim (file, file:function, or dir/)"),
    force: bool = typer.Option(False, "--force", "-f", help="Override soft conflicts"),
    notes: str = typer.Option("", "--notes", "-n", help="Optional notes"),
):
    """Claim a scope for editing."""
    repo = _resolve_repo()
    agent = get_agent_id()
    result = do_claim(repo, task_id, scope, agent_id=agent, force=force, notes=notes)

    if result.success:
        console.print(f"[green]✓[/green] {result.message}")
    else:
        console.print(f"[red]✗[/red] {result.message}")
        raise typer.Exit(code=1)


@app.command()
def release(
    task_id: str = typer.Argument(help="Task ID to release"),
    summary: str = typer.Argument(default="", help="Summary of work done"),
):
    """Release a previously claimed scope."""
    repo = _resolve_repo()
    agent = get_agent_id()
    result = do_release(repo, task_id, summary=summary, agent_id=agent)

    if result.success:
        console.print(f"[green]✓[/green] {result.message}")
    else:
        console.print(f"[red]✗[/red] {result.message}")
        raise typer.Exit(code=1)


@app.command()
def status():
    """Show all active and stale locks."""
    repo = _resolve_repo()
    st = get_status(repo)
    output = format_status(st)
    console.print(output)


@app.command(name="check-conflict")
def check_conflict_cmd(
    scope: str = typer.Argument(help="Scope to check for conflicts"),
):
    """Check if a scope would conflict with existing locks."""
    repo = _resolve_repo()
    existing = read_all_locks(repo)
    result = check_conflict(scope, existing)

    if result.result.value == "none":
        console.print(f"[green]No conflicts[/green] for '{scope}'")
    elif result.result.value == "soft":
        console.print(f"[yellow]Soft conflict:[/yellow] {result.message}")
        raise typer.Exit(code=1)
    else:
        console.print(f"[red]Hard conflict:[/red] {result.message}")
        raise typer.Exit(code=1)


@app.command()
def oracle():
    """Run pytest and ruff, report results."""
    repo = _resolve_repo()
    result = run_oracle(repo)

    if result.success:
        console.print("[green]All checks passed.[/green]")
    else:
        console.print("[red]Some checks failed.[/red]")

    console.print(result.summary)

    if not result.success:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

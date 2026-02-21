"""CLI entry point for the Swarm Lock Manager.

Commands: start, done, status, check, write-index, index-stale, hook pre-edit.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from swarm import git
from swarm.locks import (
    CLAIMED_DIR,
    delete_lock,
    lock_file_path,
    read_all_locks,
    read_lock,
    write_lock,
)
from swarm.types import LockRecord, get_agent_id

app = typer.Typer(help="Swarm Lock Manager — keyword-based distributed locking")
hook_app = typer.Typer(help="Hook subcommands for Claude Code integration")
app.add_typer(hook_app, name="hook")
console = Console()


def _resolve_repo() -> Path:
    """Find the git repo root from CWD."""
    try:
        return git.get_repo_root()
    except git.GitError:
        console.print("[red]Error: not inside a git repository.[/red]")
        raise typer.Exit(code=1)


def _top_level_dir(file_path: str) -> str:
    """'src/auth/login.py' -> 'src', 'auth/session.py' -> 'auth'"""
    parts = Path(file_path).parts
    return parts[0] if parts else file_path


def _do_start(repo: Path, agent: str, keyword: str) -> None:
    """Pull, write lock, commit, push. Raises typer.Exit on failure."""
    # Pull latest
    try:
        git.pull_rebase(repo)
    except git.GitError as e:
        console.print(f"[red]git pull failed: {e}[/red]")
        raise typer.Exit(code=1)

    # Write lock file
    now = datetime.now(timezone.utc)
    record = LockRecord(keyword=keyword, claimed_by=agent, claimed_at=now)
    written = write_lock(repo, record)
    relative = str(written.relative_to(repo))

    # Commit and push
    try:
        git.add_and_commit(repo, [relative], f"swarm: lock {keyword}")
    except git.GitError as e:
        delete_lock(repo, keyword)
        console.print(f"[red]commit failed: {e}[/red]")
        raise typer.Exit(code=1)

    try:
        pushed = git.push(repo)
    except git.GitError as e:
        git.reset_last_commit(repo)
        delete_lock(repo, keyword)
        console.print(f"[red]push failed: {e}[/red]")
        raise typer.Exit(code=1)

    if not pushed:
        git.reset_last_commit(repo)
        delete_lock(repo, keyword)
        console.print(f"[red]conflict — another agent locked '{keyword}' first[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]locked '{keyword}'[/green]")


@app.command()
def start(
    keyword: str = typer.Argument(help="Keyword to lock"),
    if_not_held: bool = typer.Option(False, "--if-not-held", help="No-op if already held by this agent"),
):
    """Lock a keyword before working on it."""
    repo = _resolve_repo()
    agent = get_agent_id()

    # Check if already locked
    lf = lock_file_path(repo, keyword)
    if lf.exists():
        try:
            existing = read_lock(lf)
            if if_not_held and existing.claimed_by == agent:
                return  # already ours, silent no-op
            console.print(
                f"[red]'{keyword}' is already locked by {existing.claimed_by} "
                f"(since {existing.claimed_at.strftime('%Y-%m-%d %H:%M:%S UTC')})[/red]"
            )
        except Exception:
            console.print(f"[red]'{keyword}' is already locked (corrupt lock file)[/red]")
        raise typer.Exit(code=1)

    _do_start(repo, agent, keyword)


@app.command()
def done(
    keyword: str = typer.Argument(help="Keyword to unlock"),
):
    """Unlock a keyword when done working on it."""
    repo = _resolve_repo()

    # Check lock exists
    lf = lock_file_path(repo, keyword)
    if not lf.exists():
        console.print(f"[red]no active lock for '{keyword}'[/red]")
        raise typer.Exit(code=1)

    relative = str(lf.relative_to(repo))

    # git rm, commit, push
    try:
        git._run_git(["rm", relative], cwd=repo)
        git._run_git(["commit", "-m", f"swarm: unlock {keyword}"], cwd=repo)
    except git.GitError as e:
        console.print(f"[red]commit failed: {e}[/red]")
        raise typer.Exit(code=1)

    try:
        pushed = git.push(repo)
    except git.GitError as e:
        git.reset_last_commit(repo)
        console.print(f"[red]push failed: {e}[/red]")
        raise typer.Exit(code=1)

    if not pushed:
        git.reset_last_commit(repo)
        console.print(f"[red]push rejected — try again[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]unlocked '{keyword}'[/green]")


@app.command()
def status():
    """Show all active locks."""
    repo = _resolve_repo()
    locks = read_all_locks(repo)

    if not locks:
        console.print("[green]no active locks[/green]")
        return

    table = Table(title="Active Locks", show_lines=True)
    table.add_column("Keyword", style="cyan")
    table.add_column("Agent", style="green")
    table.add_column("Locked At", style="dim")

    for lock in locks:
        table.add_row(
            lock.keyword,
            lock.claimed_by,
            lock.claimed_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
    console.print(table)


@app.command()
def check(keyword: str = typer.Argument(help="Keyword to check")):
    """Check if a keyword is available. Exit 0 = free/yours, 2 = blocked."""
    repo = _resolve_repo()
    agent = get_agent_id()
    lf = lock_file_path(repo, keyword)
    if not lf.exists():
        raise typer.Exit(0)
    existing = read_lock(lf)
    if existing.claimed_by == agent:
        raise typer.Exit(0)
    console.print(f"[red]BLOCKED: '{keyword}' is held by {existing.claimed_by}[/red]")
    raise typer.Exit(2)


@app.command(name="write-index")
def write_index_cmd():
    """Read JSON from stdin and write .swarm/index.json."""
    from swarm.index import SwarmIndex, compute_dir_hash, write_index

    repo = _resolve_repo()
    raw = json.load(sys.stdin)
    now = datetime.now(timezone.utc)
    index = SwarmIndex(
        created_at=now,
        last_updated=now,
        terms=raw["terms"],
        codebase_hash=compute_dir_hash(repo),
    )
    write_index(repo, index)
    console.print(f"[green]index written: {len(index.terms)} keywords[/green]")


@app.command(name="index-stale")
def index_stale():
    """Exit 0 if index is current, 1 if stale or missing."""
    from swarm.index import compute_dir_hash, read_index

    repo = _resolve_repo()
    index = read_index(repo)
    if index is None:
        raise typer.Exit(1)
    current_hash = compute_dir_hash(repo)
    if index.codebase_hash != current_hash:
        raise typer.Exit(1)
    raise typer.Exit(0)


@hook_app.command(name="pre-edit")
def hook_pre_edit():
    """
    Called by Claude Code PreToolUse hook.
    Reads JSON from stdin: {"tool_name": "Edit", "tool_input": {"file_path": "..."}}
    Resolves file -> keyword via index (falls back to top-level dir).
    Auto-claims the keyword if free or already held by this agent.
    Exit 0 = proceed. Exit 2 = blocked (shown to Claude).
    """
    from swarm.index import read_index, resolve_keyword

    payload = json.load(sys.stdin)
    file_path = (
        payload.get("tool_input", {}).get("file_path")
        or payload.get("tool_input", {}).get("path")
        or ""
    )
    if not file_path:
        raise typer.Exit(0)  # can't resolve, let it through

    repo = _resolve_repo()
    agent = get_agent_id()
    index = read_index(repo)

    if index:
        keyword = resolve_keyword(file_path, index) or _top_level_dir(file_path)
    else:
        keyword = _top_level_dir(file_path)

    # Check if blocked
    lf = lock_file_path(repo, keyword)
    if lf.exists():
        existing = read_lock(lf)
        if existing.claimed_by != agent:
            console.print(f"[red]BLOCKED: '{keyword}' held by {existing.claimed_by}[/red]")
            raise typer.Exit(2)
        raise typer.Exit(0)  # we hold it already

    # Auto-claim
    _do_start(repo, agent, keyword)
    raise typer.Exit(0)


if __name__ == "__main__":
    app()

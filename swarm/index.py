"""Semantic index: maps file paths to lock keywords.

No git calls, no lock calls — pure index I/O and file-to-keyword resolution.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

INDEX_PATH = Path(".swarm") / "index.json"


class SwarmIndex(BaseModel):
    version: int = 1
    created_at: datetime
    last_updated: datetime
    codebase_hash: str = ""
    terms: dict[str, list[str]]  # {"auth": ["src/auth/", "middleware/auth.py"]}


def read_index(repo_dir: Path) -> SwarmIndex | None:
    """Return index or None if not found."""
    path = repo_dir / INDEX_PATH
    if not path.exists():
        return None
    try:
        return SwarmIndex.model_validate_json(path.read_text())
    except Exception:
        return None


def write_index(repo_dir: Path, index: SwarmIndex) -> None:
    """Write .swarm/index.json, creating .swarm/ if needed."""
    path = repo_dir / INDEX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(index.model_dump_json(indent=2))


def resolve_keyword(file_path: str, index: SwarmIndex) -> str | None:
    """
    Given a file path, return the matching keyword by longest-prefix match.
    Returns None if no match (caller falls back to top-level directory).
    """
    best_keyword: str | None = None
    best_len: int = -1

    for keyword, patterns in index.terms.items():
        for pattern in patterns:
            # Normalize: strip trailing slash for prefix matching
            prefix = pattern.rstrip("/")
            if file_path == prefix or file_path.startswith(prefix + "/") or file_path.startswith(prefix + "\\"):
                if len(prefix) > best_len:
                    best_len = len(prefix)
                    best_keyword = keyword

    return best_keyword


def compute_dir_hash(repo_dir: Path) -> str:
    """sha256 of sorted directory listing (depth <= 3, excluding .git/.swarm)."""
    entries: list[str] = []
    _collect_dirs(repo_dir, repo_dir, depth=0, max_depth=3, entries=entries)
    digest = hashlib.sha256("\n".join(sorted(entries)).encode()).hexdigest()
    return digest


def _collect_dirs(base: Path, current: Path, depth: int, max_depth: int, entries: list[str]) -> None:
    if depth > max_depth:
        return
    try:
        for child in current.iterdir():
            if child.name in (".git", ".swarm", "__pycache__", "node_modules"):
                continue
            rel = str(child.relative_to(base))
            entries.append(rel)
            if child.is_dir() and depth < max_depth:
                _collect_dirs(base, child, depth + 1, max_depth, entries)
    except PermissionError:
        pass

"""Tests for swarm/index.py."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from swarm.index import (
    SwarmIndex,
    compute_dir_hash,
    read_index,
    resolve_keyword,
    write_index,
)


def _make_index(**kwargs) -> SwarmIndex:
    now = datetime.now(timezone.utc)
    defaults = dict(created_at=now, last_updated=now, terms={})
    defaults.update(kwargs)
    return SwarmIndex(**defaults)


def test_write_read_roundtrip(tmp_path: Path):
    index = _make_index(terms={"auth": ["src/auth/"], "api": ["src/api/"]})
    write_index(tmp_path, index)
    loaded = read_index(tmp_path)
    assert loaded is not None
    assert loaded.terms == index.terms
    assert loaded.version == index.version


def test_read_index_missing_returns_none(tmp_path: Path):
    assert read_index(tmp_path) is None


def test_resolve_exact_dir_match():
    index = _make_index(terms={"auth": ["src/auth/"]})
    assert resolve_keyword("src/auth/login.py", index) == "auth"


def test_resolve_longest_prefix_wins():
    index = _make_index(terms={"src": ["src/"], "auth": ["src/auth/"]})
    # src/auth/login.py matches both "src/" and "src/auth/" — longest wins
    assert resolve_keyword("src/auth/login.py", index) == "auth"


def test_resolve_no_match_returns_none():
    index = _make_index(terms={"auth": ["src/auth/"]})
    assert resolve_keyword("tests/test_foo.py", index) is None


def test_compute_dir_hash_deterministic(tmp_path: Path):
    # Create some dirs
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth").mkdir()
    (tmp_path / "tests").mkdir()
    h1 = compute_dir_hash(tmp_path)
    h2 = compute_dir_hash(tmp_path)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_compute_dir_hash_changes_on_new_dir(tmp_path: Path):
    (tmp_path / "src").mkdir()
    h1 = compute_dir_hash(tmp_path)
    (tmp_path / "api").mkdir()
    h2 = compute_dir_hash(tmp_path)
    assert h1 != h2

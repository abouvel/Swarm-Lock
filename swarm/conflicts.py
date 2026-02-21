"""Conflict detection logic for scope claims.

Pure logic — no I/O, no git calls. Depends only on types.
"""

from __future__ import annotations

from swarm.types import ConflictDetail, ConflictResult, LockRecord, ScopeType, parse_scope


def _split_scope(scope: str) -> tuple[str, str | None]:
    """Split a scope into file path and optional function name."""
    if ":" in scope:
        parts = scope.split(":", 1)
        return parts[0], parts[1]
    return scope.rstrip("/"), None


def _is_directory_scope(scope: str) -> bool:
    return scope.endswith("/")


def _check_pair(incoming: str, existing: str) -> ConflictResult:
    """Check conflict between two scopes."""
    # Exact match → HARD
    if incoming == existing:
        return ConflictResult.HARD

    incoming_is_dir = _is_directory_scope(incoming)
    existing_is_dir = _is_directory_scope(existing)

    incoming_file, incoming_func = _split_scope(incoming)
    existing_file, existing_func = _split_scope(existing)

    # Directory containment checks (either direction)
    if incoming_is_dir:
        incoming_dir = incoming.rstrip("/") + "/"
        # Existing scope is inside the incoming directory
        if existing_file.startswith(incoming_dir) or existing_file == incoming.rstrip("/"):
            return ConflictResult.SOFT
    if existing_is_dir:
        existing_dir = existing.rstrip("/") + "/"
        # Incoming scope is inside the existing directory
        if incoming_file.startswith(existing_dir) or incoming_file == existing.rstrip("/"):
            return ConflictResult.SOFT

    # Both are directories, check nesting
    if incoming_is_dir and existing_is_dir:
        inc = incoming.rstrip("/") + "/"
        ext = existing.rstrip("/") + "/"
        if inc.startswith(ext) or ext.startswith(inc):
            return ConflictResult.SOFT

    # Same file, different functions → SOFT
    if incoming_file == existing_file:
        if incoming_func != existing_func:
            return ConflictResult.SOFT
        # Same file, both no function → HARD (caught by exact match above for non-dir)
        return ConflictResult.HARD

    return ConflictResult.NONE


def check_conflict(incoming_scope: str, existing_locks: list[LockRecord]) -> ConflictDetail:
    """Check an incoming scope against all existing locks.

    Returns first HARD conflict found. If no HARD, returns first SOFT.
    If neither, returns NONE.
    """
    first_soft: ConflictDetail | None = None

    for lock in existing_locks:
        result = _check_pair(incoming_scope, lock.scope)

        if result == ConflictResult.HARD:
            return ConflictDetail(
                result=ConflictResult.HARD,
                blocking_lock=lock,
                message=f"Hard conflict: scope '{incoming_scope}' is already claimed by {lock.claimed_by} (task {lock.task_id})",
            )
        if result == ConflictResult.SOFT and first_soft is None:
            first_soft = ConflictDetail(
                result=ConflictResult.SOFT,
                blocking_lock=lock,
                message=f"Soft conflict: scope '{incoming_scope}' overlaps with {lock.claimed_by}'s claim on '{lock.scope}' (task {lock.task_id})",
            )

    if first_soft is not None:
        return first_soft

    return ConflictDetail(result=ConflictResult.NONE, message="No conflicts detected")

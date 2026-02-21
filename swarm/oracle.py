"""Oracle — runs pytest/ruff and captures output for Claude."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OracleResult:
    success: bool
    commands_run: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    summary: str = ""


def _run_command(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """Run a command and capture output. Returns (returncode, combined output)."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=120,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return result.returncode, output.strip()
    except FileNotFoundError:
        return -1, f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -1, f"Command timed out: {' '.join(cmd)}"


def run_oracle(
    repo_dir: Path,
    commands: list[list[str]] | None = None,
) -> OracleResult:
    """Run checks and return combined results.

    Default commands: pytest, ruff check.
    """
    if commands is None:
        commands = [
            ["python", "-m", "pytest", "--tb=short", "-q"],
            ["python", "-m", "ruff", "check", "."],
        ]

    all_passed = True
    outputs = {}
    commands_run = []

    for cmd in commands:
        cmd_str = " ".join(cmd)
        commands_run.append(cmd_str)
        code, output = _run_command(cmd, repo_dir)
        outputs[cmd_str] = output
        if code != 0:
            all_passed = False

    # Build summary
    parts = []
    for cmd_str, output in outputs.items():
        parts.append(f"$ {cmd_str}\n{output}")
    summary = "\n\n---\n\n".join(parts)

    return OracleResult(
        success=all_passed,
        commands_run=commands_run,
        outputs=outputs,
        summary=summary,
    )

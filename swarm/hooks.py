"""Git hook management for auto-releasing locks on branch switch."""

from __future__ import annotations

import stat
from pathlib import Path

from swarm import git
from swarm.locks import read_all_locks
from swarm.types import get_agent_id

# The post-checkout hook script that runs release on branch switch
HOOK_SCRIPT_TEMPLATE = '''#!/bin/bash
# Swarm Lock Manager — auto-release locks on branch switch
# Installed by: python cli.py install-hook

PREV_HEAD="$1"
NEW_HEAD="$2"
BRANCH_FLAG="$3"

# Only run on branch checkout (flag=1), not file checkout (flag=0)
if [ "$BRANCH_FLAG" != "1" ]; then
    exit 0
fi

# Only run if switching to a different branch
if [ "$PREV_HEAD" = "$NEW_HEAD" ]; then
    exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
SWARM_AGENT_ID="${{AGENT_ID:-$(git config user.name)}}"
SWARM_AGENT_ID="${{SWARM_AGENT_ID:-agent-unknown}}"

# Find and release all locks held by this agent
for lock_file in "$REPO_ROOT"/current_tasks/claimed/*.json; do
    [ -f "$lock_file" ] || continue

    # Check if this agent owns the lock
    owner=$(python3 -c "import json; print(json.load(open('$lock_file'))['claimed_by'])" 2>/dev/null)
    task_id=$(python3 -c "import json; print(json.load(open('$lock_file'))['task_id'])" 2>/dev/null)

    if [ "$owner" = "$SWARM_AGENT_ID" ]; then
        echo "[swarm] Auto-releasing lock $task_id (branch switch)"
        AGENT_ID="$SWARM_AGENT_ID" python3 {cli_path} release "$task_id" "auto-released on branch switch" 2>/dev/null || true
    fi
done
'''


def install_post_checkout_hook(repo_dir: Path, cli_path: str) -> Path:
    """Install the post-checkout hook that auto-releases locks on branch switch.

    Returns the path to the installed hook.
    """
    hooks_dir = repo_dir / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "post-checkout"

    # Check for existing hook
    if hook_path.exists():
        existing = hook_path.read_text()
        if "Swarm Lock Manager" in existing:
            # Already installed, update it
            pass
        else:
            # Append to existing hook (remove shebang from ours)
            script = HOOK_SCRIPT_TEMPLATE.format(cli_path=cli_path)
            lines = script.split("\n")
            # Skip the shebang line
            append_content = "\n" + "\n".join(lines[1:])
            with hook_path.open("a") as f:
                f.write(append_content)
            return hook_path

    # Write fresh hook
    script = HOOK_SCRIPT_TEMPLATE.format(cli_path=cli_path)
    hook_path.write_text(script)

    # Make executable
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    return hook_path


def uninstall_post_checkout_hook(repo_dir: Path) -> bool:
    """Remove the swarm post-checkout hook. Returns True if it was removed."""
    hook_path = repo_dir / ".git" / "hooks" / "post-checkout"
    if not hook_path.exists():
        return False

    content = hook_path.read_text()
    if "Swarm Lock Manager" not in content:
        return False

    hook_path.unlink()
    return True

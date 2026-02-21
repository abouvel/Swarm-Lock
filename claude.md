Ah got it — PROGRESS.txt is your own development log for building this project, not a feature of the plugin itself. So when you're working on Swarm Lock Manager across multiple Claude Code sessions, each session appends to PROGRESS.txt so any new instance can pick up exactly where the last one left off without you having to re-explain context.
So the CLAUDE.md should tell Claude to read PROGRESS.txt at the start of every session and append to it as work happens.
Here's the updated CLAUDE.md:

Swarm Lock Manager
What This Project Is
Swarm Lock Manager is a Claude Code plugin that solves a coordination problem in multi-agent workflows. When multiple Claude Code agents run in parallel on the same codebase — whether through Agent Teams, Ralph-style loops, or manual parallel sessions — they have no built-in awareness of what each other is editing. Two agents will independently decide to modify the same file, write conflicting changes, or overwrite each other's progress. Claude Code's built-in Agent Teams handles task assignment but has no awareness of what is actually happening in the repository at the file and function level.
This plugin adds the missing coordination layer. Agents claim scopes (files, functions, or directories) before editing them, and those claims are backed by Git commits pushed to a remote repository. The remote acts as a distributed mutex — only one agent can win the push for a given scope, and losers roll back and reroute. This is the same pattern Terraform uses for remote state locking, applied to code editing.
Read This First Every Session
At the start of every session, read PROGRESS.txt in full before doing anything else. This is the development log for building this project. It tells you what has been built, what decisions were made, what is currently broken, and what to work on next. Do not assume anything about the state of the project without reading it first — previous sessions may have left things half-finished or changed direction.
After reading it, briefly summarize to the user what state the project is in and what the logical next step is.
Updating PROGRESS.txt
Append to PROGRESS.txt as you work. Never edit or delete existing lines. Write in plain conversational English, not bullet points or formal structure. Future sessions need to understand not just what was done but why decisions were made.
Append an entry when:

You start working on something
You finish something
You hit a problem or dead end and how you resolved it or why you stopped
You make a decision that isn't obvious from the code
You change direction from what a previous session planned
You leave something half-finished at the end of a session

Format each entry as:
[2026-02-20T14:23:00Z] <what you did or decided and why>
Example entries:
[2026-02-20T14:23:00Z] Started implementing claim.py. Decided to put all git operations in git.py first so claim.py stays clean.
[2026-02-20T14:45:00Z] Ran into issue with filelock on Windows paths — the .claim.lock file path needs to use pathlib not string concatenation. Fixed in locks.py.
[2026-02-20T15:10:00Z] Conflicts.py is done and tested. Soft conflict detection for directory prefix matching works but same-file different-function detection has an edge case when scope has no colon — left a TODO in the code.
[2026-02-20T15:30:00Z] Stopping here. cli.py entry point is stubbed but release.py is not implemented yet. Next session should start with release.py then wire up cli.py.
Critical Rules
Never write lock files manually. Always go through cli.py so the git commit, push, and log entry happen together. If a lock file exists on disk without a corresponding git commit it is corrupted — delete it.
Never change the order of operations in claim.py. The sequence is pull → conflict check → write → commit → push. Changing this breaks the distributed mutex guarantee.
Never call subprocess or os.system for git operations outside of swarm/git.py. All git calls go through that module.
Never auto-release stale locks. Always surface them to a human first.
Never edit or delete existing lines in SWARM_LOG.md. It is append-only.
Always set AGENT_ID before running. If it falls back to agent-unknown locks are not properly identified.
Running Commands
bashexport AGENT_ID=agent-1
python cli.py claim <task-id> <scope>
python cli.py release <task-id> "optional summary"
python cli.py status
python cli.py check-conflict <scope>
python cli.py oracle

```

## The Distributed Claim Flow

This is the critical section. Order must never change:
```

1. Acquire filelock on current_tasks/claimed/.claim.lock ← same-machine protection
2. git pull --rebase origin main ← get latest remote state
3. Run conflict check against current lock files
4. If conflict: abort, report, exit
5. Write lock file to disk
6. git add + git commit
7. git push origin main ← distributed gate
   → success: claim is live, release filelock
   → rejected: git reset HEAD~1, delete lock file, release filelock, report failure
   Step 7 is the true mutex. Everything before it is optimistic.
   Conflict Rules
   Defined in swarm/conflicts.py. Three outcomes:

Hard conflict: exact scope match → block entirely, do not claim
Soft conflict: incoming scope is inside a locked directory, locked directory is inside incoming scope, or same file with different functions → warn and prompt for confirmation
No conflict: completely disjoint paths → proceed

If you add a new conflict rule add a test in tests/test_conflicts.py first.
Scope Format
Three valid formats only. Do not invent others:

File: src/auth/session.py
File and function: src/auth/session.py:validate_token
Directory: src/auth/ (trailing slash required)

Agent Identity
Resolution order:

AGENT_ID environment variable — always set this
git config user.name
Fallback: agent-unknown

Lock File Schema
Defined as a Pydantic model in swarm/types.py. On disk:
json{
"task_id": "feature-123",
"scope": "src/auth/session.py:validate_token",
"claimed_by": "agent-1",
"claimed_at": "2026-02-20T14:23:00Z",
"last_updated": "2026-02-20T14:23:00Z",
"status": "active",
"notes": ""
}

```

## Git Commit Message Format

Log parsing depends on this format. Do not deviate:
```

swarm: claim <task-id> on <scope>
swarm: release <task-id> — <summary>
swarm: gc <task-id> — stale lock removed

```

## SWARM_LOG.md Format

Append-only. Written by `locks.append_log()` only:
```

[2026-02-20T14:23:00Z] CLAIMED | feature-123 | src/auth/session.py:validate_token | agent-1
[2026-02-20T14:45:00Z] RELEASED | feature-123 | testing complete | agent-1
[2026-02-20T15:10:00Z] CONFLICT | feature-456 | blocked by feature-123 | agent-2
Testing
Run with pytest. No test should touch the real filesystem or make real git calls — mock everything in swarm/git.py and swarm/locks.py.
For manual integration testing, each agent needs its own terminal:
bash# Terminal 1
export AGENT_ID=agent-1
cd /path/to/test-repo
claude-code --plugin-dir ./swarm-lock-manager

## PROGRESS.txt Rules

At the end of every phase update PROGRESS.txt with:

- Which phases are fully done with passing tests
- Which phase is next
- Exact file to start with
- Any known issues or gotchas discovered this session

Never leave a session without updating PROGRESS.txt.
A new instance should read this file and know exactly
what to do next without opening any source file first.

# Terminal 2

export AGENT_ID=agent-2
cd /path/to/test-repo
claude-code --plugin-dir ./swarm-lock-manager

```

To reliably trigger the race condition, add a temporary `time.sleep(5)` in `claim.py` between the commit and push. Start a claim in both terminals within the window. One should succeed, one should roll back cleanly. Remove the sleep after testing.

## Stale Lock Threshold

30 minutes without a `last_updated` change. Defined as a constant in `swarm/status.py`. Flagged in status output, never auto-released.

## Project Structure
```

swarm-lock-manager/
├── .claude-plugin/
│ └── plugin.json
├── skills/
│ ├── claim.md
│ ├── check-conflict.md
│ ├── status.md
│ ├── release.md
│ └── oracle-quick.md
├── swarm/
│ ├── **init**.py
│ ├── claim.py
│ ├── release.py
│ ├── conflicts.py
│ ├── status.py
│ ├── oracle.py
│ ├── git.py
│ ├── locks.py
│ └── types.py
├── tests/
│ ├── test_conflicts.py
│ ├── test_claim.py
│ ├── test_release.py
│ └── test_status.py
├── cli.py
├── current_tasks/
│ └── claimed/
│ └── .gitkeep
├── SWARM_LOG.md
├── PROGRESS.txt
├── CLAUDE.md
├── requirements.txt
└── pyproject.toml
Module Responsibilities

types.py: Pydantic models only, no logic
locks.py: read, write, delete lock files, append to log, no git calls
git.py: all git operations, nothing else
conflicts.py: conflict detection logic only
claim.py: orchestrates the full distributed claim flow
release.py: orchestrates release and rollback
status.py: reads lock files and progress files, formats output
oracle.py: runs lint and tests, summarizes results for Claude
cli.py: thin entry point, no business logic

Known Limitations

Push-based locking cannot guarantee atomicity across high-latency remotes. Both agents can pass the conflict check before either push lands. The push rejection still catches it but wastes a commit-and-rollback cycle.
A crashed agent that fails between commit and push may leave a local commit without a corresponding remote push. On next pull this resolves itself but can cause confusion in the log.
No priority or queue system. An agent that loses the race must decide independently whether to retry or reroute.
Session resumption issues in Claude Code Agent Teams (experimental as of early 2026) can leave orphaned locks if an agent crashes mid-claim. Surface these via /swarm-status and release manually.

Tech Stack

Python 3.11+
pydantic for schema validation
filelock for same-machine race protection
typer for CLI
rich for status output
pytest for tests
Git over SSH or HTTPS as the distributed coordination layer
No database

## Git SSH Key

The GitHub SSH key on this machine has NO passphrase. Git push/pull over SSH will not prompt for a password. Do not add any passphrase handling, SSH agent logic, or credential helper workarounds — they are unnecessary and will only cause problems.

## Git Workflow

### Branches

Create a new branch for every discrete task or feature. Never work directly on main. Name branches after the task:

```bash
git checkout -b feature/<task-id>
```

### Commits

Commit after every meaningful unit of work — not after every file change, but not in one giant commit at the end either. A good rule of thumb is: if you'd want to be able to roll back to this point, commit it. Always follow the commit message format:

```
swarm: claim <task-id> on <scope>
swarm: release <task-id> — <summary>
feat: <what you built>
fix: <what you fixed>
chore: <cleanup, config, deps>
```

### Pull Requests

Open a PR when a task is complete and all tests pass. Never merge your own PR — leave it for review. PR title should match the branch name. In the PR description write:

- What changed and why
- How to test it
- Any known limitations or follow-on work

### Never

- Commit directly to main
- Push broken or untested code
- Merge without a passing test suite
- Leave a branch sitting open more than a day without a commit or PR

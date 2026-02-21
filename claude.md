Swarm Lock Manager
Read This First
Read PROGRESS.txt before doing anything else. Tell the user the current state in one sentence then start working. Do not ask for confirmation unless something is genuinely unclear.
Token Efficiency
Only open files you are about to change. Do not summarize files back to the user. Do not explain what you are about to do — just do it. When a task is done, stop.
PROGRESS.txt
Append after every meaningful action — starting something, finishing something, hitting a problem, stopping mid-session. Never edit existing lines. End every session with an entry that tells the next session exactly what file to open and what to do first.
Format: [ISO timestamp] what you did and why
Critical Rules

Never write lock files manually — always go through cli.py
Never change the order in claim.py: pull → conflict check → write → commit → push
Never call subprocess for git outside of swarm/git.py
Never auto-release stale locks
Never append to SWARM_LOG.md directly — use locks.append_log()
Never commit to main directly
Never push broken or untested code
No co-authored-by in commit messages

Claim Flow

1. filelock on current_tasks/claimed/.claim.lock
2. git pull --rebase origin main
3. conflict check
4. if conflict: abort
5. write lock file
6. git add + commit
7. git push
   → rejected: reset HEAD~1, delete lock file, report failure
   Conflict Rules

Hard: exact scope match → block
Soft: one scope contains the other, or same file different functions → warn and confirm
None: disjoint paths → proceed

New rule requires a test first.
Scope Format

File: src/auth/session.py
File and function: src/auth/session.py:validate_token
Directory: src/auth/

Commit Messages
swarm: claim <task-id> on <scope>
swarm: release <task-id> — <summary>
feat: <what you built>
fix: <what you fixed>
chore: <cleanup, config, deps>
Agent Identity
AGENT_ID env var → git config user.name → agent-unknown. Always set AGENT_ID.
SSH
No passphrase on the GitHub key. Do not add any credential handling.
Module Responsibilities

types.py — Pydantic models only
locks.py — file I/O only, no git
git.py — git only, nothing else
conflicts.py — detection logic only
claim.py — full claim flow
release.py — full release flow
status.py — read and format state
oracle.py — lint and test runner
cli.py — entry point only, no logic

Tech Stack
Python 3.11, pydantic, filelock, typer, rich, pytest. Git over SSH. No database.

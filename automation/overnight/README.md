# ABD Overnight System — Setup & Usage

## Architecture

A coordinator/executor architecture with ROADMAP-driven task selection:

```
┌────────────────────────────────────────────────────────┐
│              abd_overnight.py (Coordinator)             │
│                                                         │
│  for each cycle:                                        │
│    ┌─────────────────────────────────────────────┐      │
│    │ PHASE 1: Bug Fixes (from BUGS.md)           │      │
│    │   for each bug (priority order):            │      │
│    │     ① git checkpoint                        │      │
│    │     ② claude -p "fix BUG-XXX" (executor)    │      │
│    │     ③ run tests                             │      │
│    │     ④ regression? → rollback to checkpoint  │      │
│    │     ⑤ ok? → keep commit, update state       │      │
│    └─────────────────────────────────────────────┘      │
│    ┌─────────────────────────────────────────────┐      │
│    │ PHASE 2: ROADMAP Tasks + Improvements       │      │
│    │   ① Read ROADMAP.md → pick next TODO task   │      │
│    │   ② If no ROADMAP task → freestyle analysis │      │
│    │   ③ For each task:                          │      │
│    │       same checkpoint/execute/verify/rollback│      │
│    │   ④ Update ROADMAP.md status on success     │      │
│    └─────────────────────────────────────────────┘      │
│                                                         │
│  Safety invariants:                                     │
│    • Tests NEVER regress (auto-rollback)                │
│    • Failed tasks remembered (no retry loops)           │
│    • Circuit breaker after 5 consecutive failures       │
│    • Graceful Ctrl+C shutdown (saves state)             │
│    • State persisted to disk after every task            │
│    • Every change is one atomic, revertable commit      │
└────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **Claude Code CLI** (Node.js 18+ required):
   ```
   npm install -g @anthropic-ai/claude-code
   claude --version
   ```

2. **Authentication** — choose one:
   - **Claude Max subscription** (recommended): `claude login`
   - **API billing**: `set ANTHROPIC_API_KEY=sk-ant-...`

3. **Python 3.11+**

4. **Skip-permissions confirmation** (one-time):
   ```
   claude --dangerously-skip-permissions
   ```

## Running on Windows

```powershell
cd C:\path\to\abd_post_stage0_v1.5

# Conservative first run: bugs only, 2 cycles
python automation\overnight\abd_overnight.py --max-cycles 2 --bugs-only

# Standard run: 5 cycles (bugs + ROADMAP tasks)
python automation\overnight\abd_overnight.py --max-cycles 5

# Dry run (no Claude calls, simulates the flow):
python automation\overnight\abd_overnight.py --dry-run

# Resume after interruption:
python automation\overnight\abd_overnight.py --resume
```

## Morning Review

1. Read `OVERNIGHT_REPORT.md`
2. Check commits: `git log --oneline master..claude/overnight-*`
3. Review individually: `git show <hash>`
4. Merge: `git checkout master && git merge claude/overnight-*`
5. Or cherry-pick: `git cherry-pick <good-commit>`

## Safety Guarantees

| Failure mode | Protection |
|---|---|
| Bad commit breaks tests | Auto-rollback to pre-task checkpoint |
| Claude retries same broken fix | Failure memory: skipped after 2 failures |
| All tasks fail | Circuit breaker halts after 5 consecutive failures |
| Script crashes | State persisted to disk; --resume picks up |
| Rate limit hit (Max) | 120-second cooldown between tasks |
| Ctrl+C during task | Graceful shutdown: saves state, generates report |
| Zombie processes (Windows) | taskkill on timeout |

## Configuration

Edit constants at top of `abd_overnight.py`:

```python
MAX_TURNS_PER_TASK = 60           # Claude Code turns per task
TASK_TIMEOUT_SECONDS = 900        # 15 min per task
COOLDOWN_SECONDS = 120            # 2 min between tasks (Max rate limit)
MAX_FAILURES_PER_BUG = 2          # Skip after N failures
CIRCUIT_BREAKER_THRESHOLD = 5     # Stop after N consecutive failures
```

# ABD Overnight System — Setup & Usage

## Architecture

This is **not** a naive loop. It's a coordinator/executor architecture:

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
│    │ PHASE 2: Intelligent Improvements           │      │
│    │   ① claude -p "analyze codebase" (read-only)│      │
│    │   ② parse improvement plan (JSON)           │      │
│    │   ③ for each improvement:                   │      │
│    │       same checkpoint/execute/verify/rollback│      │
│    └─────────────────────────────────────────────┘      │
│                                                         │
│  Safety invariants:                                     │
│    • Tests NEVER regress (auto-rollback)                │
│    • Failed bugs remembered (no retry loops)            │
│    • Circuit breaker after 4 consecutive failures       │
│    • State persisted to disk after every task            │
│    • Every change is one atomic, revertable commit      │
└────────────────────────────────────────────────────────┘
```

## Prerequisites

1. **Claude Code CLI** (Node.js 18+ required):
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude --version  # verify
   ```

2. **API key with usage-based billing**:
   - Go to https://console.anthropic.com → API Keys → Create
   - Make sure you have billing set up (usage-based, not Max subscription)
   - Max subscription has rate limits that will stall the loop within ~1 hour
   - API billing just charges per token — no stalls

3. **Python 3.11+** (you already have this for ABD)

4. **Skip-permissions confirmation** (one-time):
   ```bash
   # Run once interactively to accept the warning dialog:
   claude --dangerously-skip-permissions
   # Accept the warning, then Ctrl+C to exit
   ```

## Setup

```bash
# 1. Clone fresh (recommended) or use existing clone
git clone https://github.com/rayanino/abd_post_stage0_v1.5.git abd-overnight
cd abd-overnight

# 2. Place the script in the repo root
cp /path/to/abd_overnight.py .

# 3. Set your API key
export ANTHROPIC_API_KEY="sk-ant-api03-..."

# 4. Verify everything works
python3 -m pytest tests/ -q          # Tests should pass
claude --version                      # CLI should respond
python3 abd_overnight.py --dry-run    # Simulates without calling Claude
```

## Running Overnight

```bash
# Standard run: 5 cycles of bug-fixing + improvements (~$10-20)
python3 abd_overnight.py --max-cycles 5

# Budget-conscious: bugs only, 3 cycles (~$5-10)
python3 abd_overnight.py --max-cycles 3 --bugs-only

# Aggressive: 10 cycles (~$20-40)
python3 abd_overnight.py --max-cycles 10

# Dry run (no Claude calls, simulates the flow):
python3 abd_overnight.py --dry-run

# Resume after interruption (reads .overnight_state.json):
python3 abd_overnight.py --resume
```

### Running in background (SSH-safe):

```bash
# Option A: tmux (recommended)
tmux new -s overnight
python3 abd_overnight.py --max-cycles 5
# Ctrl+B, D to detach — reconnect later with: tmux attach -t overnight

# Option B: nohup
nohup python3 abd_overnight.py --max-cycles 5 > /dev/null 2>&1 &
# Check progress: tail -f overnight-*.log

# Option C: screen
screen -S overnight
python3 abd_overnight.py --max-cycles 5
# Ctrl+A, D to detach — reconnect: screen -r overnight
```

## What You Wake Up To

1. **`OVERNIGHT_REPORT.md`** — Full summary: what was fixed, what failed, test diff, commits list
2. **`overnight-YYYYMMDD-HHMM.log`** — Detailed execution log
3. **`.overnight_state.json`** — Machine-readable state (for --resume)
4. **Git branch `claude/overnight-*`** — All changes, reviewable:
   ```bash
   git log --oneline master..claude/overnight-*
   git diff master..claude/overnight-* --stat
   ```

## Review and Merge

```bash
# Read the report first
cat OVERNIGHT_REPORT.md

# Review each commit individually
git log --oneline master..claude/overnight-*
git show <commit-hash>    # Inspect individual changes

# If everything looks good:
git checkout master
git merge claude/overnight-*

# If some commits are bad, cherry-pick the good ones:
git checkout master
git cherry-pick <good-commit-1> <good-commit-2> ...

# If it's all bad:
git branch -D claude/overnight-*
```

## Safety Guarantees

| Failure mode | Protection |
|---|---|
| Bad commit breaks tests | Auto-rollback to pre-task checkpoint |
| Claude retries same broken fix | Failure memory: previous errors passed to next attempt, then skipped after 2 failures |
| Claude goes off the rails | Each prompt is scoped to ONE specific task with explicit rules |
| Runaway costs | Per-task budget cap ($1.50) + total budget via API dashboard |
| All tasks fail | Circuit breaker halts after 4 consecutive failures |
| Script crashes | State persisted to disk; --resume picks up where it left off |
| Claude deletes important files | --disallowedTools blocks rm -rf, sudo, chmod 777 |
| Test suite hangs | 120-second timeout on pytest |
| Claude Code hangs | 600-second timeout per task |
| Rate limit hit | Claude Code handles this internally with retries |

## Tuning

**Edit constants in `abd_overnight.py`:**

```python
MAX_TURNS_PER_TASK = 40          # More turns = deeper fixes, more cost
BUDGET_PER_TASK_USD = 1.50       # Cap per individual task
TASK_TIMEOUT_SECONDS = 600       # 10 min per task
MAX_FAILURES_PER_BUG = 2         # Skip after N failures
CIRCUIT_BREAKER_THRESHOLD = 4    # Stop after N consecutive failures
```

**Estimated costs (API billing, Sonnet):**
- Simple doc fix: ~$0.10-0.30
- Code bug fix: ~$0.30-1.00
- Analysis phase: ~$0.20-0.50
- 5 cycles: ~$5-20 total
- 10 cycles: ~$15-40 total

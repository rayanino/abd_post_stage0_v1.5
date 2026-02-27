#!/usr/bin/env bash
# ============================================================================
# ABD Overnight Autonomous Loop
# ============================================================================
# Runs Claude Code in a continuous loop: fix → test → commit → repeat.
# Each iteration gets a fresh context window (no drift).
# PROGRESS.md acts as persistent memory between iterations.
#
# Usage:
#   ./scripts/overnight.sh                    # defaults: 50 iterations, opus model
#   ./scripts/overnight.sh --max 100          # 100 iterations
#   ./scripts/overnight.sh --model sonnet     # use sonnet (cheaper)
#   ./scripts/overnight.sh --dry-run          # print what would run, don't execute
#
# Prerequisites:
#   1. Claude Code CLI installed: npm install -g @anthropic-ai/claude-code
#   2. Logged in: claude login
#   3. Run from repo root: cd /path/to/abd_post_stage0_v1.5
#
# Safety:
#   - Works on a dedicated branch (overnight/auto-fixes)
#   - Tests must pass after each iteration or changes are rolled back
#   - All work is committed with descriptive messages
#   - You review and cherry-pick/merge what you want afterward
# ============================================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
MAX_ITERATIONS=50
MODEL="opus"
DRY_RUN=false
BRANCH="overnight/auto-fixes"
SLEEP_BETWEEN=15          # seconds between iterations (rate limit buffer)
LOG_DIR="scripts/logs"
PROMPT_FILE="scripts/OVERNIGHT_PROMPT.md"
PROGRESS_FILE="PROGRESS.md"

# ── Parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --max)       MAX_ITERATIONS="$2"; shift 2 ;;
        --model)     MODEL="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true; shift ;;
        --branch)    BRANCH="$2"; shift 2 ;;
        --sleep)     SLEEP_BETWEEN="$2"; shift 2 ;;
        *)           echo "Unknown flag: $1"; exit 1 ;;
    esac
done

# ── Preflight checks ─────────────────────────────────────────────────────────
echo "═══════════════════════════════════════════════════════════"
echo " ABD Overnight Autonomous Loop"
echo "═══════════════════════════════════════════════════════════"
echo " Max iterations:  $MAX_ITERATIONS"
echo " Model:           $MODEL"
echo " Branch:          $BRANCH"
echo " Sleep between:   ${SLEEP_BETWEEN}s"
echo " Dry run:         $DRY_RUN"
echo "═══════════════════════════════════════════════════════════"

# Check Claude Code is installed
if ! command -v claude &>/dev/null; then
    echo "ERROR: 'claude' CLI not found. Install: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# Check we're in the repo root
if [[ ! -f "CLAUDE.md" ]] || [[ ! -f "BUGS.md" ]]; then
    echo "ERROR: Run this from the ABD repo root (where CLAUDE.md lives)."
    exit 1
fi

# Check prompt file exists
if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "ERROR: $PROMPT_FILE not found. Did you set up the scripts/ directory?"
    exit 1
fi

# Check git is clean (no uncommitted changes)
if [[ -n "$(git status --porcelain)" ]]; then
    echo "ERROR: Working directory has uncommitted changes. Commit or stash first."
    exit 1
fi

if $DRY_RUN; then
    echo ""
    echo "[DRY RUN] Would execute $MAX_ITERATIONS iterations with:"
    echo "  claude -p <prompt> --model $MODEL --dangerously-skip-permissions"
    echo ""
    echo "Prompt contents:"
    cat "$PROMPT_FILE"
    exit 0
fi

# ── Setup branch ──────────────────────────────────────────────────────────────
ORIGINAL_BRANCH=$(git branch --show-current)
echo ""
echo "Current branch: $ORIGINAL_BRANCH"
echo "Creating work branch: $BRANCH"

# Create or switch to work branch
if git show-ref --verify --quiet "refs/heads/$BRANCH" 2>/dev/null; then
    git checkout "$BRANCH"
    git merge "$ORIGINAL_BRANCH" --no-edit 2>/dev/null || true
else
    git checkout -b "$BRANCH"
fi

# ── Initialize progress file ─────────────────────────────────────────────────
if [[ ! -f "$PROGRESS_FILE" ]]; then
    cat > "$PROGRESS_FILE" << 'EOF'
# Overnight Progress Log

> This file is updated by Claude Code after each iteration.
> It serves as persistent memory between iterations (each gets a fresh context).

## Status
- Iterations completed: 0
- Last updated: (not yet started)

## Completed This Session
(none yet)

## Next Priority
See BUGS.md for the prioritized task list. Start with Tier 1.

## Notes / Blockers
(none yet)
EOF
    git add "$PROGRESS_FILE"
    git commit -m "overnight: initialize progress tracker"
fi

# ── Create log directory ──────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

# ── Run baseline tests ────────────────────────────────────────────────────────
echo ""
echo "Running baseline tests..."
if ! python -m pytest tests/ -q 2>&1 | tee "$LOG_DIR/baseline_tests.log"; then
    echo "ERROR: Baseline tests fail. Fix them before running overnight."
    git checkout "$ORIGINAL_BRANCH"
    exit 1
fi
BASELINE_PASS_COUNT=$(grep -oP '\d+ passed' "$LOG_DIR/baseline_tests.log" | grep -oP '\d+')
echo "Baseline: $BASELINE_PASS_COUNT tests pass."

# ── Main loop ─────────────────────────────────────────────────────────────────
echo ""
echo "Starting autonomous loop at $(date)"
echo "═══════════════════════════════════════════════════════════"

ITERATION=1
SUCCESSES=0
FAILURES=0
ROLLBACKS=0
START_TIME=$(date +%s)

while [[ $ITERATION -le $MAX_ITERATIONS ]]; do
    ITER_START=$(date +%s)
    ITER_LOG="$LOG_DIR/iteration_$(printf '%03d' $ITERATION).log"

    echo ""
    echo "── Iteration $ITERATION/$MAX_ITERATIONS  ($(date '+%H:%M:%S')) ─────────"

    # Build the prompt: combine the static prompt file + current progress
    PROMPT=$(cat "$PROMPT_FILE")
    PROMPT="$PROMPT

---

## Current PROGRESS.md contents:
$(cat "$PROGRESS_FILE")

---

## Current BUGS.md summary (first 80 lines):
$(head -80 BUGS.md)
"

    # Snapshot current HEAD for rollback
    SNAPSHOT=$(git rev-parse HEAD)

    # Run Claude Code (non-interactive, skip permissions)
    echo "  Running Claude Code ($MODEL)..."
    if claude -p "$PROMPT" \
        --model "$MODEL" \
        --dangerously-skip-permissions \
        --output-format text \
        > "$ITER_LOG" 2>&1; then
        echo "  Claude Code finished."
    else
        echo "  WARNING: Claude Code exited with non-zero status."
    fi

    # Check if any files changed
    if [[ -z "$(git status --porcelain)" ]]; then
        echo "  No changes made. Skipping."
        ((ITERATION++))
        sleep "$SLEEP_BETWEEN"
        continue
    fi

    # Run tests
    echo "  Running tests..."
    TEST_LOG="$LOG_DIR/tests_$(printf '%03d' $ITERATION).log"
    if python -m pytest tests/ -q > "$TEST_LOG" 2>&1; then
        CURRENT_PASS=$(grep -oP '\d+ passed' "$TEST_LOG" | grep -oP '\d+' || echo "0")
        echo "  Tests PASS ($CURRENT_PASS passed)."

        # Commit the changes
        git add -A
        git commit -m "overnight(iter-$ITERATION): auto-fix [$(date '+%Y-%m-%d %H:%M')]

Model: $MODEL
Tests: $CURRENT_PASS passed (baseline: $BASELINE_PASS_COUNT)
See $ITER_LOG for Claude Code output." \
            --no-verify 2>/dev/null || true

        ((SUCCESSES++))
        echo "  ✅ Committed."
    else
        echo "  Tests FAIL. Rolling back..."
        git checkout -- .
        git clean -fd 2>/dev/null || true
        ((ROLLBACKS++))
        echo "  ↩️  Rolled back to $SNAPSHOT"
    fi

    # Timing
    ITER_END=$(date +%s)
    ITER_DURATION=$((ITER_END - ITER_START))
    echo "  Duration: ${ITER_DURATION}s"

    ((ITERATION++))

    # Sleep between iterations (rate limit protection)
    if [[ $ITERATION -le $MAX_ITERATIONS ]]; then
        echo "  Sleeping ${SLEEP_BETWEEN}s..."
        sleep "$SLEEP_BETWEEN"
    fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
END_TIME=$(date +%s)
TOTAL_DURATION=$(( (END_TIME - START_TIME) / 60 ))

echo ""
echo "═══════════════════════════════════════════════════════════"
echo " Overnight Loop Complete"
echo "═══════════════════════════════════════════════════════════"
echo " Total iterations:  $((ITERATION - 1))"
echo " Successful commits: $SUCCESSES"
echo " Rollbacks (test fail): $ROLLBACKS"
echo " No-ops (no changes): $(( ITERATION - 1 - SUCCESSES - ROLLBACKS ))"
echo " Total time:        ${TOTAL_DURATION} minutes"
echo " Branch:            $BRANCH"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "To review what was done:"
echo "  git log --oneline $ORIGINAL_BRANCH..$BRANCH"
echo ""
echo "To merge into $ORIGINAL_BRANCH:"
echo "  git checkout $ORIGINAL_BRANCH"
echo "  git merge $BRANCH"
echo ""
echo "To cherry-pick specific fixes:"
echo "  git cherry-pick <commit-hash>"
echo ""
echo "Logs are in: $LOG_DIR/"

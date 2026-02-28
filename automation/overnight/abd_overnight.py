#!/usr/bin/env python3
"""
ABD Overnight Autonomous Improvement System
============================================

A fault-tolerant coordinator that drives Claude Code through cycles of
ANALYZE → EXECUTE → VERIFY → REFLECT, with automatic rollback, failure
memory, and regression prevention.

Safety guarantees:
  - The repo is NEVER left in a broken state (automatic git rollback)
  - Failed fixes are remembered and skipped (state file persists)
  - Tests must pass AND no regressions (previously-passing tests can't break)
  - Circuit breaker stops the loop after consecutive failures
  - Each change is atomic: one commit per fix, revertable independently

Usage:
  export ANTHROPIC_API_KEY="sk-ant-..."
  python3 abd_overnight.py [--max-cycles 10] [--budget 20.0] [--dry-run]

Requirements:
  - Python 3.11+
  - Claude Code CLI: npm install -g @anthropic-ai/claude-code
  - ANTHROPIC_API_KEY environment variable
  - Git repository with clean working tree
"""

import json
import subprocess
import os
import sys
import re
import time
import signal
import argparse
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Graceful shutdown
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SHUTDOWN_REQUESTED = False


def _handle_shutdown(signum, frame):
    """Handle Ctrl+C gracefully — finish current task, save state, exit."""
    global _SHUTDOWN_REQUESTED
    if _SHUTDOWN_REQUESTED:
        # Second Ctrl+C = force exit
        print("\n[FORCED EXIT] Exiting immediately.", flush=True)
        sys.exit(1)
    _SHUTDOWN_REQUESTED = True
    print("\n[SHUTDOWN] Ctrl+C received. Will finish current task and exit cleanly.", flush=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CLAUDE_CMD = "claude"
MAX_TURNS_PER_TASK = 60           # Claude Code turns per task (deeper work)
BUDGET_PER_TASK_USD = 5.00        # Per-task budget cap (stage-building needs more)
TASK_TIMEOUT_SECONDS = 900        # 15 min timeout per task
MAX_FAILURES_PER_BUG = 2          # Skip bug after N failures
CIRCUIT_BREAKER_THRESHOLD = 5     # Stop after N consecutive failures (was 4)
COOLDOWN_SECONDS = 120            # 2 min pause between tasks (Max rate limit buffer)
STATE_FILE = ".overnight_state.json"
REPORT_FILE = "OVERNIGHT_REPORT.md"
ROADMAP_FILE = "ROADMAP.md"       # Strategic task list (Phase 2 reads this)

# Tools Claude Code is NOT allowed to use
DISALLOWED_TOOLS = [
    "Bash(rm -rf:*)",
    "Bash(sudo:*)",
    "Bash(chmod 777:*)",
    "Bash(rm -r automation:*)",
    "Bash(rm -r scripts:*)",
    "Bash(rm -r taxonomy:*)",
    "Bash(rm -r gold_baselines:*)",
    "Bash(rm -r schemas:*)",
    "Bash(rm BUGS.md:*)",
    "Bash(rm CLAUDE.md:*)",
    "Bash(rm ROADMAP.md:*)",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data structures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class TestResult:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    raw_output: str = ""

    @property
    def total_collected(self):
        return self.passed + self.failed + self.skipped + self.errors

    @property
    def ok(self):
        return self.failed == 0 and self.errors == 0


@dataclass
class BugEntry:
    bug_id: str
    severity: str          # "CRITICAL", "MODERATE", "LOW"
    status: str            # "OPEN", "FIXED", "NEW"
    title: str
    full_text: str         # Full markdown text of the bug entry
    priority_rank: int = 0 # Lower = higher priority


@dataclass
class TaskResult:
    task_id: str
    task_type: str         # "bug_fix", "improvement", "doc_fix"
    description: str
    status: str            # "success", "failed", "skipped", "rollback"
    commit_hash: Optional[str] = None
    error_reason: Optional[str] = None
    tests_before: Optional[dict] = None
    tests_after: Optional[dict] = None
    duration_seconds: float = 0.0


@dataclass
class OvernightState:
    started_at: str = ""
    branch_name: str = ""
    baseline_tests: dict = field(default_factory=dict)
    current_best_tests: dict = field(default_factory=dict)
    bug_attempts: dict = field(default_factory=dict)   # bug_id → {attempts, status, commits, errors}
    improvements_done: list = field(default_factory=list)
    task_history: list = field(default_factory=list)
    consecutive_failures: int = 0
    total_cycles: int = 0
    total_commits: int = 0
    halted: bool = False
    halt_reason: str = ""

    def save(self, path: str = STATE_FILE):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str = STATE_FILE) -> "OvernightState":
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            state = cls()
            for k, v in data.items():
                if hasattr(state, k):
                    setattr(state, k, v)
            return state
        return cls()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Utility: logging
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LOG_FILE = None

def log(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line, flush=True)
    if LOG_FILE:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def log_separator(title: str = ""):
    line = f"━━━ {title} " + "━" * max(0, 60 - len(title))
    log(line)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Git operations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def git(*args, check=True) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, encoding="utf-8",
        timeout=30
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def git_current_branch() -> str:
    return git("branch", "--show-current")


def git_head_hash() -> str:
    return git("rev-parse", "--short", "HEAD")


def git_checkpoint(message: str) -> str:
    """Stage everything and commit if there are changes. Returns commit hash."""
    git("add", "-A")
    # Check if there's anything to commit
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True, timeout=10
    )
    if result.returncode != 0:  # There are staged changes
        git("commit", "-m", message)
    return git_head_hash()


def git_rollback_to(commit_hash: str):
    """Hard reset to a specific commit, discarding all changes after it."""
    git("reset", "--hard", commit_hash)
    git("clean", "-fd")
    log(f"Rolled back to {commit_hash}", "WARN")


def git_has_uncommitted_changes() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, timeout=10
    )
    return bool(result.stdout.strip())


def git_log_since(base_commit: str) -> str:
    return git("log", "--oneline", f"{base_commit}..HEAD", check=False)


def git_diff_stat_since(base_commit: str) -> str:
    return git("diff", "--stat", f"{base_commit}..HEAD", check=False)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Critical file protection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Files that must NEVER be deleted by overnight automation.
# These are the exact files Codex kept deleting across branches.
PROTECTED_FILES = [
    "BUGS.md",
    "CLAUDE.md",
    ".gitignore",
    "automation/overnight/abd_overnight.py",
    "automation/overnight/README.md",
    "scripts/OVERNIGHT_PROMPT.md",
    "scripts/overnight.sh",
    "taxonomy/balagha/balagha_v1_0.yaml",
    "taxonomy/imlaa/imlaa_v1_0.yaml",
    "taxonomy/nahw/nahw_v1_0.yaml",
    "taxonomy/sarf/sarf_v1_0.yaml",
]


def _check_critical_file_deletions() -> list[str]:
    """Check if any protected files were deleted (staged or unstaged).

    Returns list of deleted file paths, empty if all OK.
    """
    deleted = []
    try:
        # Check both staged and unstaged deletions
        status_output = git("status", "--porcelain", check=False)
        for line in status_output.splitlines():
            if not line.strip():
                continue
            # Porcelain format: XY filename (D = deleted)
            status_code = line[:2]
            filepath = line[3:].strip()
            if "D" in status_code:
                if filepath in PROTECTED_FILES:
                    deleted.append(filepath)

        # Also check committed deletions (in case Claude already committed)
        diff_output = git("diff", "--name-status", "HEAD~1..HEAD", check=False)
        for line in diff_output.splitlines():
            if line.startswith("D\t"):
                filepath = line[2:].strip()
                if filepath in PROTECTED_FILES:
                    deleted.append(filepath)
    except Exception:
        pass  # If we can't check, don't block

    return list(set(deleted))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Test runner
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_tests() -> TestResult:
    """Run pytest and parse the summary line."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
            capture_output=True, text=True, encoding="utf-8",
            timeout=120
        )
        output = result.stdout + result.stderr
        tr = TestResult(raw_output=output)

        # Parse pytest summary: "469 passed, 7 skipped in 11.99s"
        # or "3 failed, 466 passed, 7 skipped in 12.5s"
        for line in output.splitlines():
            m_passed = re.search(r"(\d+) passed", line)
            m_failed = re.search(r"(\d+) failed", line)
            m_skipped = re.search(r"(\d+) skipped", line)
            m_errors = re.search(r"(\d+) error", line)
            if m_passed:
                tr.passed = int(m_passed.group(1))
            if m_failed:
                tr.failed = int(m_failed.group(1))
            if m_skipped:
                tr.skipped = int(m_skipped.group(1))
            if m_errors:
                tr.errors = int(m_errors.group(1))

        return tr
    except subprocess.TimeoutExpired:
        return TestResult(raw_output="TIMEOUT: tests took >120s")
    except Exception as e:
        return TestResult(raw_output=f"ERROR running tests: {e}")


def tests_are_acceptable(before: TestResult, after: TestResult) -> tuple[bool, str]:
    """
    Check that tests didn't regress.
    Rules:
      1. No new failures (after.failed must be <= before.failed)
      2. Pass count must not decrease
      3. No new errors
    Returns (acceptable, reason).
    """
    if after.failed > before.failed:
        return False, f"New test failures: {before.failed}→{after.failed}"
    if after.errors > before.errors:
        return False, f"New test errors: {before.errors}→{after.errors}"
    if after.passed < before.passed:
        return False, f"Fewer tests passing: {before.passed}→{after.passed}"
    return True, "OK"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BUGS.md parser
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_bugs_md(filepath: str = "BUGS.md") -> list[BugEntry]:
    """Extract bug entries from BUGS.md."""
    if not os.path.exists(filepath):
        log(f"{filepath} not found", "WARN")
        return []

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    bugs = []
    # Split by ### BUG-NNN headers
    sections = re.split(r"(?=^### BUG-\d+)", content, flags=re.MULTILINE)

    severity_order = {"CRITICAL": 0, "MODERATE": 1, "LOW": 2}

    for section in sections:
        # Match: ### BUG-001 🔴 OPEN — Title
        # Accept any status word (OPEN, FIXED, NEW, DONE, etc.)
        m = re.match(
            r"### (BUG-\d+)\s+(🔴|🟡|🟢)\s+(\w+)\s+—\s+(.+)",
            section.strip()
        )
        if not m:
            continue

        bug_id = m.group(1)
        emoji = m.group(2)
        status = m.group(3)
        title = m.group(4).strip()

        severity_map = {"🔴": "CRITICAL", "🟡": "MODERATE", "🟢": "LOW"}
        severity = severity_map.get(emoji, "LOW")

        bugs.append(BugEntry(
            bug_id=bug_id,
            severity=severity,
            status=status,
            title=title,
            full_text=section.strip(),
            priority_rank=severity_order.get(severity, 99)
        ))

    # Sort by priority (CRITICAL first, then MODERATE, then LOW)
    bugs.sort(key=lambda b: b.priority_rank)
    return bugs


def get_actionable_bugs(bugs: list[BugEntry], state: OvernightState) -> list[BugEntry]:
    """Filter to bugs that are OPEN/NEW and haven't been skipped."""
    actionable = []
    for bug in bugs:
        if bug.status.upper() in ("FIXED", "DONE", "RESOLVED"):
            continue
        attempts = state.bug_attempts.get(bug.bug_id, {})
        if attempts.get("status") in ("fixed", "skipped"):
            continue
        if attempts.get("attempts", 0) >= MAX_FAILURES_PER_BUG:
            continue
        actionable.append(bug)
    return actionable


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Claude Code runner
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_claude(prompt: str, dry_run: bool = False) -> tuple[bool, str]:
    """
    Run Claude Code in headless mode with the given prompt.
    Returns (success, output_text).

    On Windows, uses CREATE_NEW_PROCESS_GROUP + taskkill to prevent
    zombie Claude Code processes on timeout.
    """
    if dry_run:
        log("[DRY RUN] Would send prompt to Claude Code", "DEBUG")
        return True, "[DRY RUN] No changes made"

    cmd = [
        CLAUDE_CMD,
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--max-turns", str(MAX_TURNS_PER_TASK),
        "--output-format", "text",
    ]

    # Add disallowed tools
    for tool in DISALLOWED_TOOLS:
        cmd.extend(["--disallowedTools", tool])

    try:
        # On Windows, create a new process group so we can kill the whole tree
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, encoding="utf-8",
            timeout=TASK_TIMEOUT_SECONDS,
            env={**os.environ},
            **kwargs,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        return success, output

    except subprocess.TimeoutExpired:
        log(f"Claude Code timed out after {TASK_TIMEOUT_SECONDS}s", "WARN")
        # On Windows, kill the entire process tree to prevent zombies
        if sys.platform == "win32":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/IM", "claude.exe"],
                               capture_output=True, timeout=10)
            except Exception:
                pass
        return False, "TIMEOUT"

    except FileNotFoundError:
        log(f"'{CLAUDE_CMD}' not found. Install: npm install -g @anthropic-ai/claude-code", "ERROR")
        return False, "CLAUDE_NOT_FOUND"

    except Exception as e:
        log(f"Claude Code error: {e}", "ERROR")
        return False, str(e)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Project context loader (ensures Claude Code understands the project)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROJECT_CONTEXT_PREAMBLE = """## IMPORTANT: Read project context first!
Before making ANY changes, read these files for project understanding:
1. `CLAUDE.md` — Full project orientation, architecture, and conventions
2. `BUGS.md` — Known bugs and their status

This is the Arabic Book Digester (ABD) project — a precision pipeline for
extracting scholarly excerpts from classical Arabic texts. Accuracy is the
non-negotiable standard. Follow all conventions in CLAUDE.md.

## CRITICAL: Files you must NEVER delete or modify (unless the task explicitly requires it)
- `BUGS.md` — Bug tracker
- `ROADMAP.md` — Strategic task list
- `PROGRESS.md` — Session state tracker
- `CLAUDE.md` — Project orientation
- `automation/overnight/abd_overnight.py` — Overnight automation system
- `automation/overnight/README.md` — Overnight docs
- `scripts/OVERNIGHT_PROMPT.md` — Overnight prompt
- `scripts/overnight.sh` — Overnight shell script
- `taxonomy/**/*.yaml` — Taxonomy trees (hand-crafted, weeks of work)
- `gold_baselines/**/*` — Gold standard excerpts (hand-crafted)
- `.gitignore` — Git configuration

"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Prompt builders
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_bug_fix_prompt(bug: BugEntry, failed_before: list[str]) -> str:
    """Build a precise, scoped prompt for fixing one specific bug."""

    previous_failures = ""
    if failed_before:
        previous_failures = (
            "\n\n## IMPORTANT: Previous attempts at this bug FAILED\n"
            "The following approaches were tried and did NOT work. "
            "Do NOT repeat them. Try a DIFFERENT approach:\n"
            + "\n".join(f"- {f}" for f in failed_before)
        )

    return PROJECT_CONTEXT_PREAMBLE + f"""You are fixing exactly ONE bug in the Arabic Book Digester (ABD) project.

## Your target

{bug.full_text}
{previous_failures}

## Instructions

1. Read the files mentioned in the bug report to understand the problem.
2. Implement the MINIMAL fix. Change only what is necessary.
3. Run the test suite: `python -m pytest tests/ -q --tb=short`
4. If tests pass, commit with message: `fix: {bug.bug_id} — {bug.title[:60]}`
5. If tests fail because of YOUR changes, fix them. If tests fail for unrelated reasons, still commit your fix.
6. Update BUGS.md: change this bug's status from OPEN/NEW to FIXED, like: `### {bug.bug_id} 🔴 FIXED — {bug.title}`

## Rules

- Do NOT fix other bugs. Do NOT refactor unrelated code. Do NOT add features.
- Do NOT modify test files to make tests pass — fix the source code.
- Do NOT modify gold baselines, schemas, or committed extraction outputs unless the bug specifically requires it.
- Do NOT delete ANY files that are not directly related to this bug fix.
- Keep changes MINIMAL and SURGICAL.
- If the fix requires a design decision you're unsure about, implement the safest option and add a comment explaining the tradeoff.
"""


def build_analyze_prompt(state: OvernightState) -> str:
    """Build a prompt for the ANALYZE phase.

    Priority: ROADMAP.md tasks first, then freestyle improvements.
    """
    completed = []
    for task in state.task_history:
        if task.get("status") == "success":
            completed.append(f"- {task['task_id']}: {task['description']}")
    completed_text = "\n".join(completed) if completed else "(none yet)"

    # Load ROADMAP if it exists
    roadmap_section = ""
    if os.path.exists(ROADMAP_FILE):
        with open(ROADMAP_FILE, encoding="utf-8") as f:
            roadmap_content = f.read()
        roadmap_section = f"""
### Priority 1: Check ROADMAP.md for structured tasks

Here is the current ROADMAP.md:

<roadmap>
{roadmap_content}
</roadmap>

Find the FIRST task in the roadmap with:
- Status: `TODO`
- All "Depends on" tasks have status: `DONE` (or no dependencies)
- Not already completed this session (see list above)

If you find such a task, output ONLY that one task as a JSON array with one item.
The "description" field MUST include the full acceptance criteria from the roadmap.

### Priority 2: If no ROADMAP task is ready, find freestyle improvements
"""
    else:
        roadmap_section = "### Find concrete improvements\n"

    return PROJECT_CONTEXT_PREAMBLE + f"""You are analyzing the Arabic Book Digester (ABD) project to find the next task.

## Context
Read CLAUDE.md for full project context and BUGS.md for known issues.

## Already completed this session
{completed_text}

## Task selection
{roadmap_section}
Examine the codebase and identify up to 5 CONCRETE, TESTABLE improvements that are NOT already in BUGS.md. Focus on:

1. Test coverage gaps (functions with no tests, edge cases not covered)
2. Code correctness issues not in BUGS.md (silent bugs, wrong defaults, missing error handling)
3. Documentation-code mismatches (docs say one thing, code does another)
4. Missing validation or error handling that could cause silent failures
5. Dead code or unused imports that add confusion

## Output format

Respond with ONLY a JSON array. No markdown, no explanation, no preamble. Example:
[
  {{
    "id": "1.1",
    "type": "roadmap",
    "title": "Fix taxonomy leaf extraction for v1 format",
    "description": "The full task description with acceptance criteria...",
    "files": ["tools/extract_passages.py", "tests/test_extraction.py"],
    "complexity": "medium",
    "verification": "python -m pytest tests/ -q"
  }}
]

Only suggest things you are CONFIDENT can be implemented correctly. No speculative refactors.
Do NOT suggest anything that would require changing the project's architecture or design decisions.
Do NOT suggest things already listed in BUGS.md.
"""


def _parse_json_from_output(output: str) -> list[dict]:
    """Robustly extract a JSON array from Claude Code's output.

    Claude Code output includes tool calls, file contents, and other artifacts.
    We need to find the actual JSON array among all that text.
    Strategy: try multiple extraction approaches, from most to least specific.
    """
    # Approach 1: Look for a JSON array that starts at a line beginning
    for line_start in re.finditer(r"^\[", output, re.MULTILINE):
        # Find the matching closing bracket
        depth = 0
        start = line_start.start()
        for i in range(start, len(output)):
            if output[i] == "[":
                depth += 1
            elif output[i] == "]":
                depth -= 1
                if depth == 0:
                    candidate = output[start:i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, list) and len(parsed) > 0:
                            # Validate structure
                            if all(isinstance(item, dict) and "id" in item for item in parsed):
                                return parsed
                    except json.JSONDecodeError:
                        continue
                    break

    # Approach 2: Try the old regex as fallback
    json_match = re.search(r"\[[\s\S]*\]", output)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    return []


def build_improvement_prompt(improvement: dict, failed_before: list[str]) -> str:
    """Build a prompt for implementing one specific improvement."""

    previous_failures = ""
    if failed_before:
        previous_failures = (
            "\n\n## Previous attempts FAILED. Try a different approach:\n"
            + "\n".join(f"- {f}" for f in failed_before)
        )

    files_str = ", ".join(improvement.get("files", []))

    # For ROADMAP tasks, add extra instructions to update ROADMAP.md status
    roadmap_instructions = ""
    if improvement.get("type") == "roadmap":
        roadmap_instructions = f"""

## After completing the fix — UPDATE ROADMAP.md
This task is from ROADMAP.md. After successful implementation:
1. In ROADMAP.md, change this task's `**Status:** \\`TODO\\`` to `**Status:** \\`DONE\\``
2. Commit all changes together (code + test + ROADMAP.md update)
"""

    return PROJECT_CONTEXT_PREAMBLE + f"""You are implementing exactly ONE improvement in the Arabic Book Digester (ABD) project.

## Your target

**{improvement['id']}**: {improvement['title']}

{improvement['description']}

Relevant files: {files_str}
{previous_failures}

## Instructions

1. Read the relevant files to understand the current state.
2. Implement the improvement. Change only what is necessary.
3. Run tests: `python -m pytest tests/ -q --tb=short`
4. If tests pass, commit with message: `improve: {improvement['id']} — {improvement['title'][:60]}`
5. If your changes break tests, fix them or revert your changes.

## Rules

- Do NOT fix unrelated bugs. Do NOT refactor unrelated code.
- Do NOT modify gold baselines or schemas.
- Keep changes MINIMAL.
- If adding tests, make sure they actually test something meaningful and pass.
{roadmap_instructions}"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Core: Execute one task with safety wrapper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def execute_task_safely(
    task_id: str,
    task_type: str,
    description: str,
    prompt: str,
    baseline: TestResult,
    state: OvernightState,
    dry_run: bool = False,
) -> TaskResult:
    """
    Execute one task with full safety:
    1. Checkpoint current state
    2. Run Claude Code
    3. Run tests
    4. If regression → rollback
    5. Return result
    """
    start_time = time.time()
    checkpoint = git_head_hash()
    log(f"Checkpoint: {checkpoint}")

    # Run Claude Code
    log("Running Claude Code...")
    success, output = run_claude(prompt, dry_run=dry_run)

    if not success:
        duration = time.time() - start_time
        # Rollback any partial changes
        if git_has_uncommitted_changes():
            git_rollback_to(checkpoint)
        return TaskResult(
            task_id=task_id, task_type=task_type, description=description,
            status="failed", error_reason=f"Claude Code failed: {output[:200]}",
            duration_seconds=duration
        )

    # ── SAFETY: Check for deleted critical files ──────────────────
    deleted = _check_critical_file_deletions()
    if deleted:
        log(f"CRITICAL FILES DELETED: {deleted}", "ERROR")
        git_rollback_to(checkpoint)
        duration = time.time() - start_time
        return TaskResult(
            task_id=task_id, task_type=task_type, description=description,
            status="rollback",
            error_reason=f"Deleted critical files: {', '.join(deleted)}",
            duration_seconds=duration
        )

    # Run tests AFTER Claude's changes
    tests_after = run_tests()
    log(f"Tests after: {tests_after.passed} passed, {tests_after.failed} failed, {tests_after.skipped} skipped")

    # Check for regressions
    acceptable, reason = tests_are_acceptable(baseline, tests_after)

    if not acceptable:
        log(f"REGRESSION DETECTED: {reason}", "WARN")
        git_rollback_to(checkpoint)
        duration = time.time() - start_time
        return TaskResult(
            task_id=task_id, task_type=task_type, description=description,
            status="rollback", error_reason=f"Test regression: {reason}",
            tests_before={"passed": baseline.passed, "failed": baseline.failed},
            tests_after={"passed": tests_after.passed, "failed": tests_after.failed},
            duration_seconds=duration
        )

    # Ensure all changes are committed (Claude might have forgotten)
    if git_has_uncommitted_changes():
        git_checkpoint(f"fix: {task_id} — {description[:60]}")

    commit = git_head_hash()
    duration = time.time() - start_time

    # Check if Claude actually made any changes
    if commit == checkpoint:
        return TaskResult(
            task_id=task_id, task_type=task_type, description=description,
            status="failed", error_reason="No changes were made",
            duration_seconds=duration
        )

    log(f"✓ Task succeeded. Commit: {commit}")
    return TaskResult(
        task_id=task_id, task_type=task_type, description=description,
        status="success", commit_hash=commit,
        tests_before={"passed": baseline.passed, "failed": baseline.failed},
        tests_after={"passed": tests_after.passed, "failed": tests_after.failed},
        duration_seconds=duration
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase: Fix known bugs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_bug_fix_phase(state: OvernightState, baseline: TestResult, dry_run: bool) -> TestResult:
    """Fix known bugs from BUGS.md in priority order."""
    log_separator("PHASE: Bug Fixes")

    bugs = parse_bugs_md()
    actionable = get_actionable_bugs(bugs, state)
    log(f"Found {len(bugs)} total bugs, {len(actionable)} actionable")

    if not actionable:
        log("No actionable bugs remaining.")
        return baseline

    current_baseline = baseline

    for bug in actionable:
        if state.halted:
            break

        log_separator(f"{bug.bug_id} [{bug.severity}] {bug.title[:50]}")

        # Get previous failure reasons for this bug
        attempts_info = state.bug_attempts.get(bug.bug_id, {})
        previous_errors = attempts_info.get("errors", [])

        prompt = build_bug_fix_prompt(bug, previous_errors)
        result = execute_task_safely(
            task_id=bug.bug_id,
            task_type="bug_fix",
            description=bug.title,
            prompt=prompt,
            baseline=current_baseline,
            state=state,
            dry_run=dry_run,
        )

        # Update state
        if bug.bug_id not in state.bug_attempts:
            state.bug_attempts[bug.bug_id] = {"attempts": 0, "status": "open", "commits": [], "errors": []}

        state.bug_attempts[bug.bug_id]["attempts"] += 1
        state.task_history.append(asdict(result))

        if result.status == "success":
            state.bug_attempts[bug.bug_id]["status"] = "fixed"
            state.bug_attempts[bug.bug_id]["commits"].append(result.commit_hash)
            state.consecutive_failures = 0
            state.total_commits += 1
            # Update baseline to include any new passing tests
            current_baseline = run_tests()
            state.current_best_tests = {"passed": current_baseline.passed, "failed": current_baseline.failed}
            log(f"✓ {bug.bug_id} fixed. Tests: {current_baseline.passed} passed")
        else:
            error_msg = result.error_reason or "unknown"
            state.bug_attempts[bug.bug_id]["errors"].append(error_msg[:200])
            state.consecutive_failures += 1
            log(f"✗ {bug.bug_id} failed: {error_msg[:100]}", "WARN")

            if state.bug_attempts[bug.bug_id]["attempts"] >= MAX_FAILURES_PER_BUG:
                state.bug_attempts[bug.bug_id]["status"] = "skipped"
                log(f"  Skipping {bug.bug_id} after {MAX_FAILURES_PER_BUG} failures", "WARN")

            # Circuit breaker
            if state.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                state.halted = True
                state.halt_reason = f"Circuit breaker: {CIRCUIT_BREAKER_THRESHOLD} consecutive failures"
                log(f"CIRCUIT BREAKER: {state.halt_reason}", "ERROR")
                break

        state.save()
        time.sleep(COOLDOWN_SECONDS)

    return current_baseline


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase: Intelligent improvements
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_improvement_phase(state: OvernightState, baseline: TestResult, dry_run: bool) -> TestResult:
    """Analyze codebase and implement improvements."""
    log_separator("PHASE: Intelligent Improvements")

    if state.halted:
        log("Halted — skipping improvement phase")
        return baseline

    # ANALYZE: Ask Claude to identify improvements (read-only)
    log("Analyzing codebase for improvements...")
    analyze_prompt = build_analyze_prompt(state)
    success, output = run_claude(analyze_prompt, dry_run=dry_run)

    if not success:
        log("Analysis failed, skipping improvement phase", "WARN")
        return baseline

    # Parse the improvement plan using robust JSON extraction
    improvements = _parse_json_from_output(output)
    if not improvements:
        log("No valid improvement plan found in analysis output", "WARN")
        return baseline

    log(f"Found {len(improvements)} improvements to implement")

    current_baseline = baseline

    for imp in improvements[:5]:  # Cap at 5 improvements per cycle
        if state.halted:
            break

        imp_id = imp.get("id", f"IMP-{len(state.improvements_done)+1:03d}")
        title = imp.get("title", "untitled")
        log_separator(f"{imp_id}: {title[:50]}")

        # Check if already done
        if imp_id in [i.get("id") for i in state.improvements_done]:
            log(f"Already done, skipping")
            continue

        # Check if previously failed (failure memory across cycles)
        imp_attempts = state.bug_attempts.get(imp_id, {})
        if imp_attempts.get("status") == "skipped":
            log(f"Previously failed and skipped, moving on")
            continue
        previous_errors = imp_attempts.get("errors", [])

        prompt = build_improvement_prompt(imp, failed_before=previous_errors)
        result = execute_task_safely(
            task_id=imp_id,
            task_type="improvement",
            description=title,
            prompt=prompt,
            baseline=current_baseline,
            state=state,
            dry_run=dry_run,
        )

        state.task_history.append(asdict(result))

        if result.status == "success":
            state.improvements_done.append(imp)
            state.consecutive_failures = 0
            state.total_commits += 1
            current_baseline = run_tests()
            state.current_best_tests = {"passed": current_baseline.passed, "failed": current_baseline.failed}
            log(f"✓ {imp_id} done. Tests: {current_baseline.passed} passed")
        else:
            state.consecutive_failures += 1
            error_msg = result.error_reason or "unknown"
            # Track improvement failures (reuse bug_attempts dict for unified tracking)
            if imp_id not in state.bug_attempts:
                state.bug_attempts[imp_id] = {"attempts": 0, "status": "open", "commits": [], "errors": []}
            state.bug_attempts[imp_id]["attempts"] += 1
            state.bug_attempts[imp_id]["errors"].append(error_msg[:200])
            if state.bug_attempts[imp_id]["attempts"] >= MAX_FAILURES_PER_BUG:
                state.bug_attempts[imp_id]["status"] = "skipped"
                log(f"  Skipping {imp_id} after {MAX_FAILURES_PER_BUG} failures", "WARN")
            log(f"✗ {imp_id} failed: {error_msg[:100]}", "WARN")

            if state.consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                state.halted = True
                state.halt_reason = f"Circuit breaker: {CIRCUIT_BREAKER_THRESHOLD} consecutive failures"
                log(f"CIRCUIT BREAKER: {state.halt_reason}", "ERROR")
                break

        state.save()
        time.sleep(COOLDOWN_SECONDS)

    return current_baseline


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Morning report
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_report(state: OvernightState, base_commit: str):
    """Generate a human-readable morning report."""
    final_tests = run_tests()

    bugs_fixed = [bid for bid, info in state.bug_attempts.items() if info.get("status") == "fixed"]
    bugs_failed = [bid for bid, info in state.bug_attempts.items() if info.get("status") == "skipped"]
    bugs_attempted = [bid for bid, info in state.bug_attempts.items() if info.get("attempts", 0) > 0]

    successes = [t for t in state.task_history if t.get("status") == "success"]
    failures = [t for t in state.task_history if t.get("status") in ("failed", "rollback")]

    report = f"""# ABD Overnight Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Summary

| Metric | Value |
|--------|-------|
| Branch | `{state.branch_name}` |
| Started | {state.started_at} |
| Cycles completed | {state.total_cycles} |
| Total commits | {state.total_commits} |
| Halted | {"Yes — " + state.halt_reason if state.halted else "No (completed normally)"} |

## Test Results

| When | Passed | Failed | Skipped |
|------|--------|--------|---------|
| Baseline (before) | {state.baseline_tests.get('passed', '?')} | {state.baseline_tests.get('failed', '?')} | {state.baseline_tests.get('skipped', '?')} |
| Final (after) | {final_tests.passed} | {final_tests.failed} | {final_tests.skipped} |

## Bug Fixes

| Bug | Severity | Result |
|-----|----------|--------|
"""
    for bid in bugs_attempted:
        info = state.bug_attempts[bid]
        status_emoji = {"fixed": "✅", "skipped": "❌", "open": "⏳"}.get(info["status"], "?")
        attempts = info["attempts"]
        report += f"| {bid} | — | {status_emoji} {info['status']} ({attempts} attempt{'s' if attempts != 1 else ''}) |\n"

    if not bugs_attempted:
        report += "| (none attempted) | — | — |\n"

    report += f"""
**Fixed:** {len(bugs_fixed)} | **Skipped (failed):** {len(bugs_failed)} | **Not attempted:** (remaining)

## Improvements

"""
    for imp in state.improvements_done:
        report += f"- ✅ **{imp.get('id', '?')}**: {imp.get('title', '?')}\n"

    if not state.improvements_done:
        report += "- (none completed)\n"

    report += f"""
## All Tasks ({len(successes)} succeeded, {len(failures)} failed)

"""
    for t in state.task_history:
        emoji = "✅" if t["status"] == "success" else "❌" if t["status"] == "failed" else "⏪"
        duration = f"{t.get('duration_seconds', 0):.0f}s"
        commit = t.get("commit_hash", "—")
        error = f" — {t.get('error_reason', '')[:80]}" if t.get("error_reason") else ""
        report += f"- {emoji} `{t['task_id']}` [{t['task_type']}] {duration} commit:{commit}{error}\n"

    report += f"""
## Changes

```
{git_log_since(base_commit)}
```

```
{git_diff_stat_since(base_commit)}
```

## To review and merge

```bash
git log --oneline master..{state.branch_name}
git diff master..{state.branch_name}
git checkout master && git merge {state.branch_name}
```
"""

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)

    log(f"Report written to {REPORT_FILE}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main coordinator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    parser = argparse.ArgumentParser(description="ABD Overnight Autonomous Improvement System")
    parser.add_argument("--max-cycles", type=int, default=5,
                        help="Number of full ANALYZE→FIX→IMPROVE cycles (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate everything without calling Claude Code")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from previous state file")
    parser.add_argument("--bugs-only", action="store_true",
                        help="Only fix known bugs, skip improvement phase")
    args = parser.parse_args()

    # ── Register graceful shutdown handler ─────────────────────────
    signal.signal(signal.SIGINT, _handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_shutdown)

    # ── Setup logging ─────────────────────────────────────────────
    global LOG_FILE
    LOG_FILE = f"overnight-{datetime.now().strftime('%Y%m%d-%H%M')}.log"

    log("=" * 64)
    log("ABD Overnight Autonomous Improvement System")
    log("=" * 64)

    # ── Preflight checks ──────────────────────────────────────────
    # Claude Max uses `claude login` (no API key needed).
    # API billing uses ANTHROPIC_API_KEY. We warn but don't block.
    if not os.environ.get("ANTHROPIC_API_KEY") and not args.dry_run:
        log("ANTHROPIC_API_KEY not set. OK if using Claude Max (claude login).", "WARN")
        log("For API billing, set: export ANTHROPIC_API_KEY=sk-ant-...", "WARN")

    if not args.dry_run:
        try:
            result = subprocess.run([CLAUDE_CMD, "--version"],
                                    capture_output=True, text=True, timeout=10)
            log(f"Claude Code: {result.stdout.strip()}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            log(f"'{CLAUDE_CMD}' not found. Install: npm install -g @anthropic-ai/claude-code", "ERROR")
            sys.exit(1)

    # Must be in a git repo
    try:
        git("rev-parse", "--is-inside-work-tree")
    except RuntimeError:
        log("Not inside a git repository.", "ERROR")
        sys.exit(1)

    # Must have clean working tree (or we handle it)
    if git_has_uncommitted_changes():
        log("WARNING: Uncommitted changes detected. Stashing them.", "WARN")
        log("Run `git stash pop` after overnight to restore.", "WARN")
        git("stash", "push", "-m", "overnight-pre-stash")

    # ── Load or create state ──────────────────────────────────────
    if args.resume and os.path.exists(STATE_FILE):
        state = OvernightState.load()
        log(f"Resumed from state: {state.total_cycles} cycles done, {state.total_commits} commits")
        branch_name = state.branch_name
    else:
        branch_name = f"claude/overnight-{datetime.now().strftime('%Y%m%d-%H%M')}"
        state = OvernightState(
            started_at=datetime.now(timezone.utc).isoformat(),
            branch_name=branch_name,
        )

    # Create/switch to working branch
    current = git_current_branch()
    if current != branch_name:
        try:
            git("checkout", "-b", branch_name)
        except RuntimeError:
            git("checkout", branch_name)

    log(f"Branch: {branch_name}")
    base_commit = git_head_hash()
    log(f"Base commit: {base_commit}")

    # ── Baseline tests ────────────────────────────────────────────
    log("Running baseline tests...")
    baseline = run_tests()
    log(f"Baseline: {baseline.passed} passed, {baseline.failed} failed, {baseline.skipped} skipped")

    if not baseline.ok:
        log(f"WARNING: Baseline has {baseline.failed} failures. Will preserve this as floor.", "WARN")

    state.baseline_tests = {
        "passed": baseline.passed,
        "failed": baseline.failed,
        "skipped": baseline.skipped,
    }
    state.current_best_tests = dict(state.baseline_tests)
    state.save()

    # ── Main loop: cycles of fix → improve ────────────────────────
    log(f"\nStarting {args.max_cycles} cycles...")

    for cycle in range(1, args.max_cycles + 1):
        if state.halted or _SHUTDOWN_REQUESTED:
            if _SHUTDOWN_REQUESTED:
                state.halted = True
                state.halt_reason = "Graceful shutdown (Ctrl+C)"
                log("Shutdown requested, finishing up...", "WARN")
            break

        state.total_cycles = cycle
        log_separator(f"CYCLE {cycle} of {args.max_cycles}")

        # Phase 1: Fix known bugs
        baseline = run_bug_fix_phase(state, baseline, args.dry_run)

        # Phase 2: Intelligent improvements (unless bugs-only mode)
        if not args.bugs_only and not state.halted:
            baseline = run_improvement_phase(state, baseline, args.dry_run)

        state.save()

        # Check if all bugs are fixed and no improvements remain
        bugs = parse_bugs_md()
        actionable = get_actionable_bugs(bugs, state)
        if not actionable and args.bugs_only:
            log("All actionable bugs resolved. Stopping.")
            break

    # ── Final report ──────────────────────────────────────────────
    log_separator("COMPLETE")
    generate_report(state, base_commit)

    final = run_tests()
    log(f"Final tests:    {final.passed} passed, {final.failed} failed")
    log(f"Baseline was:   {state.baseline_tests.get('passed', '?')} passed")
    log(f"Total commits:  {state.total_commits}")
    log(f"Report:         {REPORT_FILE}")
    log(f"Log:            {LOG_FILE}")
    log(f"Review:         git log --oneline master..{branch_name}")

    if state.halted:
        log(f"HALTED: {state.halt_reason}", "WARN")
        sys.exit(2)


if __name__ == "__main__":
    main()

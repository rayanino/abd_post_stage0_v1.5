You are working on the ABD (Arabic Book Digester) project. Read CLAUDE.md for project orientation.

## Your Task This Iteration

You are in an autonomous loop. Each iteration you should make meaningful progress on ONE thing, then update PROGRESS.md for the next iteration.

### Step 1: Read context
1. Read `PROGRESS.md` to see what was done in previous iterations and what's next.
2. Read `BUGS.md` to see the prioritized bug list.

### Step 2: Pick ONE task
Pick the highest-priority unfixed item from BUGS.md that hasn't already been completed (check PROGRESS.md). Follow the priority tiers in BUGS.md § Recommended Fix Priority.

Rules for picking:
- Fix ONE bug or make ONE improvement per iteration. Do not try to fix everything.
- Prefer code fixes over doc fixes (code bugs are higher impact).
- If a code fix requires understanding a spec, read the spec first.
- If you're blocked on something (e.g., needs user input), skip it and pick the next item. Note the blocker in PROGRESS.md.

### Step 3: Implement the fix
- Make the minimal, correct fix. Don't refactor unrelated code.
- If fixing a code bug: run `python -m pytest tests/ -q` to verify you didn't break anything.
- If fixing a doc bug: verify the fix by cross-referencing the authoritative source (schema, code, glossary).
- If the fix needs new tests, add them.

### Step 4: Update PROGRESS.md
After making changes, update PROGRESS.md:
- Increment the iteration count
- Add what you did to "Completed This Session"
- Update "Next Priority" with what the next iteration should tackle
- Note any blockers or decisions needed in "Notes / Blockers"
- Update "Last updated" timestamp

### What NOT to do
- Do NOT attempt to fix bugs that require API keys or external services.
- Do NOT modify gold baselines (these are hand-crafted ground truth).
- Do NOT delete or move files in `books/*/source/` (frozen source HTML).
- Do NOT make sweeping refactors. One bug, one fix, one commit.
- Do NOT modify this prompt file or the overnight script.
- Do NOT create new pipeline stages or features — focus on bugs and consistency fixes.

### Scope of "improvements" beyond BUGS.md
Once all BUGS.md items are fixed, you may:
- Add missing test coverage for untested code paths
- Fix type hints or docstrings that are wrong
- Improve error messages that are confusing
- Add schema validation where it's missing
- Always update PROGRESS.md and run tests.

# ABD — Runtime Contract v0.1

This document defines the **reproducible runtime environment** for running ABD tooling (validators, renderers, harness scripts, checkpoint tooling).

This is written for:
- AI software builders (Claude Code / Devin / etc.)
- Future contributors running validations locally or in CI

---

## 1) Supported platforms

ABD tooling is designed to run **offline** (no network required) on:
- Windows 10/11 (primary)
- macOS
- Linux

All tools must behave deterministically given the same inputs.

---

## 2) Supported Python versions

- **Python 3.11+** is required.

Rationale:
- Type hints and stdlib improvements are used across tooling.
- Avoids edge cases with older `json` / `pathlib` behaviors.

---

## 3) Dependencies

Runtime dependencies are pinned in:
- `requirements.txt`

Dev-only dependencies are optional and pinned in:
- `requirements-dev.txt`

---

## 4) Standard environment setup

Run from the **ABD repo root** (the folder containing `READ_FIRST.md`).

### 4.1 Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

**macOS/Linux (bash/zsh):**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4.2 Verify the environment

```bash
python tools/check_env.py
```

---

## 5) Determinism and offline policy

- Tooling must not require internet access.
- Tooling must not depend on system locale.
- All generated artifacts must be deterministic (no timestamps in outputs).
- Canonical vs derived policy:
  - JSONL + metadata + taxonomy snapshots are canonical.
  - Markdown under `excerpts_rendered/` is derived and must be regeneratable.

---

## 6) Operational commands

### 6.1 Validate all active gold baselines

```bash
python tools/run_all_validations.py
```

### 6.1.1 Continuous Integration (GitHub Actions)

CI is defined in `.github/workflows/abd_validate.yml` and runs:
- dependency install from `requirements.txt`
- `python tools/check_env.py`
- `python tools/run_all_validations.py`

The workflow assumes `.github/` lives at the ABD repo root.

### 6.2 Render derived excerpt markdown for a passage baseline

From inside a passage folder:

```bash
python tools/render_excerpts_md.py --excerpts excerpts.jsonl --atoms-matn atoms_matn.jsonl --out-dir excerpts_rendered
```

---

## 7) Troubleshooting

### Missing dependencies

If `tools/check_env.py` reports missing modules, run:

```bash
python -m pip install -r requirements.txt
```

### Windows execution policy (PowerShell)

If activation fails, you may need:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

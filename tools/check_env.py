#!/usr/bin/env python3
"""ABD environment sanity-check.

Goal: remove ambiguity for AI builders by making the runtime contract executable.

Checks:
- Python version (>= 3.11)
- Required dependencies installed and (best-effort) version match with requirements.txt
- Repository root discovery (run from anywhere)
"""

from __future__ import annotations

import argparse
import importlib
import os
import platform
import sys
from pathlib import Path


MIN_PY = (3, 11)


def find_repo_root(start: Path) -> Path:
    """Find ABD repo root by walking parents.

    Repo root is the folder containing:
      - READ_FIRST.md
      - tools/
    """
    cur = start.resolve()
    for _ in range(8):
        if (cur / "READ_FIRST.md").exists() and (cur / "tools").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    raise SystemExit(
        "ERROR: Could not find ABD repo root. Run from the ABD folder (contains READ_FIRST.md), "
        "or pass --repo-root."
    )


def parse_pinned_requirements(req_path: Path) -> dict[str, str]:
    pinned: dict[str, str] = {}
    if not req_path.exists():
        return pinned
    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # only handle exact pins "name==version" in v0.1
        if "==" in line and ">" not in line and "<" not in line:
            name, ver = line.split("==", 1)
            pinned[name.strip().lower()] = ver.strip()
    return pinned


def get_installed_version(dist_name: str) -> str | None:
    try:
        from importlib import metadata  # py3.8+

        return metadata.version(dist_name)
    except Exception:
        return None


def check_python_version() -> list[str]:
    issues: list[str] = []
    if sys.version_info < MIN_PY:
        issues.append(
            f"Python >= {MIN_PY[0]}.{MIN_PY[1]} required; found {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}."
        )
    return issues


def check_import(module: str, pip_name: str) -> tuple[bool, str | None]:
    try:
        importlib.import_module(module)
        return True, None
    except Exception as e:
        return False, f"Missing module '{module}'. Install '{pip_name}' via requirements.txt. ({e})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=None, help="Path to ABD repo root (contains READ_FIRST.md)")
    args = ap.parse_args()

    start = Path(args.repo_root) if args.repo_root else Path.cwd()
    repo = find_repo_root(start)

    print("ABD environment check")
    print("-" * 72)
    print(f"Repo root: {repo}")
    print(f"Python: {sys.executable}")
    print(f"Python version: {sys.version.splitlines()[0]}")
    print(f"OS: {platform.system()} {platform.release()} ({platform.platform()})")
    print(f"CWD: {Path.cwd()}")

    issues: list[str] = []
    warnings: list[str] = []
    issues.extend(check_python_version())

    # Required deps
    required = [
        ("yaml", "PyYAML"),
        ("jsonschema", "jsonschema"),
    ]
    for mod, pip_name in required:
        ok, msg = check_import(mod, pip_name)
        if not ok and msg:
            issues.append(msg)

    # Best-effort version match
    pinned = parse_pinned_requirements(repo / "requirements.txt")
    if pinned:
        print("\nPinned dependency versions (requirements.txt):")
        for name, ver in pinned.items():
            inst = get_installed_version(name) or get_installed_version(name.replace("pyyaml", "PyYAML"))
            inst2 = get_installed_version("PyYAML") if name == "pyyaml" else None
            inst_ver = inst2 or inst
            if inst_ver is None:
                print(f"  - {name}=={ver}: NOT INSTALLED")
                issues.append(f"Dependency not installed: {name}=={ver}")
            else:
                if inst_ver == ver:
                    status = "OK"
                else:
                    status = f"MISMATCH (installed {inst_ver})"
                    warnings.append(f"Version mismatch for {name}: required {ver}, installed {inst_ver}")
                print(f"  - {name}=={ver}: {status}")

    print("\nResult:")
    if issues:
        print("ENV CHECK: FAIL")
        for i in issues:
            print(f"- {i}")
        print("\nFix:")
        print("  python -m venv .venv")
        if platform.system().lower().startswith("win"):
            print("  .\\.venv\\Scripts\\Activate.ps1")
        else:
            print("  source .venv/bin/activate")
        print("  python -m pip install --upgrade pip")
        print("  python -m pip install -r requirements.txt")
        raise SystemExit(2)
    else:
        if warnings:
            print("ENV CHECK: PASS (WARNINGS)")
            for w in warnings:
                print(f"- {w}")
            print("\nRecommended fix (for reproducibility):")
            print("  python -m pip install -r requirements.txt")
        else:
            print("ENV CHECK: PASS")
        print("Next:")
        print("  python tools/run_all_validations.py")


if __name__ == "__main__":
    main()

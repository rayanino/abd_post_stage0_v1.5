#!/usr/bin/env python3
"""ABD Gold Pipeline Runner (6-checkpoint orchestration + state machine)

This script operationalizes `2_atoms_and_excerpts/extraction_protocol_v2.4.md` as an executable contract and
maintains an explicit `checkpoint_state.json` in each baseline directory.

Design goals:
- Deterministic, conservative checks (fail fast on missing required artifacts)
- Human-approval-friendly: state file makes progress explicit and reproducible
- Baseline-standalone: uses baseline-local snapshots when present

Usage:
  python tools/pipeline_gold.py --baseline-dir <path> --checkpoint 6

Checkpoints:
  1) Clean input artifacts exist (CP1)
  2) Atoms + canonicals exist (CP2)
  3) Decision log exists (CP3)
  4) Excerpts + exclusions exist (CP4)
  5) Taxonomy changes + snapshot exist (CP5)
  6) Validation + derived views + manifest refresh (CP6)

State:
  - checkpoint_state.json is created if missing.
  - By default, state is updated in-place; use --no-write-state to run read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
import sys
from typing import Dict, Any

PIPELINE_VERSION = "gold_pipeline_v0.3"


def die(msg: str) -> None:
    print(f"ERROR: {msg}")
    sys.exit(1)


def must_exist(path: str, label: str) -> None:
    if not os.path.exists(path):
        die(f"Missing required {label}: {path}")


def sha256_file(fp: str) -> str:
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_validator_report(stdout_text: str) -> dict:
    """Extract {errors,warnings,result,validator_version} from validate_gold stdout."""
    import re
    out = {"errors": 0, "warnings": 0, "result": "FAIL", "validator_version": None}
    m = re.search(r"Gold Standard Validator v(\d+\.\d+\.\d+)", stdout_text)
    if m:
        out["validator_version"] = "v" + m.group(1)
    m2 = re.search(r"ERRORS \((\d+)\)\s*:", stdout_text)
    if m2:
        out["errors"] = int(m2.group(1))
    m3 = re.search(r"WARNINGS \((\d+)\)\s*:", stdout_text)
    if m3:
        out["warnings"] = int(m3.group(1))
    if (out["errors"] == 0) and ("ALL CHECKS PASSED" in stdout_text):
        out["result"] = "PASS"
    return out


def read_metadata(baseline_dir: str) -> Dict[str, Any]:
    for fn in os.listdir(baseline_dir):
        if fn.startswith("passage") and fn.endswith("_metadata.json"):
            with open(os.path.join(baseline_dir, fn), encoding="utf-8") as f:
                return json.load(f)
    die("No passage*_metadata.json found")


def state_path(baseline_dir: str) -> str:
    return os.path.join(baseline_dir, "checkpoint_state.json")




def outputs_dir(baseline_dir: str) -> str:
    # Standard directory for checkpoint stdout/stderr capture.
    return os.path.join(baseline_dir, 'checkpoint_outputs')


def ensure_outputs_dir(baseline_dir: str) -> str:
    od = outputs_dir(baseline_dir)
    os.makedirs(od, exist_ok=True)
    return od

def regenerate_checkpoint_index(baseline_dir: str) -> None:
    """Regenerate checkpoint_outputs/index.txt deterministically.

    This file is derived-only, must not be hand-edited, and must be stable
    (no timestamps). The validator enforces exact match with the canonical
    algorithm in tools/checkpoint_index_lib.py.
    """
    try:
        from checkpoint_index_lib import write_index_file
        write_index_file(baseline_dir)
    except Exception as e:
        die(f"Failed to generate checkpoint_outputs/index.txt: {e}")


def touch_checkpoint_index(baseline_dir: str) -> str:
    """Ensure checkpoint_outputs/index.txt exists (may be empty placeholder)."""
    od = ensure_outputs_dir(baseline_dir)
    fp = os.path.join(od, "index.txt")
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    open(fp, "a", encoding="utf-8").close()
    return os.path.relpath(fp, baseline_dir)


def init_state_if_missing(baseline_dir: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    sp = state_path(baseline_dir)
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            return json.load(f)

    # Create minimal CP0 state
    v = os.path.basename(baseline_dir).split("_v", 1)[-1]
    baseline_version = v if v.startswith("0.") else v
    st = {
        "record_type": "checkpoint_state",
        "checkpoint_state_version": "0.1",
        "book_id": meta.get("book_id", ""),
        "passage_id": meta.get("passage_id", ""),
        "baseline_version": baseline_version,
        "pipeline_version": PIPELINE_VERSION,
        "checkpoint_last_completed": 0,
        "checkpoints": {
            "1": {"name": "CP1_clean_input", "status": "pending", "artifacts": []},
            "2": {"name": "CP2_atoms_and_canonicals", "status": "pending", "artifacts": []},
            "3": {"name": "CP3_decisions", "status": "pending", "artifacts": []},
            "4": {"name": "CP4_excerpts", "status": "pending", "artifacts": []},
            "5": {"name": "CP5_taxonomy_changes", "status": "pending", "artifacts": []},
            "6": {"name": "CP6_validate_and_package", "status": "pending", "artifacts": []},
        },
        "integrity": {
            "baseline_manifest_sha256": "0" * 64,
            "validator_version": meta.get("validation", {}).get("validator_version", ""),
        },
    }
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    return st


def write_state(baseline_dir: str, st: Dict[str, Any]) -> None:
    with open(state_path(baseline_dir), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


def run_cmd(cmd: str, cwd: str, stdout_path: str | None = None, stderr_path: str | None = None) -> None:
    """Run a shell command, optionally capturing stdout/stderr to files."""
    print(f"\nRUN: {cmd}\nCWD: {cwd}\n")
    out_f = err_f = None
    try:
        if stdout_path:
            os.makedirs(os.path.dirname(stdout_path), exist_ok=True)
            out_f = open(stdout_path, 'w', encoding='utf-8')
        if stderr_path:
            os.makedirs(os.path.dirname(stderr_path), exist_ok=True)
            err_f = open(stderr_path, 'w', encoding='utf-8')
        res = subprocess.run(cmd, cwd=cwd, shell=True, stdout=out_f, stderr=err_f)
    finally:
        if out_f:
            out_f.close()
        if err_f:
            err_f.close()
    if res.returncode != 0:
        die(f"Command failed with exit code {res.returncode}")



def _set_done(st: Dict[str, Any], cp: int, artifacts: list[str], command: str | None = None, notes: str | None = None):
    cpk = str(cp)
    st["checkpoints"][cpk]["status"] = "done"
    st["checkpoints"][cpk]["artifacts"] = artifacts
    if command is not None:
        st["checkpoints"][cpk]["command"] = command
    if notes is not None:
        st["checkpoints"][cpk]["notes"] = notes
    st["checkpoint_last_completed"] = max(int(st.get("checkpoint_last_completed", 0)), cp)


def checkpoint_1(baseline_dir: str, meta: dict, st: dict, runtime: dict) -> None:
    pid = meta["passage_id"]
    a = [f"{pid}_clean_matn_input.txt", f"{pid}_clean_fn_input.txt", f"{pid}_source_slice.json"]
    for fn in a:
        must_exist(os.path.join(baseline_dir, fn), "CP1 artifact")

    od = ensure_outputs_dir(baseline_dir)
    outp = os.path.join(od, "cp1_extract_clean_input.stdout.txt")
    errp = os.path.join(od, "cp1_extract_clean_input.stderr.txt")

    cmd = meta.get("checkpoint1", {}).get("command", "").strip()
    if runtime.get("execute_cp1"):
        if not cmd:
            die("metadata.checkpoint1.command missing (cannot execute CP1)")
        run_cmd(cmd, cwd=baseline_dir, stdout_path=outp, stderr_path=errp)

    must_exist(outp, "CP1 stdout log")
    must_exist(errp, "CP1 stderr log")

    idx_rel = touch_checkpoint_index(baseline_dir)
    artifacts = a + [os.path.relpath(outp, baseline_dir), os.path.relpath(errp, baseline_dir), idx_rel]
    _set_done(st, 1, artifacts, command=cmd)
    print("CP1 OK")



def checkpoint_2(baseline_dir: str, meta: dict, st: dict, runtime: dict) -> None:
    pid = meta["passage_id"]
    a = [
        f"{pid}_matn_atoms_v02.jsonl",
        f"{pid}_fn_atoms_v02.jsonl",
        f"{pid}_matn_canonical.txt",
        f"{pid}_fn_canonical.txt",
    ]
    for fn in a:
        must_exist(os.path.join(baseline_dir, fn), "CP2 artifact")
    _set_done(st, 2, a, notes="Gold authoring: atoms + canonicals")
    print("CP2 OK")


def checkpoint_3(baseline_dir: str, meta: dict, st: dict, runtime: dict) -> None:
    pid = meta["passage_id"]
    a = [f"{pid}_decisions.jsonl"]
    for fn in a:
        must_exist(os.path.join(baseline_dir, fn), "CP3 artifact")
    _set_done(st, 3, a, notes="Gold authoring: decisions log")
    print("CP3 OK")


def checkpoint_4(baseline_dir: str, meta: dict, st: dict, runtime: dict) -> None:
    pid = meta["passage_id"]
    artifacts = [f"{pid}_excerpts_v02.jsonl"]
    # Some baselines store exclusions in a separate file; others embed exclusion_record lines in excerpts JSONL.
    maybe_excl = f"{pid}_exclusions_v01.jsonl"
    if os.path.exists(os.path.join(baseline_dir, maybe_excl)):
        artifacts.append(maybe_excl)

    for fn in artifacts:
        must_exist(os.path.join(baseline_dir, fn), "CP4 artifact")

    _set_done(st, 4, artifacts, notes="Gold authoring: excerpts (and optional exclusions)")
    print("CP4 OK")


def checkpoint_5(baseline_dir: str, meta: dict, st: dict, runtime: dict) -> None:
    tax = meta.get("taxonomy_version")
    if not tax:
        die("metadata.taxonomy_version missing")
    a = ["taxonomy_changes.jsonl", f"{tax}.yaml"]
    for fn in a:
        must_exist(os.path.join(baseline_dir, fn), "CP5 artifact")
    _set_done(st, 5, a, notes="Taxonomy changes + snapshot")
    print("CP5 OK")


def checkpoint_6(baseline_dir: str, meta: dict, st: dict, runtime: dict) -> None:
    od = ensure_outputs_dir(baseline_dir)

    v = meta.get("validation", {})
    cmd = (v.get("command") or "").strip()
    if not cmd:
        die("metadata.validation.command missing")
    v_out = os.path.join(od, "cp6_validate.stdout.txt")
    v_err = os.path.join(od, "cp6_validate.stderr.txt")
    # Use canonical renderer from repo tools/ (avoid baseline-local snapshots)
    tools_dir = os.path.dirname(__file__)
    render = os.path.join(tools_dir, "render_excerpts_md.py")
    r_out = os.path.join(od, "cp6_render_md.stdout.txt")
    r_err = os.path.join(od, "cp6_render_md.stderr.txt")
    fp_tool = os.path.join(od, "cp6_tool_fingerprint.json")
    # Pre-create log files and pre-sync checkpoint_state before validation runs (validator enforces presence).
    for fp in (v_out, v_err, r_out, r_err, fp_tool):
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        open(fp, 'a', encoding='utf-8').close()

    # Ensure cp6_tool_fingerprint.json is valid JSON early (validator parses it when CP6 is marked complete)
    try:
        if os.path.exists(fp_tool) and os.path.getsize(fp_tool) == 0:
            stub = {
                'record_type': 'cp6_tool_fingerprint',
                'fingerprint_version': '0.1',
                'generated_utc': '',
                'tools': {},
                'baseline': {},
                'validation': {},
            }
            with open(fp_tool, 'w', encoding='utf-8') as f:
                json.dump(stub, f, ensure_ascii=False, indent=2)
    except Exception as e:
        die(f'Failed to initialize cp6_tool_fingerprint.json stub: {e}')

    # Ensure checkpoint index exists early (placeholder is fine; deterministic content is generated later).
    touch_checkpoint_index(baseline_dir)

    # Pre-sync CP6 artifact listing + integrity.validator_version so validate_gold can enforce the contract.
    pre_artifacts = [
        'validation_report.txt',
        'baseline_manifest.json',
        'excerpts_rendered/INDEX.md',
        'checkpoint_outputs/index.txt',
        os.path.relpath(v_out, baseline_dir),
        os.path.relpath(v_err, baseline_dir),
        os.path.relpath(r_out, baseline_dir),
        os.path.relpath(r_err, baseline_dir),
        os.path.relpath(fp_tool, baseline_dir),
        'checkpoint_state.json',
    ]
    st['checkpoints'].setdefault('6', {})
    st['checkpoints']['6']['artifacts'] = pre_artifacts
    # Ensure integrity validator version matches metadata before validation
    st['integrity']['validator_version'] = v.get('validator_version', st.get('integrity', {}).get('validator_version', ''))
    mp0 = os.path.join(baseline_dir, 'baseline_manifest.json')
    if os.path.exists(mp0):
        st['integrity']['baseline_manifest_sha256'] = sha256_file(mp0)

    if runtime.get('write_state'):
        write_state(baseline_dir, st)
        # Index must reflect the pre-CP6 state sync BEFORE validator runs.
        regenerate_checkpoint_index(baseline_dir)

    run_cmd(cmd, cwd=baseline_dir, stdout_path=v_out, stderr_path=v_err)

    # Sync validation_report.txt to the captured validator stdout (prevents stale reports)
    try:
        with open(v_out, encoding='utf-8') as f:
            v_stdout_text = f.read()
        with open(os.path.join(baseline_dir, 'validation_report.txt'), 'w', encoding='utf-8') as f:
            f.write(v_stdout_text)
        parsed = parse_validator_report(v_stdout_text)
        # Keep in-memory metadata aligned too (used later in this function)
        meta.setdefault('validation', {})
        if parsed.get('validator_version'):
            meta['validation']['validator_version'] = parsed['validator_version']
        meta['validation']['validated_utc'] = utc_now()
        meta['validation']['warnings'] = int(parsed.get('warnings') or 0)
        meta['validation']['errors'] = int(parsed.get('errors') or 0)
        meta['validation']['result'] = parsed.get('result') or meta['validation'].get('result','')
        # Persist to passage*_metadata.json on disk
        meta_path = None
        for fn in os.listdir(baseline_dir):
            if fn.startswith('passage') and fn.endswith('_metadata.json'):
                meta_path = os.path.join(baseline_dir, fn)
                break
        if meta_path:
            meta_obj = json.load(open(meta_path, encoding='utf-8'))
            meta_obj.setdefault('validation', {})
            meta_obj['validation']['validator'] = meta_obj['validation'].get('validator', 'validate_gold.py')
            meta_obj['validation']['validator_version'] = meta['validation'].get('validator_version', meta_obj['validation'].get('validator_version',''))
            meta_obj['validation']['validated_utc'] = meta['validation'].get('validated_utc', utc_now())
            meta_obj['validation']['warnings'] = meta['validation'].get('warnings', 0)
            meta_obj['validation']['errors'] = meta['validation'].get('errors', 0)
            meta_obj['validation']['result'] = meta['validation'].get('result', meta_obj['validation'].get('result',''))
            meta_obj['validation']['command'] = cmd
            json.dump(meta_obj, open(meta_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except Exception as e:
        die(f'Failed to sync validation report/metadata: {e}')

    if os.path.exists(render):
        pid = meta["passage_id"]
        cmd2 = (
            f"python {render} --atoms {pid}_matn_atoms_v02.jsonl {pid}_fn_atoms_v02.jsonl "
            f"--excerpts {pid}_excerpts_v02.jsonl --outdir excerpts_rendered"
        )
        run_cmd(cmd2, cwd=baseline_dir, stdout_path=r_out, stderr_path=r_err)
    else:
        open(r_out, "a", encoding="utf-8").close()
        open(r_err, "a", encoding="utf-8").close()


    # Write CP6 tool fingerprint (machine-readable audit anchor)
    try:
        tools_dir_abs = os.path.dirname(__file__)
        repo_root = os.path.abspath(os.path.join(tools_dir_abs, '..'))
        def _rel_repo(pabs: str) -> str:
            return os.path.relpath(pabs, repo_root).replace('\\','/')
        tool_files = [
            os.path.join(tools_dir_abs, 'validate_gold.py'),
            os.path.join(tools_dir_abs, 'pipeline_gold.py'),
            os.path.join(tools_dir_abs, 'checkpoint_index_lib.py'),
            os.path.join(tools_dir_abs, 'render_excerpts_md.py'),
            os.path.join(tools_dir_abs, 'build_baseline_manifest.py'),
        ]
        pid = meta.get('passage_id', '')
        key_rel = [
            f'{pid}_matn_atoms_v02.jsonl',
            f'{pid}_fn_atoms_v02.jsonl',
            f'{pid}_excerpts_v02.jsonl',
            f'{pid}_decisions.jsonl',
            'taxonomy_changes.jsonl',
            (meta.get('taxonomy_version','') + '.yaml'),
        ]
        key_files = {}
        for rel in key_rel:
            if not rel:
                continue
            fp = os.path.join(baseline_dir, rel)
            if os.path.exists(fp):
                key_files[rel] = {'sha256': sha256_file(fp)}
        finger = {
            'record_type': 'cp6_tool_fingerprint',
            'fingerprint_version': '0.1',
            'generated_utc': utc_now(),
            'tools': { _rel_repo(f): {'sha256': sha256_file(f)} for f in tool_files if os.path.exists(f) },
            'baseline': {
                'baseline_dirname': os.path.basename(baseline_dir),
                'passage_id': pid,
                'taxonomy_version': meta.get('taxonomy_version',''),
                'key_files': key_files
            },
            'validation': {
                'command': cmd
            }
        }
        with open(fp_tool, 'w', encoding='utf-8') as f:
            json.dump(finger, f, ensure_ascii=False, indent=2)
    except Exception as e:
        die(f'Failed to write cp6_tool_fingerprint.json: {e}')

    # Refresh baseline_manifest.json at CP6 (keeps inventory truthful after new artifacts)
    try:
        tools_dir_abs = os.path.dirname(__file__)
        man_tool = os.path.join(tools_dir_abs, 'build_baseline_manifest.py')
        if os.path.exists(man_tool):
            run_cmd(f'python {man_tool} --baseline-dir .', cwd=baseline_dir)
    except Exception as e:
        die(f'Failed to refresh baseline_manifest.json: {e}')
    mp = os.path.join(baseline_dir, "baseline_manifest.json")
    if os.path.exists(mp):
        st["integrity"]["baseline_manifest_sha256"] = sha256_file(mp)
    st["integrity"]["validator_version"] = meta.get('validation', {}).get('validator_version', st.get('integrity', {}).get('validator_version', ''))

    artifacts = [
        "validation_report.txt",
        "baseline_manifest.json",
        "excerpts_rendered/INDEX.md",
        "checkpoint_outputs/index.txt",
        os.path.relpath(v_out, baseline_dir),
        os.path.relpath(v_err, baseline_dir),
        os.path.relpath(r_out, baseline_dir),
        os.path.relpath(r_err, baseline_dir),
        os.path.relpath(fp_tool, baseline_dir),
        "checkpoint_state.json",
    ]
    _set_done(st, 6, artifacts, command=cmd, notes="Validator + derived MD + manifest + captured logs")
    print("CP6 OK")



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-dir", required=True)
    ap.add_argument("--checkpoint", type=int, required=True, choices=[1, 2, 3, 4, 5, 6])
    ap.add_argument("--no-write-state", action="store_true", help="Do not modify checkpoint_state.json")
    ap.add_argument("--execute-cp1", action="store_true", help="Run CP1 extraction command (from metadata) and capture outputs")
    args = ap.parse_args()

    baseline_dir = os.path.abspath(args.baseline_dir)
    meta = read_metadata(baseline_dir)
    st = init_state_if_missing(baseline_dir, meta)

    # Keep checkpoint_state aligned with the current runner + directory naming (audit clarity)
    st["pipeline_version"] = PIPELINE_VERSION
    try:
        vdir = os.path.basename(baseline_dir).split("_v", 1)[-1]
        st["baseline_version"] = vdir
    except Exception:
        pass

    runtime = {"execute_cp1": bool(args.execute_cp1), "write_state": (not bool(args.no_write_state))}

    cp = args.checkpoint
    fnmap = {
        1: checkpoint_1,
        2: checkpoint_2,
        3: checkpoint_3,
        4: checkpoint_4,
        5: checkpoint_5,
        6: checkpoint_6,
    }

    fnmap[cp](baseline_dir, meta, st, runtime)

    if not args.no_write_state:
        write_state(baseline_dir, st)
        # Keep deterministic checkpoint index in sync after any checkpoint state update.
        if int(st.get('checkpoint_last_completed', 0) or 0) >= 1:
            regenerate_checkpoint_index(baseline_dir)


if __name__ == "__main__":
    main()

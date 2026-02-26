#!/usr/bin/env python3
"""Deterministically render excerpt JSONL into per-excerpt Markdown files.

Design intent:
- Canonical source of truth is JSONL (atoms/excerpts/metadata).
- Markdown is a derived, regeneratable review artifact for human approval.
- Output is stable (deterministic ordering and formatting) so diffs are meaningful.

Usage:
  python3 render_excerpts_md.py \
    --atoms passage_matn_atoms.jsonl passage_fn_atoms.jsonl \
    --excerpts passage_excerpts.jsonl \
    --outdir excerpts_rendered

Notes:
- If multiple atom files are provided, they are merged by atom_id.
- Excerpts are rendered in excerpt_id sort order.
- Filenames replace ':' with '__' to avoid filesystem issues.
"""

from __future__ import annotations

import argparse
import json
import os
import hashlib
from typing import Dict, List, Any


RENDERER_VERSION = "v0.3.7"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def safe_filename(excerpt_id: str) -> str:
    return excerpt_id.replace(":", "__") + ".md"


def compute_inputs_fingerprint(atom_files: List[str], excerpts_file: str) -> str:
    parts = [f"excerpts={os.path.basename(excerpts_file)}:{sha256_file(excerpts_file)[:12]}"]
    for p in atom_files:
        parts.append(f"atoms={os.path.basename(p)}:{sha256_file(p)[:12]}")
    combined = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return combined + " " + " ".join(parts)


def atom_text(atom_map: Dict[str, Dict[str, Any]], atom_id: str) -> str:
    a = atom_map.get(atom_id)
    if not a:
        return f"[MISSING ATOM: {atom_id}]"
    return a.get("text", "")


def render_atom_list(atom_map: Dict[str, Dict[str, Any]], atoms: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for item in atoms:
        aid = item["atom_id"]
        role = item.get("role", "")
        atype = atom_map.get(aid, {}).get("atom_type", "?")
        lines.append(f"- `{aid}`  (type={atype}, role={role})")
        txt = atom_text(atom_map, aid)
        for tline in txt.splitlines() or [""]:
            lines.append(f"  {tline}")
    return "\n".join(lines)


def render_relations(relations: List[Dict[str, Any]]) -> str:
    if not relations:
        return "(none)"
    lines: List[str] = []
    for r in relations:
        rtype = r.get("type", "?")
        tgt = r.get("target_excerpt_id")
        hint = r.get("target_hint")
        if tgt:
            lines.append(f"- `{rtype}` → `{tgt}`")
        else:
            lines.append(f"- `{rtype}` → (unresolved) — {hint}")
    return "\n".join(lines)


def render_source_spans(ss: Dict[str, Any]) -> str:
    if not ss:
        return "(none)"
    canon = ss.get("canonical_text_file", "?")
    spans = ss.get("spans", [])
    if not spans:
        return f"- canonical: `{canon}`\n- spans: (none)"
    lines = [f"- canonical: `{canon}`", "- spans:"]
    for s in spans:
        kind = s.get("span_kind", "?")
        cs = s.get("char_start")
        ce = s.get("char_end")
        lines.append(f"  - {kind}[{cs}..{ce}]")
    return "\n".join(lines)


def render_excerpt(atom_map: Dict[str, Dict[str, Any]], exc: Dict[str, Any], inputs_fingerprint: str) -> str:
    eid = exc.get("excerpt_id", "?")
    banner = [
        "<!-- GENERATED FILE — DO NOT EDIT. -->",
        f"<!-- renderer={RENDERER_VERSION} -->",
        f"<!-- inputs: {inputs_fingerprint} -->",
        "",
    ]

    header = banner + [
        f"# {(exc.get('excerpt_title') or eid)}",
        "",
        f"- excerpt_id: `{eid}`",
        "",
        "## Metadata",
        f"- book_id: `{exc.get('book_id','?')}`",
        f"- source_layer: `{exc.get('source_layer','?')}`",
        f"- excerpt_kind: `{exc.get('excerpt_kind','?')}`",
        f"- taxonomy_version: `{exc.get('taxonomy_version','?')}`",
        f"- taxonomy_node_id: `{exc.get('taxonomy_node_id','?')}`",
        f"- taxonomy_path: {exc.get('taxonomy_path','?')}",
    ]

    if exc.get("excerpt_title_reason"):
        header.append(f"- excerpt_title_reason: {exc.get('excerpt_title_reason')}")

    if exc.get("exercise_role"):
        header.append(f"- exercise_role: `{exc.get('exercise_role')}`")
    if exc.get("tests_nodes"):
        header.append(f"- tests_nodes: {', '.join(exc.get('tests_nodes'))}")
    if exc.get("primary_test_node"):
        header.append(f"- primary_test_node: `{exc.get('primary_test_node')}`")

    cases = exc.get("case_types", [])
    header.append(f"- case_types: {', '.join(cases) if cases else '(none)'}")

    # Cross-science flags (excerpt-level)
    cs = bool(exc.get("cross_science_context", False))
    rhet = bool(exc.get("rhetorical_treatment_of_cross_science", False))
    rs = exc.get("related_science")
    header.append(f"- cross_science_context: `{str(cs).lower()}`")
    if cs or rs is not None or rhet:
        header.append(f"- related_science: `{rs}`")
        header.append(f"- rhetorical_treatment_of_cross_science: `{str(rhet).lower()}`")

    # Content anomalies (excerpt-level)
    if exc.get("content_anomalies"):
        header.append("- content_anomalies:")
        for an in exc.get("content_anomalies") or []:
            header.append(f"  - type: `{an.get('type')}`")
            if an.get('details'):
                header.append(f"    details: {an.get('details')}")
            if an.get('synthesis_instruction'):
                header.append(f"    synthesis_instruction: {an.get('synthesis_instruction')}")
            e_atoms = an.get('evidence_atom_ids') or []
            if e_atoms:
                header.append(f"    evidence_atom_ids: {', '.join(e_atoms)}")
            e_exc = an.get('evidence_excerpt_ids') or []
            if e_exc:
                header.append(f"    evidence_excerpt_ids: {', '.join(e_exc)}")

    if exc.get("heading_path"):
        header.append("- heading_path:")
        for hid in exc.get("heading_path", []):
            htxt = atom_text(atom_map, hid)
            header.append(f"  - `{hid}`: {htxt}")

    if exc.get("interwoven_group_id"):
        header.append(f"- interwoven_group_id: `{exc.get('interwoven_group_id')}`")

    if exc.get("taxonomy_change_triggered"):
        header.append(f"- taxonomy_change_triggered: `{exc.get('taxonomy_change_triggered')}`")

    header.extend(
        [
            "",
            "## Relations",
            render_relations(exc.get("relations", [])),
            "",
            "## Source spans",
            render_source_spans(exc.get("source_spans")),
            "",
            "## Boundary reasoning (canonical JSONL field)",
            "```",
            (exc.get("boundary_reasoning") or "").rstrip(),
            "```",
            "",
            "## Core atoms",
            render_atom_list(atom_map, exc.get("core_atoms", [])),
            "",
            "## Context atoms",
            render_atom_list(atom_map, exc.get("context_atoms", [])) if exc.get("context_atoms") else "(none)",
            "",
        ]
    )

    return "\n".join(header)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--atoms", nargs="+", required=True, help="One or more atom JSONL files")
    ap.add_argument("--excerpts", required=True, help="Excerpts JSONL file (mixed excerpt+exclusion)")
    ap.add_argument("--outdir", required=True, help="Output directory for rendered Markdown")
    args = ap.parse_args()

    atom_map: Dict[str, Dict[str, Any]] = {}
    for p in args.atoms:
        for r in load_jsonl(p):
            if r.get("record_type") != "atom":
                continue
            atom_map[r["atom_id"]] = r

    recs = load_jsonl(args.excerpts)
    excerpts = [r for r in recs if r.get("record_type") == "excerpt"]

    os.makedirs(args.outdir, exist_ok=True)

    inputs_fp = compute_inputs_fingerprint(args.atoms, args.excerpts)

    # per-excerpt files
    for exc in sorted(excerpts, key=lambda x: x.get("excerpt_id", "")):
        eid = exc.get("excerpt_id", "unknown")
        path = os.path.join(args.outdir, safe_filename(eid))
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_excerpt(atom_map, exc, inputs_fp))

    # index
    index_path = os.path.join(args.outdir, "INDEX.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("<!-- GENERATED FILE — DO NOT EDIT. -->\n")
        f.write(f"<!-- renderer={RENDERER_VERSION} -->\n")
        f.write(f"<!-- inputs: {inputs_fp} -->\n\n")
        f.write("# Excerpts index\n\n")
        for exc in sorted(excerpts, key=lambda x: x.get("excerpt_id", "")):
            eid = exc.get("excerpt_id", "unknown")
            title = exc.get("excerpt_title")
            cs = bool(exc.get("cross_science_context", False))
            rs = exc.get("related_science")
            tag = f" [cross: {rs}]" if cs and rs else ""
            anoms = exc.get("content_anomalies") or []
            if anoms:
                # show up to 2 anomaly types for quick scanning
                types = [a.get("type") for a in anoms if a.get("type")]
                if types:
                    short = ",".join(types[:2])
                    tag += f" [anomaly: {short}]"
                else:
                    tag += " [anomaly]"
            if title:
                f.write(f"- {title}{tag} — `{eid}` → {safe_filename(eid)}\n")
            else:
                f.write(f"- `{eid}`{tag} → {safe_filename(eid)}\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generate human-readable excerpting report from gold standard data.

Usage:
    python3 generate_report.py \
        --atoms matn_atoms.jsonl fn_atoms.jsonl \
        --excerpts excerpts.jsonl \
        --metadata metadata.json \
        --output report.txt

All paths are required. The script derives book info, canonical SHAs,
and passage context from the metadata file — nothing is hardcoded.
"""
import json, textwrap, hashlib, os, argparse, sys


def load_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def sha256_of_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Generate human-readable excerpting report from gold standard data."
    )
    parser.add_argument('--atoms', nargs='+', required=True,
                        help='One or more atom JSONL files (e.g., matn_atoms.jsonl fn_atoms.jsonl)')
    parser.add_argument('--excerpts', required=True,
                        help='Excerpt/exclusion JSONL file')
    parser.add_argument('--metadata', required=True,
                        help='Passage metadata JSON file')
    parser.add_argument('--output', required=True,
                        help='Output report file path')
    args = parser.parse_args()

    # ── Load ───────────────────────────────────────────────────────────
    all_atoms = {}
    layer_counts = {}
    for atom_file in args.atoms:
        atoms = load_jsonl(atom_file)
        for a in atoms:
            all_atoms[a['atom_id']] = a
            layer = a.get('source_layer', '?')
            layer_counts[layer] = layer_counts.get(layer, 0) + 1

    records = load_jsonl(args.excerpts)
    excerpts = [r for r in records if r['record_type'] == 'excerpt']
    exclusions = [r for r in records if r['record_type'] == 'exclusion']

    with open(args.metadata, encoding='utf-8') as f:
        meta = json.load(f)

    # Derive canonical SHAs from metadata
    canon_shas = {}
    meta_dir = os.path.dirname(os.path.abspath(args.metadata))
    for layer_key, canon_info in meta.get('canonical_files', {}).items():
        canon_path = os.path.join(meta_dir, canon_info['filename'])
        if os.path.isfile(canon_path):
            canon_shas[layer_key] = sha256_of_file(canon_path)
        else:
            canon_shas[layer_key] = f"FILE NOT FOUND: {canon_info['filename']}"

    # ── Formatting ─────────────────────────────────────────────────────
    W = 90

    def wrap(text, indent=4):
        prefix = " " * indent
        return "\n".join(textwrap.wrap(
            text, width=W - indent,
            initial_indent=prefix, subsequent_indent=prefix))

    L = []

    def section(title):
        L.extend(["", "=" * W, title, "=" * W, ""])

    def subsection(title):
        L.extend(["", "-" * 50, title, "-" * 50])

    def core_ids_from(exc):
        return [ca['atom_id'] for ca in exc.get('core_atoms', [])]

    # ══════════════════════════════════════════════════════════════════
    # Banner — driven entirely by metadata
    passage_id = meta.get('passage_id', '?')
    book_id = meta.get('book_id', '?')
    book_title = meta.get('book_title', '?')
    page_range = meta.get('page_range', '?')
    schema_ver = meta.get('schema_version', '?')

    L.extend(["=" * W,
        f"{passage_id.upper()} — COMPLETE EXCERPTING REPORT (FINAL BASELINE)",
        f"Gold Standard {schema_ver} | {book_title} — ({page_range})",
        "=" * W])

    # ── Summary ────────────────────────────────────────────────────────
    subsection("SUMMARY")
    teach_m   = sum(1 for e in excerpts if e['excerpt_kind']=='teaching' and e['source_layer']=='matn')
    teach_f   = sum(1 for e in excerpts if e['excerpt_kind']=='teaching' and e['source_layer']=='footnote')
    exer_set  = sum(1 for e in excerpts if e.get('exercise_role')=='set')
    exer_item = sum(1 for e in excerpts if e.get('exercise_role')=='item')
    exer_ans  = sum(1 for e in excerpts if e.get('exercise_role')=='answer')
    c_ids = set(); x_ids = set()
    for e in excerpts:
        c_ids.update(core_ids_from(e))
        x_ids.update(ca['atom_id'] for ca in e.get('context_atoms', []))

    role_dist = {}
    for e in excerpts:
        for ca in e.get('core_atoms', []):
            role_dist[ca['role']] = role_dist.get(ca['role'], 0) + 1

    layer_summary = ' + '.join(f"{v} {k}" for k, v in sorted(layer_counts.items()))
    L.append(f"  Total atoms:             {len(all_atoms)} ({layer_summary})")
    L.append(f"  Teaching excerpts:       {teach_m+teach_f} ({teach_m} matn + {teach_f} footnote)")
    L.append(f"  Exercise excerpts:       {exer_set+exer_item+exer_ans} ({exer_set} set + {exer_item} items + {exer_ans} answers)")
    L.append(f"  Exclusion records:       {len(exclusions)}")
    L.append(f"  Taxonomy version:        {meta.get('taxonomy_version', '?')}")
    L.append(f"  Atoms as core:           {len(c_ids)}")
    for role_name in sorted(role_dist.keys()):
        L.append(f"    - {role_name}: {role_dist[role_name]}")
    L.append(f"  Atoms as context:        {len(x_ids)}")
    L.append(f"  Atoms excluded:          {len(exclusions)}")

    # ── Data Integrity ─────────────────────────────────────────────────
    subsection("DATA INTEGRITY")
    L.append(f"  Book ID:                 {book_id}")
    L.append(f"  Offset unit:             {meta.get('offset_unit', '?')}")
    L.append(f"  Canonical derivation:    {meta.get('canonical_derivation', '?')}")
    for layer_key, sha in canon_shas.items():
        L.append(f"  {layer_key} canonical SHA-256:  {sha}")
    L.append(f"  Core atom model:         structured (atom_id + role)")
    L.append(f"  Context atom scope:      external orientation only (no evidence)")

    # ── Taxonomy Nodes ─────────────────────────────────────────────────
    subsection("TAXONOMY NODES COVERED")
    node_map = {}
    for e in excerpts:
        node_map.setdefault(e['taxonomy_node_id'], []).append(e)
    for nid, excs in node_map.items():
        L.append(f"  {nid}")
        for e in excs:
            nc   = len(e['core_atoms'])
            nctx = len(e.get('context_atoms', []))
            role = e.get('exercise_role', '')
            rs   = f" {role}" if role else ""
            L.append(f"    +-- {e['excerpt_id']} [{e['excerpt_kind']}{rs}] "
                     f"core={nc}, ctx={nctx}, layer={e['source_layer']}")

    # ══════════════════════════════════════════════════════════════════
    section("DETAILED EXCERPT RECORDS")

    for e in excerpts:
        bar = "=" * 3
        L.append(f"{bar} {e['excerpt_id']} {'=' * (W - len(e['excerpt_id']) - 5)}")
        L.append(f"  Kind:          {e['excerpt_kind']}")
        if e.get('exercise_role'):
            L.append(f"  Exercise role: {e['exercise_role']}")
        L.append(f"  Layer:         {e['source_layer']}")
        L.append(f"  Node:          {e['taxonomy_node_id']}")
        L.append(f"  Path:          {e['taxonomy_path']}")
        L.append(f"  Cases:         {', '.join(e['case_types'])}")
        if e.get('tests_nodes'):
            L.append(f"  Tests nodes:   {', '.join(e['tests_nodes'])}")
        if e.get('primary_test_node'):
            L.append(f"  Primary test:  {e['primary_test_node']}")
        if e.get('cross_science_context'):
            L.append(f"  Cross-science: {e.get('related_science','?')}")
        ss = e.get('source_spans')
        if ss:
            spans_desc = ', '.join(
                f"{s['span_kind']}[{s['char_start']}..{s['char_end']}]"
                for s in ss.get('spans', [])
            )
            L.append(f"  Source:        {ss['canonical_text_file']} — {spans_desc}")
        hp = e.get('heading_path', [])
        if hp:
            hp_t = [all_atoms.get(h,{}).get('text','?') for h in hp]
            L.append(f"  Headings:      {' > '.join(hp_t)}")

        pre_ctx = [ca for ca in e.get('context_atoms', [])
                   if ca['role'] in ('classification_frame', 'preceding_setup', 'cross_science_background')]
        post_ctx = [ca for ca in e.get('context_atoms', [])
                    if ca not in pre_ctx]

        L.append("")

        if pre_ctx:
            L.append(f"  Context -- framing ({len(pre_ctx)}):")
            for ca in pre_ctx:
                a = all_atoms.get(ca['atom_id'], {})
                num = ca['atom_id'].split(':')[-1]
                L.append(f"    {num} [{a.get('atom_type','?')}] role={ca['role']}")
                L.append(wrap(a.get('text','???'), indent=8))
            L.append("")

        L.append(f"  Core atoms ({len(e['core_atoms'])}):")
        for entry in e['core_atoms']:
            aid = entry['atom_id']
            role = entry['role']
            a = all_atoms.get(aid, {})
            num = aid.split(':')[-1]
            L.append(f"    {num} [{a.get('atom_type','?')}] role={role}")
            L.append(wrap(a.get('text','???'), indent=8))

        if post_ctx:
            L.append("")
            L.append(f"  Context -- other ({len(post_ctx)}):")
            for ca in post_ctx:
                a = all_atoms.get(ca['atom_id'], {})
                num = ca['atom_id'].split(':')[-1]
                L.append(f"    {num} [{a.get('atom_type','?')}] role={ca['role']}")
                L.append(wrap(a.get('text','???'), indent=8))

        if e.get('relations'):
            L.append("")
            L.append(f"  Relations ({len(e['relations'])}):")
            for rel in e['relations']:
                L.append(f"    {rel['type']} -> {rel.get('target_excerpt_id','unresolved')}")

        L.append("")
        L.append(f"  Boundary reasoning:")
        L.append(wrap(e['boundary_reasoning'], indent=4))
        L.append("")

    # ══════════════════════════════════════════════════════════════════
    section("EXCLUSION RECORDS")
    by_reason = {}
    for ex in exclusions:
        by_reason.setdefault(ex['exclusion_reason'], []).append(ex)
    for reason, excs in by_reason.items():
        L.append(f"  {reason} ({len(excs)} atoms):")
        for ex in excs:
            a = all_atoms.get(ex['atom_id'], {})
            num = ex['atom_id'].split(':')[-1]
            layer = a.get('source_layer', '?')
            txt = a.get('text', '???')
            if len(txt) > 70: txt = txt[:67] + '...'
            L.append(f"    {num} [{layer}] {txt}")
        L.append("")

    # ══════════════════════════════════════════════════════════════════
    section("RELATION GRAPH")
    for e in excerpts:
        for rel in e.get('relations', []):
            L.append(f"  {e['excerpt_id']} --[{rel['type']}]--> {rel.get('target_excerpt_id','???')}")

    # ── Write ──────────────────────────────────────────────────────────
    report = '\n'.join(L)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Report written: {args.output}")
    print(f"  {len(L)} lines, {len(report)} characters")


if __name__ == "__main__":
    main()

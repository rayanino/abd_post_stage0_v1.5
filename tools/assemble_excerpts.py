#!/usr/bin/env python3
"""
Stage 7: Self-Contained Excerpt Assembly + Folder Distribution

Takes extraction output (atoms, excerpts, footnote_excerpts) and produces
self-contained excerpt JSON files placed in the taxonomy folder tree.

Each output file contains everything the synthesis LLM needs:
- Full Arabic text (core + context atoms concatenated)
- Author identity and scholarly context
- Book title and source page references
- Taxonomy path and topic context
- Inlined footnote text
- Content type metadata

Usage:
    python tools/assemble_excerpts.py \\
        --extraction-dir output/imlaa_extraction \\
        --intake-metadata books/imla/intake_metadata.json \\
        --taxonomy taxonomy/imlaa_v0.1.yaml \\
        --science imlaa \\
        --output-dir output/imlaa_assembled \\
        --dry-run
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # Fall back to manual parsing if PyYAML not available


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "assembled_excerpt_v0.1"
TOOL_VERSION = "0.1"
# Known sciences (informational, not enforced — the engine is science-agnostic).
# New sciences can be added without code changes; pass any science name via --science.
KNOWN_SCIENCES = {"imlaa", "sarf", "nahw", "balagha", "aqidah"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalize_node_id(node_id: str, taxonomy_map: dict) -> tuple[str, "TaxonomyNodeInfo | None", bool]:
    """Normalize a taxonomy node_id, handling full-path formats (BUG-043).

    LLMs sometimes return full paths like "aqidah.al_iman.al_istiwa" instead
    of just the leaf "al_istiwa".  This helper tries direct lookup first, then
    strips known separators (".", ":", "/") to extract the last segment.

    Returns (resolved_node_id, node_info_or_None, was_normalized).
    """
    node_info = taxonomy_map.get(node_id)
    if node_info is not None:
        return node_id, node_info, False

    if not node_id or node_id == "_unmapped":
        return node_id, None, False

    for sep in (".", ":", "/"):
        if sep in node_id:
            last_segment = node_id.rsplit(sep, 1)[-1]
            if last_segment in taxonomy_map:
                return last_segment, taxonomy_map[last_segment], True
    return node_id, None, False


# ---------------------------------------------------------------------------
# Taxonomy parser
# ---------------------------------------------------------------------------

@dataclass
class TaxonomyNodeInfo:
    """Metadata for a single taxonomy node."""
    node_id: str
    title: str
    path_ids: list[str]      # e.g. ["imlaa", "alhamza", "hamza_wasat_alkalima"]
    path_titles: list[str]   # e.g. ["علم الإملاء", "الهمزة", "الهمزة المتوسطة"]
    is_leaf: bool
    folder_path: str         # e.g. "imlaa/alhamza/hamza_wasat_alkalima"


def parse_taxonomy_yaml(yaml_path: str, science: str) -> dict[str, TaxonomyNodeInfo]:
    """Parse a taxonomy YAML file (v0 or v1) into a node_id -> TaxonomyNodeInfo map.

    Auto-detects format: v1 has a top-level ``taxonomy`` key with ``nodes``
    array; v0 is a flat nested dict with ``_leaf: true`` markers.

    Returns a dict mapping every node_id (branches + leaves) to its info.
    """
    with open(yaml_path, encoding="utf-8") as f:
        raw = f.read()

    if yaml is not None:
        data = yaml.safe_load(raw)
    else:
        # Minimal fallback: try json-like parse (shouldn't happen in practice)
        raise ImportError("PyYAML is required for taxonomy parsing")

    if data is None:
        return {}

    # Detect format
    if isinstance(data, dict) and "taxonomy" in data:
        taxonomy_block = data["taxonomy"]
        if isinstance(taxonomy_block, dict) and "nodes" in taxonomy_block:
            return _parse_v1(taxonomy_block, science)

    # v0 format: top-level key is the science name (or similar)
    return _parse_v0(data, science)


def _parse_v1(taxonomy_block: dict, science: str) -> dict[str, TaxonomyNodeInfo]:
    """Parse v1 taxonomy format (structured with nodes/children arrays)."""
    result: dict[str, TaxonomyNodeInfo] = {}
    root_title = taxonomy_block.get("title", science)
    nodes = taxonomy_block.get("nodes", [])

    def _walk(node_list: list[dict], parent_ids: list[str], parent_titles: list[str]):
        for node in node_list:
            nid = node.get("id", "")
            title = node.get("title", nid)
            is_leaf = node.get("leaf", False) is True
            has_children = "children" in node and node["children"]

            path_ids = parent_ids + [nid]
            path_titles = parent_titles + [title]
            folder_path = "/".join(path_ids)

            if nid in result:
                print(f"  WARNING: duplicate taxonomy node_id '{nid}' — "
                      f"previous at {result[nid].folder_path}, "
                      f"overwriting with {folder_path}",
                      file=sys.stderr)
            result[nid] = TaxonomyNodeInfo(
                node_id=nid,
                title=title,
                path_ids=list(path_ids),
                path_titles=list(path_titles),
                is_leaf=is_leaf,
                folder_path=folder_path,
            )

            if has_children:
                _walk(node["children"], path_ids, path_titles)

    _walk(nodes, [science], [root_title])
    return result


def _parse_v0(data: dict, science: str) -> dict[str, TaxonomyNodeInfo]:
    """Parse v0 taxonomy format (nested dicts with _leaf: true markers)."""
    result: dict[str, TaxonomyNodeInfo] = {}

    # Find the root key — typically the science name
    root_key = None
    for k in data:
        if not k.startswith("_") and k != "id_policy":
            root_key = k
            break

    if root_key is None:
        return result

    root_data = data[root_key]
    root_title = root_data.get("_label", science) if isinstance(root_data, dict) else science

    def _walk(node_dict: dict, parent_ids: list[str], parent_titles: list[str]):
        if not isinstance(node_dict, dict):
            return
        for key, value in node_dict.items():
            if key.startswith("_"):
                continue
            if key == "id_policy":
                continue

            is_leaf = False
            has_children = False

            if isinstance(value, dict):
                is_leaf = value.get("_leaf", False) is True
                has_children = any(k for k in value if not k.startswith("_"))

            # v0 stores Arabic titles in _label; fall back to node_id
            title = value.get("_label", key) if isinstance(value, dict) else key

            path_ids = parent_ids + [key]
            path_titles = parent_titles + [title]
            folder_path = "/".join(path_ids)

            if key in result:
                print(f"  WARNING: duplicate taxonomy node_id '{key}' — "
                      f"previous at {result[key].folder_path}, "
                      f"overwriting with {folder_path}",
                      file=sys.stderr)
            result[key] = TaxonomyNodeInfo(
                node_id=key,
                title=title,
                path_ids=list(path_ids),
                path_titles=list(path_titles),
                is_leaf=is_leaf,
                folder_path=folder_path,
            )

            if has_children:
                _walk(value, path_ids, path_titles)

    _walk(root_data, [science], [root_title])
    return result


def detect_taxonomy_format(yaml_path: str) -> str:
    """Return 'v0' or 'v1' based on the taxonomy YAML structure."""
    with open(yaml_path, encoding="utf-8") as f:
        raw = f.read()
    if yaml is not None:
        data = yaml.safe_load(raw)
    else:
        raise ImportError("PyYAML is required")
    if isinstance(data, dict) and "taxonomy" in data:
        tb = data["taxonomy"]
        if isinstance(tb, dict) and "nodes" in tb:
            return "v1"
    return "v0"


# ---------------------------------------------------------------------------
# Extraction data loading
# ---------------------------------------------------------------------------

def load_extraction_files(
    extraction_dir: str,
    passage_ids: list[str] | None = None,
) -> list[dict]:
    """Load all *_extraction.json files from a directory.

    Returns a list of dicts, each with keys:
    - passage_id: str (derived from filename, e.g. "P004")
    - filename: str
    - atoms: list
    - excerpts: list
    - footnote_excerpts: list
    """
    dirpath = Path(extraction_dir)
    results = []

    for fpath in sorted(dirpath.glob("*_extraction.json")):
        # Derive passage_id from filename: P004_extraction.json -> P004
        pid = fpath.stem.replace("_extraction", "")
        if passage_ids and pid not in passage_ids:
            continue

        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARNING: skipping corrupted extraction file {fpath.name}: {e}",
                  file=sys.stderr)
            continue

        results.append({
            "passage_id": pid,
            "filename": fpath.name,
            "atoms": data.get("atoms", []),
            "excerpts": data.get("excerpts", []),
            "footnote_excerpts": data.get("footnote_excerpts", []),
        })

    return results


def load_intake_metadata(path: str) -> dict:
    """Load intake_metadata.json for a book."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise RuntimeError(
            f"Failed to load intake metadata from {path}: {e}"
        ) from e


# ---------------------------------------------------------------------------
# Atom resolution helpers
# ---------------------------------------------------------------------------

def _extract_atom_id(entry) -> str:
    """Extract atom_id from either a string or a dict with 'atom_id' key."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("atom_id", "")
    return ""


def _extract_atom_role(entry) -> str:
    """Extract role from an atom reference entry."""
    if isinstance(entry, dict):
        return entry.get("role", "")
    return ""


def build_atoms_index(atoms: list[dict]) -> dict[str, dict]:
    """Build a mapping from atom_id to atom dict."""
    index = {}
    for atom in atoms:
        aid = atom.get("atom_id", "")
        if aid:
            index[aid] = atom
    return index


def resolve_atom_texts(
    atom_refs: list,
    atoms_index: dict[str, dict],
) -> tuple[str, list[dict], list[str]]:
    """Resolve atom references to concatenated text.

    Returns:
        (concatenated_text, resolved_atoms_with_text, missing_ids)
    """
    texts = []
    resolved = []
    missing = []

    for ref in atom_refs:
        aid = _extract_atom_id(ref)
        role = _extract_atom_role(ref)
        atom = atoms_index.get(aid)

        if atom is None:
            missing.append(aid)
            continue

        text = atom.get("text", "")
        texts.append(text)
        resolved.append({
            "atom_id": aid,
            "role": role or atom.get("role", ""),
            "text": text,
        })

    return "\n\n".join(texts), resolved, missing


# ---------------------------------------------------------------------------
# Excerpt assembly
# ---------------------------------------------------------------------------

def assemble_matn_excerpt(
    excerpt: dict,
    atoms_index: dict[str, dict],
    footnote_excerpts: list[dict],
    book_meta: dict,
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    science: str,
    passage_id: str,
    extraction_filename: str,
) -> tuple[dict | None, list[str]]:
    """Assemble a self-contained matn excerpt.

    Returns (assembled_dict, errors). If errors are fatal, assembled_dict is None.
    """
    errors = []
    excerpt_id = excerpt.get("excerpt_id", "")

    # Resolve core atoms
    core_refs = excerpt.get("core_atoms", [])
    core_text, core_resolved, core_missing = resolve_atom_texts(core_refs, atoms_index)
    if core_missing:
        errors.append(f"{excerpt_id}: missing core atoms: {core_missing}")
    if not core_text.strip() and not core_missing:
        errors.append(f"{excerpt_id}: empty core_text after atom resolution")

    # If all core atoms are missing, skip this excerpt
    if not core_text.strip():
        return None, errors

    # Resolve context atoms
    ctx_refs = excerpt.get("context_atoms", [])
    ctx_text, ctx_resolved, ctx_missing = resolve_atom_texts(ctx_refs, atoms_index)
    if ctx_missing:
        errors.append(f"{excerpt_id}: missing context atoms: {ctx_missing}")

    # Build full_text: context first (framing), then core
    if ctx_text.strip():
        full_text = ctx_text + "\n\n" + core_text
    else:
        full_text = core_text

    # Find linked footnotes
    linked_footnotes = []
    for fn in footnote_excerpts:
        if fn.get("linked_matn_excerpt") == excerpt_id:
            linked_footnotes.append({
                "excerpt_id": fn.get("excerpt_id", ""),
                "text": fn.get("text", ""),
                "note": fn.get("note", ""),
                "taxonomy_node_id": fn.get("taxonomy_node_id", ""),
            })

    # Look up taxonomy node title — normalize full paths to leaf IDs (BUG-043)
    raw_node_id = excerpt.get("taxonomy_node_id", "")
    node_id, node_info, node_id_was_normalized = normalize_node_id(raw_node_id, taxonomy_map)
    node_title = node_info.title if node_info else ""

    # Extract source atom IDs for provenance
    core_atom_ids = [_extract_atom_id(r) for r in core_refs]
    ctx_atom_ids = [_extract_atom_id(r) for r in ctx_refs]

    assembled = {
        "schema_version": SCHEMA_VERSION,

        # Identity
        "excerpt_id": excerpt_id,
        "book_id": book_meta.get("book_id", ""),
        "book_title": book_meta.get("title", ""),
        "author": book_meta.get("author", ""),
        "publisher": book_meta.get("publisher", ""),
        "scholarly_context": book_meta.get("scholarly_context", {}),
        "science": science,

        # Taxonomy
        "taxonomy_node_id": node_id,
        "taxonomy_path": (
            " > ".join(node_info.path_titles)
            if node_info and node_info.path_titles
            else excerpt.get("taxonomy_path", "")
        ),
        "taxonomy_node_title": node_title,
        "taxonomy_version": excerpt.get("taxonomy_version", ""),

        # Source structure
        "heading_path": excerpt.get("heading_path", []),

        # Excerpt metadata
        "excerpt_title": excerpt.get("excerpt_title", ""),
        "excerpt_kind": excerpt.get("excerpt_kind", ""),
        "source_layer": excerpt.get("source_layer", "matn"),
        "content_type": excerpt.get("content_type", "prose"),

        # Text — the core self-contained content
        "core_text": core_text,
        "context_text": ctx_text if ctx_text.strip() else "",
        "full_text": full_text,

        # Resolved atoms with text
        "core_atoms": core_resolved,
        "context_atoms": ctx_resolved,

        # Footnotes
        "footnotes": linked_footnotes,

        # Analysis metadata
        "boundary_reasoning": excerpt.get("boundary_reasoning", ""),
        "case_types": excerpt.get("case_types", []),
        "relations": excerpt.get("relations", []),

        # Provenance
        "provenance": {
            "extraction_passage_id": passage_id,
            "extraction_file": extraction_filename,
            "source_atoms": {
                "core": core_atom_ids,
                "context": ctx_atom_ids,
            },
            "assembled_utc": datetime.now(timezone.utc).isoformat(),
            "assembly_tool_version": TOOL_VERSION,
        },
    }

    return assembled, errors


def assemble_footnote_excerpt(
    fn_excerpt: dict,
    book_meta: dict,
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    science: str,
    passage_id: str,
    extraction_filename: str,
) -> dict:
    """Assemble a self-contained footnote excerpt (already has inline text)."""
    raw_node_id = fn_excerpt.get("taxonomy_node_id", "")
    node_id, node_info, node_id_was_normalized = normalize_node_id(raw_node_id, taxonomy_map)
    node_title = node_info.title if node_info else ""
    fn_text = fn_excerpt.get("text", "")

    return {
        "schema_version": SCHEMA_VERSION,

        # Identity
        "excerpt_id": fn_excerpt.get("excerpt_id", ""),
        "book_id": book_meta.get("book_id", ""),
        "book_title": book_meta.get("title", ""),
        "author": book_meta.get("author", ""),
        "publisher": book_meta.get("publisher", ""),
        "scholarly_context": book_meta.get("scholarly_context", {}),
        "science": science,

        # Taxonomy
        "taxonomy_node_id": node_id,
        "taxonomy_path": (
            " > ".join(node_info.path_titles)
            if node_info and node_info.path_titles
            else fn_excerpt.get("taxonomy_path", "")
        ),
        "taxonomy_node_title": node_title,
        "taxonomy_version": fn_excerpt.get("taxonomy_version", ""),

        # Source structure
        "heading_path": fn_excerpt.get("heading_path", []),

        # Excerpt metadata
        "excerpt_title": fn_excerpt.get("excerpt_title", ""),
        "excerpt_kind": fn_excerpt.get("excerpt_kind", ""),
        "source_layer": "footnote",
        "content_type": fn_excerpt.get("content_type", "prose"),

        # Text
        "core_text": fn_text,
        "context_text": "",
        "full_text": fn_text,

        # No atom resolution for footnotes
        "core_atoms": [],
        "context_atoms": [],

        # Linked matn excerpt
        "footnotes": [],
        "linked_matn_excerpt": fn_excerpt.get("linked_matn_excerpt", ""),

        # Analysis metadata
        "boundary_reasoning": fn_excerpt.get("boundary_reasoning", ""),
        "note": fn_excerpt.get("note", ""),
        "case_types": fn_excerpt.get("case_types", []),
        "relations": fn_excerpt.get("relations", []),

        # Provenance
        "provenance": {
            "extraction_passage_id": passage_id,
            "extraction_file": extraction_filename,
            "source_atoms": {"core": [], "context": []},
            "assembled_utc": datetime.now(timezone.utc).isoformat(),
            "assembly_tool_version": TOOL_VERSION,
        },
    }


# ---------------------------------------------------------------------------
# Filename derivation
# ---------------------------------------------------------------------------

def derive_filename(excerpt_id: str) -> str:
    """Derive output filename from an excerpt_id.

    qimlaa:exc:000001      -> qimlaa_exc_000001.json
    qimlaa:exc:fn:000001   -> qimlaa_exc_fn_000001.json
    """
    # Replace colons with underscores
    base = excerpt_id.replace(":", "_")
    return f"{base}.json"


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------

def distribute_excerpts(
    assembled_excerpts: list[dict],
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    output_dir: str,
    science: str,
    full_tree: bool = False,
    dry_run: bool = False,
) -> dict:
    """Write assembled excerpts to the taxonomy folder tree.

    Returns a summary dict with counts and warnings.
    """
    outpath = Path(output_dir)
    warnings = []
    files_written = 0
    nodes_populated: dict[str, list[str]] = {}  # node_id -> [excerpt_ids]

    # Optionally create full tree structure
    if full_tree and not dry_run:
        for node_id, info in taxonomy_map.items():
            if info.is_leaf:
                folder = outpath / info.folder_path
                folder.mkdir(parents=True, exist_ok=True)

    for exc in assembled_excerpts:
        node_id = exc.get("taxonomy_node_id", "")
        excerpt_id = exc.get("excerpt_id", "")
        book_id = exc.get("book_id", "")

        # Determine folder path — normalize full paths to leaf IDs (BUG-043)
        resolved_id, node_info, was_norm = normalize_node_id(node_id, taxonomy_map)
        if was_norm:
            # Copy before mutation to avoid modifying caller's data
            exc = dict(exc)
            exc["taxonomy_node_id"] = resolved_id
            node_id = resolved_id
            if node_info and node_info.path_titles:
                exc["taxonomy_path"] = " > ".join(node_info.path_titles)
        if node_info is not None:
            folder_path = node_info.folder_path
        elif node_id == "_unmapped" or not node_id:
            folder_path = f"{science}/_unmapped"
            warnings.append(f"{excerpt_id}: unmapped taxonomy_node_id '{node_id}'")
        else:
            folder_path = f"{science}/_unmapped"
            warnings.append(
                f"{excerpt_id}: taxonomy_node_id '{node_id}' not found in taxonomy; "
                f"placed in _unmapped/"
            )

        # Track per-node populations
        nodes_populated.setdefault(node_id, []).append(excerpt_id)

        # Derive filename and full path
        filename = derive_filename(excerpt_id)
        full_path = outpath / folder_path / filename

        if dry_run:
            print(f"  [dry-run] {full_path}")
            files_written += 1
            continue

        # Create directory and write file
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(exc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        files_written += 1

    # Check for same-book duplicates at same node
    same_book_dupes = []
    for nid, exc_ids in nodes_populated.items():
        if len(exc_ids) > 1 and nid not in ("_unmapped", ""):
            same_book_dupes.append({
                "node_id": nid,
                "count": len(exc_ids),
                "excerpt_ids": exc_ids,
            })

    return {
        "files_written": files_written,
        "unique_nodes_populated": len(nodes_populated),
        "warnings": warnings,
        "same_book_at_same_node": same_book_dupes,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_assembled_excerpt(exc: dict) -> list[str]:
    """Validate a single assembled excerpt. Returns list of issues."""
    issues = []
    eid = exc.get("excerpt_id", "?")

    if not exc.get("excerpt_id"):
        issues.append("missing excerpt_id")
    if not exc.get("core_text", "").strip():
        issues.append(f"{eid}: empty core_text")
    if not exc.get("book_title"):
        issues.append(f"{eid}: missing book_title")
    if not exc.get("taxonomy_node_id"):
        issues.append(f"{eid}: missing taxonomy_node_id")
    if not exc.get("taxonomy_path"):
        issues.append(f"{eid}: missing taxonomy_path")

    # Self-containment: scholarly_context should have at least some data
    sc = exc.get("scholarly_context")
    if sc is None or not isinstance(sc, dict):
        issues.append(f"{eid}: missing scholarly_context (synthesis LLM needs author attribution)")
    elif not any(sc.get(k) for k in ("author_death_hijri", "fiqh_madhab",
                                       "grammatical_school", "geographic_origin")):
        issues.append(f"{eid}: scholarly_context has no populated fields "
                      "(synthesis LLM cannot attribute author perspective)")

    return issues


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_summary(
    book_meta: dict,
    science: str,
    taxonomy_version: str,
    extraction_dir: str,
    output_dir: str,
    matn_count: int,
    fn_count: int,
    dist_result: dict,
    all_errors: list[str],
) -> dict:
    """Generate assembly_summary.json content."""
    return {
        "book_id": book_meta.get("book_id", ""),
        "book_title": book_meta.get("title", ""),
        "science": science,
        "taxonomy_version": taxonomy_version,
        "assembled_utc": datetime.now(timezone.utc).isoformat(),
        "extraction_dir": extraction_dir,
        "output_dir": output_dir,
        "total_matn_excerpts_assembled": matn_count,
        "total_footnote_excerpts_assembled": fn_count,
        "total_files_written": dist_result.get("files_written", 0),
        "unique_nodes_populated": dist_result.get("unique_nodes_populated", 0),
        "same_book_at_same_node": dist_result.get("same_book_at_same_node", []),
        "errors": all_errors,
        "warnings": dist_result.get("warnings", []),
    }


def generate_report_md(
    summary: dict,
    assembled_excerpts: list[dict],
    taxonomy_map: dict[str, TaxonomyNodeInfo],
) -> str:
    """Generate a human-readable assembly report."""
    lines = []
    lines.append(f"# Assembly Report — {summary['book_title']}")
    lines.append("")
    lines.append(f"- **Book:** {summary['book_title']} ({summary['book_id']})")
    lines.append(f"- **Science:** {summary['science']}")
    lines.append(f"- **Taxonomy:** {summary['taxonomy_version']}")
    lines.append(f"- **Assembled:** {summary['assembled_utc']}")
    lines.append(f"- **Matn excerpts:** {summary['total_matn_excerpts_assembled']}")
    lines.append(f"- **Footnote excerpts:** {summary['total_footnote_excerpts_assembled']}")
    lines.append(f"- **Files written:** {summary['total_files_written']}")
    lines.append(f"- **Nodes populated:** {summary['unique_nodes_populated']}")
    lines.append("")

    # Errors
    if summary["errors"]:
        lines.append("## Errors")
        lines.append("")
        for err in summary["errors"]:
            lines.append(f"- {err}")
        lines.append("")

    # Warnings
    if summary["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for warn in summary["warnings"]:
            lines.append(f"- {warn}")
        lines.append("")

    # Same-book duplicates
    dupes = summary.get("same_book_at_same_node", [])
    if dupes:
        lines.append("## Same-Book Duplicates at Same Node")
        lines.append("")
        lines.append("These nodes received multiple excerpts from the same book.")
        lines.append("This is a quality signal — consider merging or evolving the node.")
        lines.append("")
        for d in dupes:
            lines.append(f"- **{d['node_id']}**: {d['count']} excerpts")
            for eid in d["excerpt_ids"]:
                lines.append(f"  - `{eid}`")
        lines.append("")

    # Per-node breakdown
    lines.append("## Excerpts by Taxonomy Node")
    lines.append("")

    # Group excerpts by node
    by_node: dict[str, list[dict]] = {}
    for exc in assembled_excerpts:
        nid = exc.get("taxonomy_node_id", "_unmapped")
        by_node.setdefault(nid, []).append(exc)

    for nid in sorted(by_node.keys()):
        exclist = by_node[nid]
        node_info = taxonomy_map.get(nid)
        node_title = node_info.title if node_info else nid
        lines.append(f"### `{nid}` — {node_title}")
        lines.append("")
        if node_info:
            lines.append(f"Path: {' > '.join(node_info.path_titles)}")
            lines.append("")
        for exc in exclist:
            layer = exc.get("source_layer", "matn")
            lines.append(
                f"- [{layer}] **{exc.get('excerpt_title', '?')}** "
                f"(`{exc.get('excerpt_id', '?')}`)"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_assembly(args) -> int:
    """Execute the assembly pipeline. Returns exit code (0=success, 1=errors)."""
    # Validate science (informational warning, not a hard block)
    if args.science not in KNOWN_SCIENCES:
        print(f"  NOTE: --science '{args.science}' is not in the known set "
              f"{KNOWN_SCIENCES}. Proceeding anyway (engine is science-agnostic).",
              file=sys.stderr)

    # Load taxonomy
    print(f"Loading taxonomy: {args.taxonomy}")
    taxonomy_map = parse_taxonomy_yaml(args.taxonomy, args.science)
    leaf_count = sum(1 for n in taxonomy_map.values() if n.is_leaf)
    fmt = detect_taxonomy_format(args.taxonomy)
    print(f"  Format: {fmt}, {len(taxonomy_map)} nodes, {leaf_count} leaves")

    # Derive taxonomy version from filename
    tax_filename = Path(args.taxonomy).stem
    tax_version = tax_filename.replace(".", "_")

    # Load intake metadata
    print(f"Loading intake metadata: {args.intake_metadata}")
    book_meta = load_intake_metadata(args.intake_metadata)
    print(f"  Book: {book_meta.get('title', '?')} ({book_meta.get('book_id', '?')})")

    # Load extraction files
    passage_filter = None
    if args.passage_ids:
        passage_filter = [p.strip() for p in args.passage_ids.split(",")]

    print(f"Loading extraction files from: {args.extraction_dir}")
    extraction_data = load_extraction_files(args.extraction_dir, passage_filter)
    if not extraction_data:
        print("  No extraction files found!")
        return 1
    print(f"  Found {len(extraction_data)} passage(s): "
          f"{', '.join(e['passage_id'] for e in extraction_data)}")

    # Assemble all excerpts
    all_assembled = []
    all_errors = []
    total_matn = 0
    total_fn = 0

    for passage in extraction_data:
        pid = passage["passage_id"]
        fname = passage["filename"]
        atoms_index = build_atoms_index(passage["atoms"])

        print(f"\nAssembling {pid} ({len(passage['excerpts'])} excerpts, "
              f"{len(passage['footnote_excerpts'])} footnote excerpts)...")

        # Assemble matn excerpts
        for exc in passage["excerpts"]:
            assembled, errs = assemble_matn_excerpt(
                excerpt=exc,
                atoms_index=atoms_index,
                footnote_excerpts=passage["footnote_excerpts"],
                book_meta=book_meta,
                taxonomy_map=taxonomy_map,
                science=args.science,
                passage_id=pid,
                extraction_filename=fname,
            )
            all_errors.extend(errs)
            if assembled is not None:
                # Validate
                issues = validate_assembled_excerpt(assembled)
                all_errors.extend(issues)
                all_assembled.append(assembled)
                total_matn += 1

        # Assemble footnote excerpts as independent files
        for fn_exc in passage["footnote_excerpts"]:
            assembled = assemble_footnote_excerpt(
                fn_excerpt=fn_exc,
                book_meta=book_meta,
                taxonomy_map=taxonomy_map,
                science=args.science,
                passage_id=pid,
                extraction_filename=fname,
            )
            issues = validate_assembled_excerpt(assembled)
            all_errors.extend(issues)
            all_assembled.append(assembled)
            total_fn += 1

    print(f"\nAssembled {total_matn} matn + {total_fn} footnote = "
          f"{len(all_assembled)} total excerpts")

    if all_errors:
        print(f"\n{'='*60}")
        print(f"ERRORS ({len(all_errors)}):")
        for err in all_errors:
            print(f"  - {err}")
        print(f"{'='*60}")

    # Distribute to folder tree
    print(f"\nDistributing to folder tree: {args.output_dir}")
    if args.dry_run:
        print("  [DRY RUN — no files will be written]\n")

    dist_result = distribute_excerpts(
        assembled_excerpts=all_assembled,
        taxonomy_map=taxonomy_map,
        output_dir=args.output_dir,
        science=args.science,
        full_tree=args.full_tree,
        dry_run=args.dry_run,
    )

    print(f"\n  Files: {dist_result['files_written']}")
    print(f"  Nodes populated: {dist_result['unique_nodes_populated']}")

    if dist_result["warnings"]:
        print(f"\n  Warnings ({len(dist_result['warnings'])}):")
        for w in dist_result["warnings"]:
            print(f"    - {w}")

    # Generate summary and report
    summary = generate_summary(
        book_meta=book_meta,
        science=args.science,
        taxonomy_version=tax_version,
        extraction_dir=args.extraction_dir,
        output_dir=args.output_dir,
        matn_count=total_matn,
        fn_count=total_fn,
        dist_result=dist_result,
        all_errors=all_errors,
    )

    report_md = generate_report_md(summary, all_assembled, taxonomy_map)

    # Write summary and report
    outdir = Path(args.output_dir)
    if not args.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)

        summary_path = outdir / "assembly_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"\n  Summary: {summary_path}")

        report_path = outdir / "assembly_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"  Report:  {report_path}")
    else:
        print("\n  [dry-run] Would write assembly_summary.json")
        print("  [dry-run] Would write assembly_report.md")

    print("\nDone.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Assemble self-contained excerpt files and place in taxonomy folder tree"
    )
    parser.add_argument(
        "--extraction-dir", required=True,
        help="Directory containing *_extraction.json files from extraction stage"
    )
    parser.add_argument(
        "--intake-metadata", required=True,
        help="Path to intake_metadata.json for this book"
    )
    parser.add_argument(
        "--taxonomy", required=True,
        help="Path to taxonomy YAML (v0 or v1 format)"
    )
    parser.add_argument(
        "--science", required=True,
        help="Science name (e.g., imlaa, sarf, nahw, balagha, fiqh, hadith)"
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Root output directory (taxonomy tree created inside)"
    )
    parser.add_argument(
        "--full-tree", action="store_true",
        help="Create all leaf folders from taxonomy, not just populated ones"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be created without writing any files"
    )
    parser.add_argument(
        "--passage-ids", default=None,
        help="Comma-separated passage IDs to assemble (default: all)"
    )

    args = parser.parse_args()
    sys.exit(run_assembly(args))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Stage 6: Taxonomy Evolution Engine (Phase A + B)
=================================================
Phase A: Signal detection + LLM proposal generation + review artifacts.
Phase B: Apply approved proposals, version control, excerpt redistribution,
         rollback capability.

Usage:
    # Detect + Propose
    python tools/evolve_taxonomy.py \\
        --extraction-dir output/imlaa_extraction \\
        --taxonomy taxonomy/imlaa/imlaa_v1_0.yaml \\
        --science imlaa \\
        --output-dir output/imlaa_evolution \\
        --model claude-sonnet-4-5-20250929 \\
        [--assembly-dir output/imlaa_assembled] \\
        [--book-id qimlaa] \\
        [--node-ids node1,node2] \\
        [--dry-run]

    # Apply approved changes (Phase B stub)
    python tools/evolve_taxonomy.py \\
        --apply output/imlaa_evolution/evolution_proposal.json \\
        --taxonomy taxonomy/imlaa/imlaa_v1_0.yaml \\
        --output-dir output/imlaa_evolved
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tools.assemble_excerpts import (
    TaxonomyNodeInfo,
    build_atoms_index,
    load_extraction_files,
    parse_taxonomy_yaml,
    resolve_atom_texts,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NODE_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
_MAX_NODE_ID_LENGTH = 60

VALID_CHANGE_TYPES = {"node_added", "leaf_granulated", "node_renamed", "node_moved"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvolutionSignal:
    """A detected signal that a taxonomy node may need to evolve."""
    signal_type: str        # "unmapped" | "same_book_cluster" | "category_leaf"
                            # | "multi_topic_excerpt" | "user_specified"
    node_id: str            # affected taxonomy node (or "_unmapped")
    science: str
    excerpt_ids: list[str]
    excerpt_texts: list[str]       # resolved Arabic text per excerpt
    excerpt_metadata: list[dict]   # excerpt dicts (title, taxonomy_path, etc.)
    context: str                   # human-readable description


@dataclass
class EvolutionProposal:
    """An LLM-proposed taxonomy change."""
    signal: EvolutionSignal
    proposal_id: str             # "EP-001", "EP-002", ...
    change_type: str             # "node_added" | "leaf_granulated" | ...
    parent_node_id: str
    new_nodes: list[dict]        # [{node_id, title_ar, leaf: True}, ...]
    redistribution: dict         # {excerpt_id: new_node_id}
    reasoning: str
    confidence: str              # "certain" | "likely" | "uncertain"
    model: str
    cost: dict                   # {input_tokens, output_tokens, total_cost}


# ---------------------------------------------------------------------------
# Excerpt text resolution
# ---------------------------------------------------------------------------

def resolve_excerpt_full_text(
    excerpt: dict,
    atoms_index: dict[str, dict],
) -> str:
    """Resolve an excerpt's full Arabic text from atom references.

    Returns context_text + core_text (or just core_text if no context).
    """
    core_refs = excerpt.get("core_atoms", [])
    core_text, _, _ = resolve_atom_texts(core_refs, atoms_index)

    ctx_refs = excerpt.get("context_atoms", [])
    ctx_text, _, _ = resolve_atom_texts(ctx_refs, atoms_index)

    if ctx_text.strip():
        return ctx_text + "\n\n" + core_text
    return core_text


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

def scan_unmapped_signals(
    extraction_data: list[dict],
    atoms_indexes: dict[str, dict[str, dict]],
    science: str,
) -> list[EvolutionSignal]:
    """Scan extraction output for unmapped excerpts.

    Returns one signal per unmapped excerpt (they may be about different topics).
    """
    signals = []

    for passage in extraction_data:
        pid = passage["passage_id"]
        atoms_index = atoms_indexes.get(pid, {})

        for exc in passage.get("excerpts", []):
            node_id = exc.get("taxonomy_node_id", "")
            if node_id == "_unmapped" or not node_id:
                exc_id = exc.get("excerpt_id", "unknown")
                full_text = resolve_excerpt_full_text(exc, atoms_index)
                signals.append(EvolutionSignal(
                    signal_type="unmapped",
                    node_id="_unmapped",
                    science=science,
                    excerpt_ids=[exc_id],
                    excerpt_texts=[full_text],
                    excerpt_metadata=[exc],
                    context=f"Unmapped excerpt {exc_id} from passage {pid}",
                ))

    return signals


def scan_cluster_signals(
    extraction_data: list[dict],
    atoms_indexes: dict[str, dict[str, dict]],
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    science: str,
) -> list[EvolutionSignal]:
    """Scan for same-book clusters: multiple excerpts from the SAME book at
    one leaf node.

    Per CLAUDE.md: "If extraction produces two excerpts from the same book
    at the same node, that's a signal." Multiple excerpts from DIFFERENT
    books at the same node is expected and normal — not a signal.

    Groups excerpts by (book_id, node_id). Flags where a single book has
    2+ excerpts at one node.
    """
    # Group excerpts by (book_id, node_id)
    # key: (book_id, node_id) -> [(exc, pid)]
    book_node_excerpts: dict[tuple[str, str], list[tuple[dict, str]]] = {}

    for passage in extraction_data:
        pid = passage["passage_id"]
        for exc in passage.get("excerpts", []):
            node_id = exc.get("taxonomy_node_id", "")
            # Derive book_id from core_atoms atom_id prefix (book_id is on
            # atoms, not excerpts — exc.get("book_id") would always be "")
            book_id = exc.get("book_id", "")
            if not book_id:
                core_atoms = exc.get("core_atoms", [])
                if core_atoms:
                    first_ref = core_atoms[0]
                    atom_id = first_ref if isinstance(first_ref, str) else first_ref.get("atom_id", "")
                    if ":" in atom_id:
                        book_id = atom_id.split(":")[0]
            if node_id and node_id != "_unmapped":
                key = (book_id, node_id)
                book_node_excerpts.setdefault(key, []).append((exc, pid))

    signals = []
    for (book_id, node_id), excerpts_and_pids in book_node_excerpts.items():
        if len(excerpts_and_pids) < 2:
            continue

        # Resolve texts
        exc_ids = []
        exc_texts = []
        exc_meta = []
        for exc, pid in excerpts_and_pids:
            atoms_index = atoms_indexes.get(pid, {})
            exc_ids.append(exc.get("excerpt_id", "unknown"))
            exc_texts.append(resolve_excerpt_full_text(exc, atoms_index))
            exc_meta.append(exc)

        node_info = taxonomy_map.get(node_id)
        node_title = node_info.title if node_info else node_id

        signals.append(EvolutionSignal(
            signal_type="same_book_cluster",
            node_id=node_id,
            science=science,
            excerpt_ids=exc_ids,
            excerpt_texts=exc_texts,
            excerpt_metadata=exc_meta,
            context=(
                f"{len(exc_ids)} excerpts from book '{book_id}' at node "
                f"'{node_title}' ({node_id})"
            ),
        ))

    return signals


# Arabic keywords that indicate a node name is a CATEGORY (plural/collection),
# not a single topic.  When a leaf node's _label contains one of these, it
# should almost certainly be a branch with sub-leaves.
_CATEGORY_KEYWORDS_AR = [
    "مراتب",    # levels/stages
    "أقسام",    # divisions
    "أنواع",    # types
    "أحكام",    # rulings (collection)
    "شروط",    # conditions (collection)
    "أركان",    # pillars (collection)
    "واجبات",   # obligations (collection)
    "سنن",     # sunnah practices (collection)
    "صفات",    # attributes (collection)
    "مسائل",   # issues (collection)
    "أدلة",    # evidences (collection)
    "مراحل",   # phases (collection)
    "درجات",   # degrees (collection)
    "طبقات",   # classes/layers (collection)
    "فروع",    # branches/sub-topics (collection)
    "أصول",    # principles (collection)
    "نواقض",   # nullifiers (collection)
    "موانع",   # impediments (collection)
    "آداب",    # manners (collection)
]

# Also check node IDs for Latin transliteration patterns
_CATEGORY_KEYWORDS_ID = [
    "maratib",   # مراتب
    "aqsam",     # أقسام
    "anwa3",     # أنواع
    "ahkam",     # أحكام
    "shuroot",   # شروط
    "arkan",     # أركان
    "wajibat",   # واجبات
    "sifat",     # صفات
    "masail",    # مسائل
    "adillah",   # أدلة
    "marahil",   # مراحل
    "darajat",   # درجات
    "tabaqat",   # طبقات
    "furu3",     # فروع
    "usul",      # أصول
    "nawaqid",   # نواقض
    "mawani3",   # موانع
    "adab",      # آداب
]


def scan_category_leaf_signals(
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    science: str,
) -> list[EvolutionSignal]:
    """Scan for leaf nodes whose names suggest they are CATEGORIES, not topics.

    A leaf node named "الصفات الذاتية" (plural/collection) should be a branch
    with sub-leaves for individual attributes, not a leaf endpoint.  This signal
    fires regardless of how many excerpts are placed at the node — the name
    itself is the signal.

    Returns one signal per category-leaf detected.
    """
    signals = []

    for node_id, info in taxonomy_map.items():
        if not info.is_leaf:
            continue

        # Check Arabic label
        label = info.title or ""
        label_match = any(kw in label for kw in _CATEGORY_KEYWORDS_AR)

        # Check node ID (Latin transliteration)
        id_match = any(kw in node_id for kw in _CATEGORY_KEYWORDS_ID)

        if label_match or id_match:
            matched_kw = next(
                (kw for kw in _CATEGORY_KEYWORDS_AR if kw in label),
                next(
                    (kw for kw in _CATEGORY_KEYWORDS_ID if kw in node_id),
                    "?"
                ),
            )
            signals.append(EvolutionSignal(
                signal_type="category_leaf",
                node_id=node_id,
                science=science,
                excerpt_ids=[],
                excerpt_texts=[],
                excerpt_metadata=[],
                context=(
                    f"Leaf node '{label}' ({node_id}) has a category/collection "
                    f"name (matched keyword: '{matched_kw}'). "
                    f"This should likely be a branch with sub-leaves, not a leaf."
                ),
            ))

    return signals


def scan_multi_topic_signals(
    extraction_data: list[dict],
    atoms_indexes: dict[str, dict[str, dict]],
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    science: str,
    min_atoms: int = 4,
) -> list[EvolutionSignal]:
    """Scan for single excerpts that cover multiple distinct sub-topics.

    Heuristic: a single excerpt at a node with many atoms (≥ min_atoms) and
    the node has only ONE excerpt total suggests the excerpt may be covering
    multiple sub-topics that should each have their own leaf.

    This catches cases like a 5-atom excerpt listing 15 hadiths about different
    divine attributes, all dumped into one "الصفات الفعلية" leaf.

    Returns one signal per qualifying excerpt.
    """
    # First, count matn excerpts per node
    node_excerpts: dict[str, list[tuple[dict, str]]] = {}
    for passage in extraction_data:
        pid = passage["passage_id"]
        for exc in passage.get("excerpts", []):
            node_id = exc.get("taxonomy_node_id", "")
            layer = exc.get("source_layer", "matn")
            if node_id and node_id != "_unmapped" and layer != "footnote":
                node_excerpts.setdefault(node_id, []).append((exc, pid))

    signals = []
    for node_id, excerpts_and_pids in node_excerpts.items():
        # Only flag nodes with exactly 1 matn excerpt
        if len(excerpts_and_pids) != 1:
            continue

        exc, pid = excerpts_and_pids[0]
        core_atoms = exc.get("core_atoms", [])

        if len(core_atoms) < min_atoms:
            continue

        # This is a single excerpt with many atoms at a solo node — suspicious
        atoms_index = atoms_indexes.get(pid, {})
        full_text = resolve_excerpt_full_text(exc, atoms_index)
        exc_id = exc.get("excerpt_id", "unknown")
        node_info = taxonomy_map.get(node_id)
        node_title = node_info.title if node_info else node_id

        signals.append(EvolutionSignal(
            signal_type="multi_topic_excerpt",
            node_id=node_id,
            science=science,
            excerpt_ids=[exc_id],
            excerpt_texts=[full_text],
            excerpt_metadata=[exc],
            context=(
                f"Single excerpt '{exc_id}' at leaf '{node_title}' ({node_id}) "
                f"has {len(core_atoms)} atoms. May cover multiple sub-topics "
                f"that warrant separate leaves."
            ),
        ))

    return signals


def scan_user_signals(
    node_ids: list[str],
    extraction_data: list[dict],
    atoms_indexes: dict[str, dict[str, dict]],
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    science: str,
) -> list[EvolutionSignal]:
    """Create signals for user-specified nodes to investigate."""
    signals = []

    for node_id in node_ids:
        # Gather all excerpts placed at this node
        exc_ids = []
        exc_texts = []
        exc_meta = []

        for passage in extraction_data:
            pid = passage["passage_id"]
            atoms_index = atoms_indexes.get(pid, {})
            for exc in passage.get("excerpts", []):
                if exc.get("taxonomy_node_id") == node_id:
                    exc_ids.append(exc.get("excerpt_id", "unknown"))
                    exc_texts.append(resolve_excerpt_full_text(exc, atoms_index))
                    exc_meta.append(exc)

        node_info = taxonomy_map.get(node_id)
        node_title = node_info.title if node_info else node_id

        signals.append(EvolutionSignal(
            signal_type="user_specified",
            node_id=node_id,
            science=science,
            excerpt_ids=exc_ids,
            excerpt_texts=exc_texts,
            excerpt_metadata=exc_meta,
            context=(
                f"User-specified investigation of '{node_title}' ({node_id}), "
                f"{len(exc_ids)} excerpts"
            ),
        ))

    return signals


def deduplicate_signals(signals: list[EvolutionSignal]) -> list[EvolutionSignal]:
    """Merge signals that share the same (signal_type, node_id).

    When two signals target the same node with the same type, merge their
    excerpt lists into a single signal.
    """
    seen: dict[tuple[str, str], EvolutionSignal] = {}

    for sig in signals:
        # Don't merge unmapped signals — each may be about a different topic
        # and needs individual LLM evaluation
        if sig.signal_type == "unmapped":
            seen[(sig.signal_type, sig.node_id, id(sig))] = sig
            continue
        key = (sig.signal_type, sig.node_id)
        if key in seen:
            existing = seen[key]
            # Merge excerpt lists (avoid duplicates)
            for i, eid in enumerate(sig.excerpt_ids):
                if eid not in existing.excerpt_ids:
                    existing.excerpt_ids.append(eid)
                    existing.excerpt_texts.append(sig.excerpt_texts[i])
                    existing.excerpt_metadata.append(sig.excerpt_metadata[i])
            # Update context
            existing.context = (
                f"{len(existing.excerpt_ids)} excerpts at "
                f"node '{existing.node_id}'"
            )
        else:
            seen[key] = sig

    return list(seen.values())


# ---------------------------------------------------------------------------
# Taxonomy context extraction
# ---------------------------------------------------------------------------

def extract_taxonomy_section(
    taxonomy_yaml_raw: str,
    node_ids: list[str],
    context_lines: int = 10,
) -> str:
    """Extract relevant YAML lines around given node IDs.

    Follows the pattern from consensus.py:_extract_taxonomy_context but
    generalized for N node IDs.
    """
    lines = taxonomy_yaml_raw.split("\n")
    targets = set(node_ids)
    matched_indices: set[int] = set()

    for i, line in enumerate(lines):
        stripped = line.split("#")[0].strip()
        # v1 format: ``- id: node_id`` or ``id: node_id``
        if stripped.startswith("- id:") or stripped.startswith("id:"):
            value = stripped.split(":", 1)[1].strip()
            if value in targets:
                matched_indices.add(i)
                continue
        # v0 format: ``node_id:`` as a dict key on its own line
        bare = stripped.rstrip(":")
        if bare in targets and bare != stripped:
            matched_indices.add(i)

    relevant = []
    for idx in sorted(matched_indices):
        start = max(0, idx - context_lines)
        end = min(len(lines), idx + context_lines + 1)
        relevant.extend(lines[start:end])
        relevant.append("---")

    if relevant:
        # Deduplicate overlapping context windows while preserving order
        seen: set[str] = set()
        deduped = []
        for line in relevant:
            key = line.rstrip()
            if key not in seen:
                seen.add(key)
                deduped.append(line)
        return "\n".join(deduped)

    return f"(nodes {', '.join(node_ids)} not found in taxonomy)"


# ---------------------------------------------------------------------------
# Node ID validation
# ---------------------------------------------------------------------------

def validate_proposed_node_id(
    node_id: str,
    taxonomy_map: dict[str, TaxonomyNodeInfo],
) -> list[str]:
    """Validate a proposed node ID. Returns list of error messages (empty = valid)."""
    errors = []

    if not node_id:
        errors.append("Node ID is empty")
        return errors

    if not _NODE_ID_PATTERN.match(node_id):
        errors.append(
            f"Node ID '{node_id}' contains invalid characters "
            f"(must be ASCII lowercase, digits, underscores)"
        )

    if len(node_id) > _MAX_NODE_ID_LENGTH:
        errors.append(
            f"Node ID '{node_id}' is too long "
            f"({len(node_id)} chars, max {_MAX_NODE_ID_LENGTH})"
        )

    if node_id in taxonomy_map:
        errors.append(
            f"Node ID '{node_id}' already exists in taxonomy"
        )

    return errors


# ---------------------------------------------------------------------------
# LLM prompt templates
# ---------------------------------------------------------------------------

EVOLUTION_UNMAPPED_SYSTEM = """\
You are a taxonomy evolution advisor for the Arabic Book Digester (ABD) pipeline.
You are an expert in Arabic linguistics, specifically in the science of {science}.
Your task is to analyze an excerpt that could not be placed in the existing
taxonomy and propose where it belongs.

RULES:
- Node IDs must be ASCII lowercase + digits + underscores only (Franco-Arabic transliteration)
- Node IDs must be 60 characters or fewer
- New leaf nodes must have "leaf": true
- Only propose a new node if no existing leaf genuinely covers the topic
- Respond in valid JSON only (no markdown fences)
"""

EVOLUTION_UNMAPPED_USER = """\
An excerpt was extracted from an Arabic book but could not be placed in the
existing taxonomy tree.

## The Excerpt

Excerpt ID: {excerpt_id}
Title: {excerpt_title}
Boundary reasoning: {boundary_reasoning}

Arabic text:
{excerpt_text}

## Current Taxonomy (relevant section)

{taxonomy_context}

## Full Taxonomy Structure

{full_taxonomy}

## Your Task

1. Read the Arabic text carefully
2. Identify what topic this excerpt teaches
3. Check if an EXISTING leaf node covers this topic (the extraction may have
   missed it)
4. If no existing leaf fits, propose a NEW node

Return JSON:
{{
  "action": "existing_leaf" or "new_node",
  "existing_leaf_id": "node_id_if_existing_leaf_fits_or_null",
  "new_node": {{
    "node_id": "proposed_ascii_id",
    "title_ar": "Arabic title for the new node",
    "parent_node_id": "parent_to_attach_under",
    "leaf": true
  }},
  "reasoning": "detailed explanation referencing the Arabic content",
  "confidence": "certain" or "likely" or "uncertain"
}}

If action is "existing_leaf", set new_node to null.
If action is "new_node", set existing_leaf_id to null.
"""

EVOLUTION_CLUSTER_SYSTEM = """\
You are a taxonomy evolution advisor for the Arabic Book Digester (ABD) pipeline.
You are an expert in Arabic linguistics, specifically in the science of {science}.
Your task is to analyze a taxonomy node that has received multiple excerpts
from the same book and determine if it needs finer granularity.

RULES:
- Node IDs must be ASCII lowercase + digits + underscores only (Franco-Arabic transliteration)
- Node IDs must be 60 characters or fewer
- New leaf nodes must have "leaf": true
- Only propose splitting if the excerpts teach genuinely DIFFERENT subtopics
- If they cover the same topic, recommend merging or keeping as-is
- Respond in valid JSON only (no markdown fences)
"""

EVOLUTION_CLUSTER_USER = """\
A taxonomy leaf node has received multiple excerpts from the same book. This is
a quality signal that the node may need finer granularity (splitting into
sub-nodes).

## Affected Node

Node ID: {node_id}
Node title: {node_title}
Node path: {node_path}

## Excerpts at This Node

{excerpts_block}

## Surrounding Taxonomy Context

{taxonomy_context}

## Your Task

1. Read ALL the Arabic texts above carefully
2. Determine if these excerpts teach DIFFERENT subtopics that warrant separate
   nodes, or if they genuinely cover the SAME topic (and should be merged or kept)
3. If splitting is warranted, propose new sub-nodes with Arabic titles
4. Assign each existing excerpt to its new node

Return JSON:
{{
  "action": "split" or "merge" or "keep",
  "new_nodes": [
    {{"node_id": "proposed_id_1", "title_ar": "Arabic title 1", "leaf": true}},
    {{"node_id": "proposed_id_2", "title_ar": "Arabic title 2", "leaf": true}}
  ],
  "redistribution": {{
    "excerpt_id_1": "proposed_id_1",
    "excerpt_id_2": "proposed_id_2"
  }},
  "reasoning": "detailed explanation referencing the Arabic content",
  "confidence": "certain" or "likely" or "uncertain"
}}

If action is "merge" or "keep", set new_nodes to [] and redistribution to {{}}.
"""


# ---------------------------------------------------------------------------
# LLM proposal generation
# ---------------------------------------------------------------------------

def _parse_llm_json(raw_text: str) -> dict | None:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove opening fence
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _format_excerpts_block(signal: EvolutionSignal) -> str:
    """Format multiple excerpts for the cluster prompt."""
    parts = []
    for i, (eid, text, meta) in enumerate(
        zip(signal.excerpt_ids, signal.excerpt_texts, signal.excerpt_metadata),
        1,
    ):
        title = meta.get("excerpt_title", "")
        parts.append(
            f"### Excerpt {i}: {eid}\n"
            f"Title: {title}\n\n"
            f"Arabic text:\n{text}\n"
        )
    return "\n---\n\n".join(parts)


def propose_evolution_for_signal(
    signal: EvolutionSignal,
    taxonomy_yaml_raw: str,
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    model: str,
    api_key: str,
    openrouter_key: str | None = None,
    openai_key: str | None = None,
    call_llm_fn=None,
    proposal_seq: int = 1,
) -> EvolutionProposal | None:
    """Call LLM to generate an evolution proposal for one signal.

    Returns None if the LLM decides no change is needed or on error.
    ``call_llm_fn`` can be injected for testing (same pattern as consensus.py).
    """
    # Deferred import — allows dry-run without LLM infrastructure
    from tools.extract_passages import get_model_cost

    if call_llm_fn is None:
        from tools.extract_passages import call_llm_dispatch
        actual_call_fn = call_llm_dispatch
    else:
        actual_call_fn = call_llm_fn

    # Build prompt based on signal type
    if signal.signal_type == "unmapped":
        exc = signal.excerpt_metadata[0] if signal.excerpt_metadata else {}
        system_prompt = EVOLUTION_UNMAPPED_SYSTEM.format(science=signal.science)
        user_prompt = EVOLUTION_UNMAPPED_USER.format(
            excerpt_id=signal.excerpt_ids[0] if signal.excerpt_ids else "unknown",
            excerpt_title=exc.get("excerpt_title", ""),
            boundary_reasoning=exc.get("boundary_reasoning", ""),
            excerpt_text=signal.excerpt_texts[0] if signal.excerpt_texts else "",
            taxonomy_context=extract_taxonomy_section(
                taxonomy_yaml_raw,
                [exc.get("taxonomy_node_id", ""), signal.node_id],
            ),
            full_taxonomy=taxonomy_yaml_raw[:8000],  # truncate very large taxonomies
        )
    else:
        # same_book_cluster or user_specified
        node_info = taxonomy_map.get(signal.node_id)
        node_title = node_info.title if node_info else signal.node_id
        node_path = " > ".join(node_info.path_titles) if node_info else signal.node_id

        system_prompt = EVOLUTION_CLUSTER_SYSTEM.format(science=signal.science)
        user_prompt = EVOLUTION_CLUSTER_USER.format(
            node_id=signal.node_id,
            node_title=node_title,
            node_path=node_path,
            excerpts_block=_format_excerpts_block(signal),
            taxonomy_context=extract_taxonomy_section(
                taxonomy_yaml_raw,
                [signal.node_id],
                context_lines=15,
            ),
        )

    # Call LLM
    try:
        response = actual_call_fn(
            system_prompt, user_prompt, model,
            api_key, openrouter_key, openai_key,
        )
    except Exception as e:
        print(f"  ERROR: LLM call failed for signal at {signal.node_id}: {e}",
              file=sys.stderr)
        return None

    # Parse response
    parsed = response.get("parsed")
    if parsed is None:
        # Try parsing from raw text if dispatch didn't pre-parse
        raw = response.get("raw_text", "")
        parsed = _parse_llm_json(raw) if raw else None

    if parsed is None:
        print(f"  WARNING: Could not parse LLM response for {signal.node_id}",
              file=sys.stderr)
        return None

    # Calculate cost
    input_tokens = response.get("input_tokens", 0)
    output_tokens = response.get("output_tokens", 0)
    total_cost = get_model_cost(model, input_tokens, output_tokens)

    cost_dict = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_cost": total_cost,
    }

    # Interpret response
    action = parsed.get("action", "keep")

    if action in ("keep", "merge"):
        # No evolution needed
        return None

    if action == "existing_leaf":
        # LLM found an existing leaf — not a taxonomy change, but useful info
        # We still return None (no change needed) but log the finding
        existing = parsed.get("existing_leaf_id", "")
        reasoning = parsed.get("reasoning", "")
        print(f"  INFO: LLM suggests existing leaf '{existing}' "
              f"for {signal.node_id}: {reasoning[:100]}")
        return None

    # Build proposal for "new_node" or "split"
    new_nodes_raw = parsed.get("new_nodes", [])
    new_node_single = parsed.get("new_node")

    # Handle single new_node (unmapped response) vs list (cluster response)
    if new_node_single and not new_nodes_raw:
        new_nodes_raw = [new_node_single]

    if not new_nodes_raw:
        print(f"  WARNING: LLM proposed action '{action}' but no new_nodes "
              f"for {signal.node_id}", file=sys.stderr)
        return None

    # Validate proposed node IDs — reject invalid ones
    validated_nodes = []
    rejected_nodes = []
    for node_dict in new_nodes_raw:
        nid = node_dict.get("node_id", "")
        errs = validate_proposed_node_id(nid, taxonomy_map)
        if errs:
            print(f"  WARNING: Rejected proposed node '{nid}': {'; '.join(errs)}",
                  file=sys.stderr)
            rejected_nodes.append(node_dict)
        else:
            validated_nodes.append(node_dict)

    if rejected_nodes:
        parsed["confidence"] = "uncertain"

    if not validated_nodes:
        print(f"  WARNING: All proposed nodes were invalid for {signal.node_id}",
              file=sys.stderr)
        return None

    # Determine change type and parent
    if action == "split":
        change_type = "leaf_granulated"
        parent_node_id = signal.node_id
    else:
        change_type = "node_added"
        parent_node_id = new_nodes_raw[0].get("parent_node_id", "")

    redistribution = parsed.get("redistribution", {})

    proposal_id = f"EP-{proposal_seq:03d}"

    return EvolutionProposal(
        signal=signal,
        proposal_id=proposal_id,
        change_type=change_type,
        parent_node_id=parent_node_id,
        new_nodes=validated_nodes,
        redistribution=redistribution,
        reasoning=parsed.get("reasoning", ""),
        confidence=parsed.get("confidence", "uncertain"),
        model=model,
        cost=cost_dict,
    )


# ---------------------------------------------------------------------------
# Multi-model consensus for evolution proposals
# ---------------------------------------------------------------------------

def _compare_evolution_proposals(
    proposals: list[EvolutionProposal | None],
    models: list[str],
) -> dict:
    """Compare evolution proposals from multiple models.

    Returns a consensus result with:
    - status: "agreement", "partial", "disagreement", or "no_change"
    - agreed_nodes: node IDs that all models proposed
    - disagreed_nodes: node IDs that only some models proposed
    - chosen_proposal: the selected proposal (highest confidence, or first agreement)
    - model_proposals: per-model details
    """
    # Filter out None proposals (models that decided no change needed)
    active = [(p, m) for p, m in zip(proposals, models) if p is not None]
    none_count = len(proposals) - len(active)

    if not active:
        return {
            "status": "no_change",
            "note": f"All {len(models)} models agreed: no change needed",
            "chosen_proposal": None,
            "model_proposals": {m: None for m in models},
        }

    if none_count > 0 and len(active) == 1:
        # Only one model wants a change — low confidence
        return {
            "status": "disagreement",
            "note": (
                f"Only {active[0][1]} proposes a change; "
                f"{none_count} model(s) say no change needed"
            ),
            "chosen_proposal": active[0][0],
            "confidence_override": "uncertain",
            "model_proposals": {
                m: p for p, m in zip(proposals, models)
            },
        }

    # Multiple active proposals — compare node IDs
    node_sets = []
    for proposal, _ in active:
        nids = frozenset(n.get("node_id", "") for n in proposal.new_nodes)
        node_sets.append(nids)

    # Check for full agreement on node IDs
    if len(set(node_sets)) == 1:
        # All active models propose the same nodes
        # Choose the one with highest confidence
        confidence_order = {"certain": 3, "likely": 2, "uncertain": 1}
        best = max(active, key=lambda x: confidence_order.get(x[0].confidence, 0))
        return {
            "status": "agreement",
            "agreed_nodes": list(node_sets[0]),
            "chosen_proposal": best[0],
            "model_proposals": {m: p for p, m in zip(proposals, models)},
        }

    # Partial agreement — find common and differing nodes
    all_nodes = set()
    for ns in node_sets:
        all_nodes.update(ns)

    agreed = set.intersection(*[set(ns) for ns in node_sets]) if node_sets else set()
    disagreed = all_nodes - agreed

    # Choose the proposal with most agreed nodes and highest confidence
    confidence_order = {"certain": 3, "likely": 2, "uncertain": 1}
    best = max(active, key=lambda x: (
        len(set(n.get("node_id", "") for n in x[0].new_nodes) & agreed),
        confidence_order.get(x[0].confidence, 0),
    ))

    status = "partial" if agreed else "disagreement"

    return {
        "status": status,
        "agreed_nodes": list(agreed),
        "disagreed_nodes": list(disagreed),
        "chosen_proposal": best[0],
        "confidence_override": "uncertain" if status == "disagreement" else None,
        "model_proposals": {m: p for p, m in zip(proposals, models)},
    }


def propose_with_consensus(
    signal: EvolutionSignal,
    taxonomy_yaml_raw: str,
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    models: list[str],
    api_key: str,
    openrouter_key: str | None = None,
    openai_key: str | None = None,
    call_llm_fn=None,
    proposal_seq: int = 1,
) -> tuple[EvolutionProposal | None, dict]:
    """Run multiple models on the same signal and compare proposals.

    Returns (chosen_proposal, consensus_result).
    """
    proposals: list[EvolutionProposal | None] = []

    for model in models:
        proposal = propose_evolution_for_signal(
            signal=signal,
            taxonomy_yaml_raw=taxonomy_yaml_raw,
            taxonomy_map=taxonomy_map,
            model=model,
            api_key=api_key,
            openrouter_key=openrouter_key,
            openai_key=openai_key,
            call_llm_fn=call_llm_fn,
            proposal_seq=proposal_seq,
        )
        proposals.append(proposal)

    consensus = _compare_evolution_proposals(proposals, models)

    chosen = consensus.get("chosen_proposal")

    # Apply confidence override if disagreement detected
    if chosen and consensus.get("confidence_override"):
        # Create a new proposal with overridden confidence
        chosen = EvolutionProposal(
            signal=chosen.signal,
            proposal_id=chosen.proposal_id,
            change_type=chosen.change_type,
            parent_node_id=chosen.parent_node_id,
            new_nodes=chosen.new_nodes,
            redistribution=chosen.redistribution,
            reasoning=chosen.reasoning + f" [consensus: {consensus['status']}]",
            confidence=consensus["confidence_override"],
            model="+".join(models),
            cost=chosen.cost,
        )

    return chosen, consensus


# ---------------------------------------------------------------------------
# Output artifact generation
# ---------------------------------------------------------------------------

def generate_change_records(
    proposals: list[EvolutionProposal],
    taxonomy_version: str,
    book_id: str,
) -> list[dict]:
    """Convert proposals to taxonomy_changes.jsonl records (gold format)."""
    records = []
    # Derive proposed new version — use _increment_version for consistency
    new_version = _increment_version(taxonomy_version)

    for i, proposal in enumerate(proposals, 1):
        change_id = f"TC-{i:03d}"
        batch_note = (
            f"Proposed by {proposal.model}. "
            f"Confidence: {proposal.confidence}. "
            f"Pending human approval."
        )
        trigger_excerpt = (
            proposal.signal.excerpt_ids[0]
            if proposal.signal.excerpt_ids else ""
        )
        shared = {
            "record_type": "taxonomy_change",
            "change_id": change_id,
            "taxonomy_version_before": taxonomy_version,
            "taxonomy_version_after": new_version,
            "book_id": book_id,
            "passage_id": "",
            "batch_note": batch_note,
            "reasoning": proposal.reasoning,
            "triggered_by_excerpt_id": trigger_excerpt,
        }

        if proposal.change_type == "leaf_granulated":
            records.append({
                **shared,
                "change_type": "leaf_granulated",
                "node_id": proposal.signal.node_id,
                "parent_node_id": proposal.parent_node_id,
                "new_children": [
                    {"node_id": n["node_id"], "title_ar": n.get("title_ar", "")}
                    for n in proposal.new_nodes
                ],
                "migration": proposal.redistribution,
            })
        else:
            # node_added -- one record per new node
            for node_dict in proposal.new_nodes:
                records.append({
                    **shared,
                    "change_type": "node_added",
                    "node_id": node_dict.get("node_id", ""),
                    "parent_node_id": (
                        node_dict.get("parent_node_id", "")
                        or proposal.parent_node_id
                    ),
                })

    return records


def generate_proposal_json(
    signals: list[EvolutionSignal],
    proposals: list[EvolutionProposal],
    science: str,
    taxonomy_version: str,
    taxonomy_path: str,
    model: str,
) -> dict:
    """Generate the evolution_proposal.json structure."""
    # Aggregate costs
    total_input = sum(p.cost.get("input_tokens", 0) for p in proposals)
    total_output = sum(p.cost.get("output_tokens", 0) for p in proposals)
    total_cost = sum(p.cost.get("total_cost", 0) for p in proposals)

    # Count proposals by type
    by_type: dict[str, int] = {}
    for p in proposals:
        by_type[p.change_type] = by_type.get(p.change_type, 0) + 1

    return {
        "schema_version": "evolution_proposal_v0.1",
        "science": science,
        "taxonomy_version": taxonomy_version,
        "taxonomy_path": taxonomy_path,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "signals": [
            {
                "signal_type": s.signal_type,
                "node_id": s.node_id,
                "excerpt_ids": s.excerpt_ids,
                "context": s.context,
            }
            for s in signals
        ],
        "proposals": [
            {
                "proposal_id": p.proposal_id,
                "signal_type": p.signal.signal_type,
                "signal_node_id": p.signal.node_id,
                "change_type": p.change_type,
                "parent_node_id": p.parent_node_id,
                "new_nodes": p.new_nodes,
                "redistribution": p.redistribution,
                "reasoning": p.reasoning,
                "confidence": p.confidence,
                "model": p.model,
                "cost": p.cost,
            }
            for p in proposals
        ],
        "summary": {
            "total_signals": len(signals),
            "total_proposals": len(proposals),
            "no_change_needed": len(signals) - len(proposals),
            "proposals_by_type": by_type,
            "total_cost": {
                "input_tokens": total_input,
                "output_tokens": total_output,
                "total_cost": round(total_cost, 6),
            },
        },
    }


def generate_review_md(
    signals: list[EvolutionSignal],
    proposals: list[EvolutionProposal],
    science: str,
    taxonomy_version: str,
    taxonomy_map: dict[str, TaxonomyNodeInfo],
    model: str,
) -> str:
    """Generate human-readable review markdown."""
    lines = []

    # Header
    total_cost = sum(p.cost.get("total_cost", 0) for p in proposals)
    leaf_count = sum(1 for n in taxonomy_map.values() if n.is_leaf)
    lines.append(f"# Taxonomy Evolution Review — {taxonomy_version}")
    lines.append("")
    lines.append(f"- **Science:** {science}")
    lines.append(f"- **Current taxonomy:** {taxonomy_version} ({leaf_count} leaves)")
    lines.append(f"- **Signals detected:** {len(signals)}")
    lines.append(f"- **Proposals generated:** {len(proposals)}")
    lines.append(f"- **No change needed:** {len(signals) - len(proposals)}")
    lines.append(f"- **Model:** {model}")
    lines.append(f"- **Cost:** ${total_cost:.4f}")
    lines.append("")

    # Build a mapping from signal node_id to proposal
    proposal_map: dict[str, EvolutionProposal] = {}
    for p in proposals:
        proposal_map[p.signal.node_id] = p

    # Signal-by-signal detail
    for i, signal in enumerate(signals, 1):
        lines.append("---")
        lines.append("")
        lines.append(f"## Signal {i}: {signal.signal_type.replace('_', ' ').title()}")
        lines.append("")

        if signal.signal_type == "unmapped":
            lines.append(f"**Excerpt:** `{signal.excerpt_ids[0]}`")
            if signal.excerpt_metadata:
                meta = signal.excerpt_metadata[0]
                lines.append(f"**Title:** {meta.get('excerpt_title', '')}")
                lines.append(f"**Boundary reasoning:** "
                             f"{meta.get('boundary_reasoning', '')[:200]}")
            lines.append("")
            lines.append("**Arabic text:**")
            lines.append("")
            text = signal.excerpt_texts[0] if signal.excerpt_texts else ""
            lines.append(text[:500] + ("..." if len(text) > 500 else ""))
            lines.append("")

        elif signal.signal_type in ("same_book_cluster", "user_specified"):
            node_info = taxonomy_map.get(signal.node_id)
            node_title = node_info.title if node_info else signal.node_id
            node_path = (
                " > ".join(node_info.path_titles) if node_info else signal.node_id
            )
            lines.append(f"**Node:** `{signal.node_id}` — {node_title}")
            lines.append(f"**Path:** {node_path}")
            lines.append(f"**Excerpts:** {len(signal.excerpt_ids)}")
            lines.append("")
            for j, (eid, text) in enumerate(
                zip(signal.excerpt_ids, signal.excerpt_texts), 1,
            ):
                lines.append(f"### Excerpt {j}: `{eid}`")
                lines.append("")
                lines.append(text[:300] + ("..." if len(text) > 300 else ""))
                lines.append("")

        # Show proposal if one was generated
        proposal = proposal_map.get(signal.node_id)
        if proposal is not None:
            lines.append(f"### LLM Proposal ({proposal.proposal_id})")
            lines.append("")
            lines.append(
                f"**Action:** {proposal.change_type.upper()} "
                f"(confidence: {proposal.confidence})"
            )

            if proposal.new_nodes:
                lines.append("")
                lines.append("**Proposed new nodes:**")
                for node_dict in proposal.new_nodes:
                    nid = node_dict.get("node_id", "")
                    title_ar = node_dict.get("title_ar", "")
                    lines.append(f"- `{nid}` — {title_ar}")

            if proposal.redistribution:
                lines.append("")
                lines.append("**Redistribution:**")
                for exc_id, new_node in proposal.redistribution.items():
                    lines.append(f"- `{exc_id}` → `{new_node}`")

            lines.append("")
            lines.append(f"**Reasoning:** {proposal.reasoning}")
            lines.append("")

            # ASCII tree diff
            if proposal.change_type == "leaf_granulated":
                lines.append("**Proposed tree diff:**")
                lines.append("```")
                parent = proposal.parent_node_id
                lines.append(f" {parent}/")
                lines.append(f"-  (was a leaf)")
                for nd in proposal.new_nodes:
                    lines.append(f"+  {nd.get('node_id', '')}/     (new leaf)")
                lines.append("```")
                lines.append("")
            elif proposal.change_type == "node_added":
                lines.append("**Proposed tree diff:**")
                lines.append("```")
                parent = proposal.parent_node_id
                lines.append(f" {parent}/")
                lines.append(f"   ... (existing children)")
                for nd in proposal.new_nodes:
                    lines.append(f"+  {nd.get('node_id', '')}/     (new leaf)")
                lines.append("```")
                lines.append("")
        else:
            lines.append("### Result: No change needed")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase B: Apply, Version Control, Rollback, Redistribution
# ---------------------------------------------------------------------------

try:
    import yaml as _yaml
except ImportError:
    _yaml = None  # type: ignore[assignment]


def _increment_version(version_str: str) -> str:
    """Increment the last numeric segment of a version string.

    ``imlaa_v1_0`` → ``imlaa_v1_1``, ``aqidah_v0_2`` → ``aqidah_v0_3``.
    """
    parts = version_str.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return f"{parts[0]}_{int(parts[1]) + 1}"
    return f"{version_str}_1"


def _modify_v0_yaml(
    data: dict,
    parent_node_id: str,
    new_nodes: list[dict],
) -> tuple[dict, bool]:
    """Apply a leaf_granulated change to a v0 (nested-dict) taxonomy.

    Converts the parent leaf to a branch by removing ``_leaf: true`` and
    adding new sub-nodes as children.

    Returns ``(data, found)`` where *found* indicates whether the parent
    node was located in the taxonomy.
    """
    def _walk(d: dict) -> bool:
        if not isinstance(d, dict):
            return False
        for key, value in list(d.items()):
            if key == parent_node_id and isinstance(value, dict):
                # Found the target node — convert leaf to branch
                value.pop("_leaf", None)
                for new_node in new_nodes:
                    nid = new_node["node_id"]
                    child = {"_leaf": True}
                    label = new_node.get("title_ar", "")
                    if label:
                        child["_label"] = label
                    value[nid] = child
                return True
            if isinstance(value, dict) and _walk(value):
                return True
        return False

    found = _walk(data)
    return data, found


def _modify_v1_yaml(
    data: dict,
    parent_node_id: str,
    new_nodes: list[dict],
) -> tuple[dict, bool]:
    """Apply a leaf_granulated change to a v1 (structured) taxonomy.

    Converts the parent leaf to a branch by removing ``leaf: true`` and
    adding ``children`` with the new sub-nodes.

    Returns ``(data, found)`` where *found* indicates whether the parent
    node was located in the taxonomy.
    """
    taxonomy_block = data.get("taxonomy", {})
    nodes = taxonomy_block.get("nodes", [])

    def _walk(node_list: list[dict]) -> bool:
        for node in node_list:
            if node.get("id") == parent_node_id:
                # Found the target — convert leaf to branch
                node.pop("leaf", None)
                children = node.get("children", [])
                for new_node in new_nodes:
                    child = {
                        "id": new_node["node_id"],
                        "title": new_node.get("title_ar", new_node["node_id"]),
                        "leaf": True,
                    }
                    children.append(child)
                node["children"] = children
                return True
            if "children" in node:
                if _walk(node["children"]):
                    return True
        return False

    found = _walk(nodes)
    return data, found


def _add_node_v0(
    data: dict,
    parent_node_id: str,
    new_nodes: list[dict],
) -> tuple[dict, bool]:
    """Add new leaf nodes under an existing branch in v0 format.

    Returns ``(data, found)`` where *found* indicates whether the parent
    node was located in the taxonomy.
    """
    def _walk(d: dict) -> bool:
        if not isinstance(d, dict):
            return False
        for key, value in list(d.items()):
            if key == parent_node_id and isinstance(value, dict):
                for new_node in new_nodes:
                    nid = new_node["node_id"]
                    child = {"_leaf": True}
                    label = new_node.get("title_ar", "")
                    if label:
                        child["_label"] = label
                    value[nid] = child
                return True
            if isinstance(value, dict) and _walk(value):
                return True
        return False

    found = _walk(data)
    return data, found


def _add_node_v1(
    data: dict,
    parent_node_id: str,
    new_nodes: list[dict],
) -> tuple[dict, bool]:
    """Add new leaf nodes under an existing branch in v1 format.

    Returns ``(data, found)`` where *found* indicates whether the parent
    node was located in the taxonomy.
    """
    taxonomy_block = data.get("taxonomy", {})
    nodes = taxonomy_block.get("nodes", [])

    def _walk(node_list: list[dict]) -> bool:
        for node in node_list:
            if node.get("id") == parent_node_id:
                if "children" not in node:
                    node["children"] = []
                for new_node in new_nodes:
                    child = {
                        "id": new_node["node_id"],
                        "title": new_node.get("title_ar", new_node["node_id"]),
                        "leaf": True,
                    }
                    node["children"].append(child)
                return True
            if "children" in node:
                if _walk(node["children"]):
                    return True
        return False

    found = _walk(nodes)
    return data, found


def _detect_yaml_format(data: dict) -> str:
    """Detect if parsed YAML data is v0 or v1 format."""
    if isinstance(data, dict) and "taxonomy" in data:
        tb = data["taxonomy"]
        if isinstance(tb, dict) and "nodes" in tb:
            return "v1"
    return "v0"


def apply_proposal_to_yaml(
    taxonomy_path: str,
    proposals: list[dict],
    new_version: str,
    output_dir: str,
) -> str:
    """Apply approved proposals to a taxonomy YAML, producing a new version file.

    Reads the existing taxonomy, applies each proposal's structural changes,
    and writes a new versioned YAML file. The original file is never modified.

    Returns the path to the new taxonomy YAML file.
    """
    if _yaml is None:
        raise ImportError("PyYAML is required for taxonomy evolution apply step")

    with open(taxonomy_path, encoding="utf-8") as f:
        raw = f.read()

    data = _yaml.safe_load(raw)
    fmt = _detect_yaml_format(data)

    for proposal in proposals:
        change_type = proposal.get("change_type", "")
        parent_node_id = proposal.get("parent_node_id", "")
        new_nodes = proposal.get("new_nodes", [])

        if not new_nodes:
            continue

        if change_type == "leaf_granulated":
            if fmt == "v0":
                data, found = _modify_v0_yaml(data, parent_node_id, new_nodes)
            else:
                data, found = _modify_v1_yaml(data, parent_node_id, new_nodes)
        elif change_type == "node_added":
            if fmt == "v0":
                data, found = _add_node_v0(data, parent_node_id, new_nodes)
            else:
                data, found = _add_node_v1(data, parent_node_id, new_nodes)
        else:
            found = True  # unknown change types pass through

        if not found:
            print(f"  WARNING: parent node '{parent_node_id}' not found in taxonomy "
                  f"for proposal change_type='{change_type}' — skipping",
                  file=sys.stderr)

    # Write new version
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    new_filename = f"{new_version}.yaml"
    new_filepath = out_path / new_filename

    with open(new_filepath, "w", encoding="utf-8") as f:
        _yaml.dump(data, f, allow_unicode=True, default_flow_style=False,
                   sort_keys=False)

    return str(new_filepath)


def update_taxonomy_registry(
    registry_path: str,
    science: str,
    new_version: str,
    new_relpath: str,
    previous_version: str,
    notes: str = "",
) -> None:
    """Add a new version entry to taxonomy_registry.yaml.

    Marks the previous version as ``historical`` and adds the new version
    as ``active``.
    """
    if _yaml is None:
        raise ImportError("PyYAML is required for registry updates")

    with open(registry_path, encoding="utf-8") as f:
        registry = _yaml.safe_load(f)

    if registry is None:
        registry = {"registry_version": "0.1", "sciences": []}

    sciences = registry.get("sciences", [])

    # Find existing science entry
    science_entry = None
    for entry in sciences:
        if entry.get("science_id") == science:
            science_entry = entry
            break

    if science_entry is None:
        # Create new science entry
        science_entry = {
            "science_id": science,
            "display_name_ar": science,
            "versions": [],
        }
        sciences.append(science_entry)

    # Mark previous version as historical
    for ver in science_entry.get("versions", []):
        if ver.get("taxonomy_version") == previous_version:
            ver["status"] = "historical"

    # Add new version
    science_entry.setdefault("versions", []).append({
        "taxonomy_version": new_version,
        "relpath": new_relpath,
        "status": "active",
        "notes": notes or f"Evolved from {previous_version}.",
    })

    with open(registry_path, "w", encoding="utf-8") as f:
        _yaml.dump(registry, f, allow_unicode=True, default_flow_style=False,
                   sort_keys=False)


def redistribute_excerpts(
    assembly_dir: str,
    old_node_id: str,
    new_nodes: list[dict],
    science: str,
    taxonomy_path: str,
    call_llm_fn=None,
    model: str = "claude-sonnet-4-5-20250929",
    api_key: str = "",
    openrouter_key: str | None = None,
    openai_key: str | None = None,
) -> dict:
    """Redistribute assembled excerpt files from an old leaf to new sub-leaves.

    Reads all excerpt files at the old node's folder, uses an LLM to assign
    each to the correct new sub-leaf, and moves the files. Returns a mapping
    of {excerpt_file: new_node_id} plus any flagged excerpts.

    Files are MOVED (not deleted) so rollback can reverse the operation.
    """
    base_path = Path(assembly_dir)
    taxonomy_map = parse_taxonomy_yaml(taxonomy_path, science)

    # Find the old node's folder path
    old_info = taxonomy_map.get(old_node_id)
    if old_info is None:
        # Try to find via folder search
        old_folder = base_path / science / old_node_id
    else:
        old_folder = base_path / old_info.folder_path

    if not old_folder.exists():
        return {"moves": {}, "flagged": [], "error": f"Folder not found: {old_folder}"}

    # Collect excerpt files at old folder
    excerpt_files = list(old_folder.glob("*.json"))
    if not excerpt_files:
        return {"moves": {}, "flagged": [], "note": "No excerpt files to redistribute"}

    # Build new node descriptions for LLM
    node_descriptions = []
    valid_node_ids: set[str] = set()
    for node in new_nodes:
        nid = node.get("node_id", "")
        title = node.get("title_ar", nid)
        node_descriptions.append(f"- {nid}: {title}")
        if nid:
            valid_node_ids.add(nid)
    nodes_text = "\n".join(node_descriptions)

    moves: dict[str, str] = {}
    flagged: list[str] = []

    for excerpt_file in excerpt_files:
        try:
            with open(excerpt_file, encoding="utf-8") as f:
                excerpt_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            flagged.append(str(excerpt_file))
            continue

        # Extract the Arabic text from the assembled excerpt
        arabic_text = excerpt_data.get("arabic_text", "")
        if not arabic_text:
            arabic_text = excerpt_data.get("text", "")
        excerpt_title = excerpt_data.get("excerpt_title", "")

        if call_llm_fn is not None or api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            # Use LLM for placement
            system_prompt = (
                "You are a taxonomy placement advisor. Given an Arabic excerpt and "
                "a list of available taxonomy nodes, determine the most appropriate "
                "node for this excerpt. Respond with ONLY a JSON object: "
                '{"node_id": "chosen_node_id", "confidence": "certain|likely|uncertain", '
                '"reasoning": "brief explanation"}'
            )
            user_prompt = (
                f"## Excerpt\nTitle: {excerpt_title}\n\n"
                f"Arabic text:\n{arabic_text[:3000]}\n\n"
                f"## Available nodes\n{nodes_text}\n\n"
                f"Which node should this excerpt be placed at?"
            )

            if call_llm_fn is None:
                from tools.extract_passages import call_llm_dispatch
                actual_fn = call_llm_dispatch
            else:
                actual_fn = call_llm_fn

            try:
                effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
                eff_openai = openai_key or os.environ.get("OPENAI_API_KEY")
                response = actual_fn(
                    system_prompt, user_prompt, model,
                    effective_key, openrouter_key, eff_openai,
                )
                parsed = response.get("parsed")
                if parsed is None:
                    raw = response.get("raw_text", "")
                    parsed = _parse_llm_json(raw) if raw else None

                if parsed and parsed.get("node_id"):
                    target_node = parsed["node_id"]
                    if target_node not in valid_node_ids:
                        # LLM returned an invalid node_id — flag for review
                        flagged.append(str(excerpt_file))
                        continue
                    confidence = parsed.get("confidence", "uncertain")
                    if confidence == "uncertain":
                        flagged.append(str(excerpt_file))
                    moves[str(excerpt_file)] = target_node
                else:
                    flagged.append(str(excerpt_file))
            except Exception:
                flagged.append(str(excerpt_file))
        else:
            # No LLM available — flag all for manual review
            flagged.append(str(excerpt_file))

    # Execute moves
    for filepath_str, target_node_id in moves.items():
        filepath = Path(filepath_str)
        # Determine target directory
        target_dir = old_folder.parent / old_node_id / target_node_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filepath.name
        filepath.rename(target_path)
        # Update the moves dict with the new path
        moves[filepath_str] = target_node_id

    return {"moves": moves, "flagged": flagged}


def rollback_evolution(
    rollback_manifest_path: str,
) -> dict:
    """Rollback a taxonomy evolution using its manifest.

    The manifest (created during apply) records:
    - original taxonomy path and version
    - new taxonomy path and version
    - all file moves (original path → new path)
    - registry update info

    Rollback reverses all file moves and restores the previous taxonomy
    as active in the registry.

    Returns a summary dict.
    """
    with open(rollback_manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    errors: list[str] = []
    reversed_moves = 0

    # Reverse file moves
    for move in manifest.get("file_moves", []):
        src = Path(move["from"])
        dst = Path(move["to"])
        if dst.exists():
            try:
                # Move back
                src.parent.mkdir(parents=True, exist_ok=True)
                dst.rename(src)
                reversed_moves += 1
            except OSError as e:
                errors.append(f"Failed to move {dst} → {src}: {e}")
        else:
            errors.append(f"Target file not found for rollback: {dst}")

    # Clean up empty directories created during redistribution
    for move in manifest.get("file_moves", []):
        dst_dir = Path(move["to"]).parent
        try:
            if dst_dir.exists() and not list(dst_dir.iterdir()):
                dst_dir.rmdir()
        except OSError:
            pass

    # Restore registry (if applicable)
    registry_path = manifest.get("registry_path")
    if registry_path and _yaml is not None and Path(registry_path).exists():
        try:
            with open(registry_path, encoding="utf-8") as f:
                registry = _yaml.safe_load(f)

            science = manifest.get("science", "")
            old_version = manifest.get("previous_version", "")
            new_version = manifest.get("new_version", "")

            for entry in registry.get("sciences", []):
                if entry.get("science_id") == science:
                    versions = entry.get("versions", [])
                    # Remove the new version
                    entry["versions"] = [
                        v for v in versions
                        if v.get("taxonomy_version") != new_version
                    ]
                    # Restore old version as active
                    for v in entry["versions"]:
                        if v.get("taxonomy_version") == old_version:
                            v["status"] = "active"

            with open(registry_path, "w", encoding="utf-8") as f:
                _yaml.dump(registry, f, allow_unicode=True,
                           default_flow_style=False, sort_keys=False)
        except Exception as e:
            errors.append(f"Registry rollback failed: {e}")

    # Delete the new taxonomy file if it exists
    new_taxonomy_path = manifest.get("new_taxonomy_path")
    if new_taxonomy_path and Path(new_taxonomy_path).exists():
        try:
            Path(new_taxonomy_path).unlink()
        except OSError as e:
            errors.append(f"Could not delete new taxonomy file: {e}")

    return {
        "reversed_moves": reversed_moves,
        "errors": errors,
        "status": "success" if not errors else "partial",
    }


def apply_evolution(
    proposal_path: str,
    taxonomy_path: str,
    assembly_dir: str | None,
    output_dir: str,
    registry_path: str | None = None,
    call_llm_fn=None,
    model: str = "claude-sonnet-4-5-20250929",
    api_key: str = "",
    openrouter_key: str | None = None,
    openai_key: str | None = None,
) -> dict:
    """Apply approved taxonomy evolution proposals.

    1. Reads the proposal JSON (output of Phase A).
    2. Applies structural changes to the taxonomy YAML → new version file.
    3. Updates the taxonomy registry with the new version.
    4. Redistributes assembled excerpt files to new sub-leaves.
    5. Creates a rollback manifest for reversal.

    Returns a summary dict with paths to all created artifacts.
    """
    # Load proposal
    with open(proposal_path, encoding="utf-8") as f:
        proposal_data = json.load(f)

    proposals = proposal_data.get("proposals", [])
    if not proposals:
        return {"status": "no_proposals", "note": "No proposals to apply"}

    science = proposal_data.get("science", "")
    old_version = proposal_data.get("taxonomy_version", "")
    new_version = _increment_version(old_version)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Apply structural changes to taxonomy YAML
    new_taxonomy_path = apply_proposal_to_yaml(
        taxonomy_path=taxonomy_path,
        proposals=proposals,
        new_version=new_version,
        output_dir=output_dir,
    )

    # 2. Update registry
    actual_registry = registry_path or str(
        Path(taxonomy_path).parent.parent / "taxonomy_registry.yaml"
    )
    if Path(actual_registry).exists():
        try:
            # Try to compute relative path; fall back to absolute
            try:
                rel = str(Path(new_taxonomy_path).relative_to(
                    Path(actual_registry).parent
                ))
            except ValueError:
                rel = new_taxonomy_path
            update_taxonomy_registry(
                registry_path=actual_registry,
                science=science,
                new_version=new_version,
                new_relpath=rel,
                previous_version=old_version,
                notes=f"Evolved from {old_version}. {len(proposals)} proposals applied.",
            )
        except Exception as e:
            print(f"WARNING: Could not update registry: {e}", file=sys.stderr)

    # 3. Redistribute excerpts (if assembly_dir provided)
    file_moves: list[dict] = []
    redistribution_summary: dict = {}

    if assembly_dir:
        for proposal in proposals:
            if proposal.get("change_type") != "leaf_granulated":
                continue

            parent_node = proposal.get("parent_node_id", "")
            new_nodes = proposal.get("new_nodes", [])

            if not parent_node or not new_nodes:
                continue

            result = redistribute_excerpts(
                assembly_dir=assembly_dir,
                old_node_id=parent_node,
                new_nodes=new_nodes,
                science=science,
                taxonomy_path=new_taxonomy_path,
                call_llm_fn=call_llm_fn,
                model=model,
                api_key=api_key,
                openrouter_key=openrouter_key,
                openai_key=openai_key,
            )
            redistribution_summary[parent_node] = result

            # Record moves for rollback manifest
            # The actual move in redistribute_excerpts goes to:
            #   old_folder.parent / old_node_id / target_node_id
            # where old_folder is the node's current folder. Since
            # Path(original_path).parent IS old_folder, we need .parent
            # to avoid doubling the node name in the path.
            for original_path, target_node in result.get("moves", {}).items():
                src_folder = Path(original_path).parent
                new_folder = src_folder.parent / parent_node / target_node
                file_moves.append({
                    "from": original_path,
                    "to": str(new_folder / Path(original_path).name),
                })

    # 4. Create rollback manifest
    manifest = {
        "schema_version": "rollback_manifest_v0.1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "science": science,
        "previous_version": old_version,
        "new_version": new_version,
        "original_taxonomy_path": taxonomy_path,
        "new_taxonomy_path": new_taxonomy_path,
        "registry_path": actual_registry if Path(actual_registry).exists() else None,
        "file_moves": file_moves,
        "proposals_applied": len(proposals),
    }

    manifest_path = out_path / "rollback_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n=== Evolution Applied ===")
    print(f"New taxonomy: {new_taxonomy_path}")
    print(f"Version: {old_version} → {new_version}")
    print(f"Proposals applied: {len(proposals)}")
    print(f"File moves: {len(file_moves)}")
    print(f"Rollback manifest: {manifest_path}")

    return {
        "status": "applied",
        "new_version": new_version,
        "new_taxonomy_path": new_taxonomy_path,
        "manifest_path": str(manifest_path),
        "file_moves": len(file_moves),
        "redistribution": redistribution_summary,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_evolution(
    extraction_dir: str,
    taxonomy_path: str,
    science: str,
    output_dir: str,
    model: str = "claude-sonnet-4-5-20250929",
    models: list[str] | None = None,
    api_key: str | None = None,
    openrouter_key: str | None = None,
    openai_key: str | None = None,
    assembly_dir: str | None = None,
    book_id: str = "",
    node_ids: list[str] | None = None,
    skip_unmapped: bool = False,
    skip_clusters: bool = False,
    skip_category_check: bool = False,
    skip_multi_topic: bool = False,
    dry_run: bool = False,
    call_llm_fn=None,
) -> dict:
    """Main evolution pipeline. Returns summary dict."""

    # 1. Load taxonomy
    taxonomy_map = parse_taxonomy_yaml(taxonomy_path, science)
    taxonomy_yaml_raw = Path(taxonomy_path).read_text(encoding="utf-8")

    # Derive taxonomy version from filename
    tax_stem = Path(taxonomy_path).stem  # e.g. "imlaa_v1_0" or "imlaa_v0.1"
    taxonomy_version = tax_stem.replace(".", "_")

    # 2. Load extraction data
    extraction_data = load_extraction_files(extraction_dir)
    if not extraction_data:
        print("No extraction files found. Nothing to do.")
        return {"signals": 0, "proposals": 0}

    # 3. Build atom indexes per passage
    atoms_indexes: dict[str, dict[str, dict]] = {}
    for passage in extraction_data:
        pid = passage["passage_id"]
        atoms_indexes[pid] = build_atoms_index(passage["atoms"])

    # 4. Scan for signals
    signals: list[EvolutionSignal] = []

    if not skip_unmapped:
        signals.extend(
            scan_unmapped_signals(extraction_data, atoms_indexes, science)
        )
    if not skip_clusters:
        signals.extend(
            scan_cluster_signals(
                extraction_data, atoms_indexes, taxonomy_map, science,
            )
        )
    if not skip_category_check:
        signals.extend(
            scan_category_leaf_signals(taxonomy_map, science)
        )
    if not skip_multi_topic:
        signals.extend(
            scan_multi_topic_signals(
                extraction_data, atoms_indexes, taxonomy_map, science,
            )
        )
    if node_ids:
        signals.extend(
            scan_user_signals(
                node_ids, extraction_data, atoms_indexes, taxonomy_map, science,
            )
        )

    # 5. Deduplicate
    signals = deduplicate_signals(signals)

    # 6. Print signal summary
    print(f"=== Taxonomy Evolution Engine ===")
    print(f"Science: {science}")
    print(f"Taxonomy: {Path(taxonomy_path).name}")
    print(f"Signals detected: {len(signals)}")
    for s in signals:
        print(f"  [{s.signal_type}] {s.node_id}: {s.context}")

    if not signals:
        print("\nNo evolution signals detected. Taxonomy appears adequate.")
        return {"signals": 0, "proposals": 0}

    # 7. Create output directory
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if dry_run:
        # Write signals-only report
        dry_report = {
            "mode": "dry_run",
            "science": science,
            "taxonomy_version": taxonomy_version,
            "signals": [
                {
                    "signal_type": s.signal_type,
                    "node_id": s.node_id,
                    "excerpt_ids": s.excerpt_ids,
                    "context": s.context,
                }
                for s in signals
            ],
        }
        report_path = out_path / "evolution_signals_dry_run.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(dry_report, f, ensure_ascii=False, indent=2)

        print(f"\nDry-run report written to {report_path}")
        return {"signals": len(signals), "proposals": 0, "dry_run": True}

    # 8. Resolve API keys
    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    openrouter_key = openrouter_key or os.environ.get("OPENROUTER_API_KEY")
    openai_key = openai_key or os.environ.get("OPENAI_API_KEY")

    if not effective_key and not openrouter_key and not openai_key:
        print("ERROR: No API key available. Set ANTHROPIC_API_KEY, "
              "OPENAI_API_KEY, or OPENROUTER_API_KEY.", file=sys.stderr)
        return {"signals": len(signals), "proposals": 0, "error": "no_api_key"}

    # 9. Generate proposals
    use_consensus = models and len(models) > 1
    effective_models = models if use_consensus else [model]
    consensus_results: list[dict] = []

    proposals: list[EvolutionProposal] = []
    for i, signal in enumerate(signals, 1):
        print(f"\n--- Signal {i}/{len(signals)}: [{signal.signal_type}] "
              f"{signal.node_id} ---")

        if use_consensus:
            # Multi-model consensus mode
            proposal, consensus = propose_with_consensus(
                signal=signal,
                taxonomy_yaml_raw=taxonomy_yaml_raw,
                taxonomy_map=taxonomy_map,
                models=effective_models,
                api_key=effective_key,
                openrouter_key=openrouter_key,
                openai_key=openai_key,
                call_llm_fn=call_llm_fn,
                proposal_seq=len(proposals) + 1,
            )
            consensus_results.append(consensus)
            if proposal is not None:
                proposals.append(proposal)
                print(f"  -> Consensus ({consensus['status']}): "
                      f"Proposal {proposal.proposal_id}: "
                      f"{proposal.change_type} ({proposal.confidence})")
            else:
                print(f"  -> Consensus ({consensus['status']}): No change needed")
        else:
            # Single-model mode
            proposal = propose_evolution_for_signal(
                signal=signal,
                taxonomy_yaml_raw=taxonomy_yaml_raw,
                taxonomy_map=taxonomy_map,
                model=model,
                api_key=effective_key,
                openrouter_key=openrouter_key,
                openai_key=openai_key,
                call_llm_fn=call_llm_fn,
                proposal_seq=len(proposals) + 1,
            )
            if proposal is not None:
                proposals.append(proposal)
                print(f"  -> Proposal {proposal.proposal_id}: "
                      f"{proposal.change_type} ({proposal.confidence})")
            else:
                print(f"  -> No change needed")

    # 10. Generate output artifacts
    # 10a. evolution_proposal.json
    effective_model_label = "+".join(effective_models) if use_consensus else model
    proposal_dict = generate_proposal_json(
        signals=signals,
        proposals=proposals,
        science=science,
        taxonomy_version=taxonomy_version,
        taxonomy_path=taxonomy_path,
        model=effective_model_label,
    )
    proposal_path = out_path / "evolution_proposal.json"
    with open(proposal_path, "w", encoding="utf-8") as f:
        json.dump(proposal_dict, f, ensure_ascii=False, indent=2)

    # 10a-bis. consensus_results.json (when multi-model)
    if use_consensus and consensus_results:
        # Serialize consensus results (strip non-serializable proposal objects)
        serializable_consensus = []
        for cr in consensus_results:
            entry = {
                "status": cr.get("status"),
                "note": cr.get("note"),
                "agreed_nodes": cr.get("agreed_nodes"),
                "disagreed_nodes": cr.get("disagreed_nodes"),
                "confidence_override": cr.get("confidence_override"),
            }
            # Record per-model proposal IDs
            mp = cr.get("model_proposals", {})
            entry["model_proposals"] = {
                m: (p.proposal_id if p else None) for m, p in mp.items()
            }
            serializable_consensus.append(entry)
        consensus_path = out_path / "consensus_results.json"
        with open(consensus_path, "w", encoding="utf-8") as f:
            json.dump(serializable_consensus, f, ensure_ascii=False, indent=2)

    # 10b. taxonomy_changes.jsonl
    if proposals:
        change_records = generate_change_records(
            proposals, taxonomy_version, book_id,
        )
        changes_path = out_path / "taxonomy_changes.jsonl"
        with open(changes_path, "w", encoding="utf-8") as f:
            for rec in change_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 10c. evolution_review.md
    review_md = generate_review_md(
        signals=signals,
        proposals=proposals,
        science=science,
        taxonomy_version=taxonomy_version,
        taxonomy_map=taxonomy_map,
        model=effective_model_label,
    )
    review_path = out_path / "evolution_review.md"
    with open(review_path, "w", encoding="utf-8") as f:
        f.write(review_md)

    # 11. Print summary
    total_cost = sum(p.cost.get("total_cost", 0) for p in proposals)
    print(f"\n=== Evolution Summary ===")
    print(f"Signals: {len(signals)}")
    print(f"Proposals: {len(proposals)}")
    print(f"No change needed: {len(signals) - len(proposals)}")
    print(f"Total cost: ${total_cost:.4f}")
    print(f"Artifacts written to {output_dir}/")

    return proposal_dict.get("summary", {})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Taxonomy evolution engine: detect signals, propose changes, "
            "generate human review artifacts."
        )
    )

    # Phase 1: Detect + Propose
    parser.add_argument(
        "--extraction-dir",
        help="Directory containing *_extraction.json files",
    )
    parser.add_argument(
        "--assembly-dir", default=None,
        help="Directory with assembly output (optional, for cluster signals)",
    )
    parser.add_argument(
        "--taxonomy", required=True,
        help="Path to current taxonomy YAML",
    )
    parser.add_argument(
        "--science", required=True,
        help="Science name (e.g., imlaa, sarf, nahw, balagha, fiqh, hadith)",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Output directory for proposals and review artifacts",
    )
    parser.add_argument(
        "--book-id", default="",
        help="Book ID (for taxonomy_changes.jsonl records)",
    )

    # LLM configuration
    parser.add_argument(
        "--model", default="claude-sonnet-4-5-20250929",
        help="Model for evolution proposals (default: claude-sonnet-4-5-20250929)",
    )
    parser.add_argument(
        "--models", default=None,
        help=(
            "Comma-separated list of models for multi-model consensus "
            "(e.g., claude-sonnet-4-5-20250929,gpt-4o). Overrides --model."
        ),
    )
    parser.add_argument(
        "--api-key", default=None,
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    )
    parser.add_argument(
        "--openai-key", default=None,
        help="OpenAI API key (or set OPENAI_API_KEY env var)",
    )
    parser.add_argument(
        "--openrouter-key", default=None,
        help="OpenRouter API key (or set OPENROUTER_API_KEY env var)",
    )

    # Signal control
    parser.add_argument(
        "--node-ids", default=None,
        help="Comma-separated node IDs to investigate (user-specified signals)",
    )
    parser.add_argument(
        "--skip-unmapped", action="store_true",
        help="Skip unmapped excerpt signals",
    )
    parser.add_argument(
        "--skip-clusters", action="store_true",
        help="Skip same-book cluster signals",
    )
    parser.add_argument(
        "--skip-category-check", action="store_true",
        help="Skip category-name leaf signals (e.g. مراتب, صفات)",
    )
    parser.add_argument(
        "--skip-multi-topic", action="store_true",
        help="Skip multi-topic excerpt signals (single large excerpt at solo node)",
    )

    # Phase B: Apply / Rollback
    parser.add_argument(
        "--apply", default=None,
        help="Path to evolution_proposal.json to apply",
    )
    parser.add_argument(
        "--rollback", default=None,
        help="Path to rollback_manifest.json to revert an applied evolution",
    )
    parser.add_argument(
        "--registry", default=None,
        help="Path to taxonomy_registry.yaml (default: auto-detected from taxonomy path)",
    )

    # Mode
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Detect signals only, no LLM calls",
    )

    args = parser.parse_args()

    # Route to rollback mode
    if args.rollback:
        result = rollback_evolution(args.rollback)
        print(f"Rollback result: {result['status']}")
        if result.get("errors"):
            for err in result["errors"]:
                print(f"  ERROR: {err}", file=sys.stderr)
        print(f"  Reversed {result['reversed_moves']} file moves")
        return

    # Route to apply mode
    if args.apply:
        result = apply_evolution(
            proposal_path=args.apply,
            taxonomy_path=args.taxonomy,
            assembly_dir=args.assembly_dir,
            output_dir=args.output_dir,
            registry_path=args.registry,
            model=args.model,
            api_key=args.api_key,
            openrouter_key=args.openrouter_key,
            openai_key=args.openai_key,
        )
        print(f"Apply result: {result.get('status', 'unknown')}")
        return

    # Validate required args for detect+propose mode
    if not args.extraction_dir:
        parser.error("--extraction-dir is required (unless using --apply)")

    # Parse node IDs
    node_id_list = None
    if args.node_ids:
        node_id_list = [n.strip() for n in args.node_ids.split(",") if n.strip()]

    # Parse models list
    models_list = None
    if args.models:
        models_list = [m.strip() for m in args.models.split(",") if m.strip()]

    run_evolution(
        extraction_dir=args.extraction_dir,
        taxonomy_path=args.taxonomy,
        science=args.science,
        output_dir=args.output_dir,
        model=args.model,
        models=models_list,
        api_key=args.api_key,
        openrouter_key=args.openrouter_key,
        openai_key=args.openai_key,
        assembly_dir=args.assembly_dir,
        book_id=args.book_id,
        node_ids=node_id_list,
        skip_unmapped=args.skip_unmapped,
        skip_clusters=args.skip_clusters,
        skip_category_check=args.skip_category_check,
        skip_multi_topic=args.skip_multi_topic,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

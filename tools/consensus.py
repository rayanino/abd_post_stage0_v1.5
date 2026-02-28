#!/usr/bin/env python3
"""
Multi-Model Consensus Engine for ABD Extraction
=================================================
Compares extraction outputs from multiple models for the same passage,
identifies agreements and disagreements, resolves disagreements via an
arbiter LLM, and produces a consensus result with full traceability.

The key challenge: two models produce structurally incompatible atom-level
outputs (different atom counts, boundaries, IDs). Comparison works at the
excerpt level using text overlap, not atom-ID matching.
"""

import copy
import json
import re
import unicodedata


# ---------------------------------------------------------------------------
# Arabic text normalization for comparison
# ---------------------------------------------------------------------------

# Unicode range for Arabic diacritics (tashkeel)
_DIACRITICS = re.compile(
    "[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC"
    "\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]"
)

# Tatweel (kashida) used for text stretching
_TATWEEL = "\u0640"


def strip_diacritics(text: str) -> str:
    """Remove Arabic diacritics and tatweel for fuzzy comparison."""
    text = _DIACRITICS.sub("", text)
    text = text.replace(_TATWEEL, "")
    return text


def normalize_for_comparison(text: str) -> str:
    """Normalize Arabic text for comparison: strip diacritics, collapse whitespace."""
    text = strip_diacritics(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Character n-gram Jaccard similarity
# ---------------------------------------------------------------------------

def char_ngrams(text: str, n: int = 5) -> set[str]:
    """Generate character n-grams from text (whitespace collapsed).

    For very short texts (< n chars), uses progressively smaller n-grams
    down to bigrams, so short Arabic words still produce meaningful grams.
    """
    clean = re.sub(r"\s+", "", text)
    if not clean:
        return set()
    # For short text, use smaller n-grams (minimum bigrams)
    effective_n = min(n, max(2, len(clean)))
    if len(clean) < effective_n:
        return {clean}
    return {clean[i:i + effective_n] for i in range(len(clean) - effective_n + 1)}


def text_overlap_ratio(text_a: str, text_b: str) -> float:
    """Jaccard similarity on character n-grams of normalized Arabic text.

    Returns 0.0-1.0. Strips diacritics before comparison so that
    minor diacritical differences don't tank the score.

    Uses adaptive n-gram size: 5-grams for normal text, smaller for short
    text (minimum bigrams). Both texts use the same effective n.
    """
    if not text_a or not text_b:
        return 0.0
    norm_a = normalize_for_comparison(text_a)
    norm_b = normalize_for_comparison(text_b)
    if not norm_a or not norm_b:
        return 0.0
    # Use the same n for both to keep Jaccard meaningful
    clean_a = re.sub(r"\s+", "", norm_a)
    clean_b = re.sub(r"\s+", "", norm_b)
    effective_n = min(5, max(2, min(len(clean_a), len(clean_b))))
    grams_a = char_ngrams(norm_a, effective_n)
    grams_b = char_ngrams(norm_b, effective_n)
    if not grams_a or not grams_b:
        return 0.0
    intersection = grams_a & grams_b
    union = grams_a | grams_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Excerpt text span computation
# ---------------------------------------------------------------------------

def build_atom_lookup(result: dict) -> dict[str, dict]:
    """Build atom_id -> atom dict from extraction result."""
    lookup = {}
    for atom in result.get("atoms", []):
        aid = atom.get("atom_id", "")
        if aid:
            lookup[aid] = atom
    return lookup


def _extract_atom_id(entry) -> str:
    """Get atom_id from a string or object entry."""
    if isinstance(entry, dict):
        return entry.get("atom_id", "")
    return str(entry)


def compute_excerpt_text_span(excerpt: dict, atom_lookup: dict) -> str:
    """Concatenate core atom texts for an excerpt.

    This is the 'text footprint' of an excerpt -- what Arabic text it covers.
    Used for matching excerpts across models. Handles None/missing core_atoms.
    """
    core_atoms = excerpt.get("core_atoms")
    if not core_atoms:
        return ""
    texts = []
    for entry in core_atoms:
        aid = _extract_atom_id(entry)
        atom = atom_lookup.get(aid)
        if atom:
            texts.append(atom.get("text", ""))
    return " ".join(texts)


# ---------------------------------------------------------------------------
# Atom merging for cross-model consensus
# ---------------------------------------------------------------------------

def _model_tag(model_name: str) -> str:
    """Short tag for model name disambiguation in atom IDs."""
    if "/" in model_name:
        return model_name.split("/")[-1][:10]
    return model_name[:10]


def _remap_atom_refs(excerpt: dict, remap: dict[str, str]) -> None:
    """Remap atom IDs in an excerpt's core_atoms and context_atoms in-place."""
    for field in ("core_atoms", "context_atoms"):
        entries = excerpt.get(field)
        if not entries:
            continue
        for i, entry in enumerate(entries):
            if isinstance(entry, dict):
                old_id = entry.get("atom_id", "")
                if old_id in remap:
                    entry["atom_id"] = remap[old_id]
            elif isinstance(entry, str):
                if entry in remap:
                    entries[i] = remap[entry]


def _merge_atoms_for_consensus(
    result_a: dict,
    result_b: dict,
    consensus_excerpts: list[dict],
    model_a: str,
    model_b: str,
    winning_model: str,
) -> list[dict]:
    """Build merged atom list ensuring all excerpt atom references are valid.

    When the arbiter picks an excerpt from the non-winning model, that
    excerpt's core_atoms reference atom IDs from a different atom space.
    This function merges atoms from both models, disambiguating collisions
    (same ID, different text) by appending a model tag to the non-winning
    model's atom IDs and updating the excerpt references.
    """
    winning_result = result_a if winning_model == model_a else result_b
    losing_result = result_b if winning_model == model_a else result_a
    losing_model = model_b if winning_model == model_a else model_a

    winning_atoms = {}
    for a in winning_result.get("atoms", []):
        aid = a.get("atom_id", "")
        if aid:
            winning_atoms[aid] = a

    losing_atoms = {}
    for a in losing_result.get("atoms", []):
        aid = a.get("atom_id", "")
        if aid:
            losing_atoms[aid] = a

    # Identify which excerpts come from the losing model.
    # Deep-copy them so _remap_atom_refs doesn't mutate the original
    # model results (which may still be referenced for audit/raw saves).
    losing_excerpts = []
    for ce in consensus_excerpts:
        if ce["source_model"] != winning_model:
            # Deep-copy so remap doesn't corrupt the original result dicts
            ce["excerpt"] = copy.deepcopy(ce["excerpt"])
            losing_excerpts.append(ce["excerpt"])

    if not losing_excerpts:
        # All excerpts from winning model — no merge needed
        return winning_result.get("atoms", [])

    # Collect atom IDs needed by losing model's excerpts
    needed_ids = set()
    for exc in losing_excerpts:
        for entry in (exc.get("core_atoms") or []):
            aid = _extract_atom_id(entry)
            if aid:
                needed_ids.add(aid)
        for entry in (exc.get("context_atoms") or []):
            aid = _extract_atom_id(entry)
            if aid:
                needed_ids.add(aid)

    # Check for collisions: same ID, different text
    remap = {}
    tag = _model_tag(losing_model)
    for aid in needed_ids:
        if aid in winning_atoms and aid in losing_atoms:
            w_text = winning_atoms[aid].get("text", "")
            l_text = losing_atoms[aid].get("text", "")
            if w_text != l_text:
                # Real collision — disambiguate with _tag suffix to keep
                # the 3-segment atom ID format (book:section:seq)
                parts = aid.rsplit(":", 1)
                if len(parts) == 2:
                    remap[aid] = f"{parts[0]}:{parts[1]}_{tag}"
                else:
                    remap[aid] = f"{aid}_{tag}"

    # Build merged atom list
    merged = list(winning_result.get("atoms", []))
    added_ids = set(winning_atoms.keys())

    for aid in needed_ids:
        if aid in remap:
            # Colliding atom — add with new ID
            if aid in losing_atoms:
                atom_copy = dict(losing_atoms[aid])
                atom_copy["atom_id"] = remap[aid]
                atom_copy["_source_model"] = losing_model
                merged.append(atom_copy)
                added_ids.add(remap[aid])
        elif aid not in added_ids:
            # Non-colliding atom missing from winning — add it
            if aid in losing_atoms:
                atom_copy = dict(losing_atoms[aid])
                atom_copy["_source_model"] = losing_model
                merged.append(atom_copy)
                added_ids.add(aid)

    # Remap atom references in losing excerpts
    if remap:
        for exc in losing_excerpts:
            _remap_atom_refs(exc, remap)

    return merged


# ---------------------------------------------------------------------------
# Optimal bipartite matching (replaces greedy)
# ---------------------------------------------------------------------------

def _optimal_assignment(overlap_matrix: list[list[float]],
                        threshold: float) -> list[tuple[int, int]]:
    """Find optimal bipartite matching maximizing total overlap.

    Uses DP with bitmask over the smaller dimension. For typical extraction
    (2-10 excerpts per model), this is instant. Falls back to greedy for
    n > 20 on the smaller side.

    Returns list of (row, col) index pairs.
    """
    n_a = len(overlap_matrix)
    n_b = len(overlap_matrix[0]) if n_a > 0 else 0

    if n_a == 0 or n_b == 0:
        return []

    # Ensure bitmask is over the smaller dimension
    transposed = False
    matrix = overlap_matrix
    if n_b > n_a:
        matrix = [[overlap_matrix[i][j] for i in range(n_a)] for j in range(n_b)]
        n_a, n_b = n_b, n_a
        transposed = True

    if n_b > 20:
        # Fallback: too many columns for bitmask DP
        return None  # caller uses greedy

    # DP: dp[(row, mask)] = best total overlap from row onwards with mask
    # of used columns
    memo = {}

    def dp(row: int, used: int) -> float:
        if row == n_a:
            return 0.0
        key = (row, used)
        if key in memo:
            return memo[key]
        # Option: skip this row
        best = dp(row + 1, used)
        # Option: match with available column
        for col in range(n_b):
            if used & (1 << col):
                continue
            w = matrix[row][col]
            if w >= threshold:
                val = w + dp(row + 1, used | (1 << col))
                if val > best:
                    best = val
        memo[key] = best
        return best

    # Compute optimal value
    dp(0, 0)

    # Reconstruct assignment
    pairs = []
    used = 0
    for row in range(n_a):
        optimal_from_here = dp(row, used)
        skip_val = dp(row + 1, used)
        # Try each column to see which one achieves optimal
        matched = False
        for col in range(n_b):
            if used & (1 << col):
                continue
            w = matrix[row][col]
            if w >= threshold:
                val = w + dp(row + 1, used | (1 << col))
                if abs(val - optimal_from_here) < 1e-9:
                    if transposed:
                        pairs.append((col, row))
                    else:
                        pairs.append((row, col))
                    used |= (1 << col)
                    matched = True
                    break
        # If not matched, row is skipped

    return pairs


# ---------------------------------------------------------------------------
# Excerpt matching across models
# ---------------------------------------------------------------------------

def match_excerpts(
    excerpts_a: list[dict],
    excerpts_b: list[dict],
    atoms_a: dict[str, dict],
    atoms_b: dict[str, dict],
    threshold: float = 0.5,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Match excerpts between two models by text overlap.

    Uses optimal bipartite matching (DP with bitmask) to maximize total
    overlap across all pairs. Falls back to greedy for large inputs.

    Returns:
        matched: list of dicts with keys:
            excerpt_a, excerpt_b, text_a, text_b, text_overlap,
            same_taxonomy, taxonomy_a, taxonomy_b
        unmatched_a: excerpts from model A with no match
        unmatched_b: excerpts from model B with no match
    """
    # Compute text spans for all excerpts
    spans_a = [(exc, compute_excerpt_text_span(exc, atoms_a)) for exc in excerpts_a]
    spans_b = [(exc, compute_excerpt_text_span(exc, atoms_b)) for exc in excerpts_b]

    n_a = len(spans_a)
    n_b = len(spans_b)

    if n_a == 0 or n_b == 0:
        return [], list(excerpts_a), list(excerpts_b)

    # Build full overlap matrix
    overlap_matrix = []
    for i, (_, text_a) in enumerate(spans_a):
        row = []
        for j, (_, text_b) in enumerate(spans_b):
            row.append(text_overlap_ratio(text_a, text_b))
        overlap_matrix.append(row)

    # Try optimal matching
    pairs = _optimal_assignment(overlap_matrix, threshold)

    if pairs is None:
        # Fallback to greedy for large inputs
        pairs = _greedy_assignment(overlap_matrix, threshold, n_a, n_b)

    # Build result
    matched = []
    used_a = set()
    used_b = set()

    for i, j in pairs:
        used_a.add(i)
        used_b.add(j)
        exc_a, text_a = spans_a[i]
        exc_b, text_b = spans_b[j]
        tax_a = exc_a.get("taxonomy_node_id", "")
        tax_b = exc_b.get("taxonomy_node_id", "")

        matched.append({
            "excerpt_a": exc_a,
            "excerpt_b": exc_b,
            "text_a": text_a,
            "text_b": text_b,
            "text_overlap": overlap_matrix[i][j],
            "same_taxonomy": tax_a == tax_b,
            "taxonomy_a": tax_a,
            "taxonomy_b": tax_b,
        })

    unmatched_a = [exc for i, (exc, _) in enumerate(spans_a) if i not in used_a]
    unmatched_b = [exc for j, (exc, _) in enumerate(spans_b) if j not in used_b]

    return matched, unmatched_a, unmatched_b


def _greedy_assignment(overlap_matrix: list[list[float]],
                       threshold: float,
                       n_a: int, n_b: int) -> list[tuple[int, int]]:
    """Greedy fallback matching for large inputs."""
    overlaps = []
    for i in range(n_a):
        for j in range(n_b):
            ratio = overlap_matrix[i][j]
            if ratio >= threshold:
                overlaps.append((ratio, i, j))
    overlaps.sort(key=lambda x: x[0], reverse=True)

    pairs = []
    used_a = set()
    used_b = set()
    for ratio, i, j in overlaps:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((i, j))

    return pairs


# ---------------------------------------------------------------------------
# Coverage agreement
# ---------------------------------------------------------------------------

def compute_coverage_agreement(result_a: dict, result_b: dict) -> dict:
    """Compare overall text coverage between two model outputs.

    Returns dict with coverage_agreement_ratio and detail counts.
    """
    atoms_a = build_atom_lookup(result_a)
    atoms_b = build_atom_lookup(result_b)

    # Collect all core atom texts from each model
    def _all_core_texts(result, atoms):
        texts = set()
        for exc in result.get("excerpts", []):
            core = exc.get("core_atoms")
            if not core:
                continue
            for entry in core:
                aid = _extract_atom_id(entry)
                atom = atoms.get(aid)
                if atom:
                    texts.add(normalize_for_comparison(atom.get("text", "")))
        return texts

    texts_a = _all_core_texts(result_a, atoms_a)
    texts_b = _all_core_texts(result_b, atoms_b)

    # Use character-level coverage for a more precise comparison
    chars_a = set()
    for t in texts_a:
        chars_a.update(char_ngrams(t, 5))
    chars_b = set()
    for t in texts_b:
        chars_b.update(char_ngrams(t, 5))

    both = chars_a & chars_b
    a_only = chars_a - chars_b
    b_only = chars_b - chars_a
    total = chars_a | chars_b

    ratio = len(both) / len(total) if total else 1.0

    return {
        "coverage_agreement_ratio": round(ratio, 4),
        "covered_both_ngrams": len(both),
        "covered_a_only_ngrams": len(a_only),
        "covered_b_only_ngrams": len(b_only),
        "total_ngrams": len(total),
    }


# ---------------------------------------------------------------------------
# Footnote excerpt comparison + merging
# ---------------------------------------------------------------------------

def compare_footnote_excerpts(
    result_a: dict,
    result_b: dict,
    model_a: str,
    model_b: str,
) -> dict:
    """Compare footnote excerpts between two models.

    Footnote excerpts are simpler (they have inline text, no atom references)
    so we compare them by text content directly.

    Returns dict with:
        matched_count, unmatched_a_count, unmatched_b_count,
        disagreements (list of dicts),
        unmatched_a (list), unmatched_b (list)
    """
    fn_a = result_a.get("footnote_excerpts") or []
    fn_b = result_b.get("footnote_excerpts") or []

    if not fn_a and not fn_b:
        return {
            "matched_count": 0,
            "unmatched_a_count": 0,
            "unmatched_b_count": 0,
            "disagreements": [],
            "unmatched_a": [],
            "unmatched_b": [],
        }

    # Build text spans for footnote excerpts
    def _fn_text(fn_exc):
        return fn_exc.get("text", "")

    spans_a = [(fn, _fn_text(fn)) for fn in fn_a]
    spans_b = [(fn, _fn_text(fn)) for fn in fn_b]

    # Pairwise matching by text overlap
    overlaps = []
    for i, (fn_exc_a, text_a) in enumerate(spans_a):
        for j, (fn_exc_b, text_b) in enumerate(spans_b):
            ratio = text_overlap_ratio(text_a, text_b)
            if ratio >= 0.5:
                overlaps.append((ratio, i, j))

    overlaps.sort(key=lambda x: x[0], reverse=True)
    used_a = set()
    used_b = set()
    matched_count = 0

    for ratio, i, j in overlaps:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        matched_count += 1

    unmatched_a = [fn for i, (fn, _) in enumerate(spans_a) if i not in used_a]
    unmatched_b = [fn for j, (fn, _) in enumerate(spans_b) if j not in used_b]

    disagreements = []
    for fn in unmatched_a:
        disagreements.append({
            "type": "unmatched_footnote",
            "found_by": model_a,
            "not_found_by": model_b,
            "excerpt_id": fn.get("excerpt_id", "?"),
        })
    for fn in unmatched_b:
        disagreements.append({
            "type": "unmatched_footnote",
            "found_by": model_b,
            "not_found_by": model_a,
            "excerpt_id": fn.get("excerpt_id", "?"),
        })

    return {
        "matched_count": matched_count,
        "unmatched_a_count": len(unmatched_a),
        "unmatched_b_count": len(unmatched_b),
        "disagreements": disagreements,
        "unmatched_a": unmatched_a,
        "unmatched_b": unmatched_b,
    }


def merge_footnote_excerpts(
    result_a: dict,
    result_b: dict,
    model_a: str,
    model_b: str,
    winning_model: str,
    comparison: dict,
) -> list[dict]:
    """Merge footnote excerpts: winning model's matched + unmatched from both.

    Ensures footnotes found by either model are included in the output,
    not silently dropped.
    """
    winning_result = result_a if winning_model == model_a else result_b
    base = list(winning_result.get("footnote_excerpts") or [])

    # Add unmatched footnotes from the OTHER model (winning's unmatched
    # are already in base)
    if winning_model == model_a:
        # Add model B's unmatched
        for fn in comparison.get("unmatched_b", []):
            fn_copy = dict(fn)
            fn_copy["_consensus_flag"] = f"only_found_by_{model_b}"
            base.append(fn_copy)
    else:
        # Add model A's unmatched
        for fn in comparison.get("unmatched_a", []):
            fn_copy = dict(fn)
            fn_copy["_consensus_flag"] = f"only_found_by_{model_a}"
            base.append(fn_copy)

    return base


# ---------------------------------------------------------------------------
# Exclusion comparison
# ---------------------------------------------------------------------------

def compare_exclusions(
    result_a: dict,
    result_b: dict,
    model_a: str,
    model_b: str,
) -> dict:
    """Compare exclusion decisions between two models.

    Since atom IDs differ between models, we compare by normalized text.
    Returns dict with agreement stats and disagreement details.
    """
    atoms_a = build_atom_lookup(result_a)
    atoms_b = build_atom_lookup(result_b)

    # Map exclusions by normalized text — use list to handle duplicates
    def _exclusion_texts(result, atoms):
        texts = {}
        for exc in result.get("exclusions") or []:
            aid = exc.get("atom_id", "")
            atom = atoms.get(aid)
            if atom:
                norm = normalize_for_comparison(atom.get("text", ""))
                if norm:
                    # Keep last reason per text (for simple comparison)
                    texts[norm] = exc.get("exclusion_reason", "unknown")
        return texts

    excl_a = _exclusion_texts(result_a, atoms_a)
    excl_b = _exclusion_texts(result_b, atoms_b)

    texts_a = set(excl_a.keys())
    texts_b = set(excl_b.keys())

    both = texts_a & texts_b
    a_only = texts_a - texts_b
    b_only = texts_b - texts_a

    disagreements = []
    for text in a_only:
        disagreements.append({
            "type": "exclusion_disagreement",
            "excluded_by": model_a,
            "not_excluded_by": model_b,
            "reason": excl_a[text],
            "text_preview": text[:80],
        })
    for text in b_only:
        disagreements.append({
            "type": "exclusion_disagreement",
            "excluded_by": model_b,
            "not_excluded_by": model_a,
            "reason": excl_b[text],
            "text_preview": text[:80],
        })

    return {
        "agreed_count": len(both),
        "a_only_count": len(a_only),
        "b_only_count": len(b_only),
        "disagreements": disagreements,
    }


# ---------------------------------------------------------------------------
# Context atom comparison
# ---------------------------------------------------------------------------

def compare_context_atoms(
    matched_pairs: list[dict],
    atoms_a: dict[str, dict],
    atoms_b: dict[str, dict],
) -> list[dict]:
    """Compare context atom selections for matched excerpt pairs.

    Context atoms affect self-containment — disagreements here mean the
    models disagree on what surrounding context an excerpt needs.
    """
    disagreements = []
    for m in matched_pairs:
        ctx_a = m["excerpt_a"].get("context_atoms") or []
        ctx_b = m["excerpt_b"].get("context_atoms") or []

        # Compare by normalized text since atom IDs differ
        texts_a = set()
        for entry in ctx_a:
            aid = _extract_atom_id(entry)
            atom = atoms_a.get(aid)
            if atom:
                texts_a.add(normalize_for_comparison(atom.get("text", "")))

        texts_b = set()
        for entry in ctx_b:
            aid = _extract_atom_id(entry)
            atom = atoms_b.get(aid)
            if atom:
                texts_b.add(normalize_for_comparison(atom.get("text", "")))

        if texts_a != texts_b:
            disagreements.append({
                "excerpt_a_id": m["excerpt_a"].get("excerpt_id", "?"),
                "excerpt_b_id": m["excerpt_b"].get("excerpt_id", "?"),
                "a_count": len(texts_a),
                "b_count": len(texts_b),
                "a_only_count": len(texts_a - texts_b),
                "b_only_count": len(texts_b - texts_a),
            })

    return disagreements


# ---------------------------------------------------------------------------
# Arbiter prompt templates
# ---------------------------------------------------------------------------

ARBITER_PLACEMENT_PROMPT = """\
You are an expert arbiter for the Arabic Book Digester (ABD) pipeline.

Two models independently extracted the same passage and produced excerpts. \
They agree on the excerpt content but DISAGREE on taxonomy placement.

## The Excerpt Text
{excerpt_text}

## Excerpt Metadata
- Case types (Model A): {case_types_a}
- Case types (Model B): {case_types_b}
- Boundary reasoning (Model A): {boundary_reasoning_a}
- Boundary reasoning (Model B): {boundary_reasoning_b}

## Model A ({model_a}) Placement
- Taxonomy node: {taxonomy_a}
- Taxonomy path: {taxonomy_path_a}

## Model B ({model_b}) Placement
- Taxonomy node: {taxonomy_b}
- Taxonomy path: {taxonomy_path_b}

## Relevant Taxonomy Section
{taxonomy_context}

## Your Task
Analyze the Arabic text and the two proposed taxonomy placements. Determine \
which placement is CORRECT, or indicate that NEITHER is correct. Consider:
1. What topic does this excerpt actually teach?
2. Which taxonomy leaf most precisely matches that topic?
3. Is one placement more specific/accurate than the other?
4. Could BOTH placements be wrong?

Return JSON:
{{
  "correct_placement": "{taxonomy_a}" or "{taxonomy_b}" or "neither",
  "reasoning": "detailed explanation of why this placement is correct",
  "confidence": "certain" or "likely" or "uncertain"
}}
"""

ARBITER_UNMATCHED_PROMPT = """\
You are an expert arbiter for the Arabic Book Digester (ABD) pipeline.

Two models independently extracted the same passage. One model found an \
excerpt that the other model did NOT produce.

## The Passage Text (relevant section)
{passage_context}

## The Disputed Excerpt
Found by: {source_model}
Not found by: {other_model}

Excerpt text:
{excerpt_text}

Proposed taxonomy node: {taxonomy_node}
Proposed taxonomy path: {taxonomy_path}

## Your Task
Determine whether this excerpt is VALID -- does this text constitute a \
legitimate, self-contained teaching unit that belongs in the taxonomy?

Consider:
1. Is the text a coherent teaching unit on a specific topic?
2. Does it carry enough content to be independently useful?
3. Could the other model have reasonably excluded it (e.g., it's too small, \
overlaps with another excerpt, or is metadata/apparatus)?

Return JSON:
{{
  "verdict": "keep" or "discard",
  "reasoning": "detailed explanation",
  "confidence": "certain" or "likely" or "uncertain"
}}
"""

# Valid arbiter confidence values (normalized to lowercase)
_VALID_CONFIDENCES = {"certain", "likely", "uncertain"}


def _normalize_confidence(raw: str) -> str:
    """Normalize arbiter confidence to one of: certain, likely, uncertain."""
    if not raw or not isinstance(raw, str):
        return "uncertain"
    lower = raw.strip().lower()
    if lower in _VALID_CONFIDENCES:
        return lower
    # Map common variations
    if lower in ("high", "very confident", "sure", "definite", "100%"):
        return "certain"
    if lower in ("medium", "moderate", "probably", "fairly confident"):
        return "likely"
    return "uncertain"


def _compute_arbiter_cost(
    input_tokens: int,
    output_tokens: int,
    arbiter_pricing: tuple[float, float] | None = None,
) -> float:
    """Compute arbiter cost from token counts and pricing.

    arbiter_pricing: (input_per_1M, output_per_1M) or None for default.
    """
    if arbiter_pricing:
        inp_rate, out_rate = arbiter_pricing
    else:
        inp_rate, out_rate = 3.0, 15.0  # default: Claude Sonnet pricing
    return input_tokens * inp_rate / 1_000_000 + output_tokens * out_rate / 1_000_000


# ---------------------------------------------------------------------------
# Arbiter resolution
# ---------------------------------------------------------------------------

def resolve_placement_disagreement(
    match: dict,
    model_a: str,
    model_b: str,
    taxonomy_yaml: str,
    call_llm_fn,
    arbiter_model: str,
    arbiter_api_key: str,
    arbiter_pricing: tuple[float, float] | None = None,
    preferred_placement: str | None = None,
) -> dict:
    """Call arbiter LLM to resolve a taxonomy placement disagreement.

    Returns dict with: correct_placement, reasoning, confidence, cost.
    ``preferred_placement`` should be the winning model's taxonomy node,
    used as fallback when the arbiter returns invalid output or fails.
    """
    excerpt_text = match["text_a"]  # use model A's text (they overlap)

    # Extract relevant taxonomy context (the paths around both nodes)
    taxonomy_path_a = match["excerpt_a"].get("taxonomy_path", match["taxonomy_a"])
    taxonomy_path_b = match["excerpt_b"].get("taxonomy_path", match["taxonomy_b"])

    # Include case_types and boundary_reasoning for better arbiter decisions
    case_types_a = ", ".join(match["excerpt_a"].get("case_types", []))
    case_types_b = ", ".join(match["excerpt_b"].get("case_types", []))
    boundary_a = match["excerpt_a"].get("boundary_reasoning", "(none)")
    boundary_b = match["excerpt_b"].get("boundary_reasoning", "(none)")

    prompt = ARBITER_PLACEMENT_PROMPT.format(
        excerpt_text=excerpt_text,
        model_a=model_a,
        model_b=model_b,
        taxonomy_a=match["taxonomy_a"],
        taxonomy_b=match["taxonomy_b"],
        taxonomy_path_a=taxonomy_path_a,
        taxonomy_path_b=taxonomy_path_b,
        case_types_a=case_types_a or "(none)",
        case_types_b=case_types_b or "(none)",
        boundary_reasoning_a=boundary_a,
        boundary_reasoning_b=boundary_b,
        taxonomy_context=_extract_taxonomy_context(
            taxonomy_yaml, match["taxonomy_a"], match["taxonomy_b"]
        ),
    )

    try:
        response = call_llm_fn(
            "You are a precise Arabic linguistics taxonomy arbiter. Return JSON only.",
            prompt,
            arbiter_model,
            arbiter_api_key,
        )
        parsed = response.get("parsed")
        if not isinstance(parsed, dict):
            raise ValueError(f"Arbiter returned non-dict: {type(parsed)}")

        inp_tok = response.get("input_tokens", 0)
        out_tok = response.get("output_tokens", 0)
        cost = _compute_arbiter_cost(inp_tok, out_tok, arbiter_pricing)

        raw_placement = parsed.get("correct_placement", "")
        # Handle "neither" — arbiter says both are wrong
        if raw_placement == "neither":
            return {
                "correct_placement": "neither",
                "reasoning": str(parsed.get("reasoning", "")),
                "confidence": _normalize_confidence(parsed.get("confidence", "")),
                "cost": cost,
                "input_tokens": inp_tok,
                "output_tokens": out_tok,
            }
        # Validate placement is one of the two options
        fallback = preferred_placement or match["taxonomy_a"]
        if raw_placement not in (match["taxonomy_a"], match["taxonomy_b"]):
            raw_placement = fallback

        return {
            "correct_placement": raw_placement,
            "reasoning": str(parsed.get("reasoning", "")),
            "confidence": _normalize_confidence(parsed.get("confidence", "")),
            "cost": cost,
            "input_tokens": inp_tok,
            "output_tokens": out_tok,
        }
    except Exception as e:
        # Arbiter failed -- fall back to preferred model
        fallback = preferred_placement or match["taxonomy_a"]
        return {
            "correct_placement": fallback,
            "reasoning": f"Arbiter call failed: {e}. Falling back to preferred model placement.",
            "confidence": "uncertain",
            "cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        }


def resolve_unmatched_excerpt(
    excerpt: dict,
    atom_lookup: dict,
    source_model: str,
    other_model: str,
    passage_text: str,
    call_llm_fn,
    arbiter_model: str,
    arbiter_api_key: str,
    arbiter_pricing: tuple[float, float] | None = None,
) -> dict:
    """Call arbiter LLM to decide whether an unmatched excerpt should be kept.

    Returns dict with: verdict, reasoning, confidence, cost
    """
    excerpt_text = compute_excerpt_text_span(excerpt, atom_lookup)
    taxonomy_node = excerpt.get("taxonomy_node_id", "unknown")
    taxonomy_path = excerpt.get("taxonomy_path", taxonomy_node)

    # Provide surrounding passage context (truncated at word boundary)
    if len(passage_text) > 2000:
        ctx = passage_text[:2000]
        # Don't cut mid-word
        last_space = ctx.rfind(" ")
        if last_space > 1500:
            ctx = ctx[:last_space]
    else:
        ctx = passage_text

    prompt = ARBITER_UNMATCHED_PROMPT.format(
        passage_context=ctx,
        source_model=source_model,
        other_model=other_model,
        excerpt_text=excerpt_text,
        taxonomy_node=taxonomy_node,
        taxonomy_path=taxonomy_path,
    )

    try:
        response = call_llm_fn(
            "You are a precise Arabic linguistics excerpt arbiter. Return JSON only.",
            prompt,
            arbiter_model,
            arbiter_api_key,
        )
        parsed = response.get("parsed")
        if not isinstance(parsed, dict):
            raise ValueError(f"Arbiter returned non-dict: {type(parsed)}")

        inp_tok = response.get("input_tokens", 0)
        out_tok = response.get("output_tokens", 0)
        cost = _compute_arbiter_cost(inp_tok, out_tok, arbiter_pricing)

        raw_verdict = str(parsed.get("verdict", "keep")).strip().lower()
        if raw_verdict not in ("keep", "discard"):
            raw_verdict = "keep"  # safe default

        return {
            "verdict": raw_verdict,
            "reasoning": str(parsed.get("reasoning", "")),
            "confidence": _normalize_confidence(parsed.get("confidence", "")),
            "cost": cost,
            "input_tokens": inp_tok,
            "output_tokens": out_tok,
        }
    except Exception as e:
        # Arbiter failed -- default to keeping the excerpt
        return {
            "verdict": "keep",
            "reasoning": f"Arbiter call failed: {e}. Defaulting to keep.",
            "confidence": "uncertain",
            "cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        }


def _extract_taxonomy_context(taxonomy_yaml: str, node_a: str, node_b: str) -> str:
    """Extract the taxonomy YAML lines around two nodes for arbiter context.

    Handles both v0 format (``node_id:\\n  _leaf: true``) and v1 format
    (``- id: node_id\\n  leaf: true``).
    """
    lines = taxonomy_yaml.split("\n")
    relevant = []
    matched_indices: set[int] = set()
    targets = {node_a, node_b}

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
        if bare in targets and bare != stripped:  # must have had a trailing ':'
            matched_indices.add(i)

    for idx in sorted(matched_indices):
        start = max(0, idx - 5)
        end = min(len(lines), idx + 6)
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
    return f"(nodes {node_a} and {node_b} not found in taxonomy)"


# ---------------------------------------------------------------------------
# Main consensus builder
# ---------------------------------------------------------------------------

# Taxonomy nodes that indicate classification failure, not real agreement
_UNMAPPED_NODES = {"_unmapped", "__unmapped", "unmapped"}


def _is_unmapped(node: str) -> bool:
    """Check if a taxonomy node is an unmapped variant."""
    return node in _UNMAPPED_NODES


def build_consensus(
    passage_id: str,
    result_a: dict,
    result_b: dict,
    model_a: str,
    model_b: str,
    issues_a: dict,
    issues_b: dict,
    prefer_model: str | None = None,
    threshold: float = 0.5,
    call_llm_fn=None,
    arbiter_model: str | None = None,
    arbiter_api_key: str | None = None,
    taxonomy_yaml: str = "",
    passage_text: str = "",
    arbiter_pricing: tuple[float, float] | None = None,
) -> dict:
    """Build consensus from two model outputs for the same passage.

    When models agree: high confidence, use preferred model's output.
    When models disagree: call arbiter LLM to resolve, document everything.

    Returns dict with keys:
        passage_id, atoms, excerpts, footnote_excerpts, exclusions, notes,
        consensus_meta
    """
    atoms_a = build_atom_lookup(result_a)
    atoms_b = build_atom_lookup(result_b)

    # Match excerpts by text overlap (optimal matching)
    matched, unmatched_a, unmatched_b = match_excerpts(
        result_a.get("excerpts", []),
        result_b.get("excerpts", []),
        atoms_a, atoms_b,
        threshold=threshold,
    )

    # Determine preferred model (fewer issues wins, tie goes to model_a)
    issues_a_count = len(issues_a.get("errors", [])) + len(issues_a.get("warnings", []))
    issues_b_count = len(issues_b.get("errors", [])) + len(issues_b.get("warnings", []))
    if prefer_model:
        winning = prefer_model
    elif issues_a_count <= issues_b_count:
        winning = model_a
    else:
        winning = model_b

    winning_result = result_a if winning == model_a else result_b

    # Process each matched pair
    consensus_excerpts = []
    disagreements = []
    discarded_excerpts = []
    arbiter_cost = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0}

    for m in matched:
        tax_a = m["taxonomy_a"]
        tax_b = m["taxonomy_b"]
        both_unmapped = _is_unmapped(tax_a) and _is_unmapped(tax_b)

        if both_unmapped:
            # BOTH UNMAPPED -- classification failure, NOT real agreement.
            # Checked first because _unmapped variants (e.g., "_unmapped" vs
            # "__unmapped") may have same_taxonomy=False, but both indicate
            # the same failure — don't waste arbiter calls on that.
            exc = m["excerpt_a"] if winning == model_a else m["excerpt_b"]
            detail = {
                "type": "both_unmapped",
                "text_overlap": round(m["text_overlap"], 4),
                "arbiter_resolution": None,
            }
            disagreements.append(detail)
            consensus_excerpts.append({
                "excerpt": exc,
                "source_model": winning,
                "confidence": "low",
                "agreement": "both_unmapped",
                "flags": [
                    "Both models placed at _unmapped (classification failure)"
                ],
                "disagreement_detail": detail,
            })
        elif _is_unmapped(tax_a) != _is_unmapped(tax_b):
            # ONE UNMAPPED, ONE REAL -- auto-pick the real placement.
            # No arbiter needed: the model that found a real node is clearly
            # more informative than one that couldn't classify at all.
            if _is_unmapped(tax_a):
                chosen_exc = m["excerpt_b"]
                source = model_b
                real_tax = tax_b
            else:
                chosen_exc = m["excerpt_a"]
                source = model_a
                real_tax = tax_a
            detail = {
                "type": "one_unmapped",
                "unmapped_model": model_a if _is_unmapped(tax_a) else model_b,
                "real_placement": real_tax,
                "text_overlap": round(m["text_overlap"], 4),
                "arbiter_resolution": None,
            }
            disagreements.append(detail)
            consensus_excerpts.append({
                "excerpt": chosen_exc,
                "source_model": source,
                "confidence": "medium",
                "agreement": "one_unmapped",
                "flags": [
                    f"One model placed at {real_tax}, other at _unmapped — "
                    f"auto-picked real placement"
                ],
                "disagreement_detail": detail,
            })
        elif m["same_taxonomy"]:
            # FULL AGREEMENT -- high confidence
            exc = m["excerpt_a"] if winning == model_a else m["excerpt_b"]
            consensus_excerpts.append({
                "excerpt": exc,
                "source_model": winning,
                "confidence": "high",
                "agreement": "full",
                "flags": [],
                "disagreement_detail": None,
            })
        else:
            # PLACEMENT DISAGREEMENT -- call arbiter
            resolution = None
            if call_llm_fn and arbiter_model and arbiter_api_key:
                # Pass preferred placement so fallback uses winning model
                pref_tax = tax_a if winning == model_a else tax_b
                resolution = resolve_placement_disagreement(
                    m, model_a, model_b, taxonomy_yaml,
                    call_llm_fn, arbiter_model, arbiter_api_key,
                    arbiter_pricing, preferred_placement=pref_tax,
                )
                arbiter_cost["input_tokens"] += resolution.get("input_tokens", 0)
                arbiter_cost["output_tokens"] += resolution.get("output_tokens", 0)
                arbiter_cost["total_cost"] += resolution.get("cost", 0.0)

            # Pick the correct excerpt based on arbiter decision
            if resolution and resolution.get("confidence") != "uncertain":
                correct_tax = resolution["correct_placement"]
                if correct_tax == "neither":
                    # Arbiter says both are wrong — flag for human review
                    chosen_exc = m["excerpt_a"] if winning == model_a else m["excerpt_b"]
                    source = winning
                    confidence = "low"
                elif correct_tax == m["taxonomy_a"]:
                    chosen_exc = m["excerpt_a"]
                    source = model_a
                    confidence = "high" if resolution["confidence"] == "certain" else "medium"
                else:
                    chosen_exc = m["excerpt_b"]
                    source = model_b
                    confidence = "high" if resolution["confidence"] == "certain" else "medium"
            else:
                # Arbiter unavailable or uncertain -- use preferred model
                chosen_exc = m["excerpt_a"] if winning == model_a else m["excerpt_b"]
                source = winning
                confidence = "medium"

            detail = {
                "type": "placement_disagreement",
                "model_a_placement": m["taxonomy_a"],
                "model_b_placement": m["taxonomy_b"],
                "text_overlap": round(m["text_overlap"], 4),
                "arbiter_resolution": resolution,
            }
            disagreements.append(detail)

            flags = [
                f"Placement disagreement: {model_a} \u2192 {m['taxonomy_a']}, "
                f"{model_b} \u2192 {m['taxonomy_b']}"
            ]
            if resolution and resolution.get("correct_placement") == "neither":
                flags.append("Arbiter: BOTH placements are wrong — needs human review")

            consensus_excerpts.append({
                "excerpt": chosen_exc,
                "source_model": source,
                "confidence": confidence,
                "agreement": "placement_disagreement",
                "flags": flags,
                "disagreement_detail": detail,
            })

    # Process unmatched excerpts (one model only)
    def _process_unmatched(exc_list, src_atoms, src_model, other_model_name):
        for exc in exc_list:
            resolution = None
            if call_llm_fn and arbiter_model and arbiter_api_key:
                resolution = resolve_unmatched_excerpt(
                    exc, src_atoms, src_model, other_model_name, passage_text,
                    call_llm_fn, arbiter_model, arbiter_api_key,
                    arbiter_pricing,
                )
                arbiter_cost["input_tokens"] += resolution.get("input_tokens", 0)
                arbiter_cost["output_tokens"] += resolution.get("output_tokens", 0)
                arbiter_cost["total_cost"] += resolution.get("cost", 0.0)

            keep = True
            confidence = "low"
            if resolution:
                keep = resolution.get("verdict") != "discard"
                if resolution.get("confidence") == "certain":
                    confidence = "medium" if keep else "discard"

            detail = {
                "type": "unmatched_excerpt",
                "found_by": src_model,
                "not_found_by": other_model_name,
                "arbiter_resolution": resolution,
            }
            disagreements.append(detail)

            if keep:
                consensus_excerpts.append({
                    "excerpt": exc,
                    "source_model": src_model,
                    "confidence": confidence,
                    "agreement": "unmatched",
                    "flags": [f"Only found by {src_model}, not by {other_model_name}"],
                    "disagreement_detail": detail,
                })
            else:
                discarded_excerpts.append({
                    "excerpt_id": exc.get("excerpt_id", "?"),
                    "source_model": src_model,
                    "reason": resolution.get("reasoning", "") if resolution else "",
                    "disagreement_detail": detail,
                })

    _process_unmatched(unmatched_a, atoms_a, model_a, model_b)
    _process_unmatched(unmatched_b, atoms_b, model_b, model_a)

    # Coverage agreement
    coverage = compute_coverage_agreement(result_a, result_b)

    # Footnote excerpt comparison
    footnote_comparison = compare_footnote_excerpts(
        result_a, result_b, model_a, model_b
    )

    # Exclusion comparison
    exclusion_comparison = compare_exclusions(
        result_a, result_b, model_a, model_b
    )

    # Context atom comparison for matched pairs
    context_atom_disagreements = compare_context_atoms(matched, atoms_a, atoms_b)

    # Case types comparison for matched pairs
    case_type_disagreements = []
    for m in matched:
        ct_a = set(m["excerpt_a"].get("case_types") or [])
        ct_b = set(m["excerpt_b"].get("case_types") or [])
        if ct_a != ct_b:
            case_type_disagreements.append({
                "excerpt_a_id": m["excerpt_a"].get("excerpt_id", "?"),
                "excerpt_b_id": m["excerpt_b"].get("excerpt_id", "?"),
                "case_types_a": sorted(ct_a),
                "case_types_b": sorted(ct_b),
                "shared": sorted(ct_a & ct_b),
                "a_only": sorted(ct_a - ct_b),
                "b_only": sorted(ct_b - ct_a),
            })

    # Build complete disagreements list BEFORE capturing in metadata
    # (avoids mutation-after-snapshot bugs)
    all_disagreements = list(disagreements)  # copy excerpt-level disagreements
    for d in footnote_comparison.get("disagreements", []):
        all_disagreements.append(d)
    for d in exclusion_comparison.get("disagreements", []):
        all_disagreements.append(d)

    # Build consensus metadata
    consensus_meta = {
        "mode": "consensus",
        "model_a": model_a,
        "model_b": model_b,
        "winning_model": winning,
        "matched_count": len(matched),
        "full_agreement_count": sum(
            1 for m in matched
            if m["same_taxonomy"] and m["taxonomy_a"] not in _UNMAPPED_NODES
        ),
        "both_unmapped_count": sum(
            1 for m in matched
            if _is_unmapped(m["taxonomy_a"]) and _is_unmapped(m["taxonomy_b"])
        ),
        "one_unmapped_count": sum(
            1 for m in matched
            if _is_unmapped(m["taxonomy_a"]) != _is_unmapped(m["taxonomy_b"])
        ),
        "placement_disagreement_count": sum(
            1 for m in matched
            if not m["same_taxonomy"]
            and not (_is_unmapped(m["taxonomy_a"]) or _is_unmapped(m["taxonomy_b"]))
        ),
        "unmatched_a_count": len(unmatched_a),
        "unmatched_b_count": len(unmatched_b),
        "discarded_excerpts": discarded_excerpts,
        "coverage_agreement": coverage,
        "footnote_comparison": {
            k: v for k, v in footnote_comparison.items()
            if k != "unmatched_a" and k != "unmatched_b"
        },
        "exclusion_comparison": exclusion_comparison,
        "context_atom_disagreements": context_atom_disagreements,
        "case_type_disagreements": case_type_disagreements,
        "arbiter_cost": arbiter_cost,
        "disagreements": all_disagreements,
        "per_excerpt": [
            {
                "excerpt_id": ce["excerpt"].get("excerpt_id", "?"),
                "confidence": ce["confidence"],
                "source_model": ce["source_model"],
                "agreement": ce["agreement"],
                "flags": ce["flags"],
            }
            for ce in consensus_excerpts
        ],
    }

    # Merge atoms from both models to ensure all excerpt references are valid
    merged_atoms = _merge_atoms_for_consensus(
        result_a, result_b, consensus_excerpts,
        model_a, model_b, winning,
    )

    # Merge footnote excerpts (winning + unmatched from other model)
    merged_footnotes = merge_footnote_excerpts(
        result_a, result_b, model_a, model_b, winning, footnote_comparison,
    )

    # Build the final excerpt list and exclusions (merge from both models)
    final_excerpts = [ce["excerpt"] for ce in consensus_excerpts]
    losing_result = result_b if winning == model_a else result_a
    losing_model = model_b if winning == model_a else model_a
    final_exclusions = list(winning_result.get("exclusions") or [])
    # Add exclusions from the losing model that the winning model missed,
    # using normalized text to detect duplicates.
    winning_excl_texts = set()
    for exc in final_exclusions:
        atom = atoms_a.get(exc.get("atom_id", "")) if winning == model_a \
            else atoms_b.get(exc.get("atom_id", ""))
        if atom:
            winning_excl_texts.add(normalize_for_comparison(atom.get("text", "")))
    losing_atoms_lookup = atoms_b if winning == model_a else atoms_a
    for exc in (losing_result.get("exclusions") or []):
        atom = losing_atoms_lookup.get(exc.get("atom_id", ""))
        if atom:
            norm = normalize_for_comparison(atom.get("text", ""))
            if norm and norm not in winning_excl_texts:
                # Find a matching atom in merged_atoms by text
                matched_id = None
                for ma in merged_atoms:
                    if normalize_for_comparison(ma.get("text", "")) == norm:
                        matched_id = ma.get("atom_id")
                        break
                if matched_id:
                    excl_copy = dict(exc)
                    excl_copy["atom_id"] = matched_id
                    excl_copy["_consensus_flag"] = f"only_excluded_by_{losing_model}"
                    final_exclusions.append(excl_copy)
                    winning_excl_texts.add(norm)

    # F09: Filter merged atoms to only those referenced by consensus excerpts
    # or exclusions. Without this, validation Check 7 (coverage) produces
    # false positives because winning-model atoms from non-chosen excerpts
    # appear in the atom list but aren't covered by any excerpt.
    referenced_ids = set()
    for exc in final_excerpts:
        for entry in (exc.get("core_atoms") or []):
            referenced_ids.add(_extract_atom_id(entry))
        for entry in (exc.get("context_atoms") or []):
            referenced_ids.add(_extract_atom_id(entry))
    excluded_ids = set()
    for excl in final_exclusions:
        excluded_ids.add(excl.get("atom_id", ""))
    keep_ids = referenced_ids | excluded_ids
    # Also keep heading atoms (they're excluded from coverage by the validator)
    for a in merged_atoms:
        atype = a.get("atom_type", a.get("type", ""))
        if atype == "heading" or a.get("is_prose_tail"):
            keep_ids.add(a.get("atom_id", ""))
    filtered_atoms = [a for a in merged_atoms if a.get("atom_id", "") in keep_ids]

    return {
        "passage_id": passage_id,
        "atoms": filtered_atoms,
        "excerpts": final_excerpts,
        "footnote_excerpts": merged_footnotes,
        "exclusions": final_exclusions,
        "notes": winning_result.get("notes", ""),
        "consensus_meta": consensus_meta,
    }


# ---------------------------------------------------------------------------
# Review report generation
# ---------------------------------------------------------------------------

def generate_consensus_review_section(consensus_meta: dict) -> str:
    """Generate markdown section showing consensus details for the review report."""
    lines = []
    lines.append("## Multi-Model Consensus")
    lines.append("")
    lines.append(f"- **Mode:** consensus (2 models)")
    lines.append(f"- **Model A:** {consensus_meta.get('model_a', '?')}")
    lines.append(f"- **Model B:** {consensus_meta.get('model_b', '?')}")
    lines.append(f"- **Winning model:** {consensus_meta.get('winning_model', '?')}")
    lines.append("")

    # Agreement summary
    lines.append("### Agreement Summary")
    total_matched = consensus_meta.get("matched_count", 0)
    full = consensus_meta.get("full_agreement_count", 0)
    both_unmapped = consensus_meta.get("both_unmapped_count", 0)
    one_unmapped = consensus_meta.get("one_unmapped_count", 0)
    placement_dis = consensus_meta.get("placement_disagreement_count", 0)
    unmatched_a = consensus_meta.get("unmatched_a_count", 0)
    unmatched_b = consensus_meta.get("unmatched_b_count", 0)
    coverage = consensus_meta.get("coverage_agreement", {})
    coverage_ratio = coverage.get("coverage_agreement_ratio", 0)

    lines.append(f"- Matched excerpts: {total_matched}")
    lines.append(f"- Full agreement (text + taxonomy): {full}")
    if both_unmapped:
        lines.append(f"- **Both unmapped (classification failure): {both_unmapped}**")
    if one_unmapped:
        lines.append(f"- One unmapped (auto-picked real placement): {one_unmapped}")
    lines.append(f"- Placement disagreements: {placement_dis}")
    lines.append(f"- Unmatched ({consensus_meta.get('model_a', 'A')} only): {unmatched_a}")
    lines.append(f"- Unmatched ({consensus_meta.get('model_b', 'B')} only): {unmatched_b}")
    lines.append(f"- Text coverage agreement: {coverage_ratio:.1%}")

    # Discarded excerpts
    discarded = consensus_meta.get("discarded_excerpts", [])
    if discarded:
        lines.append(f"- Discarded by arbiter: {len(discarded)}")
    lines.append("")

    # Footnote comparison
    fn = consensus_meta.get("footnote_comparison", {})
    if fn.get("matched_count", 0) or fn.get("unmatched_a_count", 0) or fn.get("unmatched_b_count", 0):
        lines.append("### Footnote Excerpt Comparison")
        lines.append(f"- Matched: {fn.get('matched_count', 0)}")
        if fn.get("unmatched_a_count"):
            lines.append(f"- {consensus_meta.get('model_a', 'A')} only: {fn['unmatched_a_count']}")
        if fn.get("unmatched_b_count"):
            lines.append(f"- {consensus_meta.get('model_b', 'B')} only: {fn['unmatched_b_count']}")
        lines.append("")

    # Exclusion comparison
    excl = consensus_meta.get("exclusion_comparison", {})
    if excl.get("a_only_count", 0) or excl.get("b_only_count", 0):
        lines.append("### Exclusion Comparison")
        lines.append(f"- Agreed: {excl.get('agreed_count', 0)}")
        if excl.get("a_only_count"):
            lines.append(f"- {consensus_meta.get('model_a', 'A')} only: {excl['a_only_count']}")
        if excl.get("b_only_count"):
            lines.append(f"- {consensus_meta.get('model_b', 'B')} only: {excl['b_only_count']}")
        lines.append("")

    # Context atom disagreements
    ctx_dis = consensus_meta.get("context_atom_disagreements", [])
    if ctx_dis:
        lines.append("### Context Atom Disagreements")
        for c in ctx_dis:
            lines.append(f"- `{c.get('excerpt_a_id', '?')}`: "
                          f"A has {c.get('a_count', 0)}, B has {c.get('b_count', 0)} "
                          f"({c.get('a_only_count', 0)} A-only, {c.get('b_only_count', 0)} B-only)")
        lines.append("")

    # Case type disagreements
    ct_dis = consensus_meta.get("case_type_disagreements", [])
    if ct_dis:
        lines.append("### Case Type Disagreements")
        for ct in ct_dis:
            lines.append(f"- `{ct.get('excerpt_a_id', '?')}`: "
                          f"A={ct.get('a_only', [])}, B={ct.get('b_only', [])}, "
                          f"shared={ct.get('shared', [])}")
        lines.append("")

    # Per-excerpt confidence table
    per_excerpt = consensus_meta.get("per_excerpt", [])
    if per_excerpt:
        lines.append("### Per-Excerpt Confidence")
        lines.append("")
        lines.append("| Excerpt | Confidence | Source | Agreement | Flags |")
        lines.append("|---------|-----------|--------|-----------|-------|")
        for pe in per_excerpt:
            flags_str = "; ".join(pe.get("flags", [])) or ""
            lines.append(
                f"| `{pe.get('excerpt_id', '?')}` "
                f"| {pe.get('confidence', '?').upper()} "
                f"| {pe.get('source_model', '?')} "
                f"| {pe.get('agreement', '?')} "
                f"| {flags_str} |"
            )
        lines.append("")

    # Disagreement details
    disagreements = consensus_meta.get("disagreements", [])
    if disagreements:
        lines.append("### Disagreement Details")
        lines.append("")
        for i, d in enumerate(disagreements, 1):
            dtype = d.get("type", "unknown")
            lines.append(f"**Disagreement {i}: {dtype}**")
            if dtype == "placement_disagreement":
                lines.append(f"- Model A placement: `{d.get('model_a_placement', '?')}`")
                lines.append(f"- Model B placement: `{d.get('model_b_placement', '?')}`")
                lines.append(f"- Text overlap: {d.get('text_overlap', 0):.1%}")
            elif dtype == "unmatched_excerpt":
                lines.append(f"- Found by: {d.get('found_by', '?')}")
                lines.append(f"- Not found by: {d.get('not_found_by', '?')}")
            elif dtype == "both_unmapped":
                lines.append(f"- Text overlap: {d.get('text_overlap', 0):.1%}")
                lines.append(f"- **Neither model could classify this excerpt**")
            elif dtype == "unmatched_footnote":
                lines.append(f"- Found by: {d.get('found_by', '?')}")
                lines.append(f"- Excerpt ID: `{d.get('excerpt_id', '?')}`")
            elif dtype == "exclusion_disagreement":
                lines.append(f"- Excluded by: {d.get('excluded_by', '?')}")
                lines.append(f"- Reason: {d.get('reason', '?')}")
                lines.append(f"- Text: {d.get('text_preview', '?')}")

            resolution = d.get("arbiter_resolution")
            if resolution:
                lines.append(f"- **Arbiter resolution:**")
                if "correct_placement" in resolution:
                    cp = resolution['correct_placement']
                    if cp == "neither":
                        lines.append(f"  - Correct placement: **NEITHER** (both wrong)")
                    else:
                        lines.append(f"  - Correct placement: `{cp}`")
                if "verdict" in resolution:
                    lines.append(f"  - Verdict: {resolution['verdict']}")
                lines.append(f"  - Confidence: {resolution.get('confidence', '?')}")
                lines.append(f"  - Reasoning: {resolution.get('reasoning', '(none)')}")
            elif dtype in ("placement_disagreement", "unmatched_excerpt"):
                lines.append(f"- **Arbiter:** not called (no arbiter configured)")
            lines.append("")

    # Arbiter cost
    arbiter_cost = consensus_meta.get("arbiter_cost", {})
    if arbiter_cost.get("total_cost", 0) > 0:
        lines.append(f"### Arbiter Cost")
        lines.append(f"- Tokens: {arbiter_cost.get('input_tokens', 0)} in + "
                      f"{arbiter_cost.get('output_tokens', 0)} out")
        lines.append(f"- Cost: ${arbiter_cost.get('total_cost', 0):.4f}")
        lines.append("")

    return "\n".join(lines)

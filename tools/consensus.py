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
    """Generate character n-grams from text (whitespace collapsed)."""
    clean = re.sub(r"\s+", "", text)
    if len(clean) < n:
        return {clean} if clean else set()
    return {clean[i:i + n] for i in range(len(clean) - n + 1)}


def text_overlap_ratio(text_a: str, text_b: str) -> float:
    """Jaccard similarity on character 5-grams of normalized Arabic text.

    Returns 0.0–1.0. Strips diacritics before comparison so that
    minor diacritical differences don't tank the score.
    """
    if not text_a or not text_b:
        return 0.0
    norm_a = normalize_for_comparison(text_a)
    norm_b = normalize_for_comparison(text_b)
    grams_a = char_ngrams(norm_a)
    grams_b = char_ngrams(norm_b)
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

    This is the 'text footprint' of an excerpt — what Arabic text it covers.
    Used for matching excerpts across models.
    """
    texts = []
    for entry in excerpt.get("core_atoms", []):
        aid = _extract_atom_id(entry)
        atom = atom_lookup.get(aid)
        if atom:
            texts.append(atom.get("text", ""))
    return " ".join(texts)


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

    Uses greedy best-match: pair the highest-overlap pair first, then next,
    etc. Only pairs above threshold are matched.

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

    # Compute pairwise overlap matrix
    overlaps = []
    for i, (exc_a, text_a) in enumerate(spans_a):
        for j, (exc_b, text_b) in enumerate(spans_b):
            ratio = text_overlap_ratio(text_a, text_b)
            if ratio >= threshold:
                overlaps.append((ratio, i, j, exc_a, exc_b, text_a, text_b))

    # Sort by overlap descending for greedy matching
    overlaps.sort(key=lambda x: x[0], reverse=True)

    matched = []
    used_a = set()
    used_b = set()

    for ratio, i, j, exc_a, exc_b, text_a, text_b in overlaps:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)

        tax_a = exc_a.get("taxonomy_node_id", "")
        tax_b = exc_b.get("taxonomy_node_id", "")

        matched.append({
            "excerpt_a": exc_a,
            "excerpt_b": exc_b,
            "text_a": text_a,
            "text_b": text_b,
            "text_overlap": ratio,
            "same_taxonomy": tax_a == tax_b,
            "taxonomy_a": tax_a,
            "taxonomy_b": tax_b,
        })

    unmatched_a = [exc for i, (exc, _) in enumerate(spans_a) if i not in used_a]
    unmatched_b = [exc for j, (exc, _) in enumerate(spans_b) if j not in used_b]

    return matched, unmatched_a, unmatched_b


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
            for entry in exc.get("core_atoms", []):
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
# Arbiter prompt templates
# ---------------------------------------------------------------------------

ARBITER_PLACEMENT_PROMPT = """\
You are an expert arbiter for the Arabic Book Digester (ABD) pipeline.

Two models independently extracted the same passage and produced excerpts. \
They agree on the excerpt content but DISAGREE on taxonomy placement.

## The Excerpt Text
{excerpt_text}

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
which placement is CORRECT. Consider:
1. What topic does this excerpt actually teach?
2. Which taxonomy leaf most precisely matches that topic?
3. Is one placement more specific/accurate than the other?

Return JSON:
{{
  "correct_placement": "{taxonomy_a}" or "{taxonomy_b}",
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
Determine whether this excerpt is VALID — does this text constitute a \
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
) -> dict:
    """Call arbiter LLM to resolve a taxonomy placement disagreement.

    Args:
        match: matched excerpt pair dict from match_excerpts
        model_a, model_b: model names
        taxonomy_yaml: full taxonomy YAML text for context
        call_llm_fn: function(system, user, model, api_key) -> dict
        arbiter_model: model to use for arbitration
        arbiter_api_key: API key for arbiter

    Returns dict with: correct_placement, reasoning, confidence, cost
    """
    excerpt_text = match["text_a"]  # use model A's text (they overlap)

    # Extract relevant taxonomy context (the paths around both nodes)
    taxonomy_path_a = match["excerpt_a"].get("taxonomy_path", match["taxonomy_a"])
    taxonomy_path_b = match["excerpt_b"].get("taxonomy_path", match["taxonomy_b"])

    prompt = ARBITER_PLACEMENT_PROMPT.format(
        excerpt_text=excerpt_text,
        model_a=model_a,
        model_b=model_b,
        taxonomy_a=match["taxonomy_a"],
        taxonomy_b=match["taxonomy_b"],
        taxonomy_path_a=taxonomy_path_a,
        taxonomy_path_b=taxonomy_path_b,
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
        parsed = response["parsed"]
        cost = response.get("input_tokens", 0) * 3 / 1_000_000 + \
               response.get("output_tokens", 0) * 15 / 1_000_000
        return {
            "correct_placement": parsed.get("correct_placement", match["taxonomy_a"]),
            "reasoning": parsed.get("reasoning", ""),
            "confidence": parsed.get("confidence", "uncertain"),
            "cost": cost,
            "input_tokens": response.get("input_tokens", 0),
            "output_tokens": response.get("output_tokens", 0),
        }
    except Exception as e:
        # Arbiter failed — fall back to preferred model
        return {
            "correct_placement": match["taxonomy_a"],
            "reasoning": f"Arbiter call failed: {e}. Falling back to model A placement.",
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
) -> dict:
    """Call arbiter LLM to decide whether an unmatched excerpt should be kept.

    Returns dict with: verdict, reasoning, confidence, cost
    """
    excerpt_text = compute_excerpt_text_span(excerpt, atom_lookup)
    taxonomy_node = excerpt.get("taxonomy_node_id", "unknown")
    taxonomy_path = excerpt.get("taxonomy_path", taxonomy_node)

    # Provide surrounding passage context (truncated)
    ctx = passage_text[:2000] if len(passage_text) > 2000 else passage_text

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
        parsed = response["parsed"]
        cost = response.get("input_tokens", 0) * 3 / 1_000_000 + \
               response.get("output_tokens", 0) * 15 / 1_000_000
        return {
            "verdict": parsed.get("verdict", "keep"),
            "reasoning": parsed.get("reasoning", ""),
            "confidence": parsed.get("confidence", "uncertain"),
            "cost": cost,
            "input_tokens": response.get("input_tokens", 0),
            "output_tokens": response.get("output_tokens", 0),
        }
    except Exception as e:
        # Arbiter failed — default to keeping the excerpt
        return {
            "verdict": "keep",
            "reasoning": f"Arbiter call failed: {e}. Defaulting to keep.",
            "confidence": "uncertain",
            "cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        }


def _extract_taxonomy_context(taxonomy_yaml: str, node_a: str, node_b: str) -> str:
    """Extract the taxonomy YAML lines around two nodes for arbiter context."""
    lines = taxonomy_yaml.split("\n")
    relevant = []
    for i, line in enumerate(lines):
        stripped = line.split("#")[0].strip().rstrip(":")
        if stripped in (node_a, node_b):
            # Include 5 lines before and after for context
            start = max(0, i - 5)
            end = min(len(lines), i + 6)
            relevant.extend(lines[start:end])
            relevant.append("---")
    if relevant:
        return "\n".join(relevant)
    return f"(nodes {node_a} and {node_b} not found in taxonomy)"


# ---------------------------------------------------------------------------
# Main consensus builder
# ---------------------------------------------------------------------------

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
) -> dict:
    """Build consensus from two model outputs for the same passage.

    When models agree: high confidence, use preferred model's output.
    When models disagree: call arbiter LLM to resolve, document everything.

    Args:
        passage_id: passage identifier
        result_a, result_b: extraction results from two models
        model_a, model_b: model names
        issues_a, issues_b: validation issues from each model
        prefer_model: model to prefer for tie-breaking (default: model_a)
        threshold: minimum text overlap ratio for excerpt matching
        call_llm_fn: LLM call function for arbiter (None = skip arbiter)
        arbiter_model: model to use for arbitration
        arbiter_api_key: API key for arbiter
        taxonomy_yaml: full taxonomy YAML for arbiter context
        passage_text: full passage text for arbiter context

    Returns dict with keys:
        passage_id, atoms, excerpts, footnote_excerpts, exclusions, notes,
        consensus_meta
    """
    atoms_a = build_atom_lookup(result_a)
    atoms_b = build_atom_lookup(result_b)

    # Match excerpts by text overlap
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
    arbiter_cost = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0}

    for m in matched:
        if m["same_taxonomy"]:
            # FULL AGREEMENT — high confidence
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
            # PLACEMENT DISAGREEMENT — call arbiter
            resolution = None
            if call_llm_fn and arbiter_model and arbiter_api_key:
                resolution = resolve_placement_disagreement(
                    m, model_a, model_b, taxonomy_yaml,
                    call_llm_fn, arbiter_model, arbiter_api_key,
                )
                arbiter_cost["input_tokens"] += resolution.get("input_tokens", 0)
                arbiter_cost["output_tokens"] += resolution.get("output_tokens", 0)
                arbiter_cost["total_cost"] += resolution.get("cost", 0.0)

            # Pick the correct excerpt based on arbiter decision
            if resolution and resolution.get("confidence") != "uncertain":
                correct_tax = resolution["correct_placement"]
                if correct_tax == m["taxonomy_a"]:
                    chosen_exc = m["excerpt_a"]
                    source = model_a
                else:
                    chosen_exc = m["excerpt_b"]
                    source = model_b
                confidence = "high" if resolution["confidence"] == "certain" else "medium"
            else:
                # Arbiter unavailable or uncertain — use preferred model
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

            consensus_excerpts.append({
                "excerpt": chosen_exc,
                "source_model": source,
                "confidence": confidence,
                "agreement": "placement_disagreement",
                "flags": [
                    f"Placement disagreement: {model_a} → {m['taxonomy_a']}, "
                    f"{model_b} → {m['taxonomy_b']}"
                ],
                "disagreement_detail": detail,
            })

    # Process unmatched excerpts (one model only)
    for exc in unmatched_a:
        resolution = None
        if call_llm_fn and arbiter_model and arbiter_api_key:
            resolution = resolve_unmatched_excerpt(
                exc, atoms_a, model_a, model_b, passage_text,
                call_llm_fn, arbiter_model, arbiter_api_key,
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
            "found_by": model_a,
            "not_found_by": model_b,
            "arbiter_resolution": resolution,
        }
        disagreements.append(detail)

        if keep:
            consensus_excerpts.append({
                "excerpt": exc,
                "source_model": model_a,
                "confidence": confidence,
                "agreement": "unmatched",
                "flags": [f"Only found by {model_a}, not by {model_b}"],
                "disagreement_detail": detail,
            })

    for exc in unmatched_b:
        resolution = None
        if call_llm_fn and arbiter_model and arbiter_api_key:
            resolution = resolve_unmatched_excerpt(
                exc, atoms_b, model_b, model_a, passage_text,
                call_llm_fn, arbiter_model, arbiter_api_key,
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
            "found_by": model_b,
            "not_found_by": model_a,
            "arbiter_resolution": resolution,
        }
        disagreements.append(detail)

        if keep:
            consensus_excerpts.append({
                "excerpt": exc,
                "source_model": model_b,
                "confidence": confidence,
                "agreement": "unmatched",
                "flags": [f"Only found by {model_b}, not by {model_a}"],
                "disagreement_detail": detail,
            })

    # Coverage agreement
    coverage = compute_coverage_agreement(result_a, result_b)

    # Build consensus metadata
    consensus_meta = {
        "mode": "consensus",
        "model_a": model_a,
        "model_b": model_b,
        "winning_model": winning,
        "matched_count": len(matched),
        "full_agreement_count": sum(1 for m in matched if m["same_taxonomy"]),
        "placement_disagreement_count": sum(1 for m in matched if not m["same_taxonomy"]),
        "unmatched_a_count": len(unmatched_a),
        "unmatched_b_count": len(unmatched_b),
        "coverage_agreement": coverage,
        "arbiter_cost": arbiter_cost,
        "disagreements": disagreements,
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

    return {
        "passage_id": passage_id,
        "atoms": winning_result.get("atoms", []),
        "excerpts": [ce["excerpt"] for ce in consensus_excerpts],
        "footnote_excerpts": winning_result.get("footnote_excerpts", []),
        "exclusions": winning_result.get("exclusions", []),
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
    placement_dis = consensus_meta.get("placement_disagreement_count", 0)
    unmatched_a = consensus_meta.get("unmatched_a_count", 0)
    unmatched_b = consensus_meta.get("unmatched_b_count", 0)
    coverage = consensus_meta.get("coverage_agreement", {})
    coverage_ratio = coverage.get("coverage_agreement_ratio", 0)

    lines.append(f"- Matched excerpts: {total_matched}")
    lines.append(f"- Full agreement (text + taxonomy): {full}")
    lines.append(f"- Placement disagreements: {placement_dis}")
    lines.append(f"- Unmatched ({consensus_meta.get('model_a', 'A')} only): {unmatched_a}")
    lines.append(f"- Unmatched ({consensus_meta.get('model_b', 'B')} only): {unmatched_b}")
    lines.append(f"- Text coverage agreement: {coverage_ratio:.1%}")
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

            resolution = d.get("arbiter_resolution")
            if resolution:
                lines.append(f"- **Arbiter resolution:**")
                if "correct_placement" in resolution:
                    lines.append(f"  - Correct placement: `{resolution['correct_placement']}`")
                if "verdict" in resolution:
                    lines.append(f"  - Verdict: {resolution['verdict']}")
                lines.append(f"  - Confidence: {resolution.get('confidence', '?')}")
                lines.append(f"  - Reasoning: {resolution.get('reasoning', '(none)')}")
            else:
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

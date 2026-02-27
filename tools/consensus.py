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
# Footnote excerpt comparison
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
        disagreements (list of dicts)
    """
    fn_a = result_a.get("footnote_excerpts") or []
    fn_b = result_b.get("footnote_excerpts") or []

    if not fn_a and not fn_b:
        return {
            "matched_count": 0,
            "unmatched_a_count": 0,
            "unmatched_b_count": 0,
            "disagreements": [],
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
    }


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

    # Map exclusions by normalized text
    def _exclusion_texts(result, atoms):
        texts = {}
        for exc in result.get("exclusions") or []:
            aid = exc.get("atom_id", "")
            atom = atoms.get(aid)
            if atom:
                norm = normalize_for_comparison(atom.get("text", ""))
                if norm:
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

    Returns dict with: correct_placement, reasoning, confidence, cost
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
        cost = response.get("input_tokens", 0) * 3 / 1_000_000 + \
               response.get("output_tokens", 0) * 15 / 1_000_000

        raw_placement = parsed.get("correct_placement", "")
        # Validate placement is one of the two options
        if raw_placement not in (match["taxonomy_a"], match["taxonomy_b"]):
            raw_placement = match["taxonomy_a"]  # fall back

        return {
            "correct_placement": raw_placement,
            "reasoning": str(parsed.get("reasoning", "")),
            "confidence": _normalize_confidence(parsed.get("confidence", "")),
            "cost": cost,
            "input_tokens": response.get("input_tokens", 0),
            "output_tokens": response.get("output_tokens", 0),
        }
    except Exception as e:
        # Arbiter failed -- fall back to preferred model
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
        cost = response.get("input_tokens", 0) * 3 / 1_000_000 + \
               response.get("output_tokens", 0) * 15 / 1_000_000

        raw_verdict = str(parsed.get("verdict", "keep")).strip().lower()
        if raw_verdict not in ("keep", "discard"):
            raw_verdict = "keep"  # safe default

        return {
            "verdict": raw_verdict,
            "reasoning": str(parsed.get("reasoning", "")),
            "confidence": _normalize_confidence(parsed.get("confidence", "")),
            "cost": cost,
            "input_tokens": response.get("input_tokens", 0),
            "output_tokens": response.get("output_tokens", 0),
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

# Taxonomy nodes that indicate classification failure, not real agreement
_UNMAPPED_NODES = {"_unmapped", "__unmapped", "unmapped"}


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
    discarded_excerpts = []
    arbiter_cost = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0.0}

    for m in matched:
        tax_a = m["taxonomy_a"]
        tax_b = m["taxonomy_b"]
        both_unmapped = tax_a in _UNMAPPED_NODES and tax_b in _UNMAPPED_NODES

        if m["same_taxonomy"] and not both_unmapped:
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
        elif both_unmapped:
            # BOTH UNMAPPED -- classification failure, NOT real agreement
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
        else:
            # PLACEMENT DISAGREEMENT -- call arbiter
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

            consensus_excerpts.append({
                "excerpt": chosen_exc,
                "source_model": source,
                "confidence": confidence,
                "agreement": "placement_disagreement",
                "flags": [
                    f"Placement disagreement: {model_a} \u2192 {m['taxonomy_a']}, "
                    f"{model_b} \u2192 {m['taxonomy_b']}"
                ],
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
            if m["taxonomy_a"] in _UNMAPPED_NODES and m["taxonomy_b"] in _UNMAPPED_NODES
        ),
        "placement_disagreement_count": sum(
            1 for m in matched
            if not m["same_taxonomy"]
        ),
        "unmatched_a_count": len(unmatched_a),
        "unmatched_b_count": len(unmatched_b),
        "discarded_excerpts": discarded_excerpts,
        "coverage_agreement": coverage,
        "footnote_comparison": footnote_comparison,
        "exclusion_comparison": exclusion_comparison,
        "case_type_disagreements": case_type_disagreements,
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

    # Merge footnote/exclusion disagreements into main disagreements list
    for d in footnote_comparison.get("disagreements", []):
        disagreements.append(d)
    for d in exclusion_comparison.get("disagreements", []):
        disagreements.append(d)

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
    both_unmapped = consensus_meta.get("both_unmapped_count", 0)
    placement_dis = consensus_meta.get("placement_disagreement_count", 0)
    unmatched_a = consensus_meta.get("unmatched_a_count", 0)
    unmatched_b = consensus_meta.get("unmatched_b_count", 0)
    coverage = consensus_meta.get("coverage_agreement", {})
    coverage_ratio = coverage.get("coverage_agreement_ratio", 0)

    lines.append(f"- Matched excerpts: {total_matched}")
    lines.append(f"- Full agreement (text + taxonomy): {full}")
    if both_unmapped:
        lines.append(f"- **Both unmapped (classification failure): {both_unmapped}**")
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
                    lines.append(f"  - Correct placement: `{resolution['correct_placement']}`")
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

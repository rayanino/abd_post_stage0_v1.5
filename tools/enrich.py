#!/usr/bin/env python3
"""
Stage 0.5: Scholarly Enrichment — CLI Tool

Post-intake tool that enriches the scholarly_context field in intake_metadata.json.
Uses three complementary strategies:
  1. Interactive prompts (always available)
  2. Tarjama text extraction (user provides a ترجمة)
  3. Anthropic API (LLM knowledge of classical scholars)

The scholarly_context field is the one documented exception to intake metadata
immutability — it has an explicit extraction_source provenance field.

Usage:
  python tools/enrich.py BOOK_ID                         # Interactive
  python tools/enrich.py BOOK_ID --from-text tarjama.txt  # From ترجمة file
  python tools/enrich.py BOOK_ID --api                    # LLM enrichment
  python tools/enrich.py BOOK_ID --show                   # Show current context
  python tools/enrich.py BOOK_ID --batch                  # Non-interactive API mode
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ─── Shared with intake.py ─────────────────────────────────────────────────

MADHAB_MAP = {
    "شافعي": "shafii", "الشافعي": "shafii", "shafii": "shafii",
    "حنفي": "hanafi", "الحنفي": "hanafi", "hanafi": "hanafi",
    "مالكي": "maliki", "المالكي": "maliki", "maliki": "maliki",
    "حنبلي": "hanbali", "الحنبلي": "hanbali", "hanbali": "hanbali",
}

SCHOOL_MAP = {
    "بصري": "basri", "البصري": "basri", "basri": "basri",
    "كوفي": "kufi", "الكوفي": "kufi", "kufi": "kufi",
    "بغدادي": "baghdadi", "البغدادي": "baghdadi", "baghdadi": "baghdadi",
    "أندلسي": "andalusi", "الأندلسي": "andalusi", "andalusi": "andalusi",
    "مصري": "misri", "المصري": "misri", "misri": "misri",
    "شامي": "shami", "الشامي": "shami", "shami": "shami",
}

BOOK_TYPE_MAP = {
    "متن": "matn", "matn": "matn",
    "شرح": "sharh", "sharh": "sharh",
    "حاشية": "hashiya", "hashiya": "hashiya",
    "مختصر": "mukhtasar", "تلخيص": "mukhtasar", "mukhtasar": "mukhtasar",
    "نظم": "nazm", "nazm": "nazm",
}

VALID_MADHABS = {"shafii", "hanafi", "maliki", "hanbali", "other"}
VALID_SCHOOLS = {"basri", "kufi", "baghdadi", "andalusi", "misri", "shami", "other"}
VALID_BOOK_TYPES = {"matn", "sharh", "hashiya", "mukhtasar", "nazm", "other"}


# ─── Utilities ──────────────────────────────────────────────────────────────

def find_repo_root():
    here = Path(__file__).resolve().parent
    candidate = here.parent
    required = {"books", "schemas", "tools"}
    if required.issubset({p.name for p in candidate.iterdir() if p.is_dir()}):
        return candidate
    cwd = Path.cwd()
    if required.issubset({p.name for p in cwd.iterdir() if p.is_dir()}):
        return cwd
    print("ERROR: Cannot find repo root.", file=sys.stderr)
    sys.exit(1)


def load_metadata(repo_root, book_id):
    path = repo_root / "books" / book_id / "intake_metadata.json"
    if not path.exists():
        print(f"ERROR: No metadata found at {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f), path


def save_metadata(metadata, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Updated: {path}")


def display_context(metadata):
    """Show current scholarly context in a readable format."""
    ctx = metadata.get("scholarly_context")
    title = metadata.get("title", "?")
    author = metadata.get("author", "?")
    shamela_id = metadata.get("shamela_book_id")

    print(f"\n{'─' * 60}")
    print(f"  Book:    {title}")
    print(f"  Author:  {author}")
    print(f"  ID:      {metadata.get('book_id')}")
    if shamela_id:
        print(f"  Shamela: https://shamela.ws/book/{shamela_id}")
    print(f"{'─' * 60}")

    if ctx is None:
        print("  scholarly_context: (none — not yet extracted)")
        return ctx

    fields = [
        ("Death (Hijri)", ctx.get("author_death_hijri"), "هـ"),
        ("Birth (Hijri)", ctx.get("author_birth_hijri"), "هـ"),
        ("Fiqh madhab", ctx.get("fiqh_madhab"), ""),
        ("Grammar school", ctx.get("grammatical_school"), ""),
        ("Geographic origin", ctx.get("geographic_origin"), ""),
        ("Book type", ctx.get("book_type"), ""),
        ("Source", ctx.get("extraction_source"), ""),
    ]

    print()
    for label, value, suffix in fields:
        if value is not None:
            suf = f" {suffix}" if suffix else ""
            print(f"  ✓ {label:20s}: {value}{suf}")
        else:
            print(f"  ○ {label:20s}: (missing)")
    print()

    return ctx


def get_gaps(ctx):
    """Return list of field names that are still None."""
    if ctx is None:
        return ["author_death_hijri", "author_birth_hijri", "fiqh_madhab",
                "grammatical_school", "geographic_origin", "book_type"]
    gaps = []
    for field in ["author_death_hijri", "author_birth_hijri", "fiqh_madhab",
                  "grammatical_school", "geographic_origin", "book_type"]:
        if ctx.get(field) is None:
            gaps.append(field)
    return gaps


# ─── Strategy 1: Interactive ───────────────────────────────────────────────

FIELD_PROMPTS = {
    "author_death_hijri": {
        "question": "Author's death year (Hijri)? e.g., 471, 739. Leave blank if unknown",
        "parse": lambda v: int(v) if v.strip() else None,
        "validate": lambda v: v is None or (1 <= v <= 1500),
    },
    "author_birth_hijri": {
        "question": "Author's birth year (Hijri)? e.g., 666. Leave blank if unknown",
        "parse": lambda v: int(v) if v.strip() else None,
        "validate": lambda v: v is None or (1 <= v <= 1500),
    },
    "fiqh_madhab": {
        "question": "Fiqh madhab? [shafii/hanafi/maliki/hanbali/other] or blank",
        "parse": lambda v: MADHAB_MAP.get(v.strip(), v.strip()) if v.strip() else None,
        "validate": lambda v: v is None or v in VALID_MADHABS,
    },
    "grammatical_school": {
        "question": "Grammatical school? [basri/kufi/baghdadi/andalusi/misri/shami/other] or blank",
        "parse": lambda v: SCHOOL_MAP.get(v.strip(), v.strip()) if v.strip() else None,
        "validate": lambda v: v is None or v in VALID_SCHOOLS,
    },
    "geographic_origin": {
        "question": "Geographic origin (Arabic nisba)? e.g., القزويني, البغدادي. Or blank",
        "parse": lambda v: v.strip() if v.strip() else None,
        "validate": lambda v: True,
    },
    "book_type": {
        "question": "Book type? [matn/sharh/hashiya/mukhtasar/nazm/other] or blank",
        "parse": lambda v: BOOK_TYPE_MAP.get(v.strip(), v.strip()) if v.strip() else None,
        "validate": lambda v: v is None or v in VALID_BOOK_TYPES,
    },
}


def enrich_interactive(metadata, gaps):
    """Prompt user for each missing field."""
    ctx = metadata.get("scholarly_context") or {
        "author_death_hijri": None, "author_birth_hijri": None,
        "fiqh_madhab": None, "grammatical_school": None,
        "geographic_origin": None, "book_type": None,
        "extraction_source": "auto",
    }

    if not gaps:
        print("  No gaps to fill — all fields populated.")
        return ctx, False

    print(f"  {len(gaps)} fields to fill. Press Enter to skip any.\n")
    changed = False

    for field in gaps:
        prompt_info = FIELD_PROMPTS[field]
        while True:
            raw = input(f"  {prompt_info['question']}: ").strip()
            try:
                value = prompt_info["parse"](raw)
                if prompt_info["validate"](value):
                    if value is not None:
                        ctx[field] = value
                        changed = True
                    break
                else:
                    print(f"    Invalid value. Try again.")
            except (ValueError, TypeError):
                print(f"    Could not parse '{raw}'. Try again (or leave blank to skip).")

    if changed:
        ctx["extraction_source"] = "user_provided"

    return ctx, changed


# ─── Strategy 2: From ترجمة text ──────────────────────────────────────────

def extract_from_tarjama(text):
    """Extract scholarly fields from a ترجمة text using regex patterns."""
    extracted = {}

    # Death date: various patterns
    # (ت 739هـ), (المتوفى: 769 هـ), (ت739 هـ), توفي سنة 471 هـ
    for pattern in [
        r"(?:ت|توفي|المتوفى)[:\s]*(?:سنة\s*)?(\d+)\s*هـ",
        r"(?:ت|توفي|المتوفى)[:\s]*(?:سنة\s*)?([٠-٩]+)\s*هـ",
        r"\((\d+)\s*[-–]\s*(\d+)\s*هـ",  # (666 - 739 هـ) → death is second number
    ]:
        m = re.search(pattern, text)
        if m:
            # For the range pattern (2 groups), take the second (death) number
            raw = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
            num = int(raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
            if 1 <= num <= 1500:
                extracted["author_death_hijri"] = num
                break

    # Birth date
    for pattern in [
        r"(?:ولد|مولده)\s*(?:سنة\s*)?(\d+)\s*هـ",
        r"(?:ولد|مولده)\s*(?:سنة\s*)?([٠-٩]+)\s*هـ",
        r"\((\d+)\s*[-–]\s*\d+\s*هـ",  # (666 - 739 هـ) → birth is first number
        r"\(([٠-٩]+)\s*[-–]\s*[٠-٩]+\s*هـ",  # Arabic-Indic variant
    ]:
        m = re.search(pattern, text)
        if m:
            raw = m.group(1)
            num = int(raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
            if 1 <= num <= 1500:
                extracted["author_birth_hijri"] = num
                break

    # Madhab
    for ar, en in MADHAB_MAP.items():
        if ar in text and en in VALID_MADHABS:
            extracted["fiqh_madhab"] = en
            break

    # Grammatical school (from geographic nisbas in the text)
    for ar, en in SCHOOL_MAP.items():
        if ar in text and en in VALID_SCHOOLS:
            extracted["grammatical_school"] = en
            break

    # Geographic origin: look for nisbas in the text
    nisbas = re.findall(r"(ال[^\s,،()]+ي)\b", text)
    non_geographic = set(MADHAB_MAP.keys()) | set(SCHOOL_MAP.keys()) | {
        # Common non-geographic nisbas / false positives
        "المعروف", "العجلي", "المعالي", "الأصلي", "التقي", "العلي",
        "الملك", "العربي", "التركي", "الفارسي",
        # Arabic language terms ending in ي
        "المعاني", "البيان", "البديع", "الثاني", "الأولي", "التالي",
        "الناصري", "الرفاعي", "الصيادي",  # tribal, not geographic
    }
    geographic = [n for n in nisbas if n not in non_geographic]
    if geographic:
        extracted["geographic_origin"] = geographic[-1]

    return extracted


def enrich_from_text(metadata, text, gaps):
    """Extract scholarly fields from a ترجمة text."""
    ctx = metadata.get("scholarly_context") or {
        "author_death_hijri": None, "author_birth_hijri": None,
        "fiqh_madhab": None, "grammatical_school": None,
        "geographic_origin": None, "book_type": None,
        "extraction_source": "auto",
    }

    extracted = extract_from_tarjama(text)
    changed = False

    for field, value in extracted.items():
        if field in gaps and value is not None:
            ctx[field] = value
            changed = True
            print(f"  ✓ Extracted {field}: {value}")

    remaining = [f for f in gaps if f not in extracted or extracted[f] is None]
    if remaining:
        print(f"  ○ Still missing: {', '.join(remaining)}")

    if changed:
        ctx["extraction_source"] = "enriched"

    return ctx, changed, remaining


# ─── Strategy 3: Anthropic API ─────────────────────────────────────────────

def enrich_via_api(metadata, gaps, batch=False):
    """Use Anthropic API to research the author and fill gaps."""
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx package not installed.", file=sys.stderr)
        print("  Install with: pip install httpx", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    ctx = metadata.get("scholarly_context") or {
        "author_death_hijri": None, "author_birth_hijri": None,
        "fiqh_madhab": None, "grammatical_school": None,
        "geographic_origin": None, "book_type": None,
        "extraction_source": "auto",
    }

    title = metadata.get("title", "")
    title_formal = metadata.get("title_formal", "")
    author = metadata.get("author", "")
    author_short = metadata.get("shamela_author_short", "")
    muhaqiq = metadata.get("muhaqiq", "")
    publisher = metadata.get("publisher", "")

    gap_descriptions = {
        "author_death_hijri": "Author's death year in Hijri calendar (integer, e.g. 471)",
        "author_birth_hijri": "Author's birth year in Hijri calendar (integer, e.g. 400)",
        "fiqh_madhab": "Author's fiqh madhab: shafii, hanafi, maliki, hanbali, or other",
        "grammatical_school": "Author's grammatical school: basri, kufi, baghdadi, andalusi, misri, shami, or other. "
                              "This is about Arabic grammar traditions, particularly the بصرة vs كوفة distinction.",
        "geographic_origin": "Geographic nisba from the author's name (Arabic, e.g. القزويني, الجرجاني)",
        "book_type": "Book type: matn (base text), sharh (commentary), hashiya (marginal commentary), "
                     "mukhtasar (abridgment), nazm (versified treatise), or other",
    }

    fields_needed = "\n".join(f"- {f}: {gap_descriptions[f]}" for f in gaps)

    prompt = f"""You are a specialist in classical Arabic linguistic sciences (النحو، الصرف، البلاغة، الإملاء).

I need you to provide structured scholarly metadata for a book in my corpus. Here is what I already know:

Title: {title}
Title (formal): {title_formal}
Author (full): {author}
Author (short): {author_short}
Muhaqiq/Editor: {muhaqiq}
Publisher: {publisher}

I need you to fill in the following missing fields:
{fields_needed}

IMPORTANT RULES:
1. Only provide information you are confident about. Use null for anything uncertain.
2. For grammatical_school: this is about the author's alignment with the بصرة or كوفة grammatical traditions. Many later scholars (post-600 AH) don't have a clear school alignment — use null for these, not "other".
3. For fiqh_madhab: extract from the author's nisba or known biography. If not known, use null.
4. For geographic_origin: use the Arabic nisba form (e.g., القزويني not "Qazvin").
5. For book_type: determine from the title and the book's nature, not the author.

Respond ONLY with a JSON object containing the requested fields. No explanations, no markdown, no preamble.

Example response:
{{"author_death_hijri": 471, "author_birth_hijri": 400, "fiqh_madhab": "shafii", "grammatical_school": null, "geographic_origin": "الجرجاني", "book_type": "matn"}}"""

    print("  Calling Anthropic API...")

    raw_text = ""
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120.0,
        )
        if resp.status_code != 200:
            print(f"  ERROR: API returned status {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
            return ctx, False

        data = resp.json()
        raw_text = data["content"][0]["text"].strip()

        # Parse JSON response (strip markdown fences if present)
        clean = re.sub(r"```json\s*|```\s*", "", raw_text).strip()
        result = json.loads(clean)

    except json.JSONDecodeError:
        print(f"  ERROR: Could not parse API response as JSON:", file=sys.stderr)
        print(f"  {raw_text[:200]}", file=sys.stderr)
        return ctx, False
    except Exception as e:
        print(f"  ERROR: API call failed: {e}", file=sys.stderr)
        return ctx, False

    # Show results to user
    print("\n  API results:")
    changed = False
    pending = {}

    for field in gaps:
        value = result.get(field)
        if value is not None:
            # Validate
            valid = True
            if field in ("author_death_hijri", "author_birth_hijri"):
                valid = isinstance(value, int) and 1 <= value <= 1500
            elif field == "fiqh_madhab":
                valid = value in VALID_MADHABS
            elif field == "grammatical_school":
                valid = value in VALID_SCHOOLS
            elif field == "book_type":
                valid = value in VALID_BOOK_TYPES

            if valid:
                suffix = " هـ" if "hijri" in field else ""
                print(f"    {field}: {value}{suffix}")
                pending[field] = value
            else:
                print(f"    {field}: {value} (INVALID — skipped)")
        else:
            print(f"    {field}: null (API uncertain)")

    if not pending:
        print("  No new fields to add.")
        return ctx, False

    # Confirm with user (unless batch mode)
    if not batch:
        confirm = input("\n  Accept these values? [y/n/edit]: ").strip().lower()
        if confirm in ("n", "no"):
            print("  Discarded.")
            return ctx, False
        elif confirm in ("e", "edit"):
            # Let user edit interactively
            remaining_gaps = list(pending.keys())
            return enrich_interactive(metadata, remaining_gaps)

    # Apply
    for field, value in pending.items():
        ctx[field] = value
        changed = True

    if changed:
        ctx["extraction_source"] = "enriched"

    return ctx, changed


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enrich scholarly context for an intaken book."
    )
    parser.add_argument("book_id", help="Book ID to enrich")
    parser.add_argument("--show", action="store_true",
                        help="Show current scholarly context and exit")
    parser.add_argument("--from-text", metavar="FILE",
                        help="Extract from a ترجمة text file")
    parser.add_argument("--api", action="store_true",
                        help="Use Anthropic API for enrichment (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--batch", action="store_true",
                        help="Non-interactive mode (auto-accept API results)")
    parser.add_argument("--all-fields", action="store_true",
                        help="Re-enrich all fields, not just gaps")

    args = parser.parse_args()
    repo_root = find_repo_root()

    # Load metadata
    metadata, meta_path = load_metadata(repo_root, args.book_id)

    print("=" * 60)
    print(f"Stage 0.5: Scholarly Enrichment — {args.book_id}")
    print("=" * 60)

    current_ctx = display_context(metadata)

    if args.show:
        sys.exit(0)

    # Determine gaps
    if args.all_fields:
        gaps = ["author_death_hijri", "author_birth_hijri", "fiqh_madhab",
                "grammatical_school", "geographic_origin", "book_type"]
    else:
        gaps = get_gaps(current_ctx)

    if not gaps and not args.all_fields:
        print("  All fields populated. Use --all-fields to re-enrich.")
        sys.exit(0)

    print(f"  Fields to fill: {len(gaps)}")
    if gaps:
        print(f"  Gaps: {', '.join(gaps)}")
    print()

    # Execute enrichment strategy
    new_ctx = current_ctx
    changed = False

    if args.from_text:
        # Strategy 2: from text file
        text_path = Path(args.from_text)
        if not text_path.exists():
            print(f"ERROR: File not found: {text_path}", file=sys.stderr)
            sys.exit(1)
        text = text_path.read_text(encoding="utf-8")
        print(f"  Reading ترجمة from: {text_path} ({len(text)} chars)\n")
        new_ctx, changed, remaining = enrich_from_text(metadata, text, gaps)

        # If gaps remain, offer interactive fill (unless batch)
        if remaining and not args.batch:
            print()
            do_interactive = input("  Fill remaining fields interactively? [y/n]: ").strip().lower()
            if do_interactive in ("y", "yes"):
                new_ctx, extra_changed = enrich_interactive(
                    {**metadata, "scholarly_context": new_ctx}, remaining
                )
                changed = changed or extra_changed

    elif args.api:
        # Strategy 3: API
        new_ctx, changed = enrich_via_api(metadata, gaps, batch=args.batch)

    else:
        # Strategy 1: Interactive (default)
        new_ctx, changed = enrich_interactive(metadata, gaps)

    # Save if changed
    if changed and new_ctx:
        metadata["scholarly_context"] = new_ctx

        print(f"\n── Updated scholarly context ──")
        display_context(metadata)

        if not args.batch:
            confirm = input("  Save to disk? [y/n]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("  Not saved.")
                sys.exit(0)

        save_metadata(metadata, meta_path)
        print(f"\n✅ Enrichment saved for {args.book_id}")
    elif not changed:
        print("\n  No changes made.")


if __name__ == "__main__":
    main()

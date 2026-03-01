#!/usr/bin/env python3
"""
Stage 0: Book Intake — CLI Tool
Implements INTAKE_SPEC.md v1.5

Creates an immutable anchor for everything downstream:
  - Freezes source HTML
  - Extracts and validates metadata
  - Registers the book in the project

Usage:
  python tools/intake.py SOURCE --book-id ID --science SCIENCE [OPTIONS]
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ─── Constants ──────────────────────────────────────────────────────────────

SCHEMA_VERSION = "intake_metadata_v0.2"
# Core sciences (known and tested). New sciences are accepted via --science flag
# or interactive prompt — the engine is science-agnostic.
CORE_SCIENCES = ("balagha", "sarf", "nahw", "imlaa")
# Valid values for --science CLI arg (includes classification categories)
VALID_SCIENCES = (*CORE_SCIENCES, "adjacent", "unrelated", "multi")
# Backwards compat alias
SINGLE_SCIENCES = CORE_SCIENCES
BOOK_ID_PATTERN = re.compile(r"^[a-z][a-z_]*[a-z]$")

# Book type detection patterns (checked against title, title_formal, or unrecognized lines)
BOOK_TYPE_PATTERNS = [
    (r"\bحاشية\b", "hashiya"),        # marginal commentary
    (r"\bشرح\b", "sharh"),            # commentary
    (r"\bمختصر\b", "mukhtasar"),      # abridgment
    (r"\bتلخيص\b", "mukhtasar"),      # summary/abridgment
    (r"\bنظم\b", "nazm"),             # versified treatise
    (r"\bمتن\b", "matn"),             # base text (explicit)
]

# Fiqh madhab detection (from author field nisbas)
MADHAB_PATTERNS = {
    "الشافعي": "shafii",
    "الحنفي": "hanafi",
    "المالكي": "maliki",
    "الحنبلي": "hanbali",
}

# Grammatical school nisbas (الكوفي vs البصري is THE key distinction)
GRAMMAR_SCHOOL_NISBAS = {
    "البصري": "basri",
    "الكوفي": "kufi",
    "البغدادي": "baghdadi",
    "الأندلسي": "andalusi",
    "المصري": "misri",
}

# القسم → science mapping for validation (§3.6)
QISM_HIGH_RELIABILITY = {
    "البلاغة": "balagha",
    "الصرف": "sarf",
    "النحو": "nahw",
}
QISM_MEDIUM_RELIABILITY = {
    "النحو والصرف": ("nahw", "sarf"),
}
QISM_LOW_RELIABILITY = {"كتب اللغة"}

# Muhaqiq label patterns, ordered by priority (§3.5.2 Step 4)
MUHAQIQ_PATTERNS = [
    "دراسة وتحقيق",  # priority 4
    "المحقق",          # priority 5
    "تحقيق",           # priority 6
    "ضبط",             # priority 7
    "إعداد",           # priority 8
    "تخريج",           # priority 9
    "علق",             # priority 10
]

# Labels that contain muhaqiq substrings but are NOT muhaqiq fields.
# These are checked BEFORE muhaqiq matching to prevent false positives.
# "أصل التحقيق" = "origin of the tahqiq" (e.g., PhD thesis), not the editor.
MUHAQIQ_EXCLUSIONS = [
    "أصل التحقيق",
]

# Exact-match fields (§3.5.2 Step 4)
EXACT_FIELDS = {
    "القسم": "html_qism_field",
    "الكتاب": "title_formal",
    "المؤلف": "author",
    "الناشر": "publisher",
    "الطبعة": "shamela_edition",
    "عدد الصفحات": "shamela_page_count",
    "عدد الأجزاء": "shamela_volume_count",
    "عام النشر": "publication_year",
    "تاريخ النشر بالشاملة": "shamela_pub_date",
}


# ─── Utility ────────────────────────────────────────────────────────────────

def abort(msg):
    """Print error and exit."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg):
    """Print warning to stderr."""
    print(f"WARNING: {msg}", file=sys.stderr)


def info(msg):
    """Print info to stdout."""
    print(msg)


def prompt_yn(question, non_interactive=False, hard=False):
    """Prompt user for y/n. Returns True/False.
    
    hard=True + non_interactive=True → abort (cannot auto-decide)
    hard=False + non_interactive=True → auto-accept (soft confirmation)
    """
    if non_interactive:
        if hard:
            abort(f"Cannot auto-decide in --non-interactive mode: {question}")
        else:
            info(f"  [auto-accept] {question}")
            return True
    while True:
        answer = input(f"  {question} [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please enter 'y' or 'n'.")


def prompt_text(question, non_interactive=False):
    """Prompt user for free text. Hard in non-interactive."""
    if non_interactive:
        abort(f"Cannot collect text input in --non-interactive mode: {question}")
    return input(f"  {question} ").strip()


def sha256_file(path):
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def file_size(path):
    """Get file size in bytes."""
    return os.path.getsize(path)


def find_repo_root():
    """Find the repo root (directory containing books/, schemas/, tools/).
    taxonomy/ is checked but not required — it may not exist before Stage 5.
    Walk up from this script's location."""
    here = Path(__file__).resolve().parent  # tools/
    candidate = here.parent                 # should be repo root
    required = {"books", "schemas", "tools"}
    optional = {"taxonomy"}

    def _check(path):
        dirs = {p.name for p in path.iterdir() if p.is_dir()}
        if required.issubset(dirs):
            missing_optional = optional - dirs
            if missing_optional:
                for d in missing_optional:
                    warn(f"Optional directory '{d}/' not found at repo root. "
                         f"This is expected before the relevant stage is reached.")
            return True
        return False

    if _check(candidate):
        return candidate
    # Fallback: try CWD
    cwd = Path.cwd()
    if _check(cwd):
        return cwd
    abort("Cannot find repo root (expected directory containing books/, schemas/, tools/). "
          "Run from the repo root or from tools/.")


# ─── Metadata Parsing (§3.5) ───────────────────────────────────────────────

def strip_html(text):
    """§3.5.2 Step 2 — Strip HTML tags, normalize whitespace."""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('\xa0', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# Pattern for Shamela's floating annotations that sit between segments.
# These are NOT inside any <span class='title'> — they float in bare HTML
# between segments, so our regex attaches them to the TRAILING of the
# preceding segment, polluting that field's value.
# Known patterns: [ترقيم الكتاب ...], [الكتاب مرقم ...]
# Safe to strip because legitimate brackets (e.g., [ت 1392 هـ]) never
# start with these keywords.
_FLOATING_ANNOTATION_RE = re.compile(
    r'\s*\[(?:ترقيم الكتاب|الكتاب مرقم)[^\]]*\]\s*$'
)


def parse_metadata_card(html):
    """Parse metadata from first PageText div per §3.5.
    Returns (result_dict, error_string_or_None).
    """
    # Find first PageText div (§3.5, §3.2 regex safety note)
    m = re.search(r"<div class='PageText'>(.*?)</div>", html, re.DOTALL)
    if not m:
        return None, "No PageText div found in file."
    card = m.group(1)

    # §3.5.2 Step 1: Segment extraction
    segments = list(re.finditer(
        r"<span class='title'>(.*?)</span>(.*?)(?=<span class='title'>|$)",
        card, re.DOTALL
    ))
    if not segments:
        return None, "No <span class='title'> elements found in metadata card."

    result = {
        "title": None,
        "title_formal": None,
        "shamela_author_short": None,
        "author": None,
        "muhaqiq": None,
        "publisher": None,
        "shamela_page_count": None,
        "shamela_edition": None,
        "shamela_volume_count": None,
        "publication_year": None,
        "html_qism_field": None,
        "shamela_pub_date": None,
        "unrecognized_metadata_lines": [],
    }

    # §3.5.2 Step 3: Title extraction (first segment)
    first_span = segments[0].group(1)
    first_trail = segments[0].group(2)
    result["title"] = strip_html(first_span)

    # Author short from footnote span (raw HTML, before stripping)
    author_m = re.search(r"<span class='footnote'>\(([^)]+)\)</span>", first_trail)
    if author_m:
        result["shamela_author_short"] = author_m.group(1)

    # §3.5.2 Step 4: Field extraction (remaining segments)
    for seg in segments[1:]:
        span_content = seg.group(1)
        trailing = seg.group(2)

        # Concatenate, strip, normalize
        full_text = strip_html(span_content + trailing)

        # Strip floating annotations (e.g., [ترقيم الكتاب موافق للمطبوع])
        # that Shamela places between segments as bare HTML. These get
        # attached to the preceding segment's trailing content by our regex.
        # Only strip if the annotation is a SUFFIX of other content — if the
        # entire segment IS the annotation (as in ibn_aqil), let it through
        # to unrecognized_metadata_lines for data preservation.
        annotation_match = _FLOATING_ANNOTATION_RE.search(full_text)
        if annotation_match:
            stripped = full_text[:annotation_match.start()].rstrip()
            if stripped:  # Only strip if there's real content before the annotation
                full_text = stripped

        if ':' not in full_text:
            # No colon → unrecognized (e.g., [ترقيم...] in ibn_aqil)
            if full_text:
                result["unrecognized_metadata_lines"].append(full_text)
            continue

        label, value = full_text.split(':', 1)
        label = label.strip()
        value = value.strip()

        matched = False

        # Try exact matches first (priorities 1-3, 11-16)
        if label in EXACT_FIELDS:
            field = EXACT_FIELDS[label]
            if field in ("shamela_page_count", "shamela_volume_count"):
                dm = re.match(r'^(\d+)', value)
                result[field] = int(dm.group(1)) if dm else None
                if not dm:
                    warn(f"Could not extract digits from {label}: '{value}'")
            else:
                result[field] = value
            matched = True

        # Try muhaqiq contains patterns (ordered, first match wins)
        if not matched:
            # Check exclusions first — labels that contain muhaqiq substrings
            # but are NOT muhaqiq fields (e.g., أصل التحقيق)
            is_excluded = any(excl in label for excl in MUHAQIQ_EXCLUSIONS)
            if not is_excluded:
                for pat in MUHAQIQ_PATTERNS:
                    if pat in label:
                        if result["muhaqiq"] is None:
                            result["muhaqiq"] = value
                        else:
                            # Keep first muhaqiq, route subsequent to unrecognized
                            warn(f"Multiple muhaqiq-matching labels found. "
                                 f"Keeping first ('{result['muhaqiq'][:40]}...'). "
                                 f"Routing '{label}: {value[:40]}...' to unrecognized.")
                            result["unrecognized_metadata_lines"].append(full_text)
                        matched = True
                        break

        # Unrecognized
        if not matched:
            result["unrecognized_metadata_lines"].append(full_text)

    return result, None


def count_pages(html):
    """§3.2: Count PageNumber spans (NOT PageText divs)."""
    return len(re.findall(r"<span class='PageNumber'>", html))


# ─── Source Validation (§3.2) ──────────────────────────────────────────────

def validate_shamela_file(path):
    """§3.2: Validate a single .htm file. Returns list of errors (empty = OK)."""
    errors = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
    except UnicodeDecodeError:
        return [f"File {path.name} is not valid UTF-8. Shamela exports are expected to be UTF-8."]

    if '<html' not in html.lower():
        errors.append(f"File {path.name}: Not an HTML file (missing <html tag).")
    if "<div class='Main'>" not in html:
        errors.append(f"File {path.name}: Missing <div class='Main'> — not a Shamela format.")
    if "<div class='PageText'>" not in html:
        errors.append(f"File {path.name}: Missing <div class='PageText'> — not a Shamela format.")
    if "<span class='PageNumber'>" not in html:
        errors.append(f"File {path.name}: No PageNumber spans found. File may contain only metadata.")

    return errors


def classify_directory(dir_path):
    """§3.2: Classify files in a directory input.
    Returns (numbered_files, supplementary_candidates, skipped).
    numbered_files: list of (volume_number: int, path: Path)
    supplementary_candidates: list of Path
    skipped: list of Path
    """
    numbered = []
    supplementary = []
    skipped = []

    for entry in sorted(dir_path.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix.lower() != '.htm':
            skipped.append(entry)
            continue
        stem = entry.stem
        if re.match(r'^\d+$', stem):
            numbered.append((int(stem), entry))
        else:
            supplementary.append(entry)

    # Sort numbered by volume number
    numbered.sort(key=lambda x: x[0])
    return numbered, supplementary, skipped


# ─── Science Validation (§3.6) ─────────────────────────────────────────────

def collect_science_parts_interactive():
    """Interactively collect science parts for a multi-science book.

    Prompts the user for section name, science ID, and description in a loop.
    Requires at least 2 sections (otherwise it's not really multi-science).

    Returns a list of dicts with keys: section, science_id, description.
    """
    info("\n── Interactive multi-science mapping ──")
    info("  Define the sections of this multi-science book.")
    info(f"  Valid sciences: {', '.join(SINGLE_SCIENCES)}")
    info("  Add at least 2 sections. Press Enter on section name to finish.\n")
    parts = []
    while True:
        idx = len(parts) + 1
        section = prompt_text(f"Section {idx} name (e.g. القسم الأول) [Enter to finish]:")
        if not section:
            if len(parts) < 2:
                warn("  A multi-science book must have at least 2 sections. Keep going.")
                continue
            break
        # Science ID
        while True:
            sid = prompt_text(f"  Science for '{section}' ({'/'.join(SINGLE_SCIENCES)}):")
            if sid in SINGLE_SCIENCES:
                break
            warn(f"  Invalid science '{sid}'. Must be one of: {', '.join(SINGLE_SCIENCES)}")
        desc = prompt_text(f"  Description for '{section}' (e.g. علم الصرف والاشتقاق):")
        parts.append({
            "section": section,
            "science_id": sid,
            "description": desc,
        })
        info(f"  ✓ Added: {section} → {sid}")
    info(f"  Total sections: {len(parts)}")
    return parts


def validate_science(declared_science, qism_value, non_interactive):
    """§3.6: Cross-reference user's science declaration against القسم field.
    Returns the confirmed primary_science value.
    """
    if declared_science in ("adjacent", "unrelated", "multi"):
        # Soft confirmation for adjacent/unrelated/multi
        category_labels = {
            "adjacent": "adjacent field (related to Arabic language, not one of our 4 sciences)",
            "unrelated": "unrelated",
            "multi": "multi-science",
        }
        category_label = category_labels[declared_science]
        confirmed = prompt_yn(
            f"You declared this book as '{category_label}'. Confirm?",
            non_interactive=non_interactive, hard=False
        )
        if not confirmed:
            abort(f"User declined '{category_label}' classification. Aborting.")
        return declared_science

    if qism_value is None:
        warn("No القسم field found. Science classification relies on user declaration only.")
        return declared_science

    # High reliability — direct science match
    if qism_value in QISM_HIGH_RELIABILITY:
        mapped_science = QISM_HIGH_RELIABILITY[qism_value]
        if declared_science == mapped_science:
            info(f"  ✓ القسم '{qism_value}' matches declared science '{declared_science}'.")
            return declared_science
        else:
            # High reliability mismatch — hard confirmation
            confirmed = prompt_yn(
                f"القسم says '{qism_value}' (→ {mapped_science}), but you declared '{declared_science}'. "
                f"This is a high-reliability mismatch. Continue with '{declared_science}'?",
                non_interactive=non_interactive, hard=True
            )
            if not confirmed:
                abort("User declined science mismatch. Aborting.")
            return declared_science

    # Medium reliability — النحو والصرف
    if qism_value in QISM_MEDIUM_RELIABILITY:
        valid_pair = QISM_MEDIUM_RELIABILITY[qism_value]
        if declared_science in valid_pair:
            confirmed = prompt_yn(
                f"القسم is '{qism_value}' (could be either). You declared '{declared_science}'. Confirm?",
                non_interactive=non_interactive, hard=False
            )
            if not confirmed:
                abort("User declined science confirmation. Aborting.")
            return declared_science
        else:
            # User declared something outside the pair
            confirmed = prompt_yn(
                f"القسم is '{qism_value}', but you declared '{declared_science}'. Confirm?",
                non_interactive=non_interactive, hard=False
            )
            if not confirmed:
                abort("User declined science confirmation. Aborting.")
            return declared_science

    # Low reliability — broad categories
    if qism_value in QISM_LOW_RELIABILITY:
        info(f"  القسم '{qism_value}' is a broad category — user declaration is sole authority.")
        return declared_science

    # Unknown القسم value
    if declared_science in SINGLE_SCIENCES:
        confirmed = prompt_yn(
            f"القسم is '{qism_value}' (unknown mapping). You declared '{declared_science}'. Confirm?",
            non_interactive=non_interactive, hard=False
        )
        if not confirmed:
            abort("User declined science confirmation. Aborting.")
    return declared_science


# ─── Taxonomy Snapshot (§3.8) ──────────────────────────────────────────────

def snapshot_taxonomy(repo_root):
    """§3.8: Read active taxonomy versions from taxonomy_registry.yaml."""
    registry_path = repo_root / "taxonomy" / "taxonomy_registry.yaml"
    if not registry_path.exists():
        warn("No taxonomy registry found. taxonomy_at_intake will be empty.")
        return {}

    with open(registry_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "sciences" not in data:
        warn("Taxonomy registry is empty or malformed. taxonomy_at_intake will be empty.")
        return {}

    snapshot = {}
    for science in data["sciences"]:
        sid = science.get("science_id")
        for version in science.get("versions", []):
            if version.get("status") == "active":
                snapshot[sid] = version["taxonomy_version"]
                break

    # Check for sciences without active taxonomy
    for sid in SINGLE_SCIENCES:
        if sid not in snapshot:
            warn(f"No active taxonomy for {sid}. Taxonomy must be created before "
                 f"excerpting can begin for this science.")

    return snapshot


# ─── Registry Operations (§3.3, §3.9) ──────────────────────────────────────

def load_registry(repo_root):
    """Load books_registry.yaml. Returns (data_dict, path) or (None, path) if not found."""
    path = repo_root / "books" / "books_registry.yaml"
    if not path.exists():
        return None, path
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data, path


def check_duplicate_id(registry_data, book_id):
    """§3.1: Check if book_id already exists in registry."""
    if registry_data is None:
        return None
    books = registry_data.get("books", [])
    if not books:
        return None
    for book in books:
        if book.get("book_id") == book_id:
            return book.get("title", "(unknown)")
    return None


def check_duplicate_hashes(registry_data, file_hashes, force):
    """§3.3: Check if any file hash already exists in registry.
    file_hashes: dict of {filename: sha256_hex}
    Returns True if duplicates were found (and force-bypassed), False if clean.
    Aborts if duplicate found without --force.
    """
    if registry_data is None:
        return False
    books = registry_data.get("books", [])
    if not books:
        return False

    found_duplicate = False
    for filename, sha in file_hashes.items():
        for book in books:
            existing_hashes = book.get("source_hashes", [])
            if sha in existing_hashes:
                existing_id = book.get("book_id", "(unknown)")
                if force:
                    warn(f"File {filename} (SHA-256: {sha}) was already intaken as "
                         f"book '{existing_id}'. Proceeding due to --force.")
                    found_duplicate = True
                else:
                    abort(f"File {filename} (SHA-256: {sha}) was already intaken as "
                          f"book '{existing_id}'. Use --force to create a separate intake.")
    return found_duplicate


def build_registry_entry(metadata):
    """§4.3: Build a registry entry from intake metadata."""
    entry = {
        "book_id": metadata["book_id"],
        "shamela_book_id": metadata.get("shamela_book_id"),
        "title": metadata["title"],
        "title_formal": metadata.get("title_formal"),
        "author": metadata.get("author"),
        "muhaqiq": metadata.get("muhaqiq"),
        "primary_science": metadata.get("primary_science"),
        "book_category": metadata["book_category"],
        "source_format": "shamela_html",
        "source_files": [],
        "source_hashes": [],
        "volume_count": metadata["volume_count"],
        "language": metadata["language"],
        "edition_notes": metadata.get("edition_notes"),
        "status": "active",
    }

    for sf in metadata["source_files"]:
        sf_entry = {"relpath": sf["relpath"], "role": sf["role"]}
        if sf.get("volume_number") is not None:
            sf_entry["volume_number"] = sf["volume_number"]
        entry["source_files"].append(sf_entry)
        entry["source_hashes"].append(sf["sha256"])

    if metadata.get("science_parts"):
        entry["science_parts"] = metadata["science_parts"]

    # §3.9: Omit null fields for clean YAML
    return {k: v for k, v in entry.items() if v is not None}


def write_registry(registry_data, registry_path, new_entry):
    """§3.9: Atomically update books_registry.yaml."""
    if registry_data is None:
        # First intake — create new registry
        registry_data = {
            "registry_version": "1.0",
            "notes": (
                "Canonical registry of all input books known to the Arabic Book Digester (ABD).\n"
                "Generated by tools/intake.py. Each book's full metadata is in its intake_metadata.json.\n"
            ),
            "books": [new_entry],
        }
    else:
        if "books" not in registry_data or registry_data["books"] is None:
            registry_data["books"] = []
        registry_data["books"].append(new_entry)

    # Atomic write: write to temp file, then rename
    dir_path = registry_path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(registry_data, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False, width=120)
        os.replace(tmp_path, str(registry_path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass  # cleanup failure should not mask the original exception
        raise


# ─── Scholarly context extraction ──────────────────────────────────────────

def extract_scholarly_context(metadata):
    """Auto-extract structured scholarly context from existing metadata fields.
    
    Extracts from the author field: death date, fiqh madhab, grammatical school.
    Extracts from the title: book type (sharh, hashiya, mukhtasar, etc.).
    
    Returns a dict with all fields (None where not detected).
    """
    context = {
        "author_death_hijri": None,
        "author_birth_hijri": None,
        "fiqh_madhab": None,
        "grammatical_school": None,
        "geographic_origin": None,
        "book_type": None,
        "extraction_source": "auto",
    }

    author = metadata.get("author") or ""

    # ── Death date: patterns like (ت 739هـ), (ت ٧٣٩ هـ), (ت739 هـ) ────
    # Arabic numerals first, then Western
    death_match = re.search(r"ت\s*([٠-٩]+)\s*هـ", author)
    if death_match:
        arabic_num = death_match.group(1)
        # Convert Arabic-Indic numerals to Western
        context["author_death_hijri"] = int(
            arabic_num.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        )
    else:
        death_match = re.search(r"ت\s*(\d+)\s*هـ", author)
        if death_match:
            context["author_death_hijri"] = int(death_match.group(1))

    # ── Birth date: sometimes in (birth - death هـ) pattern ────────
    birth_match = re.search(r"\(([٠-٩\d]+)\s*[-–]\s*[٠-٩\d]+\s*هـ", author)
    if birth_match:
        raw = birth_match.group(1)
        context["author_birth_hijri"] = int(
            raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        )

    # ── Fiqh madhab: look for nisba patterns in author field ──────
    for pattern, madhab in MADHAB_PATTERNS.items():
        if pattern in author:
            context["fiqh_madhab"] = madhab
            break

    # ── Grammatical school: look for geographic nisbas ────────────
    for pattern, school in GRAMMAR_SCHOOL_NISBAS.items():
        if pattern in author:
            context["grammatical_school"] = school
            break

    # ── Geographic origin: extract the nisba (القزويني → قزوين) ───
    # Look for الXXXي pattern that's a place name (this is a heuristic)
    nisbas = re.findall(r"(ال[^\s,،()]+ي)\b", author)
    # Filter out non-geographic nisbas (madhabs, kunyah components, descriptors)
    non_geographic = set(MADHAB_PATTERNS.keys()) | {
        "المعروف", "العجلي", "المعالي",
        "الأصلي", "التقي", "العلي",
        "الأولي", "التالي", "الثاني",
    }
    geographic_nisbas = [n for n in nisbas if n not in non_geographic]
    if geographic_nisbas:
        # Prefer the last geographic nisba (most specific, closest to madhab)
        context["geographic_origin"] = geographic_nisbas[-1]

    # ── Book type: detect from title and title_formal ─────────────
    title_text = (metadata.get("title") or "") + " " + (metadata.get("title_formal") or "")
    for pattern, book_type in BOOK_TYPE_PATTERNS:
        if re.search(pattern, title_text):
            context["book_type"] = book_type
            break

    return context


def suggest_book_id(metadata):
    """Suggest a book ID based on extracted metadata.
    
    Convention: {distinctive_title_word}  or  {title_word}_{author_word}
    
    Returns a suggestion string (Arabic, for the user to transliterate)
    and a rationale.
    """
    title = metadata.get("title") or ""
    # Strip common prefixes that don't help identify the book
    skip_words = {"كتاب", "في", "على", "من", "إلى", "عن", "بين"}
    words = [w for w in title.split() if w not in skip_words and len(w) > 2]

    if not words:
        return None, None

    # First distinctive word
    key_word = words[0]

    author_short = metadata.get("shamela_author_short") or ""
    author_words = [w for w in author_short.split() if w not in skip_words and len(w) > 2]
    author_key = author_words[0] if author_words else None

    suggestion = key_word
    rationale = f"From title: '{key_word}'"
    if author_key:
        suggestion += f" ({author_key})"
        rationale += f", author: '{author_key}'"

    return suggestion, rationale


# ─── Volume filename normalization ─────────────────────────────────────────

def normalize_volume_filename(original_name, volume_number):
    """Normalize volume filenames to zero-padded 3-digit format.
    
    1.htm → 001.htm, 02.htm → 002.htm, 001.htm → 001.htm (unchanged).
    This ensures unambiguous sort order regardless of filesystem behavior.
    """
    ext = Path(original_name).suffix  # .htm
    return f"{volume_number:03d}{ext}"


# ─── Verification (--verify) ───────────────────────────────────────────────

def verify_intake(book_id, repo_root):
    """Verify integrity of an existing intake.
    Checks: metadata exists, validates against schema, source files exist
    with correct hashes, and registry entry is consistent.
    Returns (passed: bool, messages: list of str).
    """
    issues = []
    checks_passed = 0
    checks_total = 0

    book_dir = repo_root / "books" / book_id
    metadata_path = book_dir / "intake_metadata.json"

    # 1. Metadata file exists
    checks_total += 1
    if not metadata_path.exists():
        issues.append(f"FAIL: {metadata_path} does not exist.")
        # Can't continue without metadata
        return False, issues
    checks_passed += 1

    # 2. Metadata is valid JSON
    checks_total += 1
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        checks_passed += 1
    except json.JSONDecodeError as e:
        issues.append(f"FAIL: {metadata_path} is not valid JSON: {e}")
        return False, issues

    # 3. Schema validation
    checks_total += 1
    schema_path = repo_root / "schemas" / "intake_metadata_schema.json"
    if schema_path.exists():
        try:
            import jsonschema
            with open(schema_path, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(metadata, schema)
            checks_passed += 1
        except ImportError:
            issues.append("SKIP: jsonschema not installed — cannot validate schema.")
        except jsonschema.ValidationError as e:
            issues.append(f"FAIL: Schema validation error: {e.message}")
    else:
        issues.append(f"SKIP: Schema file not found at {schema_path}.")

    # 4. book_id consistency
    checks_total += 1
    if metadata.get("book_id") != book_id:
        issues.append(f"FAIL: Metadata book_id '{metadata.get('book_id')}' != requested '{book_id}'.")
    else:
        checks_passed += 1

    # 5. Source files exist and hashes match
    for sf in metadata.get("source_files", []):
        relpath = sf["relpath"]
        expected_sha = sf["sha256"]
        expected_size = sf["size_bytes"]
        full_path = repo_root / relpath

        checks_total += 1
        if not full_path.exists():
            issues.append(f"FAIL: Source file missing: {relpath}")
            continue

        actual_sha = sha256_file(full_path)
        if actual_sha != expected_sha:
            issues.append(f"FAIL: Hash mismatch for {relpath}: "
                          f"expected {expected_sha[:16]}..., got {actual_sha[:16]}...")
            continue

        actual_size = file_size(full_path)
        if actual_size != expected_size:
            issues.append(f"WARN: Size mismatch for {relpath}: "
                          f"expected {expected_size}, got {actual_size}")
            # Size mismatch with matching hash is theoretically impossible,
            # but check anyway for filesystem weirdness
        checks_passed += 1

    # 6. Registry consistency
    checks_total += 1
    registry_data, _ = load_registry(repo_root)
    reg_issues = []
    if registry_data is None:
        reg_issues.append("FAIL: books_registry.yaml not found.")
    else:
        books = registry_data.get("books", [])
        reg_entry = None
        for b in books:
            if b.get("book_id") == book_id:
                reg_entry = b
                break
        if reg_entry is None:
            reg_issues.append(f"FAIL: Book '{book_id}' not found in registry.")
        else:
            # Cross-check key fields
            if reg_entry.get("title") != metadata.get("title"):
                reg_issues.append(f"FAIL: Title mismatch between registry and metadata.")
            if reg_entry.get("volume_count") != metadata.get("volume_count"):
                reg_issues.append(f"FAIL: Volume count mismatch between registry and metadata.")

            reg_hashes = reg_entry.get("source_hashes", [])
            meta_hashes = [sf["sha256"] for sf in metadata.get("source_files", [])]
            if reg_hashes != meta_hashes:
                reg_issues.append(f"FAIL: Source hashes mismatch between registry "
                              f"({len(reg_hashes)} hashes) and metadata ({len(meta_hashes)} hashes).")

    issues.extend(reg_issues)
    if not reg_issues or all("WARN" in i or "SKIP" in i for i in reg_issues):
        checks_passed += 1

    passed = checks_passed == checks_total
    summary = f"{checks_passed}/{checks_total} checks passed"
    return passed, [summary] + issues


# ─── Main Pipeline ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Stage 0: Book Intake — freeze source, extract metadata, register book.",
        epilog="See INTAKE_SPEC.md for full documentation."
    )
    parser.add_argument("source", nargs="?", default=None,
                        help="Source .htm file or directory of .htm files")
    parser.add_argument("--book-id", default=None, help="Short ASCII book identifier (3-40 chars)")
    parser.add_argument("--science", default=None,
                        help="Primary science (e.g., imlaa, sarf, nahw, balagha, fiqh, hadith)")
    parser.add_argument("--science-parts", help="YAML file mapping sections to sciences (required for --science multi)")
    parser.add_argument("--notes", help="Free-text edition/context notes")
    parser.add_argument("--shamela-id", type=int, metavar="N",
                        help="Shamela Library book ID (enables shamela.ws/book/N reference)")
    parser.add_argument("--force", action="store_true", help="Bypass duplicate SHA-256 check")
    parser.add_argument("--non-interactive", action="store_true", help="Skip interactive prompts")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without writing")
    parser.add_argument("--verify", metavar="BOOK_ID",
                        help="Verify integrity of an existing intake (source hashes, schema, registry consistency)")

    args = parser.parse_args()
    repo_root = find_repo_root()

    # ── --verify mode: verify existing intake and exit ────────────────
    if args.verify:
        info("=" * 60)
        info(f"Stage 0: Verify Intake — {args.verify}")
        info("=" * 60)
        passed, messages = verify_intake(args.verify, repo_root)
        for msg in messages:
            info(f"  {msg}")
        if passed:
            info(f"\n✅ Intake '{args.verify}' verified successfully.")
        else:
            info(f"\n❌ Intake '{args.verify}' has integrity issues.")
        sys.exit(0 if passed else 1)

    # ── Validate required args for intake mode ────────────────────────
    if not args.source:
        parser.error("the following arguments are required: source (unless using --verify)")
    if not args.book_id:
        parser.error("the following arguments are required: --book-id (unless using --verify)")
    if not args.science:
        parser.error("the following arguments are required: --science (unless using --verify)")

    info("=" * 60)
    info("Stage 0: Book Intake")
    info("=" * 60)

    # ── §3.0 CLI and path validation ──────────────────────────────────

    source_path = Path(args.source).resolve()
    if not source_path.exists():
        abort(f"Source path '{args.source}' does not exist.")

    # Flag consistency
    if args.science == "multi" and not args.science_parts and args.non_interactive:
        abort("--science-parts is required when --science is 'multi' in --non-interactive mode.")
    if args.science_parts and args.science != "multi":
        abort(f"--science-parts is only allowed when --science is 'multi'. "
              f"You passed --science '{args.science}'.")

    # Validate or interactively build science_parts
    science_parts = None
    if args.science == "multi" and not args.science_parts:
        # Interactive multi-science input
        science_parts = collect_science_parts_interactive()
    elif args.science_parts:
        parts_path = Path(args.science_parts)
        if not parts_path.exists():
            abort(f"Science parts file '{args.science_parts}' does not exist.")
        try:
            with open(parts_path, "r", encoding="utf-8") as f:
                science_parts = yaml.safe_load(f)
        except yaml.YAMLError as e:
            abort(f"Science parts file is not valid YAML: {e}")
        if not isinstance(science_parts, list):
            abort("Science parts file must be a YAML list.")
        for i, item in enumerate(science_parts):
            if not isinstance(item, dict):
                abort(f"Science parts item {i} is not an object.")
            for key in ("section", "science_id", "description"):
                if key not in item:
                    abort(f"Science parts item {i} missing required key '{key}'.")
            if item["science_id"] not in SINGLE_SCIENCES:
                abort(f"Science parts item {i} has invalid science_id '{item['science_id']}'. "
                      f"Must be one of: {', '.join(SINGLE_SCIENCES)}.")

    info(f"\n  Source:     {source_path}")
    info(f"  Book ID:   {args.book_id}")
    info(f"  Science:   {args.science}")
    if args.dry_run:
        info("  Mode:      DRY RUN (no files will be written)")
    if args.non_interactive:
        info("  Mode:      Non-interactive")
    if args.force:
        info("  Mode:      Force (bypass duplicate check)")

    # ── §3.1 Book ID validation ───────────────────────────────────────

    info("\n── Book ID validation ──")
    book_id = args.book_id

    if len(book_id) < 3 or len(book_id) > 40:
        abort(f"Book ID '{book_id}' is {len(book_id)} characters. Must be 3–40.")

    if not BOOK_ID_PATTERN.match(book_id):
        abort(f"Book ID '{book_id}' contains invalid characters. Must match [a-z][a-z_]*[a-z] "
              f"(start and end with a letter, only lowercase letters and underscores).")

    # Check uniqueness against registry
    registry_data, registry_path = load_registry(repo_root)
    if registry_data is not None:
        existing_title = check_duplicate_id(registry_data, book_id)
        if existing_title:
            abort(f"Book ID '{book_id}' already exists in the registry (book: {existing_title}). "
                  f"Choose a different ID.")
    else:
        info("  Registry does not exist yet (first intake). Will be created.")

    info(f"  ✓ Book ID '{book_id}' is valid and unique.")

    # ── §3.2 Source validation ────────────────────────────────────────

    info("\n── Source validation ──")

    # Determine input mode and collect files
    source_files_info = []  # list of dicts with path, role, volume_number, etc.

    if source_path.is_file():
        # Single file input
        if source_path.suffix.lower() != '.htm':
            abort(f"Source file must be .htm, got '{source_path.suffix}'.")
        errors = validate_shamela_file(source_path)
        if errors:
            abort("\n".join(errors))
        html = source_path.read_text(encoding="utf-8")
        pages = count_pages(html)
        source_files_info.append({
            "original_path": source_path,
            "target_name": source_path.name,
            "role": "primary_export",
            "volume_number": None,
            "actual_page_count": pages,
            "file_note": None,
        })
        info(f"  ✓ Single file: {source_path.name} ({pages} pages)")

    elif source_path.is_dir():
        # Directory input
        numbered, supplementary_candidates, skipped = classify_directory(source_path)

        if skipped:
            for s in skipped:
                info(f"  Skipping non-.htm file: {s.name}")

        if len(numbered) == 0:
            abort("No numbered .htm files found in directory.")

        # Validate all numbered files
        for vol_num, fpath in numbered:
            errors = validate_shamela_file(fpath)
            if errors:
                abort("\n".join(errors))

        # Check for gaps in numbering
        vol_numbers = [n for n, _ in numbered]
        expected = list(range(vol_numbers[0], vol_numbers[-1] + 1))
        if vol_numbers != expected:
            missing = set(expected) - set(vol_numbers)
            warn(f"Gaps in volume numbering. Missing: {sorted(missing)}")

        if len(numbered) == 1:
            # Exactly 1 numbered file → single-volume (EC-I.12)
            vol_num, fpath = numbered[0]
            html = fpath.read_text(encoding="utf-8")
            pages = count_pages(html)
            source_files_info.append({
                "original_path": fpath,
                "target_name": fpath.name,
                "role": "primary_export",
                "volume_number": None,
                "actual_page_count": pages,
                "file_note": None,
            })
            info(f"  ✓ Single file in directory: {fpath.name} ({pages} pages)")
        else:
            # Multi-volume
            for vol_num, fpath in numbered:
                html = fpath.read_text(encoding="utf-8")
                pages = count_pages(html)
                normalized_name = normalize_volume_filename(fpath.name, vol_num)
                source_files_info.append({
                    "original_path": fpath,
                    "target_name": normalized_name,
                    "role": "volume",
                    "volume_number": vol_num,
                    "actual_page_count": pages,
                    "file_note": None,
                })
                rename_note = f" (→ {normalized_name})" if normalized_name != fpath.name else ""
                info(f"  ✓ Volume {vol_num}: {fpath.name}{rename_note} ({pages} pages)")

        # Supplementary files (§3.2)
        if supplementary_candidates:
            names = ", ".join(s.name for s in supplementary_candidates)
            include = prompt_yn(
                f"Found non-numbered file(s): {names}. Include as supplementary?",
                non_interactive=args.non_interactive, hard=True
            )
            if include:
                for sup_path in supplementary_candidates:
                    errors = validate_shamela_file(sup_path)
                    if errors:
                        abort("\n".join(errors))
                    html = sup_path.read_text(encoding="utf-8")
                    pages = count_pages(html)
                    note = prompt_text(
                        f"Brief description for {sup_path.name}:",
                        non_interactive=args.non_interactive
                    )
                    source_files_info.append({
                        "original_path": sup_path,
                        "target_name": sup_path.name,
                        "role": "supplementary",
                        "volume_number": None,
                        "actual_page_count": pages,
                        "file_note": note if note else None,
                    })
                    info(f"  ✓ Supplementary: {sup_path.name} ({pages} pages)")
    else:
        abort(f"Source path '{source_path}' is neither a file nor a directory.")

    # ── §3.3 Duplicate detection ──────────────────────────────────────

    info("\n── Duplicate detection ──")

    # Compute hashes for all files
    file_hashes = {}
    for sf in source_files_info:
        sha = sha256_file(sf["original_path"])
        sf["sha256"] = sha
        sf["size_bytes"] = file_size(sf["original_path"])
        file_hashes[sf["target_name"]] = sha

    # Intra-intake duplicates
    seen_hashes = {}
    for name, sha in file_hashes.items():
        if sha in seen_hashes:
            warn(f"Files {seen_hashes[sha]} and {name} have identical content (SHA-256: {sha}).")
        else:
            seen_hashes[sha] = name

    # Inter-book duplicates (skip if no registry)
    if registry_data is not None:
        had_duplicates = check_duplicate_hashes(registry_data, file_hashes, args.force)
        if not had_duplicates:
            info("  ✓ No duplicate files found in registry.")
    else:
        info("  ✓ No registry yet — skipping inter-book duplicate check.")

    # ── §3.5 Metadata extraction ──────────────────────────────────────

    info("\n── Metadata extraction ──")

    # Determine which file to extract metadata from
    primary_files = [sf for sf in source_files_info if sf["role"] == "primary_export"]
    volume_files = [sf for sf in source_files_info if sf["role"] == "volume"]

    if primary_files:
        metadata_source = primary_files[0]
    elif volume_files:
        metadata_source = sorted(volume_files, key=lambda x: x["volume_number"])[0]
    else:
        abort("No primary_export or volume file found to extract metadata from.")

    html = metadata_source["original_path"].read_text(encoding="utf-8")
    metadata, err = parse_metadata_card(html)
    if err:
        abort(f"Metadata extraction failed on {metadata_source['target_name']}: {err}")

    if not metadata["title"]:
        abort("Title is missing from metadata card. Cannot proceed.")

    info(f"  Title: {metadata['title']}")
    if metadata["title_formal"]:
        info(f"  Title (formal): {metadata['title_formal']}")
    if metadata["author"]:
        info(f"  Author: {metadata['author']}")
    if metadata["muhaqiq"]:
        info(f"  Muhaqiq: {metadata['muhaqiq']}")
    if metadata["publisher"]:
        info(f"  Publisher: {metadata['publisher']}")
    if metadata["html_qism_field"]:
        info(f"  القسم: {metadata['html_qism_field']}")
    if metadata["shamela_page_count"] is not None:
        info(f"  Shamela page count: {metadata['shamela_page_count']}")
    if metadata["unrecognized_metadata_lines"]:
        for line in metadata["unrecognized_metadata_lines"]:
            info(f"  [unrecognized] {line}")

    # ── §3.6 Science validation ───────────────────────────────────────

    info("\n── Science validation ──")
    confirmed_science = validate_science(
        args.science, metadata["html_qism_field"], args.non_interactive
    )

    # ── §3.7 Book category determination ──────────────────────────────

    if confirmed_science == "multi":
        book_category = "multi_science"
        primary_science = None
    elif confirmed_science == "adjacent":
        book_category = "adjacent_field"
        primary_science = None
    elif confirmed_science == "unrelated":
        book_category = "tangentially_relevant"
        primary_science = None
    else:
        # Any specific science name (known or new) is a single-science book.
        # Engine is science-agnostic — accepts any science name.
        book_category = "single_science"
        primary_science = confirmed_science
        if confirmed_science not in CORE_SCIENCES:
            info(f"  NOTE: '{confirmed_science}' is not in the core set {CORE_SCIENCES}. "
                 f"Proceeding (engine is science-agnostic).")

    info(f"  Category: {book_category}")
    if primary_science:
        info(f"  Primary science: {primary_science}")

    # ── Scholarly context extraction ──────────────────────────────────

    scholarly_ctx = extract_scholarly_context(metadata)
    has_any = any(v is not None for k, v in scholarly_ctx.items() if k != "extraction_source")

    if has_any:
        info("\n── Scholarly context (auto-extracted) ──")
        if scholarly_ctx["author_death_hijri"]:
            info(f"  Death (Hijri): {scholarly_ctx['author_death_hijri']} هـ")
        if scholarly_ctx["author_birth_hijri"]:
            info(f"  Birth (Hijri): {scholarly_ctx['author_birth_hijri']} هـ")
        if scholarly_ctx["fiqh_madhab"]:
            info(f"  Fiqh madhab: {scholarly_ctx['fiqh_madhab']}")
        if scholarly_ctx["grammatical_school"]:
            info(f"  Grammatical school: {scholarly_ctx['grammatical_school']}")
        if scholarly_ctx["geographic_origin"]:
            info(f"  Geographic origin: {scholarly_ctx['geographic_origin']}")
        if scholarly_ctx["book_type"]:
            info(f"  Book type: {scholarly_ctx['book_type']}")
    else:
        info("\n── Scholarly context ──")
        info("  (no structured data auto-extracted from metadata)")
        scholarly_ctx = None  # Don't store empty context

    # ── Book ID suggestion ────────────────────────────────────────────

    suggestion, rationale = suggest_book_id(metadata)
    if suggestion and not args.non_interactive:
        info(f"\n  Book ID convention hint: consider transliterating '{suggestion}'")
        if rationale:
            info(f"  ({rationale})")

    # ── EC-I.6 Truncation check ───────────────────────────────────────

    total_actual_pages = sum(sf["actual_page_count"] for sf in source_files_info)
    shamela_count = metadata["shamela_page_count"]

    if shamela_count is not None and shamela_count > 0:
        ratio = total_actual_pages / shamela_count
        if ratio < 0.80:
            pct = round(ratio * 100, 1)
            confirmed = prompt_yn(
                f"HTML may be truncated. Shamela metadata says {shamela_count} pages, "
                f"actual content has {total_actual_pages} pages ({pct}%). Continue anyway?",
                non_interactive=args.non_interactive, hard=False
            )
            if not confirmed:
                abort("User declined to proceed with potentially truncated source.")
        elif ratio > 1.25:
            pct = round(ratio * 100, 1)
            warn(f"Actual page count ({total_actual_pages}) significantly exceeds "
                 f"Shamela metadata ({shamela_count}) — {pct}%. "
                 f"Shamela count may be inaccurate or metadata may be stale.")

    # ── Volume count cross-check ──────────────────────────────────────

    shamela_vol_count = metadata["shamela_volume_count"]
    actual_vol_count = len([sf for sf in source_files_info if sf["role"] == "volume"])
    if shamela_vol_count is not None and actual_vol_count > 0:
        if actual_vol_count != shamela_vol_count:
            warn(f"Shamela metadata says {shamela_vol_count} volumes, "
                 f"but {actual_vol_count} volume files found. "
                 f"Export may be incomplete or Shamela count may be inaccurate.")

    # ── §3.8 Taxonomy snapshot ────────────────────────────────────────

    info("\n── Taxonomy snapshot ──")
    taxonomy_snapshot = snapshot_taxonomy(repo_root)
    if taxonomy_snapshot:
        for sid, ver in taxonomy_snapshot.items():
            info(f"  {sid}: {ver}")
    else:
        info("  (empty — no active taxonomies)")

    # ── Build complete metadata ───────────────────────────────────────

    volume_count = len([sf for sf in source_files_info if sf["role"] == "volume"])
    if volume_count == 0:
        volume_count = 1  # Single-volume book

    # Build source_files entries with relpaths
    source_files_out = []
    for sf in source_files_info:
        relpath = f"books/{book_id}/source/{sf['target_name']}"
        source_files_out.append({
            "relpath": relpath,
            "sha256": sf["sha256"],
            "size_bytes": sf["size_bytes"],
            "role": sf["role"],
            "volume_number": sf["volume_number"],
            "actual_page_count": sf["actual_page_count"],
            "file_note": sf["file_note"],
        })

    intake_metadata = {
        "schema_version": SCHEMA_VERSION,
        "book_id": book_id,
        "shamela_book_id": args.shamela_id,
        "title": metadata["title"],
        "title_formal": metadata["title_formal"],
        "shamela_author_short": metadata["shamela_author_short"],
        "author": metadata["author"],
        "muhaqiq": metadata["muhaqiq"],
        "publisher": metadata["publisher"],
        "shamela_page_count": metadata["shamela_page_count"],
        "shamela_edition": metadata["shamela_edition"],
        "shamela_volume_count": metadata["shamela_volume_count"],
        "publication_year": metadata["publication_year"],
        "html_qism_field": metadata["html_qism_field"],
        "shamela_pub_date": metadata["shamela_pub_date"],
        "primary_science": primary_science,
        "book_category": book_category,
        "science_parts": science_parts,
        "scholarly_context": scholarly_ctx,
        "volume_count": volume_count,
        "total_actual_pages": total_actual_pages,
        "source_files": source_files_out,
        "unrecognized_metadata_lines": metadata["unrecognized_metadata_lines"],
        "edition_notes": args.notes if args.notes else None,
        "language": "ar",
        "intake_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "taxonomy_at_intake": taxonomy_snapshot,
    }

    # ── §3.9 Write outputs (or dry-run preview) ──────────────────────

    book_dir = repo_root / "books" / book_id
    source_dir = book_dir / "source"
    metadata_path = book_dir / "intake_metadata.json"

    if args.dry_run:
        info("\n── DRY RUN — Preview ──")
        info(f"\n  Would create: {book_dir}/")
        info(f"  Would create: {source_dir}/")
        for sf in source_files_info:
            info(f"    Copy: {sf['original_path'].name} → {source_dir / sf['target_name']}")
        info(f"  Would write: {metadata_path}")
        info(f"  Would update: {registry_path}")
        info(f"\n  Metadata preview:")
        print(json.dumps(intake_metadata, ensure_ascii=False, indent=2))
        info("\n  Registry entry preview:")
        reg_entry = build_registry_entry(intake_metadata)
        print(yaml.dump([reg_entry], allow_unicode=True, default_flow_style=False, sort_keys=False))
        info("DRY RUN complete. No files written.")
        return

    info("\n── Writing outputs ──")

    # Atomic operation: if anything fails, clean up
    created_book_dir = False
    try:
        # Create directories
        source_dir.mkdir(parents=True, exist_ok=False)
        created_book_dir = True
        info(f"  Created: {book_dir}/")

        # §3.4 Source freezing — copy files
        for sf in source_files_info:
            src = sf["original_path"]
            dst = source_dir / sf["target_name"]
            shutil.copy2(str(src), str(dst))
            info(f"  Copied: {sf['target_name']}")

        # Verify hashes after copy
        for sf in source_files_info:
            dst = source_dir / sf["target_name"]
            actual_sha = sha256_file(dst)
            if actual_sha != sf["sha256"]:
                raise RuntimeError(f"Hash mismatch after copy for {sf['target_name']}! "
                                   f"Expected {sf['sha256']}, got {actual_sha}")
        info("  ✓ All file hashes verified after copy.")

        # Set source directory to read-only
        for f in source_dir.iterdir():
            os.chmod(str(f), 0o444)
        os.chmod(str(source_dir), 0o555)
        info("  ✓ Source directory set to read-only.")

        # Write intake_metadata.json
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(intake_metadata, f, ensure_ascii=False, indent=2)
            f.write("\n")
        info(f"  ✓ Wrote: {metadata_path}")

        # Validate against schema
        schema_path = repo_root / "schemas" / "intake_metadata_schema.json"
        if schema_path.exists():
            try:
                import jsonschema
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                jsonschema.validate(intake_metadata, schema)
                info("  ✓ Metadata validates against schema.")
            except ImportError:
                warn("jsonschema not installed — skipping schema validation.")
            except jsonschema.ValidationError as e:
                raise RuntimeError(f"Metadata fails schema validation: {e.message}")

        # Update registry
        reg_entry = build_registry_entry(intake_metadata)
        write_registry(registry_data, registry_path, reg_entry)
        info(f"  ✓ Updated: {registry_path}")

    except Exception as e:
        # Atomic rollback: remove book directory if partially created
        if created_book_dir and book_dir.exists():
            # Need to restore write permissions before removal
            for dirpath, dirnames, filenames in os.walk(str(book_dir)):
                os.chmod(dirpath, 0o755)
                for fn in filenames:
                    os.chmod(os.path.join(dirpath, fn), 0o644)
            shutil.rmtree(str(book_dir))
            warn(f"Rolled back: removed {book_dir}/")
        abort(f"Intake failed: {e}")

    # ── Success ───────────────────────────────────────────────────────

    info("\n" + "=" * 60)
    info(f"✅ Intake complete: {book_id}")
    info(f"   Title: {metadata['title']}")
    info(f"   Category: {book_category}")
    info(f"   Files: {len(source_files_info)}")
    info(f"   Pages: {total_actual_pages}")
    info(f"   Directory: {book_dir}/")
    info("=" * 60)


if __name__ == "__main__":
    main()

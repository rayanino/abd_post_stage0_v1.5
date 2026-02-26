#!/usr/bin/env python3
"""Tests for Stage 0.5: Scholarly Enrichment (tools/enrich.py)"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from enrich import extract_from_tarjama, get_gaps


# ─── Tarjama extraction ───────────────────────────────────────────────────

class TestTarjamaExtraction:
    QAZWINI = """القزويني (666 - 739 هـ = 1268 - 1338 م)
    محمد بن عبد الرحمن بن عمر، أبو المعالي، جلال الدين القزويني الشافعي،
    المعروف بخطيب دمشق. أصله من قزوين، ومولده بالموصل.
    ولي القضاء ثم توفي سنة 739 هـ."""

    JURJANI = """عبد القاهر الجرجاني (ت 471 هـ)
    أبو بكر عبد القاهر بن عبد الرحمن الجرجاني. من أئمة اللغة العربية.
    ولد في جرجان. صاحب دلائل الإعجاز وأسرار البلاغة."""

    IBN_HISHAM = """ابن هشام الأنصاري (708 - 761 هـ)
    عبد الله بن يوسف بن أحمد بن عبد الله بن هشام الأنصاري المصري الحنبلي.
    نحوي مصري من كبار العلماء بالعربية. كان يلقب بالبصري لميله إلى مذهب البصريين."""

    def test_death_from_parenthetical(self):
        result = extract_from_tarjama(self.QAZWINI)
        assert result.get("author_death_hijri") == 739

    def test_birth_from_range(self):
        result = extract_from_tarjama(self.QAZWINI)
        assert result.get("author_birth_hijri") == 666

    def test_madhab_shafii(self):
        result = extract_from_tarjama(self.QAZWINI)
        assert result.get("fiqh_madhab") == "shafii"

    def test_geographic_qazwini(self):
        result = extract_from_tarjama(self.QAZWINI)
        assert result.get("geographic_origin") == "القزويني"

    def test_death_from_ta(self):
        result = extract_from_tarjama(self.JURJANI)
        assert result.get("author_death_hijri") == 471

    def test_geographic_jurjani(self):
        result = extract_from_tarjama(self.JURJANI)
        assert result.get("geographic_origin") == "الجرجاني"

    def test_madhab_hanbali(self):
        result = extract_from_tarjama(self.IBN_HISHAM)
        assert result.get("fiqh_madhab") == "hanbali"

    def test_death_from_range_second(self):
        result = extract_from_tarjama(self.IBN_HISHAM)
        assert result.get("author_death_hijri") == 761

    def test_birth_from_range_first(self):
        result = extract_from_tarjama(self.IBN_HISHAM)
        assert result.get("author_birth_hijri") == 708

    def test_geographic_misri(self):
        result = extract_from_tarjama(self.IBN_HISHAM)
        assert result.get("geographic_origin") == "الأنصاري"

    def test_school_basri(self):
        result = extract_from_tarjama(self.IBN_HISHAM)
        assert result.get("grammatical_school") == "basri"

    def test_empty_text(self):
        result = extract_from_tarjama("")
        assert len(result) == 0

    def test_no_false_positives_on_book_terms(self):
        """Arabic language terms ending in ي should not be captured."""
        text = "كتاب في علم المعاني والبيان والبديع"
        result = extract_from_tarjama(text)
        geo = result.get("geographic_origin")
        assert geo not in ("المعاني", "البيان", "البديع")


# ─── Gap detection ─────────────────────────────────────────────────────────

class TestGetGaps:
    def test_none_context(self):
        gaps = get_gaps(None)
        assert len(gaps) == 6

    def test_full_context(self):
        ctx = {
            "author_death_hijri": 471,
            "author_birth_hijri": 400,
            "fiqh_madhab": "shafii",
            "grammatical_school": "basri",
            "geographic_origin": "الجرجاني",
            "book_type": "matn",
        }
        gaps = get_gaps(ctx)
        assert len(gaps) == 0

    def test_partial_context(self):
        ctx = {
            "author_death_hijri": 471,
            "author_birth_hijri": None,
            "fiqh_madhab": None,
            "grammatical_school": None,
            "geographic_origin": "الجرجاني",
            "book_type": None,
        }
        gaps = get_gaps(ctx)
        assert "author_birth_hijri" in gaps
        assert "fiqh_madhab" in gaps
        assert "author_death_hijri" not in gaps
        assert "geographic_origin" not in gaps

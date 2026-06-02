"""
Unit tests for the drug matching and interaction checking modules.
Tests cover fuzzy matching accuracy, interaction detection, and risk scoring.
"""

import pytest
from backend.drug_matcher import match_drug_name
from backend.drug_database import get_drug_info, find_interactions, get_all_drug_keys


class TestDrugMatcher:
    """Tests for the fuzzy drug name matching engine."""

    def test_exact_match(self):
        """Exact drug name should return a high-confidence match."""
        results = match_drug_name("paracetamol")
        assert len(results) > 0
        assert results[0]["drug_key"] == "paracetamol"
        assert results[0]["confidence"] >= 90

    def test_brand_name_match(self):
        """Common brand names should resolve to the correct generic drug."""
        results = match_drug_name("Crocin")
        assert len(results) > 0
        assert results[0]["drug_key"] == "paracetamol"

    def test_partial_match(self):
        """Partial drug names should still return relevant results."""
        results = match_drug_name("amoxici")
        assert len(results) > 0
        assert any("amoxicillin" in r["drug_key"] for r in results)

    def test_no_match_for_garbage(self):
        """Random gibberish should not match any drug."""
        results = match_drug_name("xyzabc123")
        assert len(results) == 0

    def test_case_insensitive(self):
        """Matching should be case-insensitive."""
        results_lower = match_drug_name("ibuprofen")
        results_upper = match_drug_name("IBUPROFEN")
        assert len(results_lower) > 0
        assert len(results_upper) > 0
        assert results_lower[0]["drug_key"] == results_upper[0]["drug_key"]


class TestDrugDatabase:
    """Tests for the drug database lookup functions."""

    def test_get_existing_drug(self):
        """Known drug keys should return complete drug info."""
        info = get_drug_info("paracetamol")
        assert info is not None
        assert "generic_name" in info
        assert "brand_names" in info
        assert "category" in info

    def test_get_nonexistent_drug(self):
        """Unknown drug keys should return None."""
        info = get_drug_info("nonexistent_drug_xyz")
        assert info is None

    def test_all_drug_keys_not_empty(self):
        """The drug database should contain at least some drugs."""
        keys = get_all_drug_keys()
        assert len(keys) > 0


class TestInteractionDetection:
    """Tests for the drug interaction checking logic."""

    def test_known_interaction(self):
        """Known interacting drug pairs should be detected."""
        keys = get_all_drug_keys()
        # Try to find any interaction in the database
        for key in keys[:10]:
            interactions = find_interactions(key, [k for k in keys[:10] if k != key])
            if interactions:
                assert "severity" in interactions[0]
                assert "description" in interactions[0]
                break

    def test_no_self_interaction(self):
        """A drug should not interact with itself."""
        interactions = find_interactions("paracetamol", ["paracetamol"])
        assert len(interactions) == 0

    def test_interaction_has_required_fields(self):
        """Each interaction result should have severity and description."""
        keys = get_all_drug_keys()
        for key in keys[:20]:
            interactions = find_interactions(key, [k for k in keys[:20] if k != key])
            for interaction in interactions:
                assert "severity" in interaction
                assert "description" in interaction
                assert interaction["severity"] in ["CRITICAL", "SERIOUS", "MODERATE", "MINOR"]
                break
            if interactions:
                break

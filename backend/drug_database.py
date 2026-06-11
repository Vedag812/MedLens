"""
MedLens Drug Database Module
Loads and provides access to the bundled drug + interaction database.
"""

import json
import os
from typing import Optional

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_db = None


def _load_db():
    """Load the drug database from JSON file (singleton)."""
    global _db
    if _db is None:
        db_path = os.path.join(_DATA_DIR, "drugs.json")
        with open(db_path, "r", encoding="utf-8") as f:
            _db = json.load(f)
    return _db


def get_all_drug_keys() -> list[str]:
    """Return all canonical drug keys (lowercase generic names)."""
    db = _load_db()
    return list(db["drugs"].keys())


def get_all_brand_names() -> dict[str, str]:
    """Return a mapping of brand_name (lowercase) -> canonical drug key."""
    db = _load_db()
    mapping = {}
    for key, info in db["drugs"].items():
        for brand in info.get("brand_names", []):
            # Store lowercase, strip parenthetical notes
            clean = brand.split("(")[0].strip().lower()
            mapping[clean] = key
    return mapping


def get_drug_info(drug_key: str) -> Optional[dict]:
    """Get full drug information by canonical key."""
    db = _load_db()
    return db["drugs"].get(drug_key)


def get_all_interactions() -> list[dict]:
    """Return all drug-drug interaction records."""
    db = _load_db()
    return db.get("interactions", [])


def find_interactions(drug_key: str, vault_keys: list[str]) -> list[dict]:
    """
    Check a drug against a list of vault drugs for interactions.
    Returns list of matching interactions with severity and description.
    """
    interactions = get_all_interactions()
    results = []

    for interaction in interactions:
        a = interaction["drug_a"]
        b = interaction["drug_b"]

        # Check if the scanned drug interacts with any vault drug
        if drug_key == a and b in vault_keys:
            results.append({
                "interacting_drug": b,
                "interacting_drug_name": get_drug_info(b)["generic_name"] if get_drug_info(b) else b,
                "severity": interaction["severity"],
                "description": interaction["description"],
                "recommendation": interaction["recommendation"],
            })
        elif drug_key == b and a in vault_keys:
            results.append({
                "interacting_drug": a,
                "interacting_drug_name": get_drug_info(a)["generic_name"] if get_drug_info(a) else a,
                "severity": interaction["severity"],
                "description": interaction["description"],
                "recommendation": interaction["recommendation"],
            })

    # Sort by severity: CRITICAL > SERIOUS > MODERATE > MINOR
    severity_order = {"CRITICAL": 0, "SERIOUS": 1, "MODERATE": 2, "MINOR": 3}
    results.sort(key=lambda x: severity_order.get(x["severity"], 99))

    return results


def get_interaction_matrix(vault_keys: list[str]) -> list[dict]:
    """
    Generate a full pairwise interaction matrix for all vault drugs.
    Returns list of all interactions found between any pair of vault drugs.
    """
    interactions = get_all_interactions()
    results = []
    seen = set()

    for interaction in interactions:
        a = interaction["drug_a"]
        b = interaction["drug_b"]

        if a in vault_keys and b in vault_keys:
            pair = tuple(sorted([a, b]))
            if pair not in seen:
                seen.add(pair)
                results.append({
                    "drug_a": a,
                    "drug_a_name": get_drug_info(a)["generic_name"] if get_drug_info(a) else a,
                    "drug_b": b,
                    "drug_b_name": get_drug_info(b)["generic_name"] if get_drug_info(b) else b,
                    "severity": interaction["severity"],
                    "description": interaction["description"],
                    "recommendation": interaction["recommendation"],
                })

    severity_order = {"CRITICAL": 0, "SERIOUS": 1, "MODERATE": 2, "MINOR": 3}
    results.sort(key=lambda x: severity_order.get(x["severity"], 99))

    return results

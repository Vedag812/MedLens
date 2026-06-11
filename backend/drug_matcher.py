"""
MedLens Drug Name Matcher
Matches OCR-extracted text to canonical drug names using fuzzy matching.
"""

from rapidfuzz import fuzz, process
from backend.drug_database import get_all_drug_keys, get_all_brand_names, get_drug_info


# Minimum similarity score to consider a match (0-100)
MIN_CONFIDENCE = 55


def _build_candidate_list() -> list[tuple[str, str]]:
    """
    Build a flat list of (search_term, canonical_key) pairs
    from both generic names and brand names.
    """
    candidates = []

    # Add generic drug names
    for key in get_all_drug_keys():
        info = get_drug_info(key)
        if info:
            candidates.append((info["generic_name"].lower(), key))
            # Also add the key itself
            candidates.append((key, key))

    # Add brand names
    brand_map = get_all_brand_names()
    for brand, key in brand_map.items():
        candidates.append((brand, key))

    return candidates


def match_drug_name(text: str) -> list[dict]:
    """
    Given raw OCR text, find the best matching drugs.

    Returns a list of matches sorted by confidence:
    [
        {
            "drug_key": "paracetamol",
            "matched_term": "dolo 650",
            "confidence": 92.5,
            "drug_info": { ... }
        }
    ]
    """
    if not text or not text.strip():
        return []

    candidates = _build_candidate_list()
    search_terms = [c[0] for c in candidates]

    # Clean input: lowercase, strip extra whitespace
    text_clean = text.lower().strip()

    # Split text into individual words and multi-word chunks
    words = text_clean.split()
    search_chunks = []

    # Single words
    search_chunks.extend(words)

    # 2-word combinations
    for i in range(len(words) - 1):
        search_chunks.append(f"{words[i]} {words[i+1]}")

    # 3-word combinations
    for i in range(len(words) - 2):
        search_chunks.append(f"{words[i]} {words[i+1]} {words[i+2]}")

    # Also try the full text
    search_chunks.append(text_clean)

    # De-duplicate
    search_chunks = list(set(search_chunks))

    # Find best matches for each chunk
    matches = {}
    for chunk in search_chunks:
        # Skip very short chunks (likely noise)
        if len(chunk) < 3:
            continue

        results = process.extract(
            chunk,
            search_terms,
            scorer=fuzz.WRatio,
            limit=3,
        )

        for match_text, score, idx in results:
            if score >= MIN_CONFIDENCE:
                drug_key = candidates[idx][1]
                # Keep the best score for each drug
                if drug_key not in matches or score > matches[drug_key]["confidence"]:
                    matches[drug_key] = {
                        "drug_key": drug_key,
                        "matched_term": match_text,
                        "query_chunk": chunk,
                        "confidence": round(score, 1),
                    }

    # Build results with full drug info
    results = []
    for drug_key, match_data in matches.items():
        info = get_drug_info(drug_key)
        if info:
            results.append({
                **match_data,
                "drug_info": info,
            })

    # Sort by confidence descending
    results.sort(key=lambda x: x["confidence"], reverse=True)

    # Return top 3 matches max
    return results[:3]


def match_single_drug(name: str) -> dict | None:
    """
    Match a single drug name string to its canonical entry.
    Returns the best match or None.
    """
    matches = match_drug_name(name)
    if matches and matches[0]["confidence"] >= 60:
        return matches[0]
    return None

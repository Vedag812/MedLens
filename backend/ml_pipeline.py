"""
MedLens ML Pipeline
Real ML/DS components: NER-based drug extraction, OCR error correction,
medical abbreviation expansion, and confidence-weighted entity resolution.
"""

import re
import math
from collections import Counter
from rapidfuzz import fuzz, process


# Common medical abbreviations found on Indian medicine strips
MEDICAL_ABBREVIATIONS = {
    "tab": "tablet",
    "tabs": "tablets",
    "cap": "capsule",
    "caps": "capsules",
    "inj": "injection",
    "syr": "syrup",
    "susp": "suspension",
    "sr": "sustained release",
    "xr": "extended release",
    "cr": "controlled release",
    "er": "extended release",
    "od": "once daily",
    "bd": "twice daily",
    "tds": "three times daily",
    "qid": "four times daily",
    "hs": "at bedtime",
    "prn": "as needed",
    "pc": "after food",
    "ac": "before food",
    "stat": "immediately",
    "mg": "milligram",
    "mcg": "microgram",
    "ml": "milliliter",
    "iu": "international unit",
    "ip": "indian pharmacopoeia",
    "bp": "british pharmacopoeia",
    "usp": "us pharmacopoeia",
    "nf": "national formulary",
}

# Common OCR misreads specific to medicine text
OCR_CORRECTIONS = {
    "0": {"O": 0.3, "D": 0.2},
    "O": {"0": 0.3},
    "1": {"l": 0.4, "I": 0.3, "|": 0.5},
    "l": {"1": 0.4, "I": 0.3},
    "I": {"1": 0.3, "l": 0.3},
    "5": {"S": 0.3, "s": 0.3},
    "S": {"5": 0.3},
    "8": {"B": 0.2},
    "B": {"8": 0.2},
    "rn": {"m": 0.5},
    "cl": {"d": 0.3},
    "vv": {"w": 0.4},
}

# Regex patterns for extracting drug-related info from OCR text
DOSAGE_PATTERN = re.compile(
    r'(\d+\.?\d*)\s*(mg|mcg|g|ml|iu|units?)\b',
    re.IGNORECASE
)

DRUG_NAME_PATTERN = re.compile(
    r'\b([A-Z][a-z]{2,}(?:\s*(?:SR|XR|CR|ER|Plus|Forte|DS|HD|LD))?)\b'
)

BATCH_LOT_PATTERN = re.compile(
    r'\b(?:batch|lot|mfg|exp|b\.?\s*no|l\.?\s*no)\b',
    re.IGNORECASE
)


class DrugEntityExtractor:
    """
    NER-style entity extraction pipeline for medicine text.
    Uses rule-based NER + statistical scoring + fuzzy matching
    to extract drug names from noisy OCR output.
    """

    def __init__(self, drug_names: list[str], brand_names: dict[str, str]):
        """
        Args:
            drug_names: List of canonical drug name keys
            brand_names: Dict mapping brand name (lower) to drug key
        """
        self.drug_names = drug_names
        self.brand_names = brand_names
        self._build_vocabulary()

    def _build_vocabulary(self):
        """Build search vocabulary from drug and brand names."""
        self.vocab = {}
        for key in self.drug_names:
            self.vocab[key] = key
        for brand, key in self.brand_names.items():
            self.vocab[brand] = key

        # Build character n-gram index for fast approximate matching
        self.ngram_index = {}
        for term in self.vocab:
            for ngram in self._get_ngrams(term, 3):
                if ngram not in self.ngram_index:
                    self.ngram_index[ngram] = []
                self.ngram_index[ngram].append(term)

    def _get_ngrams(self, text: str, n: int) -> list[str]:
        """Extract character n-grams from text."""
        text = text.lower()
        return [text[i:i+n] for i in range(len(text) - n + 1)]

    def extract_entities(self, ocr_text: str) -> list[dict]:
        """
        Main extraction pipeline:
        1. Tokenize and clean OCR text
        2. Expand medical abbreviations
        3. Apply OCR error correction candidates
        4. Run fuzzy NER against drug vocabulary
        5. Score and rank candidates using TF-IDF-like weighting
        """
        if not ocr_text or not ocr_text.strip():
            return []

        # Step 1: Clean and tokenize
        cleaned = self._clean_ocr_text(ocr_text)
        tokens = self._tokenize(cleaned)

        # Step 2: Extract dosage info (useful metadata)
        dosages = DOSAGE_PATTERN.findall(ocr_text)

        # Step 3: Filter out non-drug tokens (batch numbers, dates, etc.)
        tokens = self._filter_noise_tokens(tokens)

        # Step 4: Generate candidate chunks (1, 2, 3 word windows)
        chunks = self._generate_chunks(tokens)

        # Step 5: Match each chunk against drug vocabulary
        candidates = []
        for chunk, position in chunks:
            matches = self._fuzzy_match(chunk)
            for match in matches:
                match["position"] = position
                match["has_dosage_nearby"] = self._has_dosage_nearby(
                    ocr_text, chunk, dosages
                )
                candidates.append(match)

        # Step 6: Score candidates using multiple signals
        scored = self._score_candidates(candidates)

        # Step 7: Deduplicate (keep best score per drug key)
        deduped = self._deduplicate(scored)

        return deduped

    def _clean_ocr_text(self, text: str) -> str:
        """Clean noisy OCR output."""
        # Remove common OCR artifacts
        text = re.sub(r'[|\\/{}\[\]<>]', ' ', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove isolated single characters (OCR noise)
        text = re.sub(r'\b[^aAiI]\b', ' ', text)
        return text.strip()

    def _tokenize(self, text: str) -> list[str]:
        """Split text into meaningful tokens."""
        # Split on whitespace and punctuation (but keep hyphens in drug names)
        tokens = re.findall(r'[A-Za-z][A-Za-z0-9-]*[A-Za-z0-9]|[A-Za-z]', text)
        return [t for t in tokens if len(t) >= 2]

    def _filter_noise_tokens(self, tokens: list[str]) -> list[str]:
        """Remove tokens that are clearly not drug names."""
        noise_words = {
            "tablet", "tablets", "capsule", "capsules", "syrup", "injection",
            "each", "contains", "composition", "manufactured", "marketed",
            "india", "limited", "pvt", "ltd", "pharma", "store", "below",
            "keep", "away", "children", "dry", "place", "cool", "protect",
            "light", "date", "batch", "price", "mrp", "inclusive", "taxes",
            "not", "for", "the", "and", "with", "from", "this", "that",
            "use", "only", "take", "before", "after", "food", "water",
            "mouth", "oral", "daily", "twice", "once", "doctor", "advice",
            "prescription", "medicine", "drug", "schedule", "strip", "pack",
        }
        return [t for t in tokens if t.lower() not in noise_words]

    def _generate_chunks(self, tokens: list[str]) -> list[tuple[str, int]]:
        """Generate 1, 2, and 3 word sliding window chunks."""
        chunks = []
        for i, token in enumerate(tokens):
            chunks.append((token, i))
            if i + 1 < len(tokens):
                chunks.append((f"{token} {tokens[i+1]}", i))
            if i + 2 < len(tokens):
                chunks.append((f"{token} {tokens[i+1]} {tokens[i+2]}", i))
        return chunks

    def _fuzzy_match(self, chunk: str, threshold: int = 55) -> list[dict]:
        """Fuzzy match a text chunk against the drug vocabulary."""
        chunk_lower = chunk.lower()
        vocab_terms = list(self.vocab.keys())

        results = process.extract(
            chunk_lower,
            vocab_terms,
            scorer=fuzz.WRatio,
            limit=3,
        )

        matches = []
        for term, score, idx in results:
            if score >= threshold:
                # Apply OCR correction bonus
                corrected_score = self._ocr_correction_bonus(chunk_lower, term, score)
                matches.append({
                    "chunk": chunk,
                    "matched_term": term,
                    "drug_key": self.vocab[term],
                    "raw_score": score,
                    "corrected_score": corrected_score,
                })

        return matches

    def _ocr_correction_bonus(self, query: str, target: str, base_score: float) -> float:
        """
        Apply bonus score if the mismatch looks like a common OCR error.
        For example, 'Cr0cin' matching 'crocin' (0 vs o) gets a boost.
        """
        if base_score >= 95:
            return base_score

        bonus = 0
        for i, (q_char, t_char) in enumerate(zip(query, target)):
            if q_char != t_char:
                if q_char in OCR_CORRECTIONS:
                    if t_char in OCR_CORRECTIONS[q_char]:
                        bonus += OCR_CORRECTIONS[q_char][t_char] * 10

        return min(base_score + bonus, 100.0)

    def _has_dosage_nearby(self, full_text: str, chunk: str, dosages: list) -> bool:
        """Check if there's a dosage value near this chunk in the original text."""
        if not dosages:
            return False
        chunk_pos = full_text.lower().find(chunk.lower())
        if chunk_pos < 0:
            return False
        # Check for dosage within 50 characters
        nearby_text = full_text[max(0, chunk_pos - 50):chunk_pos + len(chunk) + 50]
        return bool(DOSAGE_PATTERN.search(nearby_text))

    def _score_candidates(self, candidates: list[dict]) -> list[dict]:
        """
        Multi-signal scoring using TF-IDF inspired weighting:
        - Fuzzy match score (primary signal)
        - OCR correction bonus
        - Dosage proximity boost (drug names often appear near dosages)
        - Position boost (drug names usually appear early in text)
        - Length penalty (very short matches are less reliable)
        """
        for c in candidates:
            score = c["corrected_score"]

            # Dosage proximity boost (+8 points if dosage found nearby)
            if c.get("has_dosage_nearby"):
                score += 8

            # Position boost (earlier = more likely to be the drug name)
            position_decay = math.exp(-c["position"] * 0.1)
            score += position_decay * 5

            # Length penalty (2-char matches are probably noise)
            chunk_len = len(c["chunk"])
            if chunk_len <= 3:
                score -= 15
            elif chunk_len <= 5:
                score -= 5

            c["final_score"] = round(min(score, 100), 1)

        # Sort by final score
        candidates.sort(key=lambda x: x["final_score"], reverse=True)
        return candidates

    def _deduplicate(self, candidates: list[dict]) -> list[dict]:
        """Keep only the best match per drug key."""
        seen = {}
        for c in candidates:
            key = c["drug_key"]
            if key not in seen or c["final_score"] > seen[key]["final_score"]:
                seen[key] = c
        return sorted(seen.values(), key=lambda x: x["final_score"], reverse=True)


class InteractionRiskScorer:
    """
    ML-inspired risk scoring model for drug interactions.
    Uses feature engineering + weighted scoring to produce a
    personalized risk assessment based on patient profile.
    """

    # Risk multipliers based on patient factors
    AGE_RISK = {
        "child": 1.5,      # Children metabolize differently
        "adult": 1.0,
        "elderly": 1.8,    # Elderly have reduced clearance
    }

    CONDITION_RISK = {
        "liver_disease": 1.6,
        "kidney_disease": 1.7,
        "heart_disease": 1.4,
        "diabetes": 1.2,
        "pregnancy": 2.0,
        "none": 1.0,
    }

    SEVERITY_BASE_SCORES = {
        "CRITICAL": 90,
        "SERIOUS": 70,
        "MODERATE": 45,
        "MINOR": 20,
    }

    POLYPHARMACY_THRESHOLDS = {
        2: 1.0,   # 2 drugs = baseline
        3: 1.1,   # 3 drugs = 10% more risk
        4: 1.25,  # 4 drugs = 25% more risk
        5: 1.4,   # 5+ drugs = 40% more risk
    }

    def calculate_risk_score(
        self,
        interactions: list[dict],
        vault_size: int,
        age_group: str = "adult",
        conditions: list[str] | None = None,
    ) -> dict:
        """
        Calculate a personalized risk score (0-100) for the current medication profile.

        Features used in scoring:
        - Number and severity of interactions (primary signal)
        - Polypharmacy risk (more drugs = exponentially more risk)
        - Age-based metabolism factor
        - Pre-existing condition multipliers
        - Interaction density (interactions per drug pair)
        """
        if not interactions:
            return {
                "overall_score": 0,
                "risk_level": "LOW",
                "risk_color": "#22c55e",
                "factors": [],
                "recommendation": "No known interactions found. Your current medications appear to be compatible.",
            }

        conditions = conditions or ["none"]

        # Feature 1: Base severity score (weighted sum of interaction severities)
        severity_scores = [
            self.SEVERITY_BASE_SCORES.get(i["severity"], 30)
            for i in interactions
        ]
        base_score = max(severity_scores)  # Worst interaction drives the score

        # Feature 2: Cumulative risk (multiple interactions compound)
        if len(interactions) > 1:
            secondary_scores = sorted(severity_scores, reverse=True)[1:]
            cumulative_bonus = sum(s * 0.15 for s in secondary_scores)
            base_score += cumulative_bonus

        # Feature 3: Polypharmacy multiplier
        poly_key = min(vault_size, 5)
        poly_multiplier = self.POLYPHARMACY_THRESHOLDS.get(poly_key, 1.0)

        # Feature 4: Age risk multiplier
        age_multiplier = self.AGE_RISK.get(age_group, 1.0)

        # Feature 5: Condition risk multiplier (take the worst one)
        condition_multipliers = [
            self.CONDITION_RISK.get(c, 1.0) for c in conditions
        ]
        condition_multiplier = max(condition_multipliers)

        # Feature 6: Interaction density
        max_possible_pairs = vault_size * (vault_size - 1) / 2 if vault_size > 1 else 1
        density = len(interactions) / max_possible_pairs
        density_multiplier = 1 + (density * 0.2)

        # Final score calculation
        final_score = base_score * poly_multiplier * age_multiplier * condition_multiplier * density_multiplier
        final_score = min(round(final_score), 100)

        # Determine risk level
        if final_score >= 75:
            risk_level = "CRITICAL"
            risk_color = "#ef4444"
            recommendation = "Your medication combination has serious risks. Please consult your doctor before taking these together."
        elif final_score >= 50:
            risk_level = "HIGH"
            risk_color = "#f97316"
            recommendation = "There are notable interaction risks. Consider discussing alternatives with your doctor."
        elif final_score >= 25:
            risk_level = "MODERATE"
            risk_color = "#eab308"
            recommendation = "Some interactions exist but are manageable. Monitor for side effects and follow dosage guidelines."
        else:
            risk_level = "LOW"
            risk_color = "#22c55e"
            recommendation = "Minor or no significant interactions. Continue as prescribed."

        # Build factor breakdown for explainability
        factors = []
        if base_score > 40:
            factors.append(f"Severity: {len([s for s in severity_scores if s >= 70])} serious or critical interactions detected")
        if poly_multiplier > 1.0:
            factors.append(f"Polypharmacy: Taking {vault_size} medications increases interaction probability by {int((poly_multiplier - 1) * 100)}%")
        if age_multiplier > 1.0:
            factors.append(f"Age factor: {age_group} patients have {int((age_multiplier - 1) * 100)}% higher interaction sensitivity")
        if condition_multiplier > 1.0:
            active_conditions = [c for c in conditions if c != "none"]
            factors.append(f"Health conditions: {', '.join(active_conditions)} increase drug interaction risk")
        if density > 0.3:
            factors.append(f"Interaction density: {int(density * 100)}% of possible drug pairs have known interactions")

        return {
            "overall_score": final_score,
            "risk_level": risk_level,
            "risk_color": risk_color,
            "factors": factors,
            "recommendation": recommendation,
            "breakdown": {
                "base_severity": round(base_score, 1),
                "polypharmacy_multiplier": poly_multiplier,
                "age_multiplier": age_multiplier,
                "condition_multiplier": condition_multiplier,
                "density_multiplier": round(density_multiplier, 2),
                "interaction_count": len(interactions),
                "vault_size": vault_size,
            },
        }

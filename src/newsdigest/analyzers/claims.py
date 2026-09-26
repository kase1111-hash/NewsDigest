"""Claim extractor for NewsDigest."""

import re

from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import Claim, ClaimType, Sentence


# Patterns for statistical claims
STATISTICAL_PATTERNS: list[str] = [
    r"\d+(?:\.\d+)?%",  # Percentages
    r"\$\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:million|billion|trillion))?",  # Dollar amounts
    r"\d+(?:,\d{3})*(?:\.\d+)?\s*(?:million|billion|trillion)",  # Large numbers
    r"\d+(?:\.\d+)?\s*(?:percent|percentage)",  # Percent spelled out
    r"(?:increased|decreased|rose|fell|dropped|grew|declined)\s+(?:by\s+)?\d+",  # Changes
    r"\d+\s*(?:to|through|out of)\s*\d+",  # Ranges and ratios
]

# Attribution verbs
ATTRIBUTION_VERBS: list[str] = [
    "said", "says", "stated", "announced", "declared", "claimed", "reported",
    "confirmed", "denied", "acknowledged", "admitted", "argued", "asserted",
    "contended", "maintained", "noted", "observed", "pointed out", "remarked",
    "revealed", "suggested", "told", "wrote", "explained", "added", "warned",
]


class ClaimExtractor(BaseAnalyzer):
    """Extracts falsifiable claims from sentences.

    Identifies:
    - Factual claims (declarative statements)
    - Statistical claims (numbers, percentages, data)
    - Quote claims (attributed statements)
    - Attribution claims (who said what)

    Each claim is scored for confidence based on:
    - Source attribution strength
    - Specificity (numbers, names, dates)
    - Declarative language
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize claim extractor."""
        super().__init__(config)
        self._stat_patterns = [
            re.compile(p, re.IGNORECASE) for p in STATISTICAL_PATTERNS
        ]
        self.min_confidence = self.config.get("min_confidence", 0.3)

        # Collected claims
        self.claims: list[Claim] = []

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Analyze sentences to extract claims.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list (same list, claims extracted separately).
        """
        if not self.enabled:
            return sentences

        self.claims = []

        for i, sentence in enumerate(sentences):
            if not sentence.keep:
                continue

            extracted = self._extract_claims(sentence, i)
            self.claims.extend(extracted)

        return sentences

    def _extract_claims(
        self, sentence: Sentence, index: int
    ) -> list[Claim]:
        """Extract claims from a sentence.

        Args:
            sentence: Sentence to process.
            index: Sentence index in article.

        Returns:
            List of extracted claims.
        """
        claims = []
        text = sentence.text

        # Check for statistical claims
        stat_claim = self._extract_statistical_claim(text, sentence, index)
        if stat_claim:
            claims.append(stat_claim)

        # Check for quote claims
        quote_claim = self._extract_quote_claim(text, sentence, index)
        if quote_claim:
            claims.append(quote_claim)

        # Check for attribution claims. Each claim carries the whole sentence
        # and its source, so an attributed statistic or quote is already
        # covered and a second claim would just repeat it.
        attr_claim = self._extract_attribution_claim(text, sentence, index)
        if attr_claim and not claims:
            claims.append(attr_claim)

        # Check for factual claims (if no other type found)
        if not claims:
            factual_claim = self._extract_factual_claim(text, sentence, index)
            if factual_claim:
                claims.append(factual_claim)

        return [c for c in claims if c.confidence >= self.min_confidence]

    def _extract_statistical_claim(
        self, text: str, sentence: Sentence, index: int
    ) -> Claim | None:
        """Extract statistical claim if present.

        Args:
            text: Sentence text.
            sentence: Full sentence object.
            index: Sentence index.

        Returns:
            Statistical claim or None.
        """
        for pattern in self._stat_patterns:
            if pattern.search(text):
                confidence = self._calculate_confidence(
                    text, sentence, has_numbers=True
                )
                return Claim(
                    text=text,
                    claim_type=ClaimType.STATISTICAL,
                    source=sentence.source_name,
                    source_type="quoted" if sentence.has_named_source else "unknown",
                    confidence=confidence,
                    sentence_index=index,
                )
        return None

    def _extract_quote_claim(
        self, text: str, sentence: Sentence, index: int
    ) -> Claim | None:
        """Extract quote claim if present.

        Args:
            text: Sentence text.
            sentence: Full sentence object.
            index: Sentence index.

        Returns:
            Quote claim or None.
        """
        # Check for quoted text
        quote_match = re.search(r'"([^"]+)"', text)
        if not quote_match:
            quote_match = re.search(r"'([^']+)'", text)

        if quote_match:
            quote_text = quote_match.group(1)
            # Verify it's an attributed quote
            if self._has_attribution(text):
                confidence = 0.9 if sentence.has_named_source else 0.5
                return Claim(
                    text=quote_text,
                    claim_type=ClaimType.QUOTE,
                    source=sentence.source_name,
                    source_type="quoted",
                    confidence=confidence,
                    sentence_index=index,
                )
        return None

    def _extract_attribution_claim(
        self, text: str, sentence: Sentence, index: int
    ) -> Claim | None:
        """Extract attribution claim if present.

        Args:
            text: Sentence text.
            sentence: Full sentence object.
            index: Sentence index.

        Returns:
            Attribution claim or None.
        """
        if self._has_attribution(text) and sentence.has_named_source:
            confidence = self._calculate_confidence(
                text, sentence, has_attribution=True
            )
            return Claim(
                text=text,
                claim_type=ClaimType.ATTRIBUTION,
                source=sentence.source_name,
                source_type="primary",
                confidence=confidence,
                sentence_index=index,
            )
        return None

    def _extract_factual_claim(
        self, text: str, sentence: Sentence, index: int
    ) -> Claim | None:
        """Extract factual claim from declarative sentence.

        Args:
            text: Sentence text.
            sentence: Full sentence object.
            index: Sentence index.

        Returns:
            Factual claim or None.
        """
        # Check for declarative indicators
        if not self._is_declarative(text):
            return None

        confidence = self._calculate_confidence(text, sentence)

        return Claim(
            text=text,
            claim_type=ClaimType.FACTUAL,
            source=sentence.source_name if sentence.has_named_source else None,
            source_type="primary" if sentence.has_named_source else "unknown",
            confidence=confidence,
            sentence_index=index,
        )

    def _has_attribution(self, text: str) -> bool:
        """Check if text has attribution verb.

        Args:
            text: Text to check.

        Returns:
            True if attribution found.
        """
        text_lower = text.lower()
        return any(verb in text_lower for verb in ATTRIBUTION_VERBS)

    def _is_declarative(self, text: str) -> bool:
        """Check if sentence is declarative.

        Args:
            text: Text to check.

        Returns:
            True if declarative.
        """
        # Not a question
        if text.strip().endswith("?"):
            return False

        # Has subject-verb structure (simple heuristic)
        words = text.split()
        if len(words) < 4:
            return False

        # Check for proper nouns or subject-like start
        if words[0][0].isupper():
            return True

        return True  # Default to declarative for statements

    def _calculate_confidence(
        self,
        text: str,
        sentence: Sentence,
        has_numbers: bool = False,
        has_attribution: bool = False,
    ) -> float:
        """Calculate confidence score for a claim.

        Args:
            text: Claim text.
            sentence: Source sentence.
            has_numbers: Whether claim has numbers.
            has_attribution: Whether claim has attribution.

        Returns:
            Confidence score 0.0-1.0.
        """
        score = 0.3  # Base score

        # Named source adds confidence
        if sentence.has_named_source:
            score += 0.3

        # Numbers add specificity/confidence
        if has_numbers or any(c.isdigit() for c in text):
            score += 0.2

        # Attribution adds confidence
        if has_attribution:
            score += 0.1

        # Entities add confidence
        if sentence.entities:
            score += min(0.2, len(sentence.entities) * 0.05)

        # Penalty for speculation
        if sentence.speculation_score > 0.3:
            score -= 0.2

        # Penalty for emotional language
        if sentence.emotional_score > 0.3:
            score -= 0.1

        return round(min(1.0, max(0.0, score)), 2)

    def get_claims(self) -> list[Claim]:
        """Get extracted claims.

        Returns:
            List of claims.
        """
        return self.claims

    def get_claims_by_type(self, claim_type: ClaimType) -> list[Claim]:
        """Get claims filtered by type.

        Args:
            claim_type: Type to filter by.

        Returns:
            Filtered list of claims.
        """
        return [c for c in self.claims if c.claim_type == claim_type]

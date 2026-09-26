"""NLP pipeline orchestration for NewsDigest."""

import functools
import re
from typing import Any

from newsdigest.analyzers import (
    BaseAnalyzer,
    ClaimExtractor,
    EmotionalDetector,
    FillerDetector,
    NoveltyScorer,
    QuoteIsolator,
    RepetitionCollapser,
    SourceValidator,
    SpeculationStripper,
)
from newsdigest.core.result import Claim, Sentence


# Analyzer tuning per extraction mode. "standard" matches the analyzers'
# own defaults; the other modes loosen or tighten the removal thresholds.
MODE_PRESETS: dict[str, dict[str, float]] = {
    "conservative": {
        "speculation_threshold": 0.75,
        "hedge_allowance": 1,
        "emotional_threshold": 0.5,
        "min_word_count": 3,
        "min_entity_density": 0.0,
        "similarity_offset": 0.1,
    },
    "standard": {
        "speculation_threshold": 0.5,
        "hedge_allowance": 0,
        "emotional_threshold": 0.3,
        "min_word_count": 4,
        "min_entity_density": 0.1,
        "similarity_offset": 0.0,
    },
    "aggressive": {
        # Just above a lone modal verb's maximum score (1.5 / 4.5), so
        # reported speech ("said it would") is not treated as speculation
        "speculation_threshold": 0.35,
        "hedge_allowance": -1,
        "emotional_threshold": 0.15,
        "min_word_count": 5,
        "min_entity_density": 0.15,
        "similarity_offset": -0.15,
    },
}

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_CLOSING_QUOTES = ('"', "\u201d")


def _quote_balance(text: str) -> int:
    """Count double quotes a text leaves open (positive) or closes (negative).

    Straight quotes toggle, so each one counts as opening; callers only
    care whether the running total across sentences is odd/positive.
    """
    return text.count('"') + text.count("\u201c") - text.count("\u201d")


@functools.lru_cache(maxsize=4)
def _load_spacy_model(model_name: str) -> Any:
    """Load a spaCy model once per process.

    Loading takes hundreds of milliseconds, and an Extractor is created per
    API request, so models are shared rather than loaded per pipeline.
    """
    import spacy

    return spacy.load(model_name)


def normalize_text(text: str) -> str:
    """Unwrap hard-wrapped lines while preserving paragraph breaks.

    Args:
        text: Raw article text.

    Returns:
        Text with single spaces inside paragraphs and blank lines between them.
    """
    paragraphs = (" ".join(p.split()) for p in _PARAGRAPH_BREAK.split(text))
    return "\n\n".join(p for p in paragraphs if p)


class AnalysisPipeline:
    """Orchestrates the NLP and semantic analysis pipeline.

    The pipeline:
    1. Processes raw text through spaCy for NLP annotations
    2. Converts to Sentence objects
    3. Runs sentences through analyzer chain
    4. Returns analyzed sentences with scores and flags
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the analysis pipeline.

        Args:
            config: Configuration dictionary for pipeline settings.
        """
        self.config = config or {}
        self._nlp: Any = None  # Lazy-loaded spaCy model
        self._analyzers: list[BaseAnalyzer] = []
        self._claim_extractor: ClaimExtractor | None = None

        # Initialize analyzers
        self._init_analyzers()

    @property
    def nlp(self) -> Any:
        """Lazy-load spaCy model."""
        if self._nlp is None:
            try:
                model_name = self.config.get("spacy_model", "en_core_web_sm")
                self._nlp = _load_spacy_model(model_name)
            except ImportError as e:
                raise ImportError(
                    "spaCy is required. Install with: pip install spacy && "
                    "python -m spacy download en_core_web_sm"
                ) from e
            except OSError as e:
                raise OSError(
                    f"spaCy model not found. Download with: "
                    f"python -m spacy download {self.config.get('spacy_model', 'en_core_web_sm')}"
                ) from e
        return self._nlp

    def _init_analyzers(self) -> None:
        """Initialize the analyzer chain."""
        extraction_config = self.config.get("extraction", {})
        preset = MODE_PRESETS.get(
            extraction_config.get("mode", "standard"), MODE_PRESETS["standard"]
        )

        # Build analyzer configurations
        filler_config = {
            "enabled": True,
            "min_word_count": preset["min_word_count"],
            "min_entity_density": preset["min_entity_density"],
        }
        max_hedges = extraction_config.get("max_hedges_per_sentence", 2)
        spec_config = {
            "enabled": True,
            "mode": extraction_config.get("speculation", "remove"),
            "max_hedges_per_sentence": max(0, max_hedges + preset["hedge_allowance"]),
            "speculation_threshold": preset["speculation_threshold"],
        }
        emotional_config = {
            "enabled": True,
            "mode": extraction_config.get("emotional_language", "remove"),
            "emotional_threshold": preset["emotional_threshold"],
        }
        source_config = {
            "enabled": True,
            "unnamed_sources": extraction_config.get("unnamed_sources", "flag"),
        }
        similarity = self.config.get("similarity_threshold", 0.7)
        repetition_config = {
            "enabled": True,
            "similarity_threshold": min(
                1.0, max(0.0, similarity + preset["similarity_offset"])
            ),
        }
        novelty_config = {
            "enabled": True,
            "min_novelty_score": self.config.get("min_novelty_score", 0.3),
        }
        quotes_config = extraction_config.get("quotes", {})
        quote_config = {
            "enabled": True,
            "keep_attributed": quotes_config.get("keep_attributed", True),
            "keep_unattributed": quotes_config.get("keep_unattributed", False),
            "flag_circular": quotes_config.get("flag_circular", True),
        }
        claims_config = {"enabled": True, "min_confidence": 0.3}

        # Initialize analyzers in order of processing
        # Order matters: some analyzers depend on scores from others
        self._analyzers = [
            # First pass: source and quote detection (enriches sentences)
            SourceValidator(source_config),
            QuoteIsolator(quote_config),
            # Second pass: content scoring
            SpeculationStripper(spec_config),
            EmotionalDetector(emotional_config),
            FillerDetector(filler_config),
            # Third pass: cross-sentence analysis
            RepetitionCollapser(repetition_config),
            NoveltyScorer(novelty_config),
        ]

        # Claim extractor runs separately after analysis
        self._claim_extractor = ClaimExtractor(claims_config)

    def process(self, text: str) -> list[Sentence]:
        """Process text through NLP pipeline.

        Args:
            text: Raw text content to process.

        Returns:
            List of Sentence objects with NLP annotations.
        """
        text = normalize_text(text) if text else ""
        if not text:
            return []

        # Process each paragraph separately: spaCy does not treat a blank
        # line as a sentence boundary, so a heading without punctuation
        # would otherwise merge into the following sentence
        docs = self.nlp.pipe(_PARAGRAPH_BREAK.split(text))

        sentences: list[Sentence] = []
        open_quotes = 0  # Quote marks opened by earlier sentences
        for sent in (sent for doc in docs for sent in doc.sents):
            sent_text = " ".join(sent.text.split())

            # Extract tokens
            tokens = [token.text for token in sent]

            # Extract POS tags
            pos_tags = [token.pos_ for token in sent]

            # spaCy often starts a sentence with the closing quote of an
            # earlier one ('" Sources said...'); hand it back
            if (
                sentences
                and sent_text[:1] in _CLOSING_QUOTES
                and (len(sent_text) == 1 or sent_text[1].isspace())
                and open_quotes % 2 == 1
            ):
                sentences[-1].text += sent_text[0]
                open_quotes += _quote_balance(sent_text[0])
                sent_text = sent_text[1:].lstrip()
                tokens, pos_tags = tokens[1:], pos_tags[1:]
                if not sent_text:
                    continue
            open_quotes += _quote_balance(sent_text)

            # Extract entities
            entities = [
                {
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start_char - sent.start_char,
                    "end": ent.end_char - sent.start_char,
                }
                for ent in sent.ents
            ]

            # Calculate initial density score based on entity/content ratio
            content_tokens = [t for t in sent if not t.is_stop and not t.is_punct]
            density = len(content_tokens) / len(sent) if len(sent) > 0 else 0

            sentence = Sentence(
                text=sent_text,
                index=len(sentences),
                tokens=tokens,
                pos_tags=pos_tags,
                entities=entities,
                density_score=round(density, 2),
            )
            sentences.append(sentence)

        return sentences

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Run sentences through analyzer chain.

        Args:
            sentences: List of Sentence objects from NLP processing.

        Returns:
            Analyzed sentences with scores and flags.
        """
        if not sentences:
            return sentences

        # Run through each analyzer
        for analyzer in self._analyzers:
            if analyzer.enabled:
                sentences = analyzer.analyze(sentences)

        # Extract claims
        if self._claim_extractor and self._claim_extractor.enabled:
            self._claim_extractor.analyze(sentences)

        return sentences

    def process_and_analyze(self, text: str) -> list[Sentence]:
        """Process text and run analysis in one step.

        Args:
            text: Raw text content.

        Returns:
            Fully analyzed sentences.
        """
        sentences = self.process(text)
        return self.analyze(sentences)

    def get_claims(self) -> list[Claim]:
        """Get extracted claims from last analysis.

        Returns:
            List of Claim objects.
        """
        if self._claim_extractor:
            return self._claim_extractor.get_claims()
        return []

    def get_statistics(self, sentences: list[Sentence]) -> dict[str, Any]:
        """Get analysis statistics from sentences.

        Args:
            sentences: Analyzed sentences.

        Returns:
            Dictionary of statistics.
        """
        kept = [s for s in sentences if s.keep]
        removed = [s for s in sentences if not s.keep]

        # Count by removal reason
        removal_counts: dict[str, int] = {}
        for s in removed:
            reason = s.removal_reason or "unknown"
            removal_counts[reason] = removal_counts.get(reason, 0) + 1

        # Get source validator stats
        source_validator = next(
            (a for a in self._analyzers if isinstance(a, SourceValidator)), None
        )
        named_sources = (
            source_validator.get_unique_named_sources() if source_validator else []
        )
        unnamed_count = (
            source_validator.get_unnamed_source_count() if source_validator else 0
        )

        # Get emotional word count
        emotional_detector = next(
            (a for a in self._analyzers if isinstance(a, EmotionalDetector)), None
        )
        emotional_words = (
            emotional_detector.get_emotional_word_count() if emotional_detector else 0
        )

        # Get repetition stats
        repetition_collapser = next(
            (a for a in self._analyzers if isinstance(a, RepetitionCollapser)), None
        )
        collapsed = (
            repetition_collapser.get_collapsed_count() if repetition_collapser else 0
        )

        return {
            "total_sentences": len(sentences),
            "kept_sentences": len(kept),
            "removed_sentences": len(removed),
            "removal_breakdown": removal_counts,
            "named_sources": named_sources,
            "unnamed_source_references": unnamed_count,
            "emotional_words_removed": emotional_words,
            "repetitions_collapsed": collapsed,
            "claims_extracted": len(self.get_claims()),
        }

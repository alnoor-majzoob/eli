"""Evidence verification guard (plan §8.6): hallucinated-evidence rate target is 0."""

from __future__ import annotations

from difflib import SequenceMatcher

DEFAULT_THRESHOLD = 0.9


def normalize_text(text: str) -> str:
    return " ".join(text.split()).lower()


def _sentence_slices(text: str) -> list[str]:
    return [sentence for sentence in text.split(". ") if sentence.strip()]


def verify_evidence(source_text: str, quote: str, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Deterministic check: the quote appears verbatim or at fuzzy similarity ≥ threshold."""
    normalized_quote = normalize_text(quote)
    if not normalized_quote:
        return False
    if normalized_quote in normalize_text(source_text):
        return True
    best = 0.0
    for sentence in _sentence_slices(source_text):
        ratio = SequenceMatcher(None, normalized_quote, normalize_text(sentence)).ratio()
        best = max(best, ratio)
    return best >= threshold

"""Turkish-aware in-memory BM25Okapi scoring for user long-term memory facts.

Provides lightweight, dependency-free lexical scoring with Turkish
morphology awareness (diacritics folding and prefix stemming). Enables
hybrid search to confirm or reject dense vector similarity candidates.
"""

from __future__ import annotations

from collections import Counter
import math
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

STEM_MAX_LENGTH = 5


def normalize_turkish(text: str) -> str:
    """Fold Turkish diacritics and case for uniform lexical comparison."""
    if not text:
        return ""
    tr_map = str.maketrans(
        {
            "İ": "i",
            "I": "i",
            "ı": "i",
            "ş": "s",
            "Ş": "s",
            "ğ": "g",
            "Ğ": "g",
            "ü": "u",
            "Ü": "u",
            "ö": "o",
            "Ö": "o",
            "ç": "c",
            "Ç": "c",
        }
    )
    return text.translate(tr_map).strip().lower()


def tokenize_turkish(text: str) -> tuple[list[str], list[str]]:
    """Tokenize normalized text into words and prefix stems.

    Returns:
        A tuple of ``(words, stems)`` where stems are truncated to length 5
        to match inflected agglutinative forms (e.g. 'doğum' vs 'doğumluyum').
    """
    normalized = normalize_turkish(text)
    words = re.findall(r"\w+", normalized)
    stems = [w[:STEM_MAX_LENGTH] if len(w) > STEM_MAX_LENGTH else w for w in words]
    return words, stems


class BM25Okapi:
    """In-memory BM25Okapi implementation for small, per-user fact sets.

    Uses Robertson-Spärck Jones IDF and standard BM25 document length
    normalization (k1=1.5, b=0.75).
    """

    def __init__(
        self,
        corpus_stems: list[list[str]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """Initialize BM25 index with pre-tokenized document stems."""
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus_stems)
        self.doc_lens = [len(doc) for doc in corpus_stems]
        self.avgdl = sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 0.0

        # Term frequencies per document
        self.doc_freqs: list[Counter[str]] = [Counter(doc) for doc in corpus_stems]

        # Document frequencies for IDF calculation
        df: Counter[str] = Counter()
        for doc in corpus_stems:
            df.update(set(doc))

        # Precompute RSJ IDF: ln( (N - n + 0.5) / (n + 0.5) + 1 )
        self.idf: dict[str, float] = {}
        for term, n in df.items():
            self.idf[term] = math.log((self.corpus_size - n + 0.5) / (n + 0.5) + 1.0)

    @classmethod
    def from_documents(
        cls,
        documents: Sequence[str],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> BM25Okapi:
        """Construct BM25 index from raw text documents."""
        corpus_stems: list[list[str]] = []
        for doc in documents:
            _, stems = tokenize_turkish(doc)
            corpus_stems.append(stems)
        return cls(corpus_stems, k1=k1, b=b)

    def score(self, query: str, doc_idx: int) -> float:
        """Calculate BM25 score for a specific document index against query."""
        if self.corpus_size == 0 or doc_idx >= self.corpus_size:
            return 0.0

        _, query_stems = tokenize_turkish(query)
        if not query_stems or self.avgdl == 0.0:
            return 0.0

        doc_len = self.doc_lens[doc_idx]
        frequencies = self.doc_freqs[doc_idx]
        score = 0.0

        for stem in query_stems:
            if stem not in frequencies:
                continue
            tf = frequencies[stem]
            idf = self.idf.get(stem, 0.0)
            numerator = tf * (self.k1 + 1.0)
            denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl))
            score += idf * (numerator / denominator)

        return score

    def score_all(self, query: str) -> list[float]:
        """Compute BM25 scores for all documents in the corpus."""
        return [self.score(query, idx) for idx in range(self.corpus_size)]

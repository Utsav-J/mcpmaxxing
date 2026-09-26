"""Small deterministic BM25 baseline; no models, network, or prompt construction."""

import math
import re
from collections import Counter


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)


class BM25:
    def __init__(self, documents: dict[str, str]):
        self.counts = {name: Counter(tokens(text)) for name, text in documents.items()}
        if not self.counts or any(not counter for counter in self.counts.values()):
            raise ValueError("BM25 requires non-empty tool documents.")
        self.lengths = {name: sum(counter.values()) for name, counter in self.counts.items()}
        self.average = sum(self.lengths.values()) / len(self.counts)
        self.frequency = Counter(term for counter in self.counts.values() for term in counter)

    def rank(self, query: str, k: int = 3) -> list[tuple[str, float]]:
        if type(k) is not int or not 1 <= k <= len(self.counts):
            raise ValueError("K must be an integer between 1 and the tool count.")
        if not query.strip():
            raise ValueError("Query must not be empty.")
        results = []
        n = len(self.counts)
        for name, counter in self.counts.items():
            score = 0.0
            for term in sorted(set(tokens(query))):
                tf = counter[term]
                if not tf:
                    continue
                df = self.frequency[term]
                idf = math.log1p((n - df + 0.5) / (df + 0.5))
                score += (
                    idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * self.lengths[name] / self.average))
                )
            if score > 0:
                results.append((name, score))
        return sorted(results, key=lambda entry: (-entry[1], entry[0]))[:k]

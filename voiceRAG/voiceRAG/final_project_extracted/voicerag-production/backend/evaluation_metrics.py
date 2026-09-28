from __future__ import annotations

import re
from collections import Counter


def retrieval_recall(retrieved: list[str], expected: list[str]) -> float:
    expected_set = set(expected)
    return len(expected_set.intersection(retrieved)) / len(expected_set) if expected_set else 0.0


def citation_scores(cited_document_ids: list[str], expected: list[str]) -> tuple[float, float]:
    expected_set, cited_set = set(expected), set(cited_document_ids)
    precision = len(cited_set & expected_set) / len(cited_set) if cited_set else 0.0
    recall = len(cited_set & expected_set) / len(expected_set) if expected_set else 0.0
    return precision, recall


def answer_f1(predicted: str, expected: str) -> float:
    tokenize = lambda value: re.findall(r"[\w]+", value.lower())
    predicted_counts, expected_counts = Counter(tokenize(predicted)), Counter(tokenize(expected))
    overlap = sum((predicted_counts & expected_counts).values())
    if not overlap:
        return 0.0
    precision = overlap / max(sum(predicted_counts.values()), 1)
    recall = overlap / max(sum(expected_counts.values()), 1)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0

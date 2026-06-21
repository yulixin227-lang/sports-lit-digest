from __future__ import annotations

import re
from typing import Any

from .classify_papers import classify_paper
from .keyword_utils import iter_keywords
from .utils import is_seen_paper, normalize_doi, normalize_text


def score_papers(
    papers: list[dict[str, Any]],
    journals_config: dict[str, Any],
    keywords_config: dict[str, Any],
    scoring_config: dict[str, Any],
    categories_config: dict[str, Any] | None = None,
    elite_journals_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        score_paper(
            paper,
            journals_config,
            keywords_config,
            scoring_config,
            categories_config=categories_config,
            elite_journals_config=elite_journals_config,
        )
        for paper in papers
    ]


def score_paper(
    paper: dict[str, Any],
    journals_config: dict[str, Any],
    keywords_config: dict[str, Any],
    scoring_config: dict[str, Any],
    categories_config: dict[str, Any] | None = None,
    elite_journals_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weights = scoring_config.get("weights", {})
    classification = classify_paper(
        paper,
        categories_config=categories_config,
        elite_journals_config=elite_journals_config,
        keywords_config=keywords_config,
    )
    journal_score = _journal_score(
        paper,
        journals_config,
        scoring_config,
        weights.get("journal", 30),
        classification,
    )
    article_type_score = _article_type_score(paper, scoring_config, weights.get("article_type", 20))
    method_score = _method_quality_score(paper, scoring_config, weights.get("method_quality", 20))
    keyword_score, matched_keywords = _keyword_score(
        paper,
        keywords_config,
        scoring_config,
        weights.get("keyword_match", 20),
    )
    readability_score = _readability_score(paper, scoring_config, weights.get("readability", 10))
    relevance_boost = _personal_relevance_boost(classification, scoring_config)
    population_database_score = _population_database_boost(classification, scoring_config)
    elite_radar_score = _elite_radar_boost(classification, scoring_config)

    total = (
        journal_score
        + article_type_score
        + method_score
        + keyword_score
        + readability_score
        + relevance_boost
        + population_database_score
        + elite_radar_score
    )
    paper["score"] = round(max(0, min(100, total)), 1)
    paper["score_breakdown"] = {
        "journal": round(journal_score, 1),
        "article_type": round(article_type_score, 1),
        "method_quality": round(method_score, 1),
        "keyword_match": round(keyword_score, 1),
        "readability": round(readability_score, 1),
        "personal_relevance": round(relevance_boost, 1),
        "population_database": round(population_database_score, 1),
        "elite_radar": round(elite_radar_score, 1),
    }
    paper["matched_keywords"] = matched_keywords
    paper["classification"] = classification
    paper["personal_relevance_score"] = classification.get("personal_relevance_score", 0)
    return paper


def select_top_papers(
    papers: list[dict[str, Any]],
    seen: dict[str, set[str]],
    min_score: int,
    max_papers: int,
) -> list[dict[str, Any]]:
    candidates = [
        paper
        for paper in papers
        if paper.get("score", 0) >= min_score and not is_seen_paper(seen, paper)
    ]
    return sorted(
        candidates,
        key=lambda paper: (
            paper.get("score", 0),
            str(paper.get("publication_date") or ""),
            str(paper.get("title") or ""),
        ),
        reverse=True,
    )[:max_papers]


def _journal_score(
    paper: dict[str, Any],
    journals_config: dict[str, Any],
    scoring_config: dict[str, Any],
    max_score: float,
    classification: dict[str, Any] | None = None,
) -> float:
    classification = classification or {}
    elite_config = scoring_config.get("elite_radar", {})
    if (
        classification.get("is_elite_radar")
        and float(classification.get("personal_relevance_score") or 0)
        >= float(elite_config.get("min_personal_relevance", 60))
    ):
        return min(float(elite_config.get("journal_score", max_score)), max_score)

    journal_value = paper.get("journal") or paper.get("journal_abbreviation") or ""
    semantic = paper.get("semantic_scholar") or {}
    semantic_journal = ""
    if isinstance(semantic.get("journal"), dict):
        semantic_journal = semantic["journal"].get("name") or ""
    elif semantic.get("journal"):
        semantic_journal = str(semantic.get("journal"))
    candidates = [journal_value, semantic.get("venue"), semantic_journal]

    for journal in journals_config.get("journals", []):
        names = [journal.get("name"), *journal.get("aliases", [])]
        if _matches_any(candidates, names):
            return min(float(journal.get("priority", max_score)), max_score)
    return float(scoring_config.get("journal", {}).get("unknown_score", 0))


def _article_type_score(
    paper: dict[str, Any],
    scoring_config: dict[str, Any],
    max_score: float,
) -> float:
    config = scoring_config.get("article_type", {})
    title_and_types = _article_type_blob(paper)
    score = float(config.get("base_score", 0))

    for preferred in config.get("preferred", []):
        if _term_in_blob(preferred.get("term"), title_and_types):
            score = max(score, float(preferred.get("score", 0)))

    for downgrade in config.get("downgrade", []):
        if _term_in_blob(downgrade.get("term"), title_and_types):
            score -= float(downgrade.get("penalty", 0))

    return max(0, min(max_score, score))


def _method_quality_score(
    paper: dict[str, Any],
    scoring_config: dict[str, Any],
    max_score: float,
) -> float:
    config = scoring_config.get("method_quality", {})
    blob = _paper_blob(paper)
    score = float(config.get("base_with_abstract", 0)) if paper.get("abstract") else 0.0

    for item in config.get("positive_terms", []):
        if _term_in_blob(item.get("term"), blob):
            score += float(item.get("points", 0))

    sample_size_regex = config.get("sample_size_regex")
    if sample_size_regex and re.search(sample_size_regex, str(paper.get("abstract") or ""), re.IGNORECASE):
        score += float(config.get("sample_size_points", 0))

    for item in config.get("negative_terms", []):
        if _term_in_blob(item.get("term"), blob):
            score -= float(item.get("points", 0))

    return max(0, min(max_score, score))


def _keyword_score(
    paper: dict[str, Any],
    keywords_config: dict[str, Any],
    scoring_config: dict[str, Any],
    max_score: float,
) -> tuple[float, list[dict[str, Any]]]:
    blob = _paper_blob(paper)
    matched: list[dict[str, Any]] = []
    weighted_count = 0.0

    for keyword in iter_keywords(keywords_config):
        candidates = [keyword.get("term"), *keyword.get("aliases", [])]
        if any(_term_in_blob(candidate, blob) for candidate in candidates if candidate):
            weighted_count += float(keyword.get("weight", 1.0))
            matched.append(
                {
                    "term": keyword.get("term"),
                    "zh": keyword.get("zh") or keyword.get("term"),
                    "weight": keyword.get("weight", 1.0),
                }
            )

    target = float(scoring_config.get("keyword_match", {}).get("target_matches", 4))
    score = max_score if target <= 0 else min(max_score, max_score * weighted_count / target)
    return score, matched


def _personal_relevance_boost(
    classification: dict[str, Any],
    scoring_config: dict[str, Any],
) -> float:
    config = scoring_config.get("relevance_boost", {})
    max_points = float(config.get("max_points", 8))
    score = float(classification.get("personal_relevance_score") or 0)
    return max_points * min(100, max(0, score)) / 100


def _population_database_boost(
    classification: dict[str, Any],
    scoring_config: dict[str, Any],
) -> float:
    if "公开数据库" not in (classification.get("study_type_tags") or []):
        return 0.0
    return float(scoring_config.get("population_database", {}).get("points", 5))


def _elite_radar_boost(
    classification: dict[str, Any],
    scoring_config: dict[str, Any],
) -> float:
    config = scoring_config.get("elite_radar", {})
    if not classification.get("is_elite_radar"):
        return 0.0
    if float(classification.get("personal_relevance_score") or 0) < float(config.get("min_personal_relevance", 60)):
        return 0.0
    return float(config.get("points", 6))


def _readability_score(
    paper: dict[str, Any],
    scoring_config: dict[str, Any],
    max_score: float,
) -> float:
    config = scoring_config.get("readability", {})
    abstract = str(paper.get("abstract") or "")
    score = 0.0

    if len(abstract) >= int(config.get("abstract_min_chars", 600)):
        score += float(config.get("abstract_full_score", 6))
    elif abstract:
        score += float(config.get("abstract_partial_score", 3))

    if normalize_doi(paper.get("doi")):
        score += float(config.get("doi_points", 2))

    structured_markers = ["results:", "conclusion:", "conclusions:", "methods:", "objective:"]
    if any(marker in abstract.lower() for marker in structured_markers):
        score += float(config.get("structured_abstract_points", 2))

    return max(0, min(max_score, score))


def _paper_blob(paper: dict[str, Any]) -> str:
    values = [
        paper.get("title"),
        paper.get("abstract"),
        paper.get("journal"),
        paper.get("journal_abbreviation"),
        " ".join(paper.get("article_types") or []),
    ]
    semantic = paper.get("semantic_scholar") or {}
    values.extend([semantic.get("venue"), semantic.get("journal")])
    return normalize_text(" ".join(str(value or "") for value in values))


def _article_type_blob(paper: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [
                str(paper.get("title") or ""),
                str(paper.get("abstract") or "")[:1200],
                " ".join(paper.get("article_types") or []),
            ]
        )
    )


def _term_in_blob(term: Any, blob: str) -> bool:
    normalized = normalize_text(term)
    if not normalized:
        return False
    return normalized in blob


def _matches_any(values: list[Any], candidates: list[Any]) -> bool:
    normalized_values = [normalize_text(value) for value in values if value]
    normalized_candidates = [normalize_text(candidate) for candidate in candidates if candidate]
    for value in normalized_values:
        for candidate in normalized_candidates:
            if value == candidate:
                return True
            if len(candidate) >= 8 and candidate in value:
                return True
            if len(value) >= 8 and value in candidate:
                return True
    return False

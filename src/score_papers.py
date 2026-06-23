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
    result_specificity_score = _result_specificity_score(paper)
    result_specificity_penalty = _result_specificity_penalty(result_specificity_score, scoring_config)
    presentation_value_score = _presentation_value_score(
        paper,
        classification,
        result_specificity_score,
        matched_keywords,
    )

    total = (
        journal_score
        + article_type_score
        + method_score
        + keyword_score
        + readability_score
        + relevance_boost
        + population_database_score
        + elite_radar_score
        - result_specificity_penalty
    )
    precision_gate = _precision_gate_status(
        paper=paper,
        classification=classification,
        result_specificity_score=result_specificity_score,
        matched_keywords=matched_keywords,
        scoring_config=scoring_config,
    )
    capped_total = _apply_score_caps(total, result_specificity_score, classification, scoring_config, precision_gate)
    paper["score"] = round(max(0, min(100, capped_total)), 1)
    paper["score_breakdown"] = {
        "journal": round(journal_score, 1),
        "article_type": round(article_type_score, 1),
        "method_quality": round(method_score, 1),
        "keyword_match": round(keyword_score, 1),
        "readability": round(readability_score, 1),
        "personal_relevance": round(relevance_boost, 1),
        "population_database": round(population_database_score, 1),
        "elite_radar": round(elite_radar_score, 1),
        "result_specificity": round(result_specificity_score, 1),
        "presentation_value": round(presentation_value_score, 1),
        "result_specificity_penalty": round(-result_specificity_penalty, 1),
        "score_cap": round(capped_total - total, 1),
    }
    paper["result_specificity_score"] = round(result_specificity_score, 1)
    paper["presentation_value_score"] = round(presentation_value_score, 1)
    paper["presentation_value_reason"] = _presentation_value_reason(
        paper,
        classification,
        presentation_value_score,
        result_specificity_score,
    )
    paper["precision_gate_passed"] = precision_gate["passed"]
    paper["precision_gate_reason"] = precision_gate["reason"]
    paper["reading_priority"] = _reading_priority(paper["score"], result_specificity_score)
    paper["matched_keywords"] = matched_keywords
    paper["classification"] = classification
    paper["personal_relevance_score"] = classification.get("personal_relevance_score", 0)
    return paper


def select_top_papers(
    papers: list[dict[str, Any]],
    seen: dict[str, set[str]],
    min_score: int,
    max_papers: int,
    scoring_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    candidates = [
        paper
        for paper in papers
        if paper.get("score", 0) >= min_score
        and _passes_recommendation_precision(paper, scoring_config)
        and not is_seen_paper(seen, paper)
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


def _apply_score_caps(
    total: float,
    result_specificity_score: float,
    classification: dict[str, Any],
    scoring_config: dict[str, Any],
    precision_gate: dict[str, Any],
) -> float:
    if result_specificity_score < 40:
        return min(total, 59.0)
    if result_specificity_score < 50:
        return min(total, 69.0)
    if (
        classification.get("demote_reason")
        and classification.get("has_category_config")
        and not classification.get("relevance_gate_passed")
        and not precision_gate.get("passed", False)
    ):
        return min(total, 59.0)
    if classification.get("is_elite_journal") and not classification.get("is_elite_radar"):
        return min(total, 59.0)
    precision_config = scoring_config.get("recommendation_precision", {})
    if precision_config.get("enabled", True) and not precision_gate.get("passed", True):
        return min(total, float(precision_config.get("cap_failed_score", 69)))
    return total


def _passes_recommendation_precision(paper: dict[str, Any], scoring_config: dict[str, Any] | None) -> bool:
    precision_config = (scoring_config or {}).get("recommendation_precision")
    if not precision_config or not precision_config.get("enabled", True):
        return True
    return bool(paper.get("precision_gate_passed", True))


def _precision_gate_status(
    *,
    paper: dict[str, Any],
    classification: dict[str, Any],
    result_specificity_score: float,
    matched_keywords: list[dict[str, Any]],
    scoring_config: dict[str, Any],
) -> dict[str, Any]:
    precision_config = scoring_config.get("recommendation_precision")
    if not precision_config or not precision_config.get("enabled", True):
        return {"passed": True, "reason": "precision gate disabled"}

    reasons: list[str] = []
    personal_relevance = float(classification.get("personal_relevance_score") or 0)
    min_personal_relevance = float(precision_config.get("min_personal_relevance", 50))
    min_result_specificity = float(precision_config.get("min_result_specificity", 50))
    min_observational_result_specificity = float(
        precision_config.get("min_observational_result_specificity", min_result_specificity)
    )
    min_core_keyword_matches = int(precision_config.get("min_core_keyword_matches", 2))
    core_keyword_matches = _core_keyword_match_count(matched_keywords)
    has_direction_evidence = bool(classification.get("direction_evidence"))
    study_type_tags = set(classification.get("study_type_tags") or [])

    has_relevance_evidence = personal_relevance >= min_personal_relevance or core_keyword_matches >= min_core_keyword_matches
    if not has_relevance_evidence:
        reasons.append(
            f"personal relevance {personal_relevance:.0f} < {min_personal_relevance:.0f} and core keyword hits {core_keyword_matches} < {min_core_keyword_matches}"
        )
    if precision_config.get("require_direction_evidence", True) and not (has_direction_evidence or core_keyword_matches >= min_core_keyword_matches):
        reasons.append("no direction evidence snippet")
    if result_specificity_score < min_result_specificity:
        reasons.append(f"result specificity {result_specificity_score:.0f} < {min_result_specificity:.0f}")
    if (
        study_type_tags.intersection({"观察性研究", "人群队列", "公开数据库"})
        and not study_type_tags.intersection({"系统综述", "Meta分析", "范围综述", "RCT"})
        and result_specificity_score < min_observational_result_specificity
    ):
        reasons.append(
            f"observational result specificity {result_specificity_score:.0f} < {min_observational_result_specificity:.0f}"
        )
    if (
        precision_config.get("require_observational_effect_estimate", True)
        and study_type_tags.intersection({"观察性研究", "人群队列", "公开数据库"})
        and not study_type_tags.intersection({"系统综述", "Meta分析", "范围综述", "RCT"})
        and not _has_effect_estimate_or_p_value(str(paper.get("abstract") or ""))
    ):
        reasons.append("observational abstract lacks effect estimate, CI, p value, or directional statistic")
    if (
        precision_config.get("exclude_demoted", True)
        and classification.get("demote_reason")
        and core_keyword_matches < min_core_keyword_matches
    ):
        reasons.append("demoted by relevance gate")
    if precision_config.get("exclude_optional_reading", True) and result_specificity_score < 50:
        reasons.append("optional reading because abstract lacks concrete results")

    return {
        "passed": not reasons,
        "reason": "; ".join(reasons) if reasons else "passed",
        "core_keyword_matches": core_keyword_matches,
    }


def _core_keyword_match_count(matched_keywords: list[dict[str, Any]]) -> int:
    return sum(
        1
        for keyword in matched_keywords
        if str(keyword.get("group") or "") in {"core_keywords", "keywords"}
    )


def _has_effect_estimate_or_p_value(text: str) -> bool:
    if not text:
        return False
    return bool(
        re.search(
            r"\b("
            r"odds ratio|hazard ratio|risk ratio|relative risk|confidence interval|"
            r"95\s*%\s*ci|ci\b|p\s*[<=>]\s*0?\.\d+|beta|β|effect size|cohen|"
            r"mean difference|standardized mean difference|smd|estimate"
            r")\b",
            text,
            flags=re.IGNORECASE,
        )
    )


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
        matched_candidate = next((candidate for candidate in candidates if candidate and _term_in_blob(candidate, blob)), "")
        if matched_candidate:
            weighted_count += float(keyword.get("weight", 1.0))
            matched.append(
                {
                    "term": keyword.get("term"),
                    "matched_term": matched_candidate,
                    "zh": keyword.get("zh") or keyword.get("term"),
                    "weight": keyword.get("weight", 1.0),
                    "group": keyword.get("group"),
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


def _result_specificity_score(paper: dict[str, Any]) -> float:
    abstract = str(paper.get("abstract") or "")
    results = _results_section(abstract)
    target_text = results or abstract
    if not target_text:
        return 0.0

    blob = normalize_text(target_text)
    score = 20.0 if results else 10.0
    if _extract_numbers(target_text):
        score += 25
    if re.search(r"\b(p\s*[<=>]\s*0?\.\d+|ci\b|confidence interval|odds ratio|hazard ratio|risk ratio|relative risk|effect size|cohen|beta)\b", target_text, re.IGNORECASE):
        score += 25
    if any(term in blob for term in ["associated", "increased", "decreased", "higher", "lower", "improved", "reduced", "predicted"]):
        score += 15
    if any(
        term in blob
        for term in [
            "included studies",
            "included trials",
            "reported original data",
            "directly assessed",
            "symptom duration",
            "pathogen",
            "training interruption",
            "illness duration",
            "severity",
            "physical activity",
            "return-to-sport",
            "return to sport",
            "vo2",
            "strength",
            "pain",
        ]
    ):
        score += 10
    if "conclusion" in blob and not results:
        score += 5
    return max(0.0, min(100.0, score))


def _result_specificity_penalty(score: float, scoring_config: dict[str, Any]) -> float:
    config = scoring_config.get("result_specificity", {})
    low_threshold = float(config.get("low_threshold", 50))
    medium_threshold = float(config.get("medium_threshold", 75))
    if score < low_threshold:
        return float(config.get("low_penalty", 12))
    if score < medium_threshold:
        return float(config.get("medium_penalty", 5))
    return 0.0


def _reading_priority(score: float, result_specificity_score: float) -> str:
    if result_specificity_score < 50:
        return "可选阅读"
    if score >= 80:
        return "优先阅读"
    return "推荐阅读"


def _presentation_value_score(
    paper: dict[str, Any],
    classification: dict[str, Any],
    result_specificity_score: float,
    matched_keywords: list[dict[str, Any]] | None = None,
) -> float:
    abstract = str(paper.get("abstract") or "")
    blob = _paper_blob(paper)
    study_type_tags = set(classification.get("study_type_tags") or [])
    personal_relevance = float(classification.get("personal_relevance_score") or 0)
    matched_keywords = matched_keywords or []
    core_keyword_hits = sum(
        1
        for item in matched_keywords
        if item.get("group") == "core_keywords"
        or str(item.get("term") or "").lower()
        in {
            "hiit",
            "hift",
            "mict",
            "vo2max",
            "cardiorespiratory fitness",
            "sports medicine",
            "exercise physiology",
            "rehabilitation",
            "resistance training",
            "sleep",
            "hrv",
            "semg",
        }
    )

    score = 0.0
    score += min(45.0, result_specificity_score * 0.45)
    score += min(25.0, personal_relevance * 0.25)
    score += min(10.0, core_keyword_hits * 2.5)

    if study_type_tags.intersection({"RCT", "系统综述", "Meta分析", "范围综述", "人群队列", "观察性研究", "公开数据库", "动物实验", "机制研究", "多组学"}):
        score += 10
    if _extract_numbers(abstract):
        score += 8
    if _has_effect_estimate_or_p_value(abstract):
        score += 8
    if any(
        term in blob
        for term in [
            "randomized",
            "cox regression",
            "regression",
            "mri",
            "pcr",
            "rna-seq",
            "proteomics",
            "metabolomics",
            "atac-seq",
            "dna methylation",
            "flow cytometry",
            "western blot",
        ]
    ):
        score += 6

    if classification.get("demote_reason"):
        score -= 10 if core_keyword_hits >= 2 and result_specificity_score >= 70 else 30
    if result_specificity_score < 40:
        score = min(score, 45)
    elif result_specificity_score < 50:
        score = min(score, 60)
    if personal_relevance < 40 and not classification.get("direction_evidence") and core_keyword_hits < 2:
        score = min(score, 55)
    if classification.get("is_elite_journal") and not classification.get("is_elite_radar"):
        score = min(score, 50)
    return max(0.0, min(100.0, score))


def _presentation_value_reason(
    paper: dict[str, Any],
    classification: dict[str, Any],
    presentation_value_score: float,
    result_specificity_score: float,
) -> str:
    if presentation_value_score >= 75:
        return "研究问题、方法和结果信息较完整，适合直接发展成组会汇报。"
    if presentation_value_score >= 55:
        return "主题有一定汇报价值，但仍需要阅读全文确认方法细节、图表和偏倚风险。"
    if classification.get("demote_reason"):
        return str(classification.get("demote_reason"))
    if result_specificity_score < 50:
        return "摘要结果信息不足，暂不适合作为组会主讲文献。"
    return "当前摘要可用信息有限，组会价值需要阅读全文后再判断。"


def _results_section(abstract: str) -> str:
    if not abstract:
        return ""
    match = re.search(r"(?is)\bRESULTS?\s*:\s*(.*?)(?:\bCONCLUSIONS?\s*:|\bCONCLUSION\s*:|\bINTERPRETATION\s*:|$)", abstract)
    if match:
        return match.group(1).strip()
    return ""


def _extract_numbers(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(
        r"(?:\bn\s*=\s*\d+|\b\d+\s*/\s*\d+|\b\d+(?:\.\d+)?\s*%|\b\d+(?:,\d{3})*(?:\.\d+)?)",
        text,
        flags=re.IGNORECASE,
    )


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
    return f" {normalized} " in f" {blob} "


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

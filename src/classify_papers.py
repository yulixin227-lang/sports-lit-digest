from __future__ import annotations

from typing import Any

from .journal_metrics import normalize_journal_name
from .keyword_utils import iter_keywords
from .utils import normalize_text


MISSING = "摘要中未提供"
ANIMAL_MODEL_TERMS = [
    "mouse",
    "mice",
    "rat",
    "rats",
    "murine",
    "animal model",
    "rodent",
    "swine",
    "rabbit",
    "zebrafish",
    "drosophila",
    "c elegans",
]


def classify_paper(
    paper: dict[str, Any],
    categories_config: dict[str, Any] | None = None,
    elite_journals_config: dict[str, Any] | None = None,
    keywords_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    categories_config = categories_config or {}
    elite_journals_config = elite_journals_config or {}
    keywords_config = keywords_config or {}
    blob = _paper_blob(paper)

    matched_categories = _matched_categories(blob, categories_config)
    study_type_tags = _study_type_tags(blob)
    data_sources = _data_sources(blob)
    elite_match = _is_elite_journal(paper, elite_journals_config)
    elite_topic_score = _elite_topic_score(blob, keywords_config, categories_config, elite_journals_config)
    personal_relevance_score = _personal_relevance_score(
        matched_categories=matched_categories,
        study_type_tags=study_type_tags,
        elite_topic_score=elite_topic_score,
        elite_match=elite_match,
    )
    is_elite_radar = bool(elite_match and personal_relevance_score >= 60)
    directions = [*_special_directions(blob), *[category["zh"] for category in matched_categories]]
    directions = list(dict.fromkeys(directions))
    if is_elite_radar and "顶刊雷达" not in directions:
        directions.append("顶刊雷达")

    return {
        "directions": directions,
        "direction_display": " / ".join(directions) if directions else "未明确分类",
        "matched_categories": matched_categories,
        "study_type_tags": study_type_tags,
        "study_type_display": " / ".join(study_type_tags) if study_type_tags else "未明确研究类型",
        "data_sources": data_sources,
        "data_source_display": " / ".join(data_sources) if data_sources else MISSING,
        "is_elite_journal": bool(elite_match),
        "is_elite_radar": is_elite_radar,
        "elite_radar_display": "是" if is_elite_radar else "否",
        "personal_relevance_score": personal_relevance_score,
        "relation_to_me": _relation_to_me(directions, study_type_tags, data_sources, is_elite_radar),
    }


def _matched_categories(blob: str, categories_config: dict[str, Any]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for category in categories_config.get("categories", []) or []:
        if category.get("id") == "elite_journal_radar":
            continue
        keywords = category.get("keywords") or []
        hit_terms = [term for term in keywords if _term_in_blob(term, blob)]
        anchor_terms = category.get("anchor_keywords") or keywords
        has_anchor = any(_term_in_blob(term, blob) for term in anchor_terms)
        if hit_terms and has_anchor:
            matched.append(
                {
                    "id": category.get("id") or "",
                    "zh": category.get("zh") or category.get("name") or category.get("id") or "未命名方向",
                    "en": category.get("en") or "",
                    "terms": hit_terms[:8],
                }
            )
    return matched


def _study_type_tags(blob: str) -> list[str]:
    tags: list[str] = []
    if any(_term_in_blob(term, blob) for term in ["uk biobank", "nhanes", "china kadoorie biobank", "biobank japan", "all of us"]):
        tags.append("公开数据库")
    if any(_term_in_blob(term, blob) for term in ["cohort", "prospective cohort", "longitudinal cohort", "population study", "epidemiology"]) or _is_athlete_rts_infection(blob):
        tags.append("人群队列")
    if any(_term_in_blob(term, blob) for term in ["observational study", "observational", "prospective", "cross sectional", "cross-sectional", "case control", "case-control"]) or _is_athlete_rts_infection(blob):
        tags.append("观察性研究")
    if any(_term_in_blob(term, blob) for term in ["randomized controlled trial", "randomised controlled trial", "clinical trial", "randomized trial", "controlled trial"]):
        tags.append("RCT")
    if _has_animal_model_signal(blob):
        tags.append("动物实验")
    if any(_term_in_blob(term, blob) for term in ["cell culture", "in vitro", "myotube", "c2c12"]):
        tags.append("细胞实验")
    if any(_term_in_blob(term, blob) for term in ["mechanism", "mechanistic", "pathway", "mitochondrial function", "skeletal muscle mechanism"]):
        tags.append("机制研究")
    if any(_term_in_blob(term, blob) for term in ["omics", "multi-omics", "rna-seq", "atac-seq", "single-cell", "scrna-seq", "snrna-seq", "proteomics", "metabolomics", "dna methylation", "spatial transcriptomics"]):
        tags.append("多组学")
    if _term_in_blob("systematic review", blob):
        tags.append("系统综述")
    if _term_in_blob("meta-analysis", blob) or _term_in_blob("meta analysis", blob):
        tags.append("Meta分析")
    return list(dict.fromkeys(tags))


def _data_sources(blob: str) -> list[str]:
    sources = []
    if _is_athlete_rts_infection(blob):
        sources.append("运动员临床队列")
    for term, label in [
        ("uk biobank", "UK Biobank"),
        ("nhanes", "NHANES"),
        ("china kadoorie biobank", "China Kadoorie Biobank"),
        ("biobank japan", "Biobank Japan"),
        ("all of us", "All of Us"),
        ("clinical cohort", "临床队列"),
        ("cohort", "队列研究"),
        ("mouse", "动物实验"),
        ("mice", "动物实验"),
        ("rat", "动物实验"),
        ("rats", "动物实验"),
        ("murine", "动物实验"),
        ("animal model", "动物实验"),
        ("rodent", "动物实验"),
        ("swine", "动物实验"),
        ("rabbit", "动物实验"),
        ("zebrafish", "动物实验"),
        ("drosophila", "动物实验"),
        ("c elegans", "动物实验"),
        ("cell culture", "细胞实验"),
        ("in vitro", "细胞实验"),
    ]:
        if _term_in_blob(term, blob):
            sources.append(label)
    return list(dict.fromkeys(sources))


def _is_elite_journal(paper: dict[str, Any], elite_journals_config: dict[str, Any]) -> bool:
    journals = elite_journals_config.get("journals") or []
    if not journals:
        return False
    candidates = [
        paper.get("journal"),
        paper.get("journal_abbreviation"),
        (paper.get("semantic_scholar") or {}).get("venue"),
    ]
    normalized_candidates = {normalize_journal_name(candidate) for candidate in candidates if candidate}
    for journal in journals:
        names = [journal.get("name"), *(journal.get("aliases") or [])]
        normalized_names = {normalize_journal_name(name) for name in names if name}
        if normalized_candidates & normalized_names:
            return True
    return False


def _elite_topic_score(
    blob: str,
    keywords_config: dict[str, Any],
    categories_config: dict[str, Any],
    elite_journals_config: dict[str, Any] | None = None,
) -> int:
    elite_journals_config = elite_journals_config or {}
    terms = list(elite_journals_config.get("required_topic_terms") or [])
    if not terms:
        terms = [keyword.get("term") for keyword in iter_keywords(keywords_config, ["elite_journal_keywords"])]
    if not terms:
        for category in categories_config.get("categories", []) or []:
            terms.extend(category.get("keywords") or [])
    return sum(1 for term in terms if _term_in_blob(term, blob))


def _personal_relevance_score(
    *,
    matched_categories: list[dict[str, Any]],
    study_type_tags: list[str],
    elite_topic_score: int,
    elite_match: bool,
) -> int:
    score = 0
    score += min(60, 20 * len(matched_categories))
    score += min(20, 5 * sum(len(category.get("terms") or []) for category in matched_categories))
    if any(tag in study_type_tags for tag in ["公开数据库", "RCT", "人群队列", "观察性研究", "多组学", "动物实验"]):
        score += 10
    if elite_match and elite_topic_score:
        score += min(20, 5 * elite_topic_score)
    return max(0, min(100, score))


def _relation_to_me(
    directions: list[str],
    study_type_tags: list[str],
    data_sources: list[str],
    is_elite_radar: bool,
) -> str:
    if not directions and not study_type_tags:
        return "这篇文章与当前扩展方向的关系不够明确，建议先作为候选文献保留。"

    pieces: list[str] = []
    if directions:
        pieces.append("它命中本项目关注的" + "、".join(directions[:3]) + "方向")
    if data_sources:
        pieces.append("数据来源涉及" + "、".join(data_sources[:3]))
    if study_type_tags:
        pieces.append("研究类型可标记为" + "、".join(study_type_tags[:3]))
    if is_elite_radar:
        pieces.append("同时来自 Nature/Cell/Science 相关重点期刊，适合作为顶刊雷达条目重点跟踪")
    return "；".join(pieces) + "。这有助于连接运动科学、DPT 申请、肥胖代谢、肌肉机制或运动营养选题。"


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


def _special_directions(blob: str) -> list[str]:
    if _is_athlete_rts_infection(blob):
        return ["运动医学", "运动员健康", "呼吸道感染", "重返运动"]
    return []


def _is_athlete_rts_infection(blob: str) -> bool:
    has_athlete = any(_term_in_blob(term, blob) for term in ["athlete", "athletes"])
    has_rts = any(_term_in_blob(term, blob) for term in ["return-to-sport", "return to sport", "return-to-play", "return to play"])
    has_infection = any(
        _term_in_blob(term, blob)
        for term in ["acute respiratory infection", "acute respiratory infections", "respiratory infection", "respiratory infections", "pathogen-confirmed"]
    )
    return has_athlete and has_rts and has_infection


def _has_animal_model_signal(blob: str) -> bool:
    return any(_term_in_blob(term, blob) for term in ANIMAL_MODEL_TERMS)


def _term_in_blob(term: Any, blob: str) -> bool:
    normalized = normalize_text(term)
    if not normalized:
        return False
    return f" {normalized} " in f" {blob} "

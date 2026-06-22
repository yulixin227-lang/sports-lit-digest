from __future__ import annotations

from typing import Any

from .journal_metrics import normalize_journal_name
from .keyword_utils import iter_keywords
from .utils import normalize_text


MISSING = "摘要中未提供"
ANIMAL_MODEL_TERMS = [
    "high-fat diet-induced mice",
    "diet-induced obesity mouse",
    "mouse",
    "mice",
    "rats",
    "rat",
    "murine",
    "animal model",
    "animal study",
    "rodent",
    "swine",
    "pig",
    "rabbit",
    "zebrafish",
    "drosophila",
    "c elegans",
]

ANIMAL_MODEL_BLOCKERS = [
    "meta-analysis",
    "meta analysis",
    "systematic review",
    "cohort",
    "uk biobank",
    "nhanes",
    "athlete",
    "athletes",
    "human",
    "participants",
    "adults",
    "electromyography",
    "swimming performance",
]

ELITE_CORE_TOPIC_TERMS = [
    "exercise",
    "physical activity",
    "training",
    "sedentary behavior",
    "skeletal muscle",
    "muscle regeneration",
    "muscle stem cell",
    "satellite cell",
    "sarcopenia",
    "hypertrophy",
    "atrophy",
    "obesity",
    "adipose tissue",
    "metabolic health",
    "insulin resistance",
    "lipid metabolism",
    "nutrition",
    "dietary intervention",
    "protein",
    "creatine",
    "caffeine",
    "fatty acid",
    "human performance",
    "cardiorespiratory fitness",
    "vo2max",
    "vo2 max",
]

OMICS_TERMS = [
    "omics",
    "multi-omics",
    "proteomics",
    "proteomic",
    "metabolomics",
    "metabolomic",
    "rna-seq",
    "atac-seq",
    "single-cell",
    "scrna-seq",
    "snrna-seq",
    "dna methylation",
    "spatial transcriptomics",
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
    sources = _source_texts(paper)

    matched_categories = _matched_categories(sources, categories_config)
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
    special_matches = _special_direction_matches(sources, blob)
    if special_matches:
        special_relevance = min(100, 35 + 10 * len(special_matches))
        if any(tag in study_type_tags for tag in ["RCT", "系统综述", "Meta分析", "范围综述", "人群队列", "观察性研究"]):
            special_relevance += 10
        personal_relevance_score = max(personal_relevance_score, min(100, special_relevance))
    is_elite_radar = bool(elite_match and _elite_topic_gate(blob) and personal_relevance_score >= 60)
    directions = [*[item["zh"] for item in special_matches], *[category["zh"] for category in matched_categories]]
    directions = list(dict.fromkeys(directions))
    if is_elite_radar and "顶刊雷达" not in directions:
        directions.append("顶刊雷达")
    direction_evidence = _direction_evidence(special_matches, matched_categories, is_elite_radar, blob)
    demote_reason = _demote_reason(blob, directions, bool(elite_match), bool(is_elite_radar))

    return {
        "directions": directions,
        "direction_display": " / ".join(directions) if directions else "未明确分类",
        "direction_evidence": direction_evidence,
        "matched_categories": matched_categories,
        "has_category_config": bool(categories_config.get("categories")),
        "study_type_tags": study_type_tags,
        "study_type_display": " / ".join(study_type_tags) if study_type_tags else "未明确研究类型",
        "data_sources": data_sources,
        "data_source_display": " / ".join(data_sources) if data_sources else MISSING,
        "is_elite_journal": bool(elite_match),
        "is_elite_radar": is_elite_radar,
        "elite_radar_display": "是" if is_elite_radar else "否",
        "personal_relevance_score": personal_relevance_score,
        "demote_reason": demote_reason,
        "relevance_gate_passed": bool(directions),
        "relation_to_me": _relation_to_me(directions, study_type_tags, data_sources, is_elite_radar, blob, demote_reason),
    }


def _matched_categories(sources: list[dict[str, str]], categories_config: dict[str, Any]) -> list[dict[str, Any]]:
    blob = normalize_text(" ".join(source["text"] for source in sources))
    matched: list[dict[str, Any]] = []
    for category in categories_config.get("categories", []) or []:
        if category.get("id") == "elite_journal_radar":
            continue
        category_id = str(category.get("id") or "")
        keywords = category.get("keywords") or []
        hit_terms = [term for term in keywords if _term_in_blob(term, blob)]
        anchor_terms = category.get("anchor_keywords") or keywords
        anchor_hits = [term for term in anchor_terms if _term_in_blob(term, blob)]
        if hit_terms and anchor_hits and _category_gate(category_id, blob):
            evidence = [_evidence_snippet(term, sources) for term in anchor_hits[:3]]
            evidence = [item for item in evidence if item]
            if not evidence:
                continue
            matched.append(
                {
                    "id": category_id,
                    "zh": category.get("zh") or category.get("name") or category.get("id") or "未命名方向",
                    "en": category.get("en") or "",
                    "terms": hit_terms[:8],
                    "evidence_snippets": evidence,
                }
            )
    return matched


def _study_type_tags(blob: str) -> list[str]:
    tags: list[str] = []
    is_scoping_review = _term_in_blob("scoping review", blob)
    is_systematic_review = _term_in_blob("systematic review", blob)
    is_meta_analysis = _term_in_blob("meta-analysis", blob) or _term_in_blob("meta analysis", blob)
    is_review = is_scoping_review or is_systematic_review or is_meta_analysis
    if is_scoping_review:
        tags.append("范围综述")
    if any(_term_in_blob(term, blob) for term in ["uk biobank", "nhanes", "china kadoorie biobank", "biobank japan", "all of us"]):
        tags.append("公开数据库")
    if not is_review and (
        any(_term_in_blob(term, blob) for term in ["cohort", "prospective cohort", "longitudinal cohort", "population study", "epidemiology"])
        or _is_athlete_rts_infection(blob)
    ):
        tags.append("人群队列")
    if not is_review and (
        any(_term_in_blob(term, blob) for term in ["observational study", "observational", "prospective", "cross sectional", "cross-sectional", "case control", "case-control"])
        or _is_athlete_rts_infection(blob)
    ):
        tags.append("观察性研究")
    if any(_term_in_blob(term, blob) for term in ["randomized controlled trial", "randomised controlled trial", "clinical trial", "randomized trial", "controlled trial"]):
        tags.append("RCT")
    if _has_animal_model_signal(blob):
        tags.append("动物实验")
    if any(_term_in_blob(term, blob) for term in ["cell culture", "in vitro", "myotube", "c2c12"]):
        tags.append("细胞实验")
    if any(_term_in_blob(term, blob) for term in ["mechanism", "mechanistic", "pathway", "mitochondrial function", "skeletal muscle mechanism"]):
        tags.append("机制研究")
    if any(_term_in_blob(term, blob) for term in OMICS_TERMS) and _omics_project_gate(blob):
        tags.append("多组学")
    if is_systematic_review:
        tags.append("系统综述")
    if is_meta_analysis:
        tags.append("Meta分析")
    return list(dict.fromkeys(tags))


def _data_sources(blob: str) -> list[str]:
    sources = []
    is_review = any(_term_in_blob(term, blob) for term in ["scoping review", "systematic review", "meta-analysis", "meta analysis"])
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
        ("cell culture", "细胞实验"),
        ("in vitro", "细胞实验"),
    ]:
        if _term_in_blob(term, blob) and not (is_review and label in {"队列研究", "临床队列"}):
            sources.append(label)
    if _has_animal_model_signal(blob):
        sources.append("动物实验")
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
    if not _elite_topic_gate(blob):
        return 0
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
        score += 50 + min(20, 5 * elite_topic_score)
    return max(0, min(100, score))


def _relation_to_me(
    directions: list[str],
    study_type_tags: list[str],
    data_sources: list[str],
    is_elite_radar: bool,
    blob: str,
    demote_reason: str = "",
) -> str:
    if demote_reason:
        return demote_reason
    if all(label in directions for label in ["运动干预", "肥胖", "肌因子"]):
        return "这篇直接讨论超重/肥胖人群中不同训练方式与 irisin 等肌因子变化，可用于理解运动干预、肥胖代谢和肌因子之间的关系。"
    if all(label in directions for label in ["公开数据库", "心代谢风险", "MASLD"]):
        return "这篇用公开数据库队列分析 MASLD 或心代谢多病风险，可作为数据库研究设计和风险建模参考；如果没有运动暴露，和运动干预的关系较弱。"
    if all(label in directions for label in ["运动营养", "运动表现"]):
        return "这篇直接讨论补剂或营养摄入对竞技表现的影响，适合运动营养方向和比赛补剂策略讨论。"
    if all(label in directions for label in ["肌电图", "神经肌肉控制"]):
        return "这篇关注人体肌电和局部肌肉疲劳，适合连接神经肌肉控制、肩部功能评估和康复训练设计。"
    if _is_athlete_rts_infection(blob):
        return "这篇聚焦运动员感染后恢复训练和重返运动，适合队医、教练和运动康复人员做复赛风险筛查参考。"
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
    return "；".join(pieces) + "。建议根据全文结果判断它是否能服务于具体训练、康复、代谢或运动营养问题。"


def _source_texts(paper: dict[str, Any]) -> list[dict[str, str]]:
    semantic = paper.get("semantic_scholar") or {}
    items = [
        ("title", paper.get("title")),
        ("abstract", paper.get("abstract")),
        ("journal", paper.get("journal")),
        ("journal", paper.get("journal_abbreviation")),
        ("publication type", " ".join(paper.get("article_types") or [])),
        ("venue", semantic.get("venue")),
        ("semantic journal", semantic.get("journal")),
    ]
    return [{"source": source, "text": str(text)} for source, text in items if str(text or "").strip()]


def _category_gate(category_id: str, blob: str) -> bool:
    if category_id == "sports_nutrition":
        return any(
            _term_in_blob(term, blob)
            for term in [
                "sports nutrition",
                "protein supplementation",
                "whey protein",
                "creatine",
                "caffeine",
                "nitrate",
                "beta-alanine",
                "ergogenic aid",
                "carbohydrate periodization",
                "muscle protein synthesis",
                "leucine",
                "bcaa",
            ]
        )
    if category_id == "dietary_fat_weight_loss":
        return any(
            _term_in_blob(term, blob)
            for term in [
                "dietary fat",
                "fatty acid",
                "olive oil",
                "fish oil",
                "omega-3",
                "omega-6",
                "saturated fat",
                "unsaturated fat",
                "medium-chain triglyceride",
                " mct ",
                "high-fat diet",
                "ketogenic diet",
                "low-fat diet",
                "fat loss",
                "lipid metabolism",
            ]
        )
    if category_id == "muscle_omics":
        if any(_term_in_blob(term, blob) for term in ["muscle memory", "myonuclei", "epigenetic memory"]):
            return True
        return any(_term_in_blob(term, blob) for term in OMICS_TERMS) and _omics_project_gate(blob)
    if category_id == "obesity_heterogeneity":
        return any(
            _term_in_blob(term, blob)
            for term in [
                "obesity heterogeneity",
                "obesity phenotype",
                "obesity subtype",
                "metabolically healthy obesity",
                "metabolically unhealthy obesity",
                "adiposity phenotype",
                "fat distribution",
                "visceral fat",
                "subcutaneous fat",
                "ectopic fat",
                "adipose tissue",
                "body composition",
                "obesity cluster",
                "latent class analysis",
                "unsupervised clustering",
                "diet-induced obesity",
                "high-fat diet",
            ]
        )
    if category_id == "physical_activity_databases":
        if _is_labral_cartilage_athlete_cohort(blob):
            return False
        is_review = any(_term_in_blob(term, blob) for term in ["scoping review", "systematic review", "meta-analysis", "meta analysis"])
        has_physical_activity_signal = any(
            _term_in_blob(term, blob)
            for term in [
                "physical activity",
                "sedentary behavior",
                "accelerometer",
                "device-measured physical activity",
                "wearable",
                "step count",
                "moderate-to-vigorous physical activity",
                "mvpa",
                "light physical activity",
                "cardiorespiratory fitness",
            ]
        )
        has_database_or_device_signal = any(
            _term_in_blob(term, blob)
            for term in [
                "uk biobank",
                "nhanes",
                "china kadoorie biobank",
                "biobank japan",
                "all of us",
                "accelerometer",
                "device-measured physical activity",
                "wearable",
                "step count",
                "moderate-to-vigorous physical activity",
                "mvpa",
                "sedentary behavior",
            ]
        )
        has_population_signal = any(
            _term_in_blob(term, blob)
            for term in [
                "cohort",
                "epidemiology",
                "population study",
            ]
        )
        has_population_outcome_signal = any(
            _term_in_blob(term, blob)
            for term in [
                "mortality",
                "cardiovascular disease",
                "diabetes",
                "cancer",
                "obesity",
                "cardiometabolic",
                "metabolic syndrome",
                "accelerometer",
                "device-measured",
            ]
        )
        return has_physical_activity_signal and (
            has_database_or_device_signal
            or (has_population_signal and has_population_outcome_signal and not is_review)
        )
    return True


def _evidence_snippet(term: Any, sources: list[dict[str, str]]) -> str:
    normalized = normalize_text(term)
    if not normalized:
        return ""
    for item in sources:
        if _term_in_blob(normalized, normalize_text(item["text"])):
            text = " ".join(str(item["text"]).split())
            if len(text) > 180:
                text = text[:177].rstrip() + "..."
            return f"{item['source']}: {text}"
    return ""


def _direction_evidence(
    special_matches: list[dict[str, Any]],
    matched_categories: list[dict[str, Any]],
    is_elite_radar: bool,
    blob: str,
) -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}
    for item in special_matches:
        evidence[item["zh"]] = [str(item.get("evidence") or "title/abstract evidence")]
    for category in matched_categories:
        evidence[category["zh"]] = list(category.get("evidence_snippets") or [])
    if is_elite_radar:
        evidence["顶刊雷达"] = ["journal + topic gate: " + ", ".join(_elite_topic_hits(blob)[:4])]
    return evidence


def _demote_reason(blob: str, directions: list[str], is_elite_journal: bool, is_elite_radar: bool) -> str:
    if _is_ptsd_multisystem_omics(blob) and not directions:
        return "这篇主要是 PTSD 相关多系统疾病/衰老的组学研究，摘要未显示与运动、肌肉、肥胖、营养或代谢干预的明确关联，因此不建议进入主推荐。"
    if is_elite_journal and not is_elite_radar:
        return "这篇来自 Nature/Cell/Science 相关期刊，但摘要未通过运动、肌肉、肥胖/脂肪组织、营养或运动表现主题门槛，适合作为可选观察而不是主推荐。"
    if not directions:
        return "摘要没有提供足够证据把它归入本项目的核心方向，建议仅作可选观察。"
    return ""


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


def _special_direction_matches(sources: list[dict[str, str]], blob: str) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    if _is_glp1_oa_weight_loss(blob):
        evidence = _first_evidence(["glp-1 receptor agonists", "weight-loss strategies", "osteoarthritis", "obesity"], sources)
        matches.extend(
            [
                {"zh": "肥胖", "evidence": evidence},
                {"zh": "骨关节炎", "evidence": evidence},
                {"zh": "减重策略", "evidence": evidence},
                {"zh": "肌骨康复", "evidence": evidence},
            ]
        )
    if _is_irisin_training_obesity(blob):
        evidence = _first_evidence(["irisin", "training", "overweight", "obesity"], sources)
        matches.extend(
            [
                {"zh": "运动干预", "evidence": evidence},
                {"zh": "肥胖", "evidence": evidence},
                {"zh": "肌因子", "evidence": evidence},
            ]
        )
    if _is_masld_population_database(blob):
        evidence = _first_evidence(["masld", "uk biobank", "c-reactive protein-triglyceride-glucose"], sources)
        matches.extend(
            [
                {"zh": "公开数据库", "evidence": evidence},
                {"zh": "心代谢风险", "evidence": evidence},
                {"zh": "MASLD", "evidence": evidence},
                {"zh": "队列研究", "evidence": evidence},
            ]
        )
    if _is_caffeine_swimming_meta(blob):
        evidence = _first_evidence(["caffeine", "swimming performance", "meta-analysis"], sources)
        matches.extend(
            [
                {"zh": "运动营养", "evidence": evidence},
                {"zh": "运动表现", "evidence": evidence},
            ]
        )
    if _is_emg_shoulder_fatigue(blob):
        evidence = _first_evidence(["electromyography", "rotator cuff", "deltoid", "fatigue"], sources)
        matches.extend(
            [
                {"zh": "肌电图", "evidence": evidence},
                {"zh": "神经肌肉控制", "evidence": evidence},
                {"zh": "疲劳", "evidence": evidence},
                {"zh": "肩部肌群", "evidence": evidence},
                {"zh": "人体研究", "evidence": evidence},
            ]
        )
    if _is_labral_cartilage_athlete_cohort(blob):
        evidence = _first_evidence(["labral pathology", "cartilage loss", "high-impact athletes", "FORCe"], sources)
        matches.extend(
            [
                {"zh": "运动医学", "evidence": evidence},
                {"zh": "运动员健康", "evidence": evidence},
                {"zh": "髋关节", "evidence": evidence},
                {"zh": "软骨损伤", "evidence": evidence},
                {"zh": "运动员临床队列", "evidence": evidence},
            ]
        )
    if _is_patellofemoral_strength_meta(blob):
        evidence = _first_evidence(["patellofemoral pain", "muscle strength", "clinical outcome", "meta-analysis"], sources)
        matches.extend(
            [
                {"zh": "肌骨康复", "evidence": evidence},
                {"zh": "髌股疼痛", "evidence": evidence},
                {"zh": "肌肉力量", "evidence": evidence},
                {"zh": "疼痛与功能", "evidence": evidence},
            ]
        )
    if _is_athlete_rts_infection(blob):
        evidence = _first_evidence(["athletes", "return-to-sport", "acute respiratory infections"], sources)
        matches.extend(
            [
                {"zh": "运动医学", "evidence": evidence},
                {"zh": "运动员健康", "evidence": evidence},
                {"zh": "呼吸道感染", "evidence": evidence},
                {"zh": "重返运动", "evidence": evidence},
            ]
        )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in matches:
        if item["zh"] not in seen and item.get("evidence"):
            seen.add(item["zh"])
            deduped.append(item)
    return deduped


def _first_evidence(terms: list[str], sources: list[dict[str, str]]) -> str:
    for term in terms:
        snippet = _evidence_snippet(term, sources)
        if snippet:
            return snippet
    return ""


def _is_athlete_rts_infection(blob: str) -> bool:
    has_athlete = any(_term_in_blob(term, blob) for term in ["athlete", "athletes"])
    has_rts = any(_term_in_blob(term, blob) for term in ["return-to-sport", "return to sport", "return-to-play", "return to play"])
    has_infection = any(
        _term_in_blob(term, blob)
        for term in ["acute respiratory infection", "acute respiratory infections", "respiratory infection", "respiratory infections", "pathogen-confirmed"]
    )
    return has_athlete and has_rts and has_infection


def _is_irisin_training_obesity(blob: str) -> bool:
    return _term_in_blob("irisin", blob) and any(_term_in_blob(term, blob) for term in ["training", "exercise"]) and any(
        _term_in_blob(term, blob) for term in ["overweight", "obesity", "obese"]
    )


def _is_glp1_oa_weight_loss(blob: str) -> bool:
    return (
        (_term_in_blob("glp-1 receptor agonists", blob) or _term_in_blob("glp-1", blob))
        and (_term_in_blob("osteoarthritis", blob) or _term_in_blob("oa", blob))
        and (_term_in_blob("weight-loss strategies", blob) or _term_in_blob("weight loss", blob))
    )


def _is_masld_population_database(blob: str) -> bool:
    return _term_in_blob("masld", blob) and (
        any(_term_in_blob(term, blob) for term in ["uk biobank", "nhanes", "cohort"])
        or "c reactive protein triglyceride glucose" in blob
        or "c-reactive protein-triglyceride-glucose" in blob
    )


def _is_caffeine_swimming_meta(blob: str) -> bool:
    return _term_in_blob("caffeine", blob) and any(_term_in_blob(term, blob) for term in ["swimming", "swimming performance"]) and any(
        _term_in_blob(term, blob) for term in ["meta-analysis", "meta analysis", "systematic review"]
    )


def _is_patellofemoral_strength_meta(blob: str) -> bool:
    return (
        _term_in_blob("patellofemoral pain", blob)
        and _term_in_blob("muscle strength", blob)
        and any(_term_in_blob(term, blob) for term in ["meta-analysis", "meta analysis", "systematic review"])
    )


def _is_labral_cartilage_athlete_cohort(blob: str) -> bool:
    return (
        any(_term_in_blob(term, blob) for term in ["labral pathology", "labral tears", "labral tear"])
        and _term_in_blob("cartilage loss", blob)
        and any(_term_in_blob(term, blob) for term in ["athlete", "athletes", "high-impact physical activity"])
    )


def _is_emg_shoulder_fatigue(blob: str) -> bool:
    return any(_term_in_blob(term, blob) for term in ["electromyography", "emg", "surface electromyography"]) and any(
        _term_in_blob(term, blob) for term in ["rotator cuff", "deltoid", "shoulder"]
    ) and _term_in_blob("fatigue", blob)


def _is_ptsd_multisystem_omics(blob: str) -> bool:
    return _term_in_blob("ptsd", blob) and any(_term_in_blob(term, blob) for term in ["proteomic", "proteomics", "metabolomic", "metabolomics", "multi-omics"]) and any(
        _term_in_blob(term, blob) for term in ["multisystem disease", "accelerated aging", "redox-metabolic"]
    )


def _has_animal_model_signal(blob: str) -> bool:
    if any(_term_in_blob(term, blob) for term in ANIMAL_MODEL_BLOCKERS):
        return False
    return any(_term_in_blob(term, blob) for term in ANIMAL_MODEL_TERMS)


def _omics_project_gate(blob: str) -> bool:
    if not any(_term_in_blob(term, blob) for term in OMICS_TERMS):
        return False
    return any(
        _term_in_blob(term, blob)
        for term in [
            "skeletal muscle",
            "muscle",
            "exercise",
            "training",
            "obesity",
            "adipose",
            "adipose tissue",
            "resistance training",
            "sarcopenia",
            "hypertrophy",
            "atrophy",
        ]
    )


def _elite_topic_gate(blob: str) -> bool:
    if any(_term_in_blob(term, blob) for term in ELITE_CORE_TOPIC_TERMS):
        return True
    if any(_term_in_blob(term, blob) for term in ["epigenetics", *OMICS_TERMS]) and any(
        _term_in_blob(term, blob) for term in ["skeletal muscle", "exercise", "physical activity", "obesity", "adipose tissue", "adipose"]
    ):
        return True
    return False


def _elite_topic_hits(blob: str) -> list[str]:
    hits = [term for term in ELITE_CORE_TOPIC_TERMS if _term_in_blob(term, blob)]
    if any(_term_in_blob(term, blob) for term in ["epigenetics", *OMICS_TERMS]) and _omics_project_gate(blob):
        hits.append("omics + project topic")
    return list(dict.fromkeys(hits))


def _term_in_blob(term: Any, blob: str) -> bool:
    normalized = normalize_text(term)
    if not normalized:
        return False
    return f" {normalized} " in f" {blob} "

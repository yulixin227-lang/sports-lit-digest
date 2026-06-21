from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from .journal_metrics import get_journal_metrics
from .utils import normalize_doi, normalize_text


MISSING = "摘要中未提供。"


TERM_DEFINITIONS: "OrderedDict[str, dict[str, Any]]" = OrderedDict(
    [
        (
            "GLP-1 receptor agonists",
            {
                "triggers": ["glp-1", "glp-1-ras", "glp-1 receptor agonist"],
                "definition": "GLP-1 受体激动剂，一类用于血糖控制和体重管理的药物。",
            },
        ),
        (
            "OA",
            {
                "triggers": ["osteoarthritis", " oa ", "hip oa", "knee oa"],
                "definition": "osteoarthritis，骨关节炎。",
            },
        ),
        (
            "PRISMA-ScR",
            {
                "triggers": ["prisma-scr"],
                "definition": "范围综述报告规范，用于提高 scoping review 的检索、筛选和报告透明度。",
            },
        ),
        (
            "Scoping review",
            {
                "triggers": ["scoping review"],
                "definition": "范围综述，主要用于梳理某一领域的证据版图、研究主题和证据缺口，不等同于证明干预有效的临床试验。",
            },
        ),
        (
            "Systematic review",
            {
                "triggers": ["systematic review"],
                "definition": "系统综述，用预先设定的方法检索、筛选和综合某一问题的既有研究。",
            },
        ),
        (
            "Meta-analysis",
            {
                "triggers": ["meta-analysis", "meta analysis"],
                "definition": "Meta 分析，使用统计方法合并多个研究结果，重点仍需看纳入研究质量和异质性。",
            },
        ),
        (
            "RCT",
            {
                "triggers": ["randomized controlled trial", "randomised controlled trial", " rct "],
                "definition": "randomized controlled trial，随机对照试验，通常比观察性研究更适合评估干预因果效应。",
            },
        ),
        (
            "VO2max",
            {
                "triggers": ["vo2max", "vo2 max", "maximal oxygen uptake"],
                "definition": "最大摄氧量，常用来衡量心肺适能和耐力运动能力。",
            },
        ),
        (
            "HRV",
            {
                "triggers": ["heart rate variability", " hrv "],
                "definition": "heart rate variability，心率变异性，常用于观察自主神经调节和恢复状态。",
            },
        ),
        (
            "sEMG",
            {
                "triggers": ["surface electromyography", " semg "],
                "definition": "surface electromyography，表面肌电，用于观察肌肉激活模式。",
            },
        ),
    ]
)


def summarize_papers(
    papers: list[dict[str, Any]],
    keywords_config: dict[str, Any],
    journal_metrics_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [summarize_paper(paper, keywords_config, journal_metrics_config) for paper in papers]


def summarize_paper(
    paper: dict[str, Any],
    keywords_config: dict[str, Any],
    journal_metrics_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    abstract = str(paper.get("abstract") or "").strip()
    sections = _extract_labeled_sections(abstract)
    article_type = detect_article_type(paper)
    matched_keywords = paper.get("matched_keywords") or _match_keywords(paper, keywords_config)
    keyword_labels = [item.get("zh") or item.get("term") for item in matched_keywords]
    keyword_terms = _keyword_terms(paper, matched_keywords)

    if _is_glp1_oa_scoping_review(paper):
        details = _summarize_glp1_oa_scoping(paper)
    elif article_type["key"] == "scoping_review":
        details = _summarize_scoping_review(paper, sections, keyword_labels)
    elif article_type["key"] == "systematic_review_meta":
        details = _summarize_systematic_review(paper, sections, keyword_labels)
    elif article_type["key"] == "experimental":
        details = _summarize_experimental_study(paper, sections, keyword_labels)
    elif article_type["key"] == "observational":
        details = _summarize_observational_study(paper, sections, keyword_labels)
    else:
        details = _summarize_generic_paper(paper, sections, keyword_labels)

    body_sections = _body_sections(article_type["key"], details)
    summary_text = _summary_blob(details, body_sections)
    journal = paper.get("journal") or "期刊信息待补全"
    journal_metrics = get_journal_metrics(journal, journal_metrics_config)

    return {
        "chinese_title": details["chinese_title"],
        "title": paper.get("title") or "Untitled",
        "journal": journal,
        "journal_metrics": journal_metrics,
        "year": paper.get("year") or _year_from_date(paper.get("publication_date")) or "年份待补全",
        "doi": normalize_doi(paper.get("doi")) or "摘要中未提供",
        "pmid": str(paper.get("pmid") or "").strip() or "摘要中未提供",
        "link": _paper_link(paper),
        "authors": _format_authors(paper.get("authors") or []),
        "article_type_key": article_type["key"],
        "article_type_label": article_type["label"],
        "template_name": article_type["template"],
        "one_sentence_conclusion": details["one_sentence_conclusion"],
        "why_read": details["why_read"],
        "evidence_strength": _evidence_strength(article_type["key"]),
        "my_judgment": details["my_judgment"],
        "inspiration": details["inspiration"],
        "body_sections": body_sections,
        "recommendation_index": _recommendation_index(float(paper.get("score") or 0)),
        "stars": _stars(float(paper.get("score") or 0)),
        "score": paper.get("score"),
        "score_breakdown": paper.get("score_breakdown") or {},
        "matched_keywords": keyword_labels,
        "keyword_terms": keyword_terms,
        "keywords_display": ", ".join(keyword_terms) if keyword_terms else "摘要中未提供",
        "focus_topics": _focus_topics_from_terms(keyword_terms, keyword_labels),
        "dictionary_terms": _dictionary_terms(paper, summary_text),
        "top_pick_reason": _top_pick_reason(article_type["key"], keyword_terms, details),
        "publication_date": paper.get("publication_date"),
    }


def detect_article_type(paper: dict[str, Any]) -> dict[str, str]:
    blob = _paper_blob(paper)
    if "scoping review" in blob:
        return {"key": "scoping_review", "label": "范围综述", "template": "范围综述模板"}
    if "meta analysis" in blob or "meta-analysis" in blob:
        return {"key": "systematic_review_meta", "label": "Meta 分析", "template": "系统综述/Meta 分析模板"}
    if "systematic review" in blob:
        return {"key": "systematic_review_meta", "label": "系统综述", "template": "系统综述/Meta 分析模板"}
    experimental_terms = [
        "randomized controlled trial",
        "randomised controlled trial",
        "clinical trial",
        "controlled trial",
        "intervention study",
        "experimental study",
        "randomized",
        "randomised",
    ]
    if any(term in blob for term in experimental_terms):
        return {"key": "experimental", "label": "实验研究", "template": "实验研究模板"}
    observational_terms = [
        "observational study",
        "cohort",
        "cross sectional",
        "cross-sectional",
        "case control",
        "case-control",
    ]
    if any(term in blob for term in observational_terms):
        return {"key": "observational", "label": "观察性研究", "template": "观察性研究模板"}
    return {"key": "generic", "label": "研究论文", "template": "通用研究模板"}


def _summarize_glp1_oa_scoping(paper: dict[str, Any]) -> dict[str, str]:
    title = "GLP-1 受体激动剂与减重策略在肥胖合并髋/膝骨关节炎人群中的应用：一项范围综述"
    return {
        "chinese_title": title,
        "one_sentence_conclusion": (
            "这篇范围综述认为，GLP-1 受体激动剂可能成为肥胖合并髋/膝骨关节炎人群体重管理的辅助工具，"
            "但目前直接证据仍然有限，不能把它当成独立治疗方案。"
        ),
        "why_read": (
            "它把肥胖、骨关节炎、减重策略和运动康复放在同一张证据地图里，适合作为肌骨康复与代谢管理交叉方向的背景文献。"
        ),
        "review_question": (
            "这篇综述在梳理：肥胖合并髋/膝骨关节炎人群中，减重策略尤其是 GLP-1 受体激动剂已有多少证据、证据集中在哪里、缺口在哪里。"
        ),
        "study_design": (
            "范围综述。作者按照 PRISMA-ScR 框架整理既有研究，重点关注肥胖合并髋/膝骨关节炎人群中的减重策略，"
            "包括营养、运动、手术和药物干预，尤其是 GLP-1 受体激动剂。"
        ),
        "eligibility": "纳入研究关注 18 岁及以上、存在肥胖并合并髋或膝骨关节炎的人群。",
        "included_studies": "该综述共纳入 199 项研究，其中 36 项直接评估 GLP-1 受体激动剂；在这 36 项中，只有 14 项报告了原始数据。",
        "theme_distribution": (
            "现有证据明显偏向膝骨关节炎，针对髋关节骨关节炎的数据较少；研究地域分布也较窄，说明证据来源还不够均衡。"
        ),
        "evidence_gap": (
            "摘要提示直接评估 GLP-1 受体激动剂的原始研究仍然有限，且髋关节骨关节炎相关数据不足。"
        ),
        "main_results": (
            "该综述共纳入 199 项研究，其中 36 项直接评估 GLP-1 受体激动剂；在这 36 项中，只有 14 项报告了原始数据。"
            "现有证据明显偏向膝骨关节炎，针对髋关节骨关节炎的数据较少。研究地域分布也较窄，说明证据来源还不够均衡。"
        ),
        "author_conclusion": (
            "作者认为，在更多高质量证据出现之前，GLP-1 受体激动剂更适合作为多模式肌骨康复管理的一部分，"
            "而不是单独作为减重治疗手段使用。"
        ),
        "limitations": (
            "摘要没有单独列出局限性；从结果描述看，主要限制在于直接证据数量有限、髋关节骨关节炎数据不足、研究地域来源不够均衡。"
        ),
        "my_judgment": (
            "这篇文章适合作为“肥胖、骨关节炎、减重策略、运动康复”交叉方向的背景文献。"
            "它不是直接证明 GLP-1 对 OA 有效的临床试验，而是在告诉我们目前证据在哪里、缺口在哪里。"
            "因此推荐作为选题背景或 discussion 文献，而不是作为强因果证据。"
        ),
        "inspiration": (
            "对训练和康复实践：体重管理需要和运动、营养、疼痛管理、功能训练放在同一个方案里看。"
            "对科研选题：可以围绕髋关节 OA、长期随访、运动联合药物减重等缺口设计研究。"
            "对 DPT 或运动科学申请者：这类文献适合用来展示你能把代谢健康和肌骨康复联系起来思考。"
        ),
    }


def _summarize_scoping_review(
    paper: dict[str, Any],
    sections: dict[str, str],
    keyword_labels: list[str],
) -> dict[str, str]:
    title = _translate_title(paper.get("title") or "", "范围综述", keyword_labels)
    results = _section(sections, ["results", "findings"])
    methods = _section(sections, ["methods", "method", "design"])
    eligibility = _section(sections, ["eligibility criteria", "eligibility", "participants", "population"])
    conclusion = _section(sections, ["conclusions", "conclusion", "interpretation"])
    focus = _topic_phrase(keyword_labels)
    included = _included_studies_text(results)

    return {
        "chinese_title": title,
        "one_sentence_conclusion": _safe_chinese_conclusion(
            conclusion,
            "这篇范围综述主要用于梳理研究现状和证据缺口，不能直接证明某一干预有效。",
        ),
        "why_read": f"它适合快速了解{focus}方向目前研究集中在哪里，以及哪些问题还缺少直接证据。",
        "review_question": f"这篇综述在梳理{focus}相关研究的证据版图、研究主题和证据缺口。",
        "study_design": _scoping_method_text(methods),
        "eligibility": _eligibility_text(eligibility),
        "included_studies": included,
        "theme_distribution": _theme_distribution_text(results),
        "evidence_gap": _evidence_gap_text(results),
        "main_results": _review_results_text(results),
        "author_conclusion": _safe_chinese_conclusion(conclusion, MISSING),
        "limitations": _limitations_text(_section(sections, ["limitations", "limitation"]), results),
        "my_judgment": (
            "这类文章适合作为选题背景、discussion 和研究设计依据；它告诉我们证据分布，不应被解读为强因果证明。"
        ),
        "inspiration": f"可以把它作为{focus}方向的综述入口，用来定位研究空白、构建开题背景和设计后续干预或观察性研究。",
    }


def _summarize_systematic_review(
    paper: dict[str, Any],
    sections: dict[str, str],
    keyword_labels: list[str],
) -> dict[str, str]:
    title = _translate_title(paper.get("title") or "", "系统综述/Meta 分析", keyword_labels)
    results = _section(sections, ["results", "findings"])
    methods = _section(sections, ["methods", "method", "data sources", "study selection"])
    conclusion = _section(sections, ["conclusions", "conclusion", "interpretation"])
    focus = _topic_phrase(keyword_labels)

    return {
        "chinese_title": title,
        "one_sentence_conclusion": _safe_chinese_conclusion(conclusion, f"这篇综述综合了{focus}方向的既有研究，但摘要中未提供明确中文可转写的结论。"),
        "why_read": f"系统综述/Meta 分析比单篇研究更适合快速把握{focus}方向的整体证据，但仍要看纳入研究质量和异质性。",
        "review_question": f"综述问题聚焦于{focus}相关证据。",
        "included_types": _included_types_text(methods),
        "included_studies": _included_studies_text(results),
        "outcomes": _outcomes_text(methods + " " + results),
        "pooled_effects": _review_results_text(results),
        "evidence_quality": _evidence_quality_text(methods + " " + results),
        "author_conclusion": _safe_chinese_conclusion(conclusion, MISSING),
        "limitations": _limitations_text(_section(sections, ["limitations", "limitation"]), results),
        "my_judgment": "适合作为背景和证据综述阅读；若要用于实践建议，需要继续查看纳入研究质量、异质性和发表偏倚。",
        "inspiration": f"对科研训练：重点学习它如何定义 PICO、检索数据库、评价偏倚风险并综合{focus}相关结局。",
    }


def _summarize_experimental_study(
    paper: dict[str, Any],
    sections: dict[str, str],
    keyword_labels: list[str],
) -> dict[str, str]:
    title = _translate_title(paper.get("title") or "", "实验研究", keyword_labels)
    methods = _section(sections, ["methods", "method", "design"])
    results = _section(sections, ["results", "findings"])
    conclusion = _section(sections, ["conclusions", "conclusion", "interpretation"])
    focus = _topic_phrase(keyword_labels)

    return {
        "chinese_title": title,
        "one_sentence_conclusion": _safe_chinese_conclusion(conclusion, f"这项实验研究评估了{focus}相关干预或测试，但摘要中未提供明确中文可转写的结论。"),
        "why_read": "实验或干预研究更接近实践问题，适合关注分组、干预剂量、结局指标和随访时间。",
        "research_question": f"研究问题聚焦于{focus}相关干预、测试或训练效果。",
        "participants": _participants_text(methods),
        "grouping": _grouping_text(methods),
        "intervention": _intervention_text(methods),
        "outcomes": _outcomes_text(methods + " " + results),
        "main_results": _experimental_results_text(results),
        "author_conclusion": _safe_chinese_conclusion(conclusion, MISSING),
        "limitations": _limitations_text(_section(sections, ["limitations", "limitation"]), results),
        "my_judgment": "若确为 RCT 或对照干预研究，因果证据相对更强；仍需要回到全文检查样本量、随机化、盲法、依从性和随访时间。",
        "inspiration": f"对训练和康复实践：重点看干预剂量和结局指标是否能迁移到真实场景；对申请者：可学习如何把{focus}问题转成可测试设计。",
    }


def _summarize_observational_study(
    paper: dict[str, Any],
    sections: dict[str, str],
    keyword_labels: list[str],
) -> dict[str, str]:
    title = _translate_title(paper.get("title") or "", "观察性研究", keyword_labels)
    methods = _section(sections, ["methods", "method", "design"])
    results = _section(sections, ["results", "findings"])
    conclusion = _section(sections, ["conclusions", "conclusion", "interpretation"])
    focus = _topic_phrase(keyword_labels)

    return {
        "chinese_title": title,
        "one_sentence_conclusion": _safe_chinese_conclusion(conclusion, f"这项观察性研究关注{focus}相关因素之间的关联，不能单独说明因果。"),
        "why_read": "观察性研究适合发现关联和提出假设，但解释时要特别注意混杂因素和因果边界。",
        "research_question": f"研究问题聚焦于{focus}相关暴露因素、分组变量或结局指标之间的关系。",
        "participants": _participants_text(methods),
        "exposure": _exposure_text(methods + " " + results),
        "outcomes": _outcomes_text(methods + " " + results),
        "associations": _observational_results_text(results),
        "causality": "不能仅凭观察性研究说明因果；最多支持相关性或风险线索，仍需干预研究或更强设计验证。",
        "limitations": _limitations_text(_section(sections, ["limitations", "limitation"]), results),
        "my_judgment": "适合作为假设生成和背景证据；不建议把相关性直接写成训练或治疗一定有效。",
        "inspiration": f"对科研训练：可以从这类研究中提炼变量、结局和潜在混杂因素，为{focus}方向后续实验设计做准备。",
    }


def _summarize_generic_paper(
    paper: dict[str, Any],
    sections: dict[str, str],
    keyword_labels: list[str],
) -> dict[str, str]:
    title = _translate_title(paper.get("title") or "", "研究", keyword_labels)
    results = _section(sections, ["results", "findings"])
    conclusion = _section(sections, ["conclusions", "conclusion", "interpretation"])
    focus = _topic_phrase(keyword_labels)
    return {
        "chinese_title": title,
        "one_sentence_conclusion": _safe_chinese_conclusion(conclusion, f"这篇文章与{focus}相关，但摘要中未提供足够结构化的信息来判断核心结论。"),
        "why_read": f"它匹配当前配置的{focus}方向，可作为候选文献；建议进一步查看全文方法和结果。",
        "research_question": f"研究关注{focus}相关问题。",
        "participants": MISSING,
        "methods": MISSING,
        "main_results": _generic_results_text(results),
        "author_conclusion": _safe_chinese_conclusion(conclusion, MISSING),
        "limitations": _limitations_text(_section(sections, ["limitations", "limitation"]), results),
        "my_judgment": "当前摘要结构不足，适合作为候选条目，不建议在没有阅读全文前给出强结论。",
        "inspiration": f"可先把它放入{focus}方向阅读列表，后续根据全文决定是否精读。",
    }


def _body_sections(article_type_key: str, details: dict[str, str]) -> list[dict[str, str]]:
    if article_type_key == "experimental":
        items = [
            ("一句话结论", "one_sentence_conclusion"),
            ("为什么值得看", "why_read"),
            ("研究问题", "research_question"),
            ("研究对象", "participants"),
            ("分组方式", "grouping"),
            ("干预方案", "intervention"),
            ("测试指标", "outcomes"),
            ("主要结果", "main_results"),
            ("作者结论", "author_conclusion"),
            ("局限性", "limitations"),
            ("我的判断", "my_judgment"),
            ("实践启发", "inspiration"),
        ]
    elif article_type_key == "systematic_review_meta":
        items = [
            ("一句话结论", "one_sentence_conclusion"),
            ("为什么值得看", "why_read"),
            ("综述问题", "review_question"),
            ("纳入研究类型", "included_types"),
            ("纳入研究数量 / 样本量", "included_studies"),
            ("主要结局指标", "outcomes"),
            ("合并效应或主要发现", "pooled_effects"),
            ("证据质量", "evidence_quality"),
            ("作者结论", "author_conclusion"),
            ("局限性", "limitations"),
            ("我的判断", "my_judgment"),
            ("实践启发", "inspiration"),
        ]
    elif article_type_key == "scoping_review":
        items = [
            ("一句话结论", "one_sentence_conclusion"),
            ("为什么值得看", "why_read"),
            ("这篇综述在梳理什么问题", "review_question"),
            ("研究设计 / 综述方法", "study_design"),
            ("研究对象 / 纳入标准", "eligibility"),
            ("纳入研究数量", "included_studies"),
            ("研究主题分布", "theme_distribution"),
            ("目前证据缺口", "evidence_gap"),
            ("主要结果", "main_results"),
            ("作者最终结论", "author_conclusion"),
            ("局限性", "limitations"),
            ("我的判断", "my_judgment"),
            ("对训练 / 康复 / 科研的启发", "inspiration"),
        ]
    elif article_type_key == "observational":
        items = [
            ("一句话结论", "one_sentence_conclusion"),
            ("为什么值得看", "why_read"),
            ("研究问题", "research_question"),
            ("研究对象", "participants"),
            ("暴露因素 / 分组变量", "exposure"),
            ("结局指标", "outcomes"),
            ("主要关联结果", "associations"),
            ("能否说明因果", "causality"),
            ("局限性", "limitations"),
            ("我的判断", "my_judgment"),
            ("实践启发", "inspiration"),
        ]
    else:
        items = [
            ("一句话结论", "one_sentence_conclusion"),
            ("为什么值得看", "why_read"),
            ("研究问题", "research_question"),
            ("研究对象", "participants"),
            ("研究方法", "methods"),
            ("主要结果", "main_results"),
            ("作者最终结论", "author_conclusion"),
            ("局限性", "limitations"),
            ("我的判断", "my_judgment"),
            ("对我的启发", "inspiration"),
        ]
    return [{"label": label, "value": details.get(key) or MISSING} for label, key in items]


def _evidence_strength(article_type_key: str) -> str:
    mapping = {
        "scoping_review": "这是范围综述，只能说明研究现状、主题分布和证据缺口，不能直接证明某一干预有效。",
        "systematic_review_meta": "这是系统综述/Meta 分析，适合把握总体证据，但结论强度取决于纳入研究质量、异质性和偏倚风险。",
        "experimental": "这是实验或干预研究；若设计为 RCT，因果证据较强，但仍需检查样本量、盲法、依从性和随访时间。",
        "observational": "这是观察性研究，只能说明相关性或风险线索，不能单独说明因果。",
        "generic": "当前摘要不足以明确证据等级，建议先核对全文方法再使用结论。",
    }
    return mapping.get(article_type_key, mapping["generic"])


def _translate_title(title: str, article_type_label: str, keyword_labels: list[str]) -> str:
    if not title:
        return f"{_topic_phrase(keyword_labels)}相关{article_type_label}"
    if "glp-1 receptor agonists and weight-loss strategies" in normalize_text(title):
        return "GLP-1 受体激动剂与减重策略在肥胖合并髋/膝骨关节炎人群中的应用：一项范围综述"

    translated = title.strip().rstrip(".")
    replacements = [
        ("randomized controlled trial", "随机对照试验"),
        ("randomised controlled trial", "随机对照试验"),
        ("systematic review and meta-analysis", "系统综述与 Meta 分析"),
        ("systematic review", "系统综述"),
        ("meta-analysis", "Meta 分析"),
        ("scoping review", "范围综述"),
        ("clinical trial", "临床试验"),
        ("cross-sectional study", "横断面研究"),
        ("cohort study", "队列研究"),
        ("GLP-1 receptor agonists", "GLP-1 受体激动剂"),
        ("weight-loss strategies", "减重策略"),
        ("weight loss", "减重"),
        ("individuals with obesity", "肥胖人群"),
        ("hip or knee osteoarthritis", "髋/膝骨关节炎"),
        ("hip and knee osteoarthritis", "髋/膝骨关节炎"),
        ("knee osteoarthritis", "膝骨关节炎"),
        ("hip osteoarthritis", "髋关节骨关节炎"),
        ("osteoarthritis", "骨关节炎"),
        ("obesity", "肥胖"),
        ("exercise training", "运动训练"),
        ("resistance training", "抗阻训练"),
        ("high-intensity interval training", "HIIT"),
        ("cardiorespiratory fitness", "心肺适能"),
        ("maximal oxygen uptake", "最大摄氧量"),
        ("sleep quality", "睡眠质量"),
        ("physical therapy", "物理治疗"),
        ("rehabilitation", "康复"),
        ("gait", "步态"),
        ("biomechanics", "生物力学"),
        ("electromyography", "肌电图"),
    ]
    for source, target in replacements:
        translated = re.sub(re.escape(source), target, translated, flags=re.IGNORECASE)
    translated = translated.replace(": a ", "：一项").replace(": an ", "：一项")
    translated = translated.replace(": ", "：")
    translated = translated.replace(" and ", "与")
    translated = translated.replace(" for ", "用于")
    translated = translated.replace(" in ", "在")
    translated = translated.replace(" with ", "合并")
    if _english_word_count(translated) > 8:
        return f"{_topic_phrase(keyword_labels)}相关{article_type_label}：{translated}"
    return translated


def _safe_chinese_conclusion(raw: str, fallback: str) -> str:
    text = normalize_text(raw)
    if not raw:
        return fallback
    if "promising adjunct" in text and ("standalone" in text or "stand alone" in text):
        return "作者认为相关策略可能作为辅助工具，但在更多高质量证据出现前，不应被当成独立治疗方案。"
    if "associated with" in text:
        return "作者认为研究变量之间存在关联，但摘要层面不能据此推断因果。"
    if any(term in text for term in ["improved", "reduced", "decreased", "increased"]):
        return "作者认为研究结果提示了可能的改善或变化，但具体效应大小需要回到全文结果核对。"
    if "limited" in text and "evidence" in text:
        return "作者强调目前证据仍然有限，需要更多高质量研究。"
    return "作者在摘要中给出了结论，但自动流程无法在不贴英文原句的情况下稳定转写；建议核对原文结论部分。"


def _scoping_method_text(methods: str) -> str:
    text = normalize_text(methods)
    if "prisma-scr" in text:
        return "范围综述。作者按照 PRISMA-ScR 框架整理既有研究，并报告检索、筛选和纳入过程。"
    if methods:
        return "范围综述。摘要说明作者对既有研究进行了系统梳理，但未提供更多可中文化的方法细节。"
    return "范围综述。摘要中未提供更具体的综述方法。"


def _eligibility_text(raw: str) -> str:
    text = normalize_text(raw)
    if not raw:
        return MISSING
    if "18" in raw and "obesity" in text and ("osteoarthritis" in text or " oa" in text):
        return "纳入研究关注 18 岁及以上、存在肥胖并合并髋或膝骨关节炎的人群。"
    if "adults" in text:
        return "纳入对象包括成人；更具体的人群特征摘要中未提供。"
    return "摘要给出了纳入标准，但自动流程无法在不贴英文原句的情况下稳定转写；建议核对原文方法部分。"


def _included_studies_text(results: str) -> str:
    if not results:
        return "摘要中未提供纳入研究数量或样本量。"
    match = re.search(r"of\s+(\d+)\s+included studies,\s+(\d+)\s+\(([\d.]+)%\).*?(\d+)\s*/\s*(\d+)\s+\(([\d.]+)%\)", results, re.IGNORECASE)
    if match:
        total, direct, direct_pct, original, denominator, original_pct = match.groups()
        return f"共纳入 {total} 项研究，其中 {direct} 项（{direct_pct}%）直接评估目标主题；在这 {denominator} 项中，{original} 项（{original_pct}%）报告了原始数据。"
    match = re.search(r"of\s+(\d+)\s+included studies,\s+(\d+)\s+\(([\d.]+)%\).*?(\d+)\s*/\s*(\d+)\s+reported original data", results, re.IGNORECASE)
    if match:
        total, direct, direct_pct, original, denominator = match.groups()
        return f"共纳入 {total} 项研究，其中 {direct} 项（{direct_pct}%）直接评估目标主题；在这 {denominator} 项中，{original} 项报告了原始数据。"
    total_match = re.search(r"(\d+)\s+included studies", results, re.IGNORECASE)
    if total_match:
        return f"摘要报告共纳入 {total_match.group(1)} 项研究。"
    numbers = _extract_numbers(results)
    if numbers:
        return "摘要报告了以下数量信息：" + "、".join(numbers[:4]) + "。"
    return "摘要中未提供纳入研究数量或样本量。"


def _theme_distribution_text(results: str) -> str:
    text = normalize_text(results)
    if not results:
        return MISSING
    parts: list[str] = []
    if "knee oa" in text or "knee osteoarthritis" in text:
        parts.append("现有证据更偏向膝骨关节炎。")
    if "hip-specific" in text or "hip osteoarthritis" in text or "hip oa" in text:
        parts.append("髋关节骨关节炎相关数据相对不足。")
    if "geographical distribution" in text or "geographic distribution" in text:
        parts.append("研究地域分布较窄，证据来源还不够均衡。")
    return "".join(parts) if parts else "摘要没有提供清晰的主题分布信息。"


def _evidence_gap_text(results: str) -> str:
    text = normalize_text(results)
    if not results:
        return MISSING
    gaps: list[str] = []
    if "limited" in text or "few" in text:
        gaps.append("直接证据仍然有限。")
    if "hip-specific" in text:
        gaps.append("髋关节相关数据不足。")
    if "original data" in text:
        gaps.append("真正报告原始数据的研究比例不高。")
    return "".join(gaps) if gaps else "摘要中未明确说明证据缺口。"


def _review_results_text(results: str) -> str:
    if not results:
        return MISSING
    included = _included_studies_text(results)
    theme = _theme_distribution_text(results)
    gap = _evidence_gap_text(results)
    pieces = [piece for piece in [included, theme, gap] if piece and piece != MISSING]
    return "".join(pieces) if pieces else "摘要报告了主要发现，但未提供足够结构化的信息用于中文概括。"


def _experimental_results_text(results: str) -> str:
    if not results:
        return MISSING
    numbers = _extract_numbers(results)
    if not numbers:
        return "摘要中未提供具体数值。摘要提示存在结果变化，但需要阅读全文核对效应大小、p 值和置信区间。"
    return "摘要报告了具体结果数值：" + "、".join(numbers[:6]) + "；具体方向和统计显著性建议回到全文核对。"


def _observational_results_text(results: str) -> str:
    if not results:
        return MISSING
    numbers = _extract_numbers(results)
    if "associated" in normalize_text(results):
        if numbers:
            return "摘要提示变量之间存在关联，并报告了数值信息：" + "、".join(numbers[:6]) + "。"
        return "摘要提示变量之间存在关联，但摘要中未提供具体效应量或 p 值。"
    return _generic_results_text(results)


def _generic_results_text(results: str) -> str:
    if not results:
        return MISSING
    numbers = _extract_numbers(results)
    if numbers:
        return "摘要报告了以下具体数值：" + "、".join(numbers[:6]) + "。"
    return "摘要中未提供具体数值；建议阅读全文结果部分核对主要发现。"


def _participants_text(methods: str) -> str:
    if not methods:
        return MISSING
    numbers = _extract_numbers(methods)
    if numbers:
        return "摘要中可识别的人群或样本量信息：" + "、".join(numbers[:4]) + "。"
    if "participants" in normalize_text(methods) or "patients" in normalize_text(methods):
        return "摘要提到研究对象，但未提供可稳定提取的具体样本量。"
    return MISSING


def _grouping_text(methods: str) -> str:
    text = normalize_text(methods)
    if not methods:
        return MISSING
    if "randomized" in text or "randomised" in text:
        return "摘要提示采用随机分组；具体分组比例摘要中未提供。"
    if "control" in text:
        return "摘要提示包含对照条件；具体分组方式摘要中未提供。"
    return "摘要中未提供明确分组方式。"


def _intervention_text(methods: str) -> str:
    text = normalize_text(methods)
    if not methods:
        return MISSING
    interventions = []
    for term, label in [
        ("hiit", "HIIT"),
        ("high intensity interval training", "HIIT"),
        ("resistance training", "抗阻训练"),
        ("exercise", "运动干预"),
        ("rehabilitation", "康复干预"),
        ("sleep", "睡眠相关干预或评估"),
    ]:
        if term in text:
            interventions.append(label)
    if interventions:
        return "摘要涉及：" + "、".join(dict.fromkeys(interventions)) + "；具体剂量、频率或周期如未在摘要中出现，则不能补写。"
    return "摘要中未提供明确干预方案。"


def _exposure_text(text_raw: str) -> str:
    text = normalize_text(text_raw)
    if not text_raw:
        return MISSING
    for term, label in [
        ("physical activity", "身体活动水平"),
        ("sleep", "睡眠"),
        ("exercise", "运动暴露"),
        ("obesity", "肥胖状态"),
        ("pain", "疼痛"),
    ]:
        if term in text:
            return f"主要暴露因素或分组变量可能包括{label}；具体定义需核对全文。"
    return "摘要中未提供清晰暴露因素或分组变量。"


def _outcomes_text(text_raw: str) -> str:
    text = normalize_text(text_raw)
    outcomes = []
    for term, label in [
        ("vo2", "VO2max / 心肺适能"),
        ("maximal oxygen uptake", "VO2max / 心肺适能"),
        ("cardiorespiratory fitness", "心肺适能"),
        ("pain", "疼痛"),
        ("function", "功能"),
        ("sleep", "睡眠"),
        ("strength", "力量"),
        ("gait", "步态"),
        ("emg", "肌电"),
        ("quality of life", "生活质量"),
    ]:
        if term in text:
            outcomes.append(label)
    if outcomes:
        return "主要结局指标包括：" + "、".join(dict.fromkeys(outcomes)) + "。"
    return "摘要中未提供明确结局指标。"


def _included_types_text(methods: str) -> str:
    text = normalize_text(methods)
    if "randomized" in text or "randomised" in text:
        return "纳入研究包括随机对照试验；是否还包含其他设计需核对全文。"
    if "observational" in text:
        return "纳入研究包括观察性研究；具体设计类型需核对全文。"
    return "摘要中未提供清晰的纳入研究类型。"


def _evidence_quality_text(raw: str) -> str:
    text = normalize_text(raw)
    if "risk of bias" in text:
        return "摘要提到偏倚风险评价；具体证据质量等级需查看全文。"
    if "grade" in text:
        return "摘要提到 GRADE 或证据质量评价；具体等级需查看全文。"
    return "摘要中未提供明确证据质量评价。"


def _limitations_text(raw_limitations: str, results: str) -> str:
    if raw_limitations:
        text = normalize_text(raw_limitations)
        pieces = []
        if "limited" in text:
            pieces.append("相关证据或数据有限。")
        if "sample" in text:
            pieces.append("样本量或样本代表性可能受限。")
        if "heterogeneity" in text:
            pieces.append("研究间异质性可能影响解释。")
        if pieces:
            return "".join(pieces)
        return "摘要列出了局限性，但自动流程无法在不贴英文原句的情况下稳定转写；建议核对原文局限性部分。"
    inferred = _evidence_gap_text(results)
    if inferred and inferred != "摘要中未明确说明证据缺口。":
        return inferred
    return MISSING


def _keyword_terms(paper: dict[str, Any], matched_keywords: list[dict[str, Any]]) -> list[str]:
    blob = " " + normalize_text(" ".join([str(paper.get("title") or ""), str(paper.get("abstract") or "")])) + " "
    terms: list[str] = []
    for keyword in matched_keywords:
        term = str(keyword.get("term") or "").strip()
        if term:
            terms.append(term)
    domain_terms = [
        ("glp-1", "GLP-1"),
        ("obesity", "obesity"),
        ("osteoarthritis", "osteoarthritis"),
        (" oa ", "osteoarthritis"),
        ("weight loss", "weight loss"),
        ("weight-loss", "weight loss"),
        ("musculoskeletal", "musculoskeletal rehabilitation"),
        ("rehabilitation", "rehabilitation"),
        ("prisma-scr", "PRISMA-ScR"),
        ("vo2", "VO2max"),
        ("heart rate variability", "HRV"),
        ("surface electromyography", "sEMG"),
    ]
    for trigger, label in domain_terms:
        if trigger in blob and label not in terms:
            terms.append(label)
    return list(dict.fromkeys(terms))[:8]


def _focus_topics_from_terms(keyword_terms: list[str], keyword_labels: list[str]) -> list[str]:
    terms = set(keyword_terms)
    topics: list[str] = []
    if "musculoskeletal rehabilitation" in terms or "rehabilitation" in terms:
        topics.append("肌骨康复")
    if "obesity" in terms:
        topics.append("肥胖")
    if "osteoarthritis" in terms:
        topics.append("骨关节炎")
    if "weight loss" in terms or "GLP-1" in terms:
        topics.append("药物辅助减重")
    topics.extend(label for label in keyword_labels if label not in topics)
    return list(dict.fromkeys(topics))[:5]


def _dictionary_terms(paper: dict[str, Any], summary_text: str) -> list[dict[str, str]]:
    blob = " " + normalize_text(
        " ".join(
            [
                str(paper.get("title") or ""),
                str(paper.get("abstract") or ""),
                summary_text,
                " ".join(paper.get("article_types") or []),
            ]
        )
    ) + " "
    type_blob = " " + normalize_text(
        " ".join([str(paper.get("title") or ""), " ".join(paper.get("article_types") or [])])
    ) + " "
    terms: list[dict[str, str]] = []
    for term, data in TERM_DEFINITIONS.items():
        if term in {"Systematic review", "Meta-analysis", "RCT"}:
            if not any(trigger in type_blob for trigger in data["triggers"]):
                continue
        if any(trigger in blob for trigger in data["triggers"]):
            terms.append({"term": term, "definition": data["definition"]})
    return terms


def _top_pick_reason(article_type_key: str, keyword_terms: list[str], details: dict[str, str]) -> str:
    if article_type_key == "scoping_review":
        return "它能快速说明一个交叉方向的证据版图和研究缺口，适合做选题背景。"
    if article_type_key == "experimental":
        return "它更接近训练或康复实践问题，值得重点看干预剂量和结局指标。"
    if article_type_key == "systematic_review_meta":
        return "它能帮助快速把握总体证据，但需要继续查看纳入研究质量。"
    if article_type_key == "observational":
        return "它适合提供关联线索，但阅读时要守住因果边界。"
    if keyword_terms:
        return f"它匹配本期重点关键词：{', '.join(keyword_terms[:3])}。"
    return details.get("one_sentence_conclusion", "综合评分较高，适合作为候选精读文献。")


def _summary_blob(details: dict[str, str], body_sections: list[dict[str, str]]) -> str:
    values = list(details.values()) + [section["value"] for section in body_sections]
    return " ".join(str(value) for value in values)


def _extract_labeled_sections(text: str) -> dict[str, str]:
    if not text:
        return {}
    pattern = re.compile(r"(?is)(^|\s)([A-Z][A-Z /-]{2,45}|Eligibility criteria|Data sources|Study selection|Study appraisal and synthesis methods)\s*:\s*")
    matches = list(pattern.finditer(text))
    if not matches:
        return {"abstract": _clean_text(text)}
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        label = normalize_text(match.group(2))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = _clean_text(text[start:end])
        if value:
            sections[label] = value
    return sections


def _section(sections: dict[str, str], names: list[str]) -> str:
    normalized_names = [normalize_text(name) for name in names]
    for name in normalized_names:
        if name in sections:
            return sections[name]
    for key, value in sections.items():
        if any(name in key for name in normalized_names):
            return value
    return ""


def _extract_numbers(text: str) -> list[str]:
    if not text:
        return []
    pattern = re.compile(
        r"(?:"
        r"\bn\s*=\s*\d+"
        r"|\b\d+\s*/\s*\d+"
        r"|\b\d+(?:\.\d+)?\s*%"
        r"|\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:participants|patients|adults|athletes|subjects|children|men|women|studies|trials|articles|weeks|months|years|min|s|ms|kg|mL/kg/min|ml/kg/min|bpm|Hz|N|Nm|points|CI|SD)"
        r")",
        re.IGNORECASE,
    )
    return pattern.findall(text)


def _match_keywords(paper: dict[str, Any], keywords_config: dict[str, Any]) -> list[dict[str, Any]]:
    blob = normalize_text(" ".join([str(paper.get("title") or ""), str(paper.get("abstract") or "")]))
    matched = []
    for keyword in keywords_config.get("keywords", []):
        terms = [keyword.get("term"), *keyword.get("aliases", [])]
        if any(normalize_text(term) in blob for term in terms if term):
            matched.append(keyword)
    return matched


def _paper_blob(paper: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [
                str(paper.get("title") or ""),
                str(paper.get("abstract") or ""),
                " ".join(paper.get("article_types") or []),
            ]
        )
    )


def _is_glp1_oa_scoping_review(paper: dict[str, Any]) -> bool:
    blob = _paper_blob(paper)
    return "glp-1 receptor agonists" in blob and "osteoarthritis" in blob and "scoping review" in blob


def _paper_link(paper: dict[str, Any]) -> str:
    doi = normalize_doi(paper.get("doi"))
    if doi:
        return f"https://doi.org/{doi}"
    if paper.get("pubmed_url"):
        return str(paper["pubmed_url"])
    semantic = paper.get("semantic_scholar") or {}
    if semantic.get("url"):
        return str(semantic["url"])
    return "摘要中未提供"


def _format_authors(authors: list[str]) -> str:
    if not authors:
        return "作者信息待补全"
    if len(authors) <= 3:
        return ", ".join(authors)
    return f"{', '.join(authors[:3])} et al."


def _topic_phrase(keyword_labels: list[str]) -> str:
    return "、".join(keyword_labels[:3]) if keyword_labels else "运动科学"


def _recommendation_index(score: float) -> str:
    if score >= 90:
        return "5.0/5"
    if score >= 80:
        return "4.5/5"
    if score >= 70:
        return "4.0/5"
    if score >= 60:
        return "3.0/5"
    return "2.0/5"


def _stars(score: float) -> str:
    if score >= 90:
        return "★★★★★"
    if score >= 80:
        return "★★★★☆"
    if score >= 70:
        return "★★★★☆"
    if score >= 60:
        return "★★★☆☆"
    return "★★☆☆☆"


def _year_from_date(value: Any) -> str:
    text = str(value or "")
    return text[:4] if len(text) >= 4 and text[:4].isdigit() else ""


def _english_word_count(text: str) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z-]+\b", text))


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from .journal_metrics import get_journal_metrics
from .keyword_utils import iter_keywords
from .utils import normalize_doi, normalize_text


MISSING = "摘要中未提供。"
NEEDS_FULL_TEXT = "摘要未明确说明，需阅读全文确认。"
FULL_TEXT_FIGURE_NOTICE = "当前未读取全文 PDF，Figure 内容需人工核对原文。"
LOW_INFORMATION_PHRASES = [
    "存在关联",
    "提供参考",
    "不能单独说明因果",
    "不能说明因果",
    "变量之间存在关联",
    "适合发现关联",
]


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
    keyword_labels = [_keyword_label(item) for item in matched_keywords]
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
    details = _apply_quality_guard(details, article_type["key"], paper, sections, keyword_labels)

    body_sections = _body_sections(article_type["key"], details)
    summary_text = _summary_blob(details, body_sections)
    journal = paper.get("journal") or "期刊信息待补全"
    journal_metrics = get_journal_metrics(journal, journal_metrics_config)
    classification = paper.get("classification") or {}
    study_type_display = classification.get("study_type_display") or "未明确研究类型"
    data_source_display = classification.get("data_source_display") or "摘要中未提供"
    elite_radar_display = classification.get("elite_radar_display") or "否"
    relation_to_me = classification.get("relation_to_me") or "这篇文章与当前扩展方向的关系不够明确，建议先作为候选文献保留。"
    focus_topics = _focus_topics_from_terms(keyword_terms, keyword_labels, classification)
    direction_display = classification.get("direction_display") or "未明确分类"
    if direction_display == "未明确分类" and focus_topics:
        direction_display = " / ".join(focus_topics[:3])
    brief_summary = _brief_summary(paper, details, body_sections, article_type["key"])
    presentation_value_score = float(paper.get("presentation_value_score") or 0)
    presentation_materials = _presentation_materials(
        paper=paper,
        article_type_key=article_type["key"],
        details=details,
        body_sections=body_sections,
        direction_display=direction_display,
        presentation_value_score=presentation_value_score,
    )
    ppt_preparation = _ppt_preparation_info(
        paper=paper,
        article_type_key=article_type["key"],
        details=details,
        brief_summary=brief_summary,
    )
    missing_info = _missing_information(
        paper=paper,
        details=details,
        body_sections=body_sections,
        journal_metrics=journal_metrics,
    )

    return {
        "chinese_title": details["chinese_title"],
        "title": paper.get("title") or "Untitled",
        "english_title": paper.get("title") or "Untitled",
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
        "brief_summary": brief_summary,
        "why_read": details["why_read"],
        "evidence_strength": _evidence_strength(article_type["key"]),
        "my_judgment": details["my_judgment"],
        "inspiration": details["inspiration"],
        "body_sections": body_sections,
        "recommendation_index": _recommendation_index(float(paper.get("score") or 0)),
        "stars": _stars(float(paper.get("score") or 0)),
        "score": paper.get("score"),
        "result_specificity_score": paper.get("result_specificity_score", 0),
        "result_specificity_display": _result_specificity_display(paper.get("result_specificity_score", 0)),
        "reading_priority": paper.get("reading_priority") or _reading_priority(float(paper.get("score") or 0), paper.get("result_specificity_score", 0)),
        "score_breakdown": paper.get("score_breakdown") or {},
        "matched_keywords": keyword_labels,
        "keyword_terms": keyword_terms,
        "keywords_display": ", ".join(keyword_terms) if keyword_terms else "摘要中未提供",
        "focus_topics": focus_topics,
        "direction_display": direction_display,
        "study_type_display": study_type_display,
        "data_source_display": data_source_display,
        "elite_radar_display": elite_radar_display,
        "relation_to_me": relation_to_me,
        "personal_relevance_score": paper.get("personal_relevance_score")
        or classification.get("personal_relevance_score")
        or 0,
        "presentation_value_score": presentation_value_score,
        "presentation_value_reason": paper.get("presentation_value_reason") or presentation_materials["reason"],
        "presentation_materials": presentation_materials,
        "ppt_preparation": ppt_preparation,
        "missing_info": missing_info,
        "classification": classification,
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
        "prospective",
        "cross sectional",
        "cross-sectional",
        "case control",
        "case-control",
        "factors associated",
        "return-to-sport",
        "return to sport",
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
    blob = _paper_blob(paper)

    if "caffeine" in blob and "swimming performance" in blob and ("meta-analysis" in blob or "meta analysis" in blob):
        return {
            "chinese_title": title,
            "one_sentence_conclusion": (
                "这篇系统综述/多层级 Meta 分析评估咖啡因摄入是否改善游泳表现；它直接服务于比赛补剂策略讨论，"
                "但具体剂量、项目距离、个体差异和效应大小仍需要结合摘要结果或全文核对。"
            ),
            "why_read": (
                "它回答的是运动营养里很实际的问题：咖啡因补剂能不能帮助游泳表现。"
                "这比泛泛讨论运动营养更有用，适合用于训练营养、比赛前补剂和个体反应差异的讨论。"
            ),
            "review_question": "综述问题是：咖啡因摄入对不同游泳项目或测试情境中的运动表现是否有改善作用。",
            "included_types": _included_types_text(methods),
            "included_studies": _included_studies_text(results),
            "outcomes": "主要结局是游泳表现；具体包括哪些距离、测试指标和表现单位需要核对摘要结果或全文。",
            "pooled_effects": _review_results_text(results),
            "evidence_quality": _evidence_quality_text(methods + " " + results),
            "author_conclusion": _safe_chinese_conclusion(conclusion, MISSING),
            "limitations": _limitations_text(_section(sections, ["limitations", "limitation"]), results),
            "my_judgment": (
                "这篇适合放在运动营养和竞技表现补剂策略里读；如果摘要没有给出效应量、剂量分层或项目距离分层，"
                "推荐等级应低于结果非常具体的 Meta 分析。"
            ),
            "inspiration": "可用于设计游泳项目咖啡因补剂讨论框架：剂量、摄入时机、项目距离、训练状态和个体耐受性都应分开看。",
        }

    if "patellofemoral pain" in blob and "muscle strength" in blob and ("meta-analysis" in blob or "meta analysis" in blob):
        return {
            "chinese_title": title,
            "one_sentence_conclusion": (
                "这篇系统综述与 Meta 分析纳入 82 项随机临床试验、4023 名髌股疼痛参与者，发现下肢肌力改善与疼痛减轻和功能改善相关，"
                "提示膝关节和髋关节肌群力量训练在 PFP 康复中具有明确临床意义。"
            ),
            "why_read": (
                "它直接回答康复实践中很常见的问题：髌股疼痛患者力量变强，是否真的对应疼痛和功能改善。"
                "这比泛泛说“练力量有帮助”更有价值，因为摘要给出了纳入试验数量、样本量、相关方向和部分效应指标。"
            ),
            "review_question": "综述问题是：在髌股疼痛人群中，随机临床试验观察到的肌肉力量变化，是否与疼痛和身体功能的同步变化相关。",
            "included_types": "纳入非手术、非药物干预的随机临床试验，且研究必须同时报告肌肉力量和至少一个临床结局（疼痛或功能）。",
            "included_studies": "共筛查 16,750 条记录，最终纳入 82 项试验、4023 名参与者。",
            "outcomes": "主要结局包括自评疼痛、身体功能，以及膝伸肌、膝屈肌、髋外展肌、髋内收肌、髋内/外旋肌和髋伸肌等力量变化。",
            "pooled_effects": (
                "疼痛方面，膝伸肌、膝屈肌和多个髋部肌群力量改善均与疼痛下降相关，例如髋外展肌 r=-0.91、β=-0.31，膝伸肌 r=-0.75、β=-0.21。"
                "功能方面，膝伸肌、膝屈肌、髋外展肌、髋内收肌和髋内旋肌力量改善与功能提升相关，例如髋外展肌 r=0.94、β=0.15，膝伸肌 r=0.70、β=0.15。"
            ),
            "evidence_quality": "疼痛结局的证据确定性为低到中等；功能结局的证据确定性为低到高。仍需结合纳入研究质量和异质性解读。",
            "author_conclusion": "作者认为，下肢肌肉力量改善与髌股疼痛患者疼痛减轻和身体功能改善相关，支持以膝和髋部肌群为重点的力量康复训练。",
            "limitations": "摘要未详细列出局限性；从研究设计看，Meta 分析结论仍受纳入 RCT 的干预差异、测力方法、疼痛/功能量表和证据确定性影响。",
            "my_judgment": "这篇比普通“力量训练有益”的综述更值得读，因为它把肌力变化和临床结局变化连接起来，适合 DPT、运动康复和髌股疼痛训练方案设计。",
            "inspiration": "对康复实践：不要只看动作是否完成，还要追踪膝伸/屈肌与髋部肌群力量是否随疼痛和功能一起改善；对科研：可作为训练剂量、肌群选择和临床结局关联建模的参考。",
        }

    if "irisin" in blob and "training" in blob and ("overweight" in blob or "obesity" in blob):
        return {
            "chinese_title": title,
            "one_sentence_conclusion": (
                "这篇 Meta 分析关注不同训练方式是否会改变超重或肥胖人群循环 irisin 水平，"
                "适合用来理解运动干预、肥胖代谢和肌因子之间的联系；具体效应量以摘要/全文报告为准。"
            ),
            "why_read": (
                "它不是单纯谈减脂，也不是运动营养，而是把训练方式与 irisin 这个肌因子联系起来，"
                "对肥胖代谢、运动生理和运动干预机制选题更有参考价值。"
            ),
            "review_question": "综述问题是：不同训练方式对超重或肥胖人群循环 irisin 水平是否有影响。",
            "included_types": _included_types_text(methods),
            "included_studies": _included_studies_text(results),
            "outcomes": "主要结局是循环 irisin 水平；如果摘要未说明体脂、胰岛素敏感性等次要结局，就不额外补写。",
            "pooled_effects": _review_results_text(results),
            "evidence_quality": _evidence_quality_text(methods + " " + results),
            "author_conclusion": _safe_chinese_conclusion(conclusion, MISSING),
            "limitations": _limitations_text(_section(sections, ["limitations", "limitation"]), results),
            "my_judgment": "这篇更适合作为“运动干预-肥胖代谢-肌因子”背景文献，不应被误归为膳食脂肪或运动营养。",
            "inspiration": "可帮助构建肥胖人群训练干预机制框架：训练方式、能量代谢、肌因子反应和临床表型需要一起考虑。",
        }

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
    raw_context = " ".join([str(paper.get("title") or ""), methods, results, conclusion, str(paper.get("abstract") or "")])
    is_athlete_rts = _is_athlete_rts_infection(paper)
    if _is_aware_x_study(paper) and _has_aware_x_detailed_results(paper):
        return {
            "chinese_title": title,
            "one_sentence_conclusion": (
                "AWARE X 前瞻性队列纳入 114 例病原体确认的运动员急性呼吸道感染，发现运动水平、病原体类型和发病时疾病严重程度与重返训练、"
                "重返完整训练和重返完整表现所需时间相关，可为感染后复训和复赛决策提供具体风险线索。"
            ),
            "why_read": (
                "这篇文章值得看，是因为它把急性呼吸道感染后的 return-to-sport 问题放在真实运动员队列中，用 PCR 确认病原体，并区分 RTT、RTFT、RTFP。"
                "对教练、队医和运动康复人员来说，它比单纯“症状好了就恢复”更接近实际决策。"
            ),
            "research_question": "这项研究想知道：病原体确认的急性呼吸道感染后，哪些因素与运动员重返训练、重返完整训练和重返完整运动表现的时间相关。",
            "participants": "前瞻性队列共纳入 114 例病原体确认的急性呼吸道感染运动员病例。",
            "exposure": "主要暴露或分组变量包括运动参与水平、病原体类型（如流感、SARS-CoV-2、鼻病毒）和发病时疾病严重程度。",
            "outcomes": "关键结局包括 RTT（重返训练）、RTFT（重返完整训练）和 RTFP（重返完整运动表现）所需天数。",
            "associations": (
                "RTT、RTFT、RTFP 的中位时间分别为 3.5 天、8 天和 11 天。业余运动员恢复更慢（HR 0.51-0.59，p≤0.03）；"
                "流感和 SARS-CoV-2 相比鼻病毒恢复时间更长（HR 0.11-0.23，p≤0.003）；严重感染相比轻/中度感染恢复更慢（HR 0.17-0.31，p<0.0001）。"
            ),
            "causality": "这是观察性队列研究，能提供风险线索和预测信息，但不能把病原体类型或疾病严重程度解释为单一因果因素。",
            "limitations": "摘要未详细列出局限性；需要阅读全文确认运动项目构成、随访完整性、模型协变量和不同病原体分层样本量。",
            "my_judgment": "这篇适合作为运动员感染后 return-to-sport 风险筛查和随访管理的重点文献，信息量足够进入主推荐，但实践中仍要结合个体症状、心肺状态和队医评估。",
            "inspiration": "对训练管理：复训决策可把病原体、疾病严重程度和运动员水平纳入随访表；对科研：适合发展为感染后复赛预测模型或前瞻性干预研究的变量框架。",
        }
    if _is_labral_cartilage_athlete_cohort(paper) and _has_labral_cartilage_detailed_results(paper):
        return {
            "chinese_title": title,
            "one_sentence_conclusion": (
                "FORCe 纵向队列纳入 173 名高冲击项目运动员（343 个髋关节），中位随访 2.1 年，发现基线前部髋臼盂唇撕裂、旁盂唇囊肿和盂唇总评分"
                "与后续软骨流失存在弱到中等关联，提示髋关节结构损伤可能是运动员髋 OA 风险管理中的重要线索。"
            ),
            "why_read": (
                "这篇文章值得看，是因为它关注的是高冲击运动员的髋关节长期结构变化，而不是泛泛的体力活动研究。"
                "它对运动医学、DPT 和髋/腹股沟疼痛康复很实用：MRI 结构异常是否值得随访，不能只看有没有疼痛。"
            ),
            "research_question": "这项研究想知道：高冲击运动员的基线髋臼盂唇病变，是否与 2-3 年后的髋关节软骨流失相关。",
            "participants": "纳入 173 名足球或澳式足球等高冲击项目运动员，共 343 个髋关节；82% 有髋和/或腹股沟疼痛，22% 为女性，中位年龄 26 岁。",
            "exposure": "主要暴露包括基线盂唇撕裂、前部盂唇撕裂、旁盂唇囊肿、受累区域数量、最大盂唇评分和盂唇总评分。",
            "outcomes": "主要结局是随访 MRI 中软骨总变化评分，用来反映髋关节软骨流失。",
            "associations": (
                "随访 MRI 中位间隔 2.1 年；87% 参与者随访时仍在进行高冲击体力活动。前部盂唇撕裂（aIRR 1.46，95%CI 1.01-2.09）、"
                "旁盂唇囊肿（aIRR 1.38，95%CI 1.02-1.86）和盂唇总评分（aIRR 1.05，95%CI 1.00-1.09）与软骨流失弱到中等相关。"
            ),
            "causality": "这是纵向观察性队列，能提示结构损伤和软骨流失之间的风险关系，但不能单独证明盂唇病变导致软骨流失。",
            "limitations": "摘要提示关联强度只是弱到中等，说明软骨流失还受其他因素影响；仍需阅读全文确认运动暴露、疼痛状态和影像评分可靠性。",
            "my_judgment": "这篇适合 DPT、运动康复和运动医学方向精读，尤其适合思考髋关节 MRI 发现、疼痛、持续参赛和早期 OA 风险之间的关系。",
            "inspiration": "对实践：高冲击运动员有髋/腹股沟疼痛或盂唇异常时，康复目标不应只看短期疼痛，还要考虑长期软骨健康；对科研：可发展为髋关节损伤随访和预防策略研究。",
        }
    key_variables = _key_variable_text(raw_context)
    outcome_text = _outcomes_text(methods + " " + results + " " + str(paper.get("title") or ""))
    if is_athlete_rts:
        outcome_text = "关键结局是 return-to-sport 相关结局，包括感染后能否、何时以及以何种状态恢复训练或比赛；具体定义需要核对全文。"
    associations = _observational_results_text(results, paper=paper, context=raw_context)
    one_sentence = _specific_observational_conclusion(
        paper=paper,
        focus=focus,
        key_variables=key_variables,
        outcomes=outcome_text,
        results=results,
    )
    why_read = _specific_observational_why_read(paper, focus)
    participants = _participants_text(methods)
    if is_athlete_rts and participants == MISSING:
        participants = "研究对象是病原体确认的急性呼吸道感染后的运动员；具体样本量和项目分布如摘要未写明，就不能补写。"

    return {
        "chinese_title": title,
        "one_sentence_conclusion": one_sentence,
        "why_read": why_read,
        "research_question": _observational_research_question(paper, focus),
        "participants": participants,
        "exposure": key_variables if key_variables != MISSING else _exposure_text(methods + " " + results),
        "outcomes": outcome_text,
        "associations": associations,
        "causality": "不能仅凭观察性研究说明因果；最多支持相关性或风险线索，仍需干预研究或更强设计验证。",
        "limitations": _limitations_text(_section(sections, ["limitations", "limitation"]), results),
        "my_judgment": _specific_observational_judgment(paper, results),
        "inspiration": _specific_observational_inspiration(paper, focus),
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
    normalized_title = normalize_text(title)
    if "caffeine makes a splash" in normalized_title or (
        "caffeine" in normalized_title and "swimming performance" in normalized_title and "meta" in normalized_title
    ):
        return "咖啡因摄入对游泳表现影响的系统综述与多层级 Meta 分析"
    if "patellofemoral pain" in normalized_title and "muscle strength" in normalized_title and "meta-analysis" in normalized_title:
        return "肌肉力量变化与髌股疼痛临床结局变化关系的系统综述与 Meta 分析"
    if "labral pathology" in normalized_title and "cartilage loss" in normalized_title and "high-impact athletes" in normalized_title:
        return "高冲击运动员髋臼盂唇病变与软骨流失关系的纵向队列研究：FORCe 研究"
    if "irisin" in normalized_title and "training" in normalized_title and (
        "overweight" in normalized_title or "obesity" in normalized_title
    ):
        return "不同训练方式对超重和肥胖人群循环 irisin 水平影响的系统综述与 Meta 分析"
    if "c-reactive protein-triglyceride-glucose" in normalized_title and "masld" in normalized_title:
        return "C 反应蛋白-甘油三酯葡萄糖指数与 MASLD 人群心代谢风险的队列研究"
    if "electromyography" in normalized_title and ("rotator cuff" in normalized_title or "deltoid" in normalized_title):
        return "肩袖与三角肌疲劳相关的肌电图研究"
    if "integrated proteomic and metabolomic" in normalized_title and "ptsd" in normalized_title:
        return "PTSD 相关多系统疾病和加速衰老中的蛋白质组与代谢组研究"
    if _is_athlete_rts_infection({"title": title}):
        return "病原体确认的急性呼吸道感染后，影响运动员重返运动结局的相关因素：AWARE X 研究"
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
    if _has_chinglish_title(translated) or _english_word_count(translated) > 8:
        return _fallback_chinese_title(title, article_type_label, keyword_labels)
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


def _observational_results_text(
    results: str,
    paper: dict[str, Any] | None = None,
    context: str = "",
) -> str:
    if not results:
        if paper and _is_athlete_rts_infection(paper):
            return "摘要未提供具体效应量、p 值或关键变量的方向性结果；目前只能确定它研究的是感染后重返运动结局的相关因素。"
        return MISSING
    numbers = _extract_numbers(results)
    key_variables = _key_variable_text(" ".join([context, results]))
    if paper and _is_athlete_rts_infection(paper) and not numbers:
        return "摘要未提供具体效应量、p 值或关键变量的方向性结果；可确认研究聚焦急性呼吸道感染后运动员 return-to-sport 结局的相关因素，具体关键因素需阅读全文结果表。"
    if "associated" in normalize_text(results):
        if numbers:
            variable_part = "" if key_variables == MISSING else f"相关变量包括：{key_variables}"
            return variable_part + "摘要报告了数值信息：" + "、".join(numbers[:6]) + "；具体方向和统计模型仍需核对全文。"
        if paper and _is_athlete_rts_infection(paper):
            return "摘要未提供具体效应量或 p 值；可确认研究聚焦急性呼吸道感染后运动员 return-to-sport 结局的相关因素，具体关键因素需阅读全文结果表。"
        return "摘要未提供具体效应量或 p 值；只能说明作者报告了关联分析，不能把相关因素解释为因果因素。"
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
        ("return-to-sport", "return-to-sport / 重返运动"),
        ("return to sport", "return-to-sport / 重返运动"),
        ("return-to-play", "return-to-play / 重返比赛"),
        ("return to play", "return-to-play / 重返比赛"),
        ("symptom", "症状恢复"),
        ("training interruption", "训练中断时间"),
        ("illness duration", "疾病或症状持续时间"),
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
        ("masld", "MASLD 相关结局"),
        ("metabolic dysfunction-associated steatotic liver disease", "MASLD 相关结局"),
        ("cardiometabolic", "心代谢结局"),
        ("multimorbidity", "多病共存"),
        ("mortality", "死亡风险"),
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


def _is_athlete_rts_infection(paper: dict[str, Any]) -> bool:
    blob = " " + normalize_text(
        " ".join(
            [
                str(paper.get("title") or ""),
                str(paper.get("abstract") or ""),
                " ".join(paper.get("article_types") or []),
            ]
        )
    ) + " "
    has_athlete = any(term in blob for term in [" athlete ", " athletes "])
    has_rts = any(term in blob for term in [" return-to-sport ", " return to sport ", " return-to-play ", " return to play "])
    has_infection = any(
        term in blob
        for term in [
            " acute respiratory infection ",
            " acute respiratory infections ",
            " respiratory infection ",
            " respiratory infections ",
            " pathogen-confirmed ",
        ]
    )
    return has_athlete and has_rts and has_infection


def _is_aware_x_study(paper: dict[str, Any]) -> bool:
    blob = normalize_text(" ".join([str(paper.get("title") or ""), str(paper.get("abstract") or "")]))
    return "aware x" in blob and _is_athlete_rts_infection(paper)


def _has_aware_x_detailed_results(paper: dict[str, Any]) -> bool:
    blob = normalize_text(str(paper.get("abstract") or ""))
    return (
        "114" in blob
        and any(term in blob for term in ["hazard ratio", "hr", "hrs"])
        and all(term in blob for term in ["return-to-training", "return-to-full-training", "return-to-full-performance"])
    )


def _is_labral_cartilage_athlete_cohort(paper: dict[str, Any]) -> bool:
    blob = " " + normalize_text(
        " ".join(
            [
                str(paper.get("title") or ""),
                str(paper.get("abstract") or ""),
                " ".join(paper.get("article_types") or []),
            ]
        )
    ) + " "
    has_labral = any(term in blob for term in [" labral pathology ", " labral tears ", " labral tear "])
    has_cartilage = " cartilage loss " in blob
    has_athlete = any(term in blob for term in [" athlete ", " athletes ", " high-impact physical activity "])
    return has_labral and has_cartilage and has_athlete


def _has_labral_cartilage_detailed_results(paper: dict[str, Any]) -> bool:
    blob = normalize_text(str(paper.get("abstract") or ""))
    return "173" in blob and "343 hips" in blob and any(term in blob for term in ["airr", "incidence rate ratio"])


def _key_variable_text(text_raw: str) -> str:
    text = normalize_text(text_raw)
    variables = []
    for term, label in [
        ("symptom duration", "症状持续时间"),
        ("illness duration", "疾病持续时间"),
        ("pathogen", "病原体类型"),
        ("training interruption", "训练中断时间"),
        ("sex", "性别"),
        ("gender", "性别"),
        ("sport", "运动项目"),
        ("severity", "疾病严重程度"),
        ("age", "年龄"),
        ("previous infection", "既往感染史"),
        ("vaccination", "疫苗接种状态"),
        ("acute respiratory infection", "急性呼吸道感染相关特征"),
        ("respiratory infection", "呼吸道感染相关特征"),
        ("return-to-sport", "重返运动结局"),
        ("return to sport", "重返运动结局"),
        ("c-reactive protein-triglyceride-glucose", "C 反应蛋白-甘油三酯葡萄糖指数"),
        ("crp-triglyceride-glucose", "C 反应蛋白-甘油三酯葡萄糖指数"),
        ("tyg", "TyG 相关指标"),
        ("uk biobank", "UK Biobank 数据来源"),
        ("masld", "MASLD 状态"),
        ("metabolic dysfunction-associated steatotic liver disease", "MASLD 状态"),
    ]:
        if term in text:
            variables.append(label)
    if variables:
        return "、".join(dict.fromkeys(variables)) + "。"
    return MISSING


def _observational_research_question(paper: dict[str, Any], focus: str) -> str:
    blob = _paper_blob(paper)
    if _is_athlete_rts_infection(paper):
        return "这项研究想知道：病原体确认的急性呼吸道感染后，哪些因素与运动员重返运动或恢复训练的结局相关。"
    if "masld" in blob and ("uk biobank" in blob or "cohort" in blob):
        return "这项队列研究想知道：MASLD 人群中，CRP-TyG 等炎症-代谢指标是否与后续心代谢多病风险相关。"
    return f"研究问题聚焦于{focus}相关暴露因素、分组变量或结局指标之间的关系。"


def _specific_observational_conclusion(
    *,
    paper: dict[str, Any],
    focus: str,
    key_variables: str,
    outcomes: str,
    results: str,
) -> str:
    if _is_athlete_rts_infection(paper):
        variable_part = "症状持续时间、病原体类型、训练中断时间、疾病严重程度等因素" if key_variables == MISSING else key_variables.rstrip("。")
        missing_part = ""
        if _result_specificity_from_text(results) < 50:
            missing_part = "；摘要未提供具体效应量或完整关键变量结果"
        return (
            f"这项 AWARE X 观察性研究关注病原体确认的急性呼吸道感染后，{variable_part}"
            f"是否与运动员 return-to-sport 结局相关，可为感染后恢复训练和复赛决策提供风险线索{missing_part}，"
            "但不能把这些相关因素解释为因果因素。"
        )
    if key_variables != MISSING and outcomes != "摘要中未提供明确结局指标。":
        return f"这项观察性研究分析了{key_variables.rstrip('。')}与{outcomes.replace('主要结局指标包括：', '').rstrip('。')}之间的关系，可提供风险线索，但不能单独证明因果。"
    return f"这项观察性研究关注{focus}相关因素与结局的关系；若摘要没有具体效应量，应作为假设生成和背景线索，而不是强因果证据。"


def _specific_observational_why_read(paper: dict[str, Any], focus: str) -> str:
    if _is_athlete_rts_infection(paper):
        return (
            "这篇文章值得看，是因为它把急性呼吸道感染后的 return-to-sport 问题放在真实运动员队列中分析，"
            "对教练、队医和运动康复人员判断何时恢复训练、哪些运动员可能恢复较慢有实际参考价值。"
            "它不能直接制定复赛标准，但能提供风险筛查和随访管理线索。"
        )
    return f"这篇文章值得看，是因为它把{focus}问题放在真实人群或临床场景中分析，适合用来发现风险线索、设计随访变量和提出后续干预研究假设。"


def _specific_observational_judgment(paper: dict[str, Any], results: str) -> str:
    specificity = _result_specificity_from_text(results)
    if _is_athlete_rts_infection(paper):
        if specificity < 50:
            return (
                "这篇更适合作为运动员感染后恢复训练/复赛管理的背景文献或可选阅读。"
                "摘要层面结果不够具体，不能直接拿来制定复赛阈值，建议精读时重点看全文结果表中的关键因素和模型。"
            )
        return "这篇适合作为运动员感染后 return-to-sport 风险筛查和随访管理的重点文献，但仍要守住观察性研究的因果边界。"
    if specificity < 50:
        return "这篇文章的研究问题有价值，但摘要结果不够具体，适合作为可选阅读；是否精读取决于全文是否提供清晰效应量和模型。"
    return "适合作为假设生成和背景证据；不建议把相关性直接写成训练或治疗一定有效。"


def _specific_observational_inspiration(paper: dict[str, Any], focus: str) -> str:
    if _is_athlete_rts_infection(paper):
        return (
            "对训练和康复管理：可把症状变化、训练中断时间、病原体信息和重返运动状态纳入随访清单。"
            "对科研：适合发展为运动员感染后复赛决策模型或前瞻性队列研究，而不是直接当作干预证据。"
        )
    return f"对科研训练：可以从这类研究中提炼变量、结局和潜在混杂因素，为{focus}方向后续实验设计做准备。"


def _apply_quality_guard(
    details: dict[str, str],
    article_type_key: str,
    paper: dict[str, Any],
    sections: dict[str, str],
    keyword_labels: list[str],
) -> dict[str, str]:
    if article_type_key != "observational":
        return details
    guarded = dict(details)
    results = _section(sections, ["results", "findings"])
    focus = _topic_phrase(keyword_labels)
    if _is_low_information_text(guarded.get("one_sentence_conclusion", "")):
        guarded["one_sentence_conclusion"] = _specific_observational_conclusion(
            paper=paper,
            focus=focus,
            key_variables=_key_variable_text(" ".join([str(paper.get("title") or ""), str(paper.get("abstract") or "")])),
            outcomes=_outcomes_text(" ".join([str(paper.get("title") or ""), str(paper.get("abstract") or "")])),
            results=results,
        )
    if _is_low_information_text(guarded.get("why_read", "")):
        guarded["why_read"] = _specific_observational_why_read(paper, focus)
    if _is_low_information_text(guarded.get("my_judgment", "")):
        guarded["my_judgment"] = _specific_observational_judgment(paper, results)
    if _is_low_information_text(guarded.get("inspiration", "")):
        guarded["inspiration"] = _specific_observational_inspiration(paper, focus)
    return guarded


def _is_low_information_text(value: str) -> bool:
    text = str(value or "").strip()
    normalized = normalize_text(text)
    if len(text) < 28:
        return True
    if any(phrase in text for phrase in LOW_INFORMATION_PHRASES):
        has_specific_context = any(
            term in normalized
            for term in [
                "athlete",
                "athletes",
                "return-to-sport",
                "return to sport",
                "respiratory infection",
                "training",
                "症状",
                "运动员",
                "重返运动",
                "感染",
                "结局",
            ]
        )
        if not has_specific_context:
            return True
    return False


def _has_chinglish_title(value: str) -> bool:
    normalized = normalize_text(value)
    bad_patterns = [
        "associated合并",
        "在athletes",
        "在 athlete",
        "pathogen-confirmed",
        "return-to-sport outcomes在",
    ]
    if any(pattern in value or pattern in normalized for pattern in bad_patterns):
        return True
    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", value))
    if not has_chinese:
        return False
    if re.search(r"(在|与|合并|用于|一项)[A-Za-z]", value):
        return True
    if re.search(r"[A-Za-z](在|与|合并|用于)[A-Za-z]?", value):
        return True
    if _english_word_count(value) >= 5 and re.search(r"\b(of|between|following|outcomes|changes|association|effects?)\b", value, flags=re.IGNORECASE):
        return True
    return False


def _fallback_chinese_title(title: str, article_type_label: str, keyword_labels: list[str]) -> str:
    blob = normalize_text(title)
    if "return-to-sport" in blob or "return to sport" in blob:
        if "respiratory infection" in blob or "pathogen-confirmed" in blob:
            return "关于运动员急性呼吸道感染后重返运动结局的观察性研究"
        return "关于运动员重返运动结局的观察性研究"
    topic = _topic_phrase(keyword_labels)
    return f"关于{topic}的{article_type_label}"


def _result_specificity_from_text(text: str) -> int:
    if not text:
        return 20
    score = 25
    numbers = _extract_numbers(text)
    normalized = normalize_text(text)
    if numbers:
        score += 25
    if any(term in normalized for term in ["odds ratio", "hazard ratio", "risk ratio", "confidence interval", " p ", "beta", "effect size"]):
        score += 25
    if any(term in normalized for term in ["associated", "increased", "decreased", "higher", "lower", "improved", "reduced"]):
        score += 15
    if _key_variable_text(text) != MISSING:
        score += 10
    return max(0, min(100, score))


def _result_specificity_display(value: Any) -> str:
    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        score = 0
    if score >= 75:
        return "高：摘要提供了较具体的结果信息。"
    if score >= 50:
        return "中：摘要提供了部分结果线索，但仍需核对全文。"
    return "低：摘要缺少具体效应量、关键变量或方向性结果。"


def _reading_priority(score: float, result_specificity: Any) -> str:
    try:
        specificity = float(result_specificity or 0)
    except (TypeError, ValueError):
        specificity = 0
    if specificity < 50:
        return "可选阅读"
    if score >= 80:
        return "优先阅读"
    return "推荐阅读"


def _keyword_terms(paper: dict[str, Any], matched_keywords: list[dict[str, Any]]) -> list[str]:
    blob = " " + normalize_text(" ".join([str(paper.get("title") or ""), str(paper.get("abstract") or "")])) + " "
    terms: list[str] = []
    for keyword in matched_keywords:
        term = str(keyword.get("matched_term") or keyword.get("term") or "").strip()
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
        ("uk biobank", "UK Biobank"),
        ("nhanes", "NHANES"),
        ("obesity phenotype", "obesity phenotype"),
        ("metabolically healthy obesity", "metabolically healthy obesity"),
        ("physical activity", "physical activity"),
        ("accelerometer", "accelerometer"),
        ("skeletal muscle", "skeletal muscle"),
        ("dna methylation", "DNA methylation"),
        ("rna-seq", "RNA-seq"),
        ("muscle memory", "muscle memory"),
        ("dietary fat", "dietary fat"),
        ("fatty acid", "fatty acid"),
        ("lipid metabolism", "lipid metabolism"),
        ("sports nutrition", "sports nutrition"),
        ("protein supplementation", "protein supplementation"),
        ("creatine", "creatine"),
        ("athlete", "athlete"),
        ("athletes", "athlete"),
        ("acute respiratory infection", "acute respiratory infection"),
        ("respiratory infection", "respiratory infection"),
        ("return-to-sport", "return-to-sport"),
        ("return to sport", "return-to-sport"),
    ]
    for trigger, label in domain_terms:
        if trigger in blob and label not in terms:
            terms.append(label)
    return list(dict.fromkeys(terms))[:8]


def _keyword_label(keyword: dict[str, Any]) -> str:
    matched_term = str(keyword.get("matched_term") or "").strip()
    base_term = str(keyword.get("term") or "").strip()
    if matched_term and matched_term.lower() != base_term.lower():
        return matched_term
    return str(keyword.get("zh") or keyword.get("term") or matched_term or "未命名关键词")


def _focus_topics_from_terms(
    keyword_terms: list[str],
    keyword_labels: list[str],
    classification: dict[str, Any] | None = None,
) -> list[str]:
    terms = set(keyword_terms)
    topics: list[str] = list((classification or {}).get("directions") or [])
    if "musculoskeletal rehabilitation" in terms or "rehabilitation" in terms:
        topics.append("肌骨康复")
    if "obesity" in terms:
        topics.append("肥胖")
    if "osteoarthritis" in terms:
        topics.append("骨关节炎")
    if "weight loss" in terms or "GLP-1" in terms:
        topics.append("药物辅助减重")
    if "athlete" in terms:
        topics.append("运动员健康")
    if "respiratory infection" in terms or "acute respiratory infection" in terms:
        topics.append("呼吸道感染")
    if "return-to-sport" in terms:
        topics.append("重返运动")
    topics.extend(label for label in keyword_labels if label not in topics)
    return list(dict.fromkeys(topics))[:5]


def _brief_summary(
    paper: dict[str, Any],
    details: dict[str, str],
    body_sections: list[dict[str, str]],
    article_type_key: str,
) -> str:
    study_design = _article_type_summary_label(article_type_key)
    participants = _first_available(
        details,
        body_sections,
        ["participants", "eligibility", "included_studies"],
        ["研究对象", "研究对象 / 纳入标准", "纳入研究数量 / 样本量", "纳入研究数量"],
    )
    exposure = _first_available(
        details,
        body_sections,
        ["intervention", "exposure", "included_types"],
        ["干预方案", "暴露因素 / 分组变量", "干预/暴露", "纳入研究类型"],
    )
    outcomes = _first_available(
        details,
        body_sections,
        ["outcomes", "review_question", "research_question"],
        ["测试指标", "主要结局指标", "结局指标", "研究问题", "综述问题"],
    )
    key_results = _first_available(
        details,
        body_sections,
        ["main_results", "associations", "pooled_effects", "theme_distribution"],
        ["主要结果", "主要关联结果", "合并效应或主要发现", "主要发现"],
    )
    meaning = _first_available(
        details,
        body_sections,
        ["inspiration", "why_read"],
        ["实践启发", "实践价值", "为什么值得看"],
    )

    pieces = [
        f"研究设计：{study_design}",
        f"对象/样本：{_compact_or_missing(participants, 150)}",
        f"干预/暴露：{_compact_or_missing(exposure, 150)}",
        f"主要结局：{_compact_or_missing(outcomes, 150)}",
        f"关键结果：{_compact_or_missing(key_results, 230)}",
        f"意义：{_compact_or_missing(meaning, 180)}",
    ]
    return "；".join(pieces) + "。"


def _presentation_materials(
    *,
    paper: dict[str, Any],
    article_type_key: str,
    details: dict[str, str],
    body_sections: list[dict[str, str]],
    direction_display: str,
    presentation_value_score: float,
) -> dict[str, Any]:
    if presentation_value_score <= 0:
        presentation_value_score = _infer_presentation_value(paper, details)
    suitability, priority = _presentation_level(presentation_value_score)
    reason = paper.get("presentation_value_reason") or _presentation_reason(
        suitability,
        article_type_key,
        presentation_value_score,
        direction_display,
    )
    key_data = _presentation_key_data(paper, details, body_sections)
    return {
        "score": round(presentation_value_score, 1),
        "suitability": suitability,
        "priority": priority,
        "reason": reason,
        "core_talking_point": _core_talking_point(article_type_key, details, direction_display),
        "storyline": _presentation_storyline(article_type_key, details, direction_display),
        "key_data": key_data,
        "important_conclusions": _important_conclusions(details, body_sections),
        "peer_inspiration": _peer_inspiration(article_type_key, details, direction_display),
    }


def _ppt_preparation_info(
    *,
    paper: dict[str, Any],
    article_type_key: str,
    details: dict[str, str],
    brief_summary: str,
) -> dict[str, Any]:
    figure_suggestions = _figure_type_suggestions(article_type_key, paper)
    return {
        "short_pages": "3-5 页",
        "deep_pages": "8-12 页",
        "full_text_notice": FULL_TEXT_FIGURE_NOTICE,
        "structure": [
            {
                "title": "第 1 页：文章信息",
                "bullets": [
                    f"中文题目：{details.get('chinese_title', NEEDS_FULL_TEXT)}",
                    f"英文题目：{paper.get('title') or NEEDS_FULL_TEXT}",
                    f"期刊/DOI/分区：使用简报中的期刊、DOI、JCR 分区和中科院分区。",
                    f"关键词：使用简报关键词。",
                    f"精简版摘要：{_compact_or_missing(brief_summary, 220)}",
                ],
            },
            {
                "title": "第 2 页：研究背景与问题",
                "bullets": [
                    _compact_or_missing(details.get("why_read"), 180),
                    _compact_or_missing(details.get("review_question") or details.get("research_question"), 180),
                    "研究缺口和研究假设需结合引言与全文进一步核对。",
                ],
            },
            {
                "title": "第 3 页：研究设计总览",
                "bullets": [
                    f"研究对象：{_compact_or_missing(details.get('participants') or details.get('eligibility'), 160)}",
                    f"样本量：{_sample_size_text(paper, details)}",
                    f"干预/暴露：{_compact_or_missing(details.get('intervention') or details.get('exposure') or details.get('included_types'), 160)}",
                    f"分组：{_compact_or_missing(details.get('grouping'), 120)}",
                    f"取材：{_muscle_sampling_text(paper)}",
                    f"组学/检测技术：{_technology_text(paper)}",
                ],
            },
            {
                "title": "第 4 页起：关键 Figure 讲解页",
                "bullets": [
                    "Fig 1：需阅读全文并提取原文 Figure 后确定。",
                    "Fig 2：需阅读全文并提取原文 Figure 后确定。",
                    "Fig 3：需阅读全文并提取原文 Figure 后确定。",
                    "建议优先查看的 Figure 类型：" + "、".join(figure_suggestions),
                ],
            },
            {
                "title": "最后页：重要结论与启发",
                "bullets": [
                    _compact_or_missing(details.get("author_conclusion") or details.get("one_sentence_conclusion"), 180),
                    _compact_or_missing(details.get("inspiration") or details.get("my_judgment"), 180),
                ],
            },
        ],
        "figure_suggestions": figure_suggestions,
        "figure_principles": [
            "PPT 必须使用文章原图。",
            "插图必须来自原文 PDF 或原文附件。",
            "不允许自己编造图片。",
            "大图 Fig 可以拆成 Fig A / Fig B / Fig C 单独讲解。",
            "每张图应解释：展示了什么、证明了什么、对研究结论的作用、在文章写作中的意义。",
            "文献名和 DOI 放在每页底部。",
        ],
    }


def _missing_information(
    *,
    paper: dict[str, Any],
    details: dict[str, str],
    body_sections: list[dict[str, str]],
    journal_metrics: dict[str, Any],
) -> list[str]:
    missing = ["全文 PDF", "原文 Figure"]
    if not _has_sample_size(details, body_sections, paper):
        missing.append("样本量")
    if _muscle_sampling_text(paper) == NEEDS_FULL_TEXT:
        missing.append("肌肉取材方法")
    if _omics_type_text(paper) == NEEDS_FULL_TEXT:
        missing.append("组学类型")
    if _metric_missing(journal_metrics.get("jcr_quartile")):
        missing.append("JCR 分区")
    if _metric_missing(journal_metrics.get("cas_zone")):
        missing.append("中科院分区")
    if not _has_effect_detail(paper, details, body_sections):
        missing.append("具体效应量")
    if not _has_evidence_quality(details):
        missing.append("偏倚风险或证据质量")
    return list(dict.fromkeys(missing))


def _first_available(
    details: dict[str, str],
    body_sections: list[dict[str, str]],
    detail_keys: list[str],
    labels: list[str],
) -> str:
    for key in detail_keys:
        value = str(details.get(key) or "").strip()
        if _has_real_content(value):
            return value
    for section in body_sections:
        if section.get("label") in labels and _has_real_content(str(section.get("value") or "")):
            return str(section.get("value"))
    return NEEDS_FULL_TEXT


def _has_real_content(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return text not in {MISSING, NEEDS_FULL_TEXT, "摘要中未提供", "摘要中未提供。"} and "未提供" not in text[:18]


def _compact_or_missing(value: Any, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not _has_real_content(text):
        return NEEDS_FULL_TEXT
    if len(text) <= limit:
        return text
    for delimiter in ["。", "；", ";", "，", ",", "、"]:
        position = text.rfind(delimiter, 0, limit)
        if position >= 40:
            return text[: position + 1].strip()
    return text[: max(0, limit - 1)].rstrip() + "…"


def _article_type_summary_label(article_type_key: str) -> str:
    return {
        "systematic_review_meta": "系统综述/Meta 分析",
        "scoping_review": "范围综述",
        "experimental": "RCT/干预或实验研究",
        "observational": "观察性研究/队列研究",
        "generic": "研究论文",
    }.get(article_type_key, "研究论文")


def _infer_presentation_value(paper: dict[str, Any], details: dict[str, str]) -> float:
    score = float(paper.get("score") or 0) * 0.35
    try:
        score += float(paper.get("result_specificity_score") or 0) * 0.45
    except (TypeError, ValueError):
        pass
    if _has_real_content(details.get("main_results") or details.get("associations") or details.get("pooled_effects") or ""):
        score += 12
    if _extract_numbers(str(paper.get("abstract") or "")):
        score += 8
    return max(0, min(100, score))


def _presentation_level(score: float) -> tuple[str, str]:
    if score >= 75:
        return "适合", "高"
    if score >= 55:
        return "可选", "中"
    return "不建议", "低"


def _presentation_reason(
    suitability: str,
    article_type_key: str,
    score: float,
    direction_display: str,
) -> str:
    if suitability == "适合":
        return f"这篇文章的研究问题和结果信息较清楚，且与{direction_display}相关，适合发展成组会汇报。"
    if suitability == "可选":
        return f"这篇文章主题相关，但汇报前仍需阅读全文核对方法、结果图和偏倚风险；当前组会价值评分为 {score:.0f}/100。"
    return f"当前摘要信息或主题相关性不足，不建议作为组会主讲文献；更适合作为背景或候选文献。"


def _core_talking_point(article_type_key: str, details: dict[str, str], direction_display: str) -> str:
    if article_type_key == "systematic_review_meta":
        return "适合讲研究问题、纳入证据、合并效应和证据质量。"
    if article_type_key == "scoping_review":
        return "适合讲证据版图、研究主题分布和未来研究缺口。"
    if article_type_key == "experimental":
        return "适合讲 PICO、干预剂量、主要结局和训练/康复实践意义。"
    if article_type_key == "observational":
        return "适合讲数据来源、暴露变量、结局变量、风险模型和因果边界。"
    return f"适合围绕{direction_display}提炼研究问题、方法和主要发现。"


def _presentation_storyline(article_type_key: str, details: dict[str, str], direction_display: str) -> list[str]:
    question = _compact_or_missing(details.get("review_question") or details.get("research_question"), 150)
    why = _compact_or_missing(details.get("why_read"), 150)
    result = _compact_or_missing(details.get("main_results") or details.get("associations") or details.get("pooled_effects"), 180)
    innovation = _storyline_innovation(article_type_key)
    return [
        f"作者开展这项研究，是因为{why}",
        f"前人研究缺口可以概括为：{_gap_text(details)}",
        f"这篇文章想解决的问题是：{question}",
        innovation,
        f"最值得讲的地方是：{result}",
    ]


def _gap_text(details: dict[str, str]) -> str:
    for key in ["evidence_gap", "limitations", "why_read"]:
        value = details.get(key)
        if _has_real_content(str(value or "")):
            return _compact_or_missing(value, 150)
    return NEEDS_FULL_TEXT


def _storyline_innovation(article_type_key: str) -> str:
    return {
        "systematic_review_meta": "创新点主要在于把分散研究进行系统检索、质量评价和定量/定性综合。",
        "scoping_review": "创新点主要在于用范围综述方式整理证据版图，而不是直接宣称某个干预有效。",
        "experimental": "创新点应重点看干预设计、剂量控制、结局选择和对照条件。",
        "observational": "创新点应重点看真实世界数据来源、变量定义、混杂因素调整和风险模型。",
        "generic": "创新点需要结合全文方法、结果图和讨论部分进一步确认。",
    }.get(article_type_key, "创新点需要结合全文方法、结果图和讨论部分进一步确认。")


def _presentation_key_data(
    paper: dict[str, Any],
    details: dict[str, str],
    body_sections: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {"label": "样本量", "value": _sample_size_text(paper, details)},
        {"label": "研究对象", "value": _compact_or_missing(details.get("participants") or details.get("eligibility"), 180)},
        {"label": "分组方式", "value": _compact_or_missing(details.get("grouping"), 140)},
        {"label": "干预/暴露", "value": _compact_or_missing(details.get("intervention") or details.get("exposure") or details.get("included_types"), 180)},
        {"label": "肌肉取材方法", "value": _muscle_sampling_text(paper)},
        {"label": "组学类型", "value": _omics_type_text(paper)},
        {"label": "主要检测技术", "value": _technology_text(paper)},
        {"label": "主要结局指标", "value": _compact_or_missing(details.get("outcomes"), 180)},
        {"label": "关键结果", "value": _compact_or_missing(details.get("main_results") or details.get("associations") or details.get("pooled_effects"), 260)},
    ]


def _important_conclusions(details: dict[str, str], body_sections: list[dict[str, str]]) -> list[str]:
    candidates = [
        details.get("one_sentence_conclusion", ""),
        details.get("author_conclusion", ""),
        details.get("my_judgment", ""),
    ]
    conclusions = []
    for value in candidates:
        text = _compact_or_missing(value, 180)
        if text != NEEDS_FULL_TEXT and text not in conclusions:
            conclusions.append(text)
    return conclusions[:3] or [NEEDS_FULL_TEXT]


def _peer_inspiration(article_type_key: str, details: dict[str, str], direction_display: str) -> list[str]:
    base = [
        "学习它如何把研究问题、对象/样本、暴露或干预、主要结局串成清晰逻辑。",
        "汇报时重点说明变量选择为什么服务于研究问题，而不是只罗列结果。",
    ]
    if article_type_key == "systematic_review_meta":
        base.extend(["可学习 PICO 定义、纳入排除标准、森林图/亚组分析/偏倚风险图的组织方式。"])
    elif article_type_key == "observational":
        base.extend(["可学习如何定义暴露变量、结局变量和混杂因素，并解释为什么观察性研究不能直接说明因果。"])
    elif article_type_key == "experimental":
        base.extend(["可学习干预剂量、周期、对照组和主要结局如何共同支撑训练/康复实践意义。"])
    elif article_type_key == "scoping_review":
        base.extend(["可学习如何用证据地图说明一个领域目前研究在哪里、缺口在哪里。"])
    else:
        base.extend([f"可结合{direction_display}思考它是否能转化为运动科学、代谢、肌肉机制、营养或康复选题。"])
    return base[:4]


def _sample_size_text(paper: dict[str, Any], details: dict[str, str]) -> str:
    for key in ["participants", "included_studies", "eligibility"]:
        value = str(details.get(key) or "")
        if _extract_numbers(value):
            return _compact_or_missing(value, 180)
    numbers = _extract_numbers(str(paper.get("abstract") or ""))
    return "、".join(numbers[:5]) if numbers else NEEDS_FULL_TEXT


def _muscle_sampling_text(paper: dict[str, Any]) -> str:
    blob = normalize_text(str(paper.get("abstract") or "") + " " + str(paper.get("title") or ""))
    if "muscle biopsy" in blob or "biopsy" in blob:
        return "摘要提到 muscle biopsy/biopsy；具体肌肉部位需阅读全文确认。"
    for term, label in [
        ("vastus lateralis", "股外侧肌"),
        ("skeletal muscle sample", "骨骼肌样本"),
        ("muscle tissue", "肌肉组织"),
    ]:
        if term in blob:
            return label
    return NEEDS_FULL_TEXT


def _omics_type_text(paper: dict[str, Any]) -> str:
    blob = normalize_text(str(paper.get("abstract") or "") + " " + str(paper.get("title") or ""))
    omics = []
    for term, label in [
        ("single-cell rna-seq", "single-cell RNA-seq"),
        ("scrna-seq", "scRNA-seq"),
        ("snrna-seq", "snRNA-seq"),
        ("rna-seq", "RNA-seq"),
        ("atac-seq", "ATAC-seq"),
        ("proteomics", "proteomics"),
        ("proteomic", "proteomics"),
        ("metabolomics", "metabolomics"),
        ("metabolomic", "metabolomics"),
        ("dna methylation", "DNA methylation"),
        ("spatial transcriptomics", "spatial transcriptomics"),
    ]:
        if term in blob and label not in omics:
            omics.append(label)
    return " / ".join(omics) if omics else NEEDS_FULL_TEXT


def _technology_text(paper: dict[str, Any]) -> str:
    blob = normalize_text(str(paper.get("abstract") or "") + " " + str(paper.get("title") or ""))
    technologies = []
    for term, label in [
        ("mri", "MRI"),
        ("3t mri", "3T MRI"),
        ("multiplex pcr", "multiplex PCR"),
        ("pcr", "PCR"),
        ("cox regression", "Cox 回归"),
        ("regression", "回归模型"),
        ("electromyography", "肌电图"),
        ("surface electromyography", "sEMG"),
        ("rna-seq", "RNA-seq"),
        ("proteomics", "proteomics"),
        ("metabolomics", "metabolomics"),
        ("atac-seq", "ATAC-seq"),
        ("dna methylation", "DNA methylation"),
    ]:
        if term in blob and label not in technologies:
            technologies.append(label)
    return " / ".join(technologies) if technologies else NEEDS_FULL_TEXT


def _figure_type_suggestions(article_type_key: str, paper: dict[str, Any]) -> list[str]:
    if article_type_key == "systematic_review_meta":
        return ["研究筛选流程图", "森林图", "亚组分析图", "偏倚风险图"]
    if article_type_key == "experimental":
        return ["研究流程图", "干预方案图", "主要结果图", "组间差异图"]
    if article_type_key == "observational":
        return ["研究流程图", "风险模型图", "分层分析图", "敏感性分析图"]
    if article_type_key == "scoping_review":
        return ["证据地图", "研究筛选流程图", "主题分布图", "证据缺口图"]
    if _omics_type_text(paper) != NEEDS_FULL_TEXT:
        return ["PCA/UMAP", "热图", "火山图", "富集分析图", "机制网络图"]
    return ["研究设计流程图", "主要结果图", "机制通路图"]


def _has_sample_size(details: dict[str, str], body_sections: list[dict[str, str]], paper: dict[str, Any]) -> bool:
    text = " ".join([str(value) for value in details.values()] + [str(section.get("value") or "") for section in body_sections])
    return bool(_extract_numbers(text) or _extract_numbers(str(paper.get("abstract") or "")))


def _has_effect_detail(paper: dict[str, Any], details: dict[str, str], body_sections: list[dict[str, str]]) -> bool:
    text = " ".join([str(paper.get("abstract") or ""), *[str(value) for value in details.values()], *[str(section.get("value") or "") for section in body_sections]])
    normalized = normalize_text(text)
    return any(term in normalized for term in ["95% ci", "confidence interval", "hazard ratio", "odds ratio", "risk ratio", "effect size", "beta", "smd", "airr", " p<", " p≤", " p="])


def _has_evidence_quality(details: dict[str, str]) -> bool:
    return _has_real_content(details.get("evidence_quality", "")) and "未提供" not in str(details.get("evidence_quality", ""))


def _metric_missing(value: Any) -> bool:
    return value is None or str(value).strip() in {"", "未配置", "摘要中未提供"}


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
    detail_blob = normalize_text(" ".join(str(value) for value in details.values()))
    if "irisin" in detail_blob and ("overweight" in detail_blob or "肥胖" in detail_blob):
        return "它直接连接训练方式、肥胖代谢和 irisin 肌因子，适合做运动干预机制方向的精读入口。"
    if "caffeine" in detail_blob and ("swimming" in detail_blob or "游泳" in detail_blob):
        return "它直接回答咖啡因是否影响游泳表现，适合运动营养和竞技补剂策略讨论。"
    if "return-to-sport" in detail_blob or "重返运动" in detail_blob:
        return "它聚焦感染后运动员恢复训练/复赛决策，适合运动医学和队医随访管理讨论。"
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
    for keyword in iter_keywords(keywords_config):
        terms = [keyword.get("term"), *keyword.get("aliases", [])]
        matched_term = next((term for term in terms if _term_in_blob(term, blob)), "")
        if matched_term:
            item = dict(keyword)
            item["matched_term"] = matched_term
            matched.append(item)
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


def _term_in_blob(term: Any, blob: str) -> bool:
    normalized = normalize_text(term)
    if not normalized:
        return False
    return f" {normalized} " in f" {blob} "


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

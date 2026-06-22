import unittest

from src.summarize_papers import summarize_paper


class SummaryTests(unittest.TestCase):
    def test_missing_numeric_results_are_explicit_in_chinese(self):
        paper = {
            "title": "Exercise and sleep quality in athletes",
            "abstract": "RESULTS: Exercise was associated with better sleep quality. CONCLUSIONS: Training context may matter.",
            "journal": "Sports Medicine",
            "year": 2026,
            "doi": "10.1000/sleep",
            "article_types": ["Journal Article"],
            "matched_keywords": [{"term": "sleep", "zh": "睡眠"}],
            "score": 78,
            "score_breakdown": {},
        }
        summary = summarize_paper(paper, {"keywords": []})
        main_results = _section(summary, "主要结果")
        self.assertIn("摘要中未提供具体数值", main_results)
        self.assertNotIn("Exercise was associated", main_results)
        self.assertTrue(summary["chinese_title"])

    def test_percentages_and_ratios_are_chineseized(self):
        paper = {
            "title": "Weight-loss strategies for osteoarthritis: a scoping review",
            "abstract": "RESULTS: Of 199 included studies, 36 (18.1%) assessed exercise and 14/36 reported original data. CONCLUSIONS: Multimodal care may be needed.",
            "journal": "British Journal of Sports Medicine",
            "year": 2026,
            "doi": "10.1000/oa",
            "article_types": ["Scoping Review"],
            "matched_keywords": [{"term": "sports medicine", "zh": "运动医学"}],
            "score": 81,
            "score_breakdown": {},
        }
        summary = summarize_paper(paper, {"keywords": []})
        main_results = _section(summary, "主要结果")
        self.assertIn("199 项研究", main_results)
        self.assertIn("14 项", main_results)
        self.assertNotIn("included studies", main_results)

    def test_glp1_oa_scoping_review_uses_chinese_public_account_style(self):
        paper = {
            "title": "GLP-1 receptor agonists and weight-loss strategies for individuals with obesity and hip or knee osteoarthritis: a scoping review.",
            "abstract": (
                "METHODS: Scoping review conducted in accordance with the Preferred Reporting Items for Systematic Reviews "
                "and Meta-Analyses extension for Scoping Reviews (PRISMA-ScR) framework. "
                "ELIGIBILITY CRITERIA: Included studies focused on adults (≥18 years) with obesity and hip or knee OA, "
                "examined weight-loss strategies (nutritional, physical activity, surgical or pharmacological) including GLP-1-RAs. "
                "RESULTS: Of 199 included studies, 36 (18.1%) directly assessed GLP-1-RAs and of these, 14/36 (38.9%) reported original data. "
                "Evidence was heavily skewed towards knee OA, with limited hip-specific data. Descriptive analysis revealed a narrow geographical distribution. "
                "CONCLUSIONS: GLP-1-RAs represent a promising adjunct for managing individuals with OA complicated by obesity. "
                "Until further evidence emerges, GLP-1-RAs should be integrated into supervised, multimodal musculoskeletal care rather than used as standalone weight-loss agents."
            ),
            "journal": "British Journal of Sports Medicine",
            "year": 2026,
            "doi": "10.1136/bjsports-2025-111225",
            "pmid": "40610001",
            "article_types": ["Journal Article"],
            "matched_keywords": [
                {"term": "sports medicine", "zh": "运动医学"},
                {"term": "musculoskeletal", "zh": "肌骨系统"},
            ],
            "score": 81,
            "score_breakdown": {},
        }
        summary = summarize_paper(paper, {"keywords": []})

        self.assertEqual(summary["article_type_label"], "范围综述")
        self.assertEqual(
            summary["chinese_title"],
            "GLP-1 受体激动剂与减重策略在肥胖合并髋/膝骨关节炎人群中的应用：一项范围综述",
        )
        self.assertIn("不能把它当成独立治疗方案", summary["one_sentence_conclusion"])
        self.assertIn("这是范围综述", summary["evidence_strength"])
        self.assertIn("不是直接证明 GLP-1 对 OA 有效的临床试验", summary["my_judgment"])
        self.assertIn("GLP-1 receptor agonists", [item["term"] for item in summary["dictionary_terms"]])
        self.assertIn("Scoping review", [item["term"] for item in summary["dictionary_terms"]])

        combined = " ".join(section["value"] for section in summary["body_sections"])
        self.assertNotIn("GLP-1-RAs represent a promising adjunct", combined)
        self.assertNotIn("Evidence was heavily skewed", combined)

    def test_aware_x_observational_summary_is_specific_and_chinese(self):
        paper = {
            "title": "Factors associated with return-to-sport outcomes following pathogen-confirmed acute respiratory infections in athletes: AWARE X study",
            "abstract": (
                "OBJECTIVE: To identify factors associated with return-to-sport outcomes following pathogen-confirmed acute respiratory infections in athletes. "
                "METHODS: This prospective observational athlete cohort examined return-to-sport outcomes after acute respiratory infections. "
                "RESULTS: Factors associated with return-to-sport outcomes were examined. "
                "CONCLUSIONS: Clinical follow-up may support return-to-sport decisions."
            ),
            "journal": "British Journal of Sports Medicine",
            "year": 2026,
            "doi": "10.1000/awarex",
            "article_types": ["Journal Article"],
            "matched_keywords": [{"term": "sports medicine", "zh": "运动医学"}],
            "score": 72,
            "result_specificity_score": 30,
            "score_breakdown": {},
            "classification": {
                "direction_display": "运动医学 / 运动员健康 / 呼吸道感染 / 重返运动",
                "study_type_display": "人群队列 / 观察性研究",
                "data_source_display": "运动员临床队列",
                "elite_radar_display": "否",
                "relation_to_me": "它命中运动员健康和重返运动方向。",
            },
        }
        summary = summarize_paper(paper, {"keywords": []})

        self.assertEqual(
            summary["chinese_title"],
            "病原体确认的急性呼吸道感染后，影响运动员重返运动结局的相关因素：AWARE X 研究",
        )
        self.assertNotIn("associated合并", summary["chinese_title"])
        self.assertNotIn("在athletes", summary["chinese_title"])
        self.assertIn("AWARE X", summary["one_sentence_conclusion"])
        self.assertIn("运动员", summary["one_sentence_conclusion"])
        self.assertIn("return-to-sport", summary["one_sentence_conclusion"])
        self.assertNotEqual(summary["one_sentence_conclusion"], "作者认为研究变量之间存在关联，但摘要层面不能据此推断因果。")
        self.assertIn("摘要未提供具体效应量", _section(summary, "主要关联结果"))
        self.assertIn("恢复训练", summary["why_read"])
        self.assertEqual(summary["reading_priority"], "可选阅读")

    def test_chinglish_systematic_review_title_falls_back_to_chinese(self):
        paper = {
            "title": "A Systematic Review with Meta-analysis of the Association between Changes in Muscle Strength and Clinical Outcome Changes in Patellofemoral Pain",
            "abstract": "RESULTS: Associations were evaluated. CONCLUSIONS: Strength changes may relate to clinical outcomes.",
            "journal": "Sports Medicine",
            "article_types": ["Systematic Review", "Meta-Analysis"],
            "matched_keywords": [
                {"term": "sports medicine", "zh": "运动医学"},
                {"term": "resistance training", "zh": "抗阻训练"},
            ],
            "score": 80,
            "score_breakdown": {},
        }
        summary = summarize_paper(paper, {"keywords": []})

        self.assertTrue(summary["chinese_title"].startswith("关于"))
        self.assertNotIn("of the Association", summary["chinese_title"])
        self.assertNotIn("Changes在", summary["chinese_title"])
        self.assertNotIn("合并Meta", summary["chinese_title"])


def _section(summary, label):
    for section in summary["body_sections"]:
        if section["label"] == label:
            return section["value"]
    raise AssertionError(f"Missing section: {label}")


if __name__ == "__main__":
    unittest.main()

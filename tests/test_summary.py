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


def _section(summary, label):
    for section in summary["body_sections"]:
        if section["label"] == label:
            return section["value"]
    raise AssertionError(f"Missing section: {label}")


if __name__ == "__main__":
    unittest.main()

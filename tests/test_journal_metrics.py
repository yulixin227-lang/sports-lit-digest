import tempfile
import unittest
from pathlib import Path

from src.journal_metrics import get_journal_metrics, load_journal_metrics_config
from src.render_digest import render_digest
from src.utils import ROOT


class JournalMetricsTests(unittest.TestCase):
    def test_british_journal_matches_display_name(self):
        config = load_journal_metrics_config()

        metrics = get_journal_metrics("British journal of sports medicine", config)

        self.assertTrue(metrics["configured"])
        self.assertEqual(metrics["display_name"], "British Journal of Sports Medicine")
        self.assertEqual(metrics["jcr_quartile"], "Q1")
        self.assertEqual(metrics["cas_zone"], "一区")

    def test_matching_is_case_insensitive(self):
        config = load_journal_metrics_config()

        metrics = get_journal_metrics("BRITISH JOURNAL OF SPORTS MEDICINE", config)

        self.assertEqual(metrics["display_name"], "British Journal of Sports Medicine")

    def test_unknown_journal_returns_unconfigured_values(self):
        metrics = get_journal_metrics("Unknown Exercise Journal", {"journals": {}})

        self.assertFalse(metrics["configured"])
        self.assertEqual(metrics["impact_factor_display"], "未配置")
        self.assertEqual(metrics["jcr_quartile"], "未配置")
        self.assertEqual(metrics["cas_zone"], "未配置")
        self.assertEqual(metrics["metrics_source"], "未配置")

    def test_null_impact_factor_renders_as_unconfigured(self):
        config = load_journal_metrics_config()
        metrics = get_journal_metrics("British Journal of Sports Medicine", config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "outputs"
            md_path, _ = render_digest(
                papers=[
                    {
                        "focus_topics": ["肌骨康复"],
                        "score": 81,
                        "chinese_title": "测试文章",
                        "title": "Example sports medicine paper",
                        "journal": "British Journal of Sports Medicine",
                        "journal_metrics": metrics,
                        "year": 2026,
                        "doi": "10.1000/example",
                        "pmid": "123456",
                        "article_type_label": "范围综述",
                        "stars": "★★★★☆",
                        "recommendation_index": "4.5/5",
                        "keywords_display": "sports medicine",
                        "link": "https://pubmed.ncbi.nlm.nih.gov/123456/",
                        "evidence_strength": "这是范围综述。",
                        "body_sections": [],
                        "dictionary_terms": [],
                    }
                ],
                output_dir=output_dir,
                template_dir=ROOT / "templates",
                digest_date="2026-06-20",
                start_date="2026-06-18",
                end_date="2026-06-20",
                metadata={"fetched_count": 1},
            )
            markdown = md_path.read_text(encoding="utf-8")

        self.assertIn("影响因子：未配置", markdown)
        self.assertIn("JCR分区：Q1 / Sport Sciences", markdown)
        self.assertNotIn("null", markdown.lower())


if __name__ == "__main__":
    unittest.main()

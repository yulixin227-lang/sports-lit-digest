import tempfile
import unittest
from pathlib import Path

from src.render_digest import render_digest


class RenderDigestTests(unittest.TestCase):
    def test_render_digest_writes_pages_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "outputs"
            template_dir = root / "templates"
            template_dir.mkdir()
            (template_dir / "daily_digest.md.j2").write_text(
                "# 每日运动科学文献简报 | {{ date }}\n\n"
                "* 最终推荐：{{ overview.selected_count }} 篇\n"
                "* 本期重点方向：{{ overview.focus_topics }}\n",
                encoding="utf-8",
            )
            (template_dir / "daily_digest.html.j2").write_text(
                "<!doctype html><html><body>{{ date }}</body></html>",
                encoding="utf-8",
            )

            render_digest(
                papers=[
                    {
                        "focus_topics": ["肌骨康复", "肥胖"],
                        "score": 81,
                        "chinese_title": "测试文章",
                        "title": "Example sports medicine paper",
                        "journal": "British Journal of Sports Medicine",
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
                template_dir=template_dir,
                digest_date="2026-06-20",
                start_date="2026-06-18",
                end_date="2026-06-20",
                metadata={"fetched_count": 4},
            )

            index_html = (output_dir / "index.html").read_text(encoding="utf-8")

        self.assertIn("每日运动科学文献简报", index_html)
        self.assertIn("2026-06-20-digest.html", index_html)
        self.assertIn("最终推荐 1 篇", index_html)
        self.assertIn("肌骨康复 / 肥胖", index_html)
        self.assertIn("?stay=1", index_html)


if __name__ == "__main__":
    unittest.main()

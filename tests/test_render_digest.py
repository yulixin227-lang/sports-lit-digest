import tempfile
import unittest
from pathlib import Path

from src.render_digest import render_digest
from src.utils import ROOT


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

    def test_render_digest_includes_presentation_and_ppt_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "outputs"
            papers = [
                _presentation_test_paper(
                    title="Lower relevance high score paper",
                    chinese_title="质量分较高但不适合组会的文章",
                    score=95,
                    presentation_score=42,
                    suitability="可选",
                ),
                _presentation_test_paper(
                    title="High-intensity interval training improves VO2max in adults with obesity",
                    chinese_title="高强度间歇训练改善肥胖成年人 VO2max 的研究",
                    score=82,
                    presentation_score=86,
                    suitability="适合",
                ),
            ]

            md_path, html_path = render_digest(
                papers=papers,
                output_dir=output_dir,
                template_dir=ROOT / "templates",
                digest_date="2026-06-22",
                start_date="2026-06-16",
                end_date="2026-06-22",
                metadata={"fetched_count": 8},
            )

            md_text = md_path.read_text(encoding="utf-8")
            html_text = html_path.read_text(encoding="utf-8")

        self.assertIn("今日最适合组会讲：第 2 篇", md_text)
        self.assertIn("组会汇报素材", html_text)
        self.assertIn("PPT 生成准备信息", html_text)
        self.assertIn("需要人工核对", html_text)
        self.assertIn("当前未读取全文 PDF，Figure 内容需人工核对原文。", html_text)
        self.assertIn("需阅读全文并提取原文 Figure 后确定", html_text)
        self.assertNotIn("Fig 1 显示", html_text)
        self.assertNotIn("Fig 2 展示", html_text)
        self.assertIn("样本量", html_text)
        self.assertIn("组学类型", html_text)
        self.assertIn("摘要未明确说明，需阅读全文确认。", html_text)


def _presentation_test_paper(
    *,
    title: str,
    chinese_title: str,
    score: int,
    presentation_score: int,
    suitability: str,
) -> dict:
    return {
        "focus_topics": ["运动干预", "肥胖代谢"],
        "score": score,
        "chinese_title": chinese_title,
        "title": title,
        "english_title": title,
        "brief_summary": "这项研究围绕肥胖成年人训练干预与 VO2max 改善展开，摘要提供了研究问题和主要结局。",
        "journal": "British Journal of Sports Medicine",
        "year": 2026,
        "doi": "10.1000/example",
        "pmid": "123456",
        "article_type_label": "RCT / 干预研究",
        "stars": "★★★★☆",
        "recommendation_index": "4.0/5",
        "keywords_display": "HIIT, VO2max, obesity",
        "link": "https://pubmed.ncbi.nlm.nih.gov/123456/",
        "evidence_strength": "这是 RCT，因果证据较强，但仍需检查样本量、盲法和随访时间。",
        "why_worth_reading": "它直接回答训练干预是否改善肥胖成年人心肺适能的问题。",
        "relation_to_me": "这篇适合连接运动干预、肥胖代谢和心肺适能研究。",
        "reading_priority": "推荐阅读",
        "result_specificity_display": "高：摘要提供了较具体的结果信息。",
        "direction_display": "运动干预 / 肥胖代谢",
        "study_type_display": "RCT / 人体干预研究",
        "data_source_display": "临床试验",
        "elite_radar_display": "否",
        "journal_metrics": {
            "display_name": "British Journal of Sports Medicine",
            "impact_factor_display": "未配置",
            "jcr_display": "Q1 / Sport Sciences",
            "cas_display": "一区 / 体育科学",
            "metrics_year_display": "未配置",
            "metrics_source": "manual",
        },
        "body_sections": [
            {"label": "研究问题", "value": "这项研究想知道 HIIT 是否改善肥胖成年人的 VO2max。"},
            {"label": "主要结果", "value": "摘要未明确说明具体效应量，需阅读全文确认。"},
        ],
        "presentation_value_score": presentation_score,
        "presentation_materials": {
            "score": presentation_score,
            "suitability": suitability,
            "priority": "高" if suitability == "适合" else "中",
            "reason": "研究问题、干预和主要结局清晰，适合讲研究设计。",
            "core_talking_point": "适合讲 HIIT 如何作为肥胖代谢和心肺适能研究的干预范式。",
            "storyline": [
                "作者关注肥胖人群心肺适能不足的问题。",
                "这篇文章想解决不同训练方式是否改善 VO2max 的问题。",
                "最值得讲的是 PICO 设计和主要结局选择。",
            ],
            "key_data": [
                {"label": "样本量", "value": "摘要未明确说明，需阅读全文确认。"},
                {"label": "研究对象", "value": "肥胖成年人"},
                {"label": "组学类型", "value": "摘要未明确说明，需阅读全文确认。"},
            ],
            "important_conclusions": ["HIIT 可能改善肥胖成年人 VO2max，但具体效应量需阅读全文确认。"],
            "peer_inspiration": ["学习它如何把人群、干预和主要结局串成清晰 PICO。"],
        },
        "ppt_preparation": {
            "short_pages": "3-5 页",
            "deep_pages": "8-12 页",
            "full_text_notice": "当前未读取全文 PDF，Figure 内容需人工核对原文。",
            "structure": [
                {"title": "第 1 页：文章信息", "bullets": ["中文题目、英文题目、期刊和 DOI。"]},
                {
                    "title": "第 4 页起：关键 Figure 讲解页",
                    "bullets": [
                        "Fig 1：需阅读全文并提取原文 Figure 后确定。",
                        "建议优先查看的 Figure 类型：研究设计流程图、主要结果图。",
                    ],
                },
            ],
            "figure_principles": [
                "PPT 必须使用文章原图。",
                "不允许自己编造图片。",
                "文献名和 DOI 放在每页底部。",
            ],
        },
        "missing_info": ["全文 PDF", "原文 Figure", "样本量", "组学类型", "具体效应量"],
        "dictionary_terms": [],
    }


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.send_wxpusher import (
    WXPUSHER_SEND_URL,
    WXPUSHER_SIMPLE_SEND_URL,
    build_wechat_message,
    extract_spt_from_url,
    send_wxpusher_digest,
    split_markdown_by_paragraph,
)


class WxPusherTests(unittest.TestCase):
    def test_build_message_uses_public_digest_base_url(self):
        paper = {
            "chinese_title": "GLP-1 受体激动剂与减重策略在肥胖合并髋/膝骨关节炎人群中的应用：一项范围综述",
            "article_type_label": "范围综述",
            "stars": "★★★★☆",
            "recommendation_index": "4.5/5",
            "score": 81,
            "reading_priority": "优先阅读",
            "result_specificity_display": "高：摘要提供了较具体的结果信息。",
            "one_sentence_conclusion": "这篇范围综述认为，GLP-1 受体激动剂可能是辅助工具。",
            "evidence_strength": "这是范围综述，只能说明研究现状和证据缺口，不能直接证明干预有效。",
            "body_sections": [
                {"label": "为什么值得看", "value": "它把肥胖、骨关节炎和运动康复放在同一张证据地图里。"},
                {"label": "研究问题", "value": "这篇综述在梳理减重策略证据。"},
                {"label": "结局指标", "value": "体重管理和骨关节炎相关结局。"},
                {"label": "实践启发", "value": "把运动、营养和药物减重放在同一方案中思考。"},
            ],
            "focus_topics": ["肌骨康复", "肥胖"],
            "direction_display": "肥胖异质性 / 公开数据库",
            "study_type_display": "公开数据库 / 人群队列",
            "data_source_display": "摘要中未提供",
            "journal_metrics": {
                "display_name": "British Journal of Sports Medicine",
                "jcr_quartile": "Q1",
                "cas_zone": "一区",
                "impact_factor_display": "未配置",
            },
            "top_pick_reason": "它能快速说明一个交叉方向的证据版图和研究缺口。",
        }
        with patch.dict(os.environ, {"PUBLIC_DIGEST_BASE_URL": "https://example.com/digests"}, clear=False):
            message = build_wechat_message(
                papers=[paper],
                metadata={"fetched_count": 4},
                digest_date="2026-06-20",
                start_date="2026-06-18",
                end_date="2026-06-20",
                html_path=Path("outputs/2026-06-20-digest.html"),
            )

        self.assertIn("今日概览", message["content"])
        self.assertIn("最终推荐：1 篇", message["content"])
        self.assertIn("【文章 1】", message["content"])
        self.assertIn("【研究问题】", message["content"])
        self.assertIn("【核心发现】", message["content"])
        self.assertIn("【为什么值得看】", message["content"])
        self.assertIn("【实践意义】", message["content"])
        self.assertIn("【证据边界】", message["content"])
        self.assertIn("期刊：British Journal of Sports Medicine｜JCR：Q1｜中科院：一区｜IF：未配置", message["content"])
        self.assertIn("方向：肥胖异质性 / 公开数据库", message["content"])
        self.assertIn("研究类型：公开数据库 / 人群队列", message["content"])
        self.assertIn("数据/样本：摘要中未提供", message["content"])
        self.assertIn("这篇综述在梳理减重策略证据。", message["content"])
        self.assertIn("这篇范围综述认为，GLP-1 受体激动剂可能是辅助工具。", message["content"])
        self.assertIn("把运动、营养和药物减重放在同一方案中思考。", message["content"])
        self.assertIn("这是范围综述，只能说明研究现状和证据缺口", message["content"])
        self.assertIn("【阅读全文】", message["content"])
        self.assertIn("【历史简报】", message["content"])
        self.assertNotIn("## 今日推荐", message["content"])
        self.assertIn("https://example.com/digests/2026-06-20-digest.html", message["content"])
        self.assertIn("[https://example.com/digests/](https://example.com/digests/)", message["content"])
        self.assertEqual(message["public_url"], "https://example.com/digests/2026-06-20-digest.html")

    def test_build_message_warns_when_only_local_digest_path_is_available(self):
        with patch.dict(os.environ, {"PUBLIC_DIGEST_BASE_URL": ""}, clear=False):
            message = build_wechat_message(
                papers=[],
                metadata={"fetched_count": 0},
                digest_date="2026-06-20",
                start_date="2026-06-20",
                end_date="2026-06-20",
                html_path=Path("outputs/2026-06-20-digest.html"),
            )

        self.assertIn("手机微信可能无法打开本地路径", message["content"])
        self.assertIn("outputs", message["content"])

    def test_dry_run_does_not_require_credentials(self):
        with patch.dict(
            os.environ,
            {
                "WXPUSHER_ENABLED": "false",
                "WXPUSHER_APP_TOKEN": "",
                "WXPUSHER_UIDS": "",
                "WXPUSHER_TOPIC_IDS": "",
                "PUBLIC_DIGEST_BASE_URL": "",
            },
            clear=False,
        ):
            result = send_wxpusher_digest(
                papers=[],
                metadata={"fetched_count": 0},
                digest_date="2026-06-20",
                start_date="2026-06-20",
                end_date="2026-06-20",
                html_path=Path("outputs/2026-06-20-digest.html"),
                dry_run=True,
            )

        self.assertFalse(result.sent)
        self.assertTrue(result.skipped)
        self.assertIn("每日运动科学文献简报", result.preview)
        self.assertTrue(any("dry-run" in warning for warning in result.warnings))

    def test_extract_spt_from_full_url(self):
        url = "https://wxpusher.zjiecode.com/api/send/message/SPT_abc123xyz/Hello%20WxPusher"
        self.assertEqual(extract_spt_from_url(url), "SPT_abc123xyz")
        self.assertEqual(extract_spt_from_url("SPT_directToken"), "SPT_directToken")

    def test_standard_mode_has_priority_over_spt_when_configured(self):
        with patch.dict(
            os.environ,
            {
                "WXPUSHER_SPT_ENABLED": "true",
                "WXPUSHER_SPT_URL": "https://wxpusher.zjiecode.com/api/send/message/SPT_abc123xyz/Hello",
                "WXPUSHER_ENABLED": "true",
                "WXPUSHER_APP_TOKEN": "AT_standard",
                "WXPUSHER_UIDS": "",
                "WXPUSHER_TOPIC_IDS": "123,456",
                "PUBLIC_DIGEST_BASE_URL": "",
            },
            clear=False,
        ):
            result = send_wxpusher_digest(
                papers=[],
                metadata={"fetched_count": 0},
                digest_date="2026-06-20",
                start_date="2026-06-20",
                end_date="2026-06-20",
                html_path=Path("outputs/2026-06-20-digest.html"),
                dry_run=True,
            )

        self.assertEqual(result.mode, "standard")
        self.assertIn("SPT_ab", result.target_spt)
        self.assertEqual(result.target_topic_ids, [123, 456])
        self.assertFalse(result.sent)

    def test_standard_send_supports_topic_ids_without_uids(self):
        calls = []

        def fake_post_json(url, payload):
            calls.append((url, payload))
            return {"code": 1000, "success": True, "data": [{"code": 1000, "topicId": 123}]}

        with patch.dict(
            os.environ,
            {
                "WXPUSHER_SPT_ENABLED": "false",
                "WXPUSHER_SPT_URL": "",
                "WXPUSHER_ENABLED": "true",
                "WXPUSHER_APP_TOKEN": "AT_standard",
                "WXPUSHER_UIDS": "",
                "WXPUSHER_TOPIC_IDS": "123,456",
                "PUBLIC_DIGEST_BASE_URL": "https://example.com/digests",
            },
            clear=False,
        ):
            with patch("src.send_wxpusher._post_json", side_effect=fake_post_json):
                result = send_wxpusher_digest(
                    papers=[],
                    metadata={"fetched_count": 0},
                    digest_date="2026-06-20",
                    start_date="2026-06-20",
                    end_date="2026-06-20",
                    html_path=Path("outputs/2026-06-20-digest.html"),
                    dry_run=False,
                )

        self.assertTrue(result.sent)
        self.assertEqual(result.mode, "standard")
        self.assertEqual(calls[0][0], WXPUSHER_SEND_URL)
        self.assertEqual(calls[0][1]["appToken"], "AT_standard")
        self.assertEqual(calls[0][1]["topicIds"], [123, 456])
        self.assertNotIn("uids", calls[0][1])

    def test_spt_send_uses_simple_push_post_payload(self):
        calls = []

        def fake_post_json(url, payload):
            calls.append((url, payload))
            return {"code": 1000, "success": True, "data": []}

        with patch.dict(
            os.environ,
            {
                "WXPUSHER_SPT_ENABLED": "true",
                "WXPUSHER_SPT_URL": "https://wxpusher.zjiecode.com/api/send/message/SPT_abc123xyz/Hello",
                "WXPUSHER_ENABLED": "false",
                "WXPUSHER_APP_TOKEN": "",
                "WXPUSHER_UIDS": "",
                "PUBLIC_DIGEST_BASE_URL": "https://example.com/digests",
            },
            clear=False,
        ):
            with patch("src.send_wxpusher._post_json", side_effect=fake_post_json):
                result = send_wxpusher_digest(
                    papers=[],
                    metadata={"fetched_count": 0},
                    digest_date="2026-06-20",
                    start_date="2026-06-20",
                    end_date="2026-06-20",
                    html_path=Path("outputs/2026-06-20-digest.html"),
                    dry_run=False,
                )

        self.assertTrue(result.sent)
        self.assertEqual(calls[0][0], WXPUSHER_SIMPLE_SEND_URL)
        self.assertEqual(calls[0][1]["spt"], "SPT_abc123xyz")
        self.assertEqual(calls[0][1]["contentType"], 3)
        self.assertIn("每日运动科学文献简报", calls[0][1]["content"])
        self.assertEqual(calls[0][1]["url"], "https://example.com/digests/2026-06-20-digest.html")

    def test_full_digest_chunks_on_paragraph_boundaries(self):
        markdown = "# 每日运动科学文献简报 | 2026-06-20\n\n" + "\n\n".join(
            f"## 第 {index} 篇\n\n这是一段完整内容，用来测试微信完整正文推送的段落边界。"
            for index in range(1, 80)
        )
        chunks = split_markdown_by_paragraph(markdown, max_chars=1000)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1000 for chunk in chunks))
        self.assertFalse(any("这是一段完整" in chunk and "段落边界" not in chunk for chunk in chunks))

    def test_full_digest_send_uses_markdown_file_and_multiple_posts(self):
        calls = []

        def fake_post_json(url, payload):
            calls.append((url, payload))
            return {"code": 1000, "success": True, "data": [{"code": 1000, "status": "ok"}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "2026-06-20-digest.md"
            md_path.write_text(
                "# 每日运动科学文献简报 | 2026-06-20\n\n"
                + "\n\n".join(
                    f"## 第 {index} 篇\n\n这是一段完整内容，用来测试微信完整正文推送的段落边界。"
                    for index in range(1, 80)
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "WXPUSHER_SPT_ENABLED": "true",
                    "WXPUSHER_SPT_URL": "https://wxpusher.zjiecode.com/api/send/message/SPT_abc123xyz/Hello",
                    "WXPUSHER_ENABLED": "false",
                    "PUBLIC_DIGEST_BASE_URL": "",
                    "WXPUSHER_FULL_CHUNK_CHARS": "1000",
                },
                clear=False,
            ):
                with patch("src.send_wxpusher._post_json", side_effect=fake_post_json):
                    result = send_wxpusher_digest(
                        papers=[],
                        metadata={"fetched_count": 0},
                        digest_date="2026-06-20",
                        start_date="2026-06-20",
                        end_date="2026-06-20",
                        html_path=md_path.with_suffix(".html"),
                        dry_run=False,
                        full_body=True,
                        markdown_path=md_path,
                    )

        self.assertTrue(result.sent)
        self.assertGreater(result.chunk_count, 1)
        self.assertEqual(len(calls), result.chunk_count)
        self.assertTrue(all(call[0] == WXPUSHER_SIMPLE_SEND_URL for call in calls))
        self.assertIn("每日运动科学文献简报 | 2026-06-20", calls[0][1]["content"])
        self.assertTrue(any("（1/" in call[1]["content"] for call in calls))
        self.assertTrue(any("继续下一条" in call[1]["content"] for call in calls[:-1]))
        self.assertIn("本期结束", calls[-1][1]["content"])

    def test_full_digest_includes_public_html_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "2026-06-20-digest.md"
            html_path = Path(tmpdir) / "2026-06-20-digest.html"
            md_path.write_text("# 每日运动科学文献简报 | 2026-06-20\n\n正文。", encoding="utf-8")

            with patch.dict(
                os.environ,
                {"PUBLIC_DIGEST_BASE_URL": "https://yulixin227-lang.github.io/sports-lit-digest"},
                clear=False,
            ):
                result = send_wxpusher_digest(
                    papers=[],
                    metadata={"fetched_count": 0},
                    digest_date="2026-06-20",
                    start_date="2026-06-20",
                    end_date="2026-06-20",
                    html_path=html_path,
                    dry_run=True,
                    wechat_mode="full",
                    markdown_path=md_path,
                )

        self.assertIn(
            "https://yulixin227-lang.github.io/sports-lit-digest/2026-06-20-digest.html",
            result.preview,
        )
        self.assertNotIn("手机微信可能无法打开本地路径", result.preview)


if __name__ == "__main__":
    unittest.main()

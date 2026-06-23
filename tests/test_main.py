import unittest

from src.main import (
    count_optional_observation,
    empty_seen,
    resolve_wechat_mode,
    should_send_empty_status,
    should_skip_wechat_push,
)


class MainFlowTests(unittest.TestCase):
    def test_skip_empty_push_only_for_real_empty_wechat_send(self):
        self.assertTrue(
            should_skip_wechat_push(
                send_wechat=True,
                dry_run=False,
                skip_empty_push=True,
                selected_count=0,
                send_empty_status=False,
                fetched_count=2,
            )
        )
        self.assertFalse(
            should_skip_wechat_push(
                send_wechat=True,
                dry_run=True,
                skip_empty_push=True,
                selected_count=0,
                send_empty_status=False,
                fetched_count=2,
            )
        )

    def test_resolve_wechat_smart_mode(self):
        self.assertEqual(resolve_wechat_mode("smart", 0), "short")
        self.assertEqual(resolve_wechat_mode("smart", 1), "full")
        self.assertEqual(resolve_wechat_mode("smart", 2), "short")
        self.assertEqual(resolve_wechat_mode("short", 1), "short")
        self.assertEqual(resolve_wechat_mode("full", 3), "full")
        self.assertFalse(
            should_skip_wechat_push(
                send_wechat=True,
                dry_run=False,
                skip_empty_push=True,
                selected_count=1,
                send_empty_status=True,
                fetched_count=2,
            )
        )
        self.assertFalse(
            should_skip_wechat_push(
                send_wechat=True,
                dry_run=False,
                skip_empty_push=False,
                selected_count=0,
                send_empty_status=False,
                fetched_count=2,
            )
        )

    def test_empty_status_prevents_skip_when_enabled(self):
        self.assertTrue(
            should_send_empty_status(
                send_wechat=True,
                selected_count=0,
                fetched_count=3,
                send_empty_status=True,
                force_send=False,
            )
        )
        self.assertFalse(
            should_skip_wechat_push(
                send_wechat=True,
                dry_run=False,
                skip_empty_push=True,
                selected_count=0,
                send_empty_status=True,
                fetched_count=3,
            )
        )

    def test_empty_status_can_be_forced_for_cloud_push_test(self):
        self.assertTrue(
            should_send_empty_status(
                send_wechat=True,
                selected_count=0,
                fetched_count=0,
                send_empty_status=True,
                force_send=True,
            )
        )
        self.assertFalse(
            should_send_empty_status(
                send_wechat=True,
                selected_count=0,
                fetched_count=0,
                send_empty_status=False,
                force_send=True,
            )
        )

    def test_optional_observation_count_excludes_main_selected(self):
        scored = [
            {"doi": "10.1/a", "title": "A"},
            {"doi": "10.1/b", "title": "B"},
            {"pmid": "123", "title": "C"},
        ]
        selected = [{"doi": "10.1/b", "title": "B"}]
        self.assertEqual(count_optional_observation(scored, selected), 2)

    def test_empty_seen_for_force_send(self):
        seen = empty_seen()
        self.assertEqual(seen, {"dois": set(), "pmids": set()})


if __name__ == "__main__":
    unittest.main()

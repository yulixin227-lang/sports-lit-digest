import unittest

from src.main import empty_seen, resolve_wechat_mode, should_skip_wechat_push


class MainFlowTests(unittest.TestCase):
    def test_skip_empty_push_only_for_real_empty_wechat_send(self):
        self.assertTrue(
            should_skip_wechat_push(
                send_wechat=True,
                dry_run=False,
                skip_empty_push=True,
                selected_count=0,
            )
        )
        self.assertFalse(
            should_skip_wechat_push(
                send_wechat=True,
                dry_run=True,
                skip_empty_push=True,
                selected_count=0,
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
            )
        )
        self.assertFalse(
            should_skip_wechat_push(
                send_wechat=True,
                dry_run=False,
                skip_empty_push=False,
                selected_count=0,
            )
        )

    def test_empty_seen_for_force_send(self):
        seen = empty_seen()
        self.assertEqual(seen, {"dois": set(), "pmids": set()})


if __name__ == "__main__":
    unittest.main()

import unittest

from scripts.ci.codex_task import existing_attempt


class CodexTaskTest(unittest.TestCase):
    def test_closed_failed_attempt_prevents_automatic_retry(self):
        issue = {'number': 3, 'state': 'closed', 'body': '<!-- wechatpad-adaptation:3200-abc -->\nStatus: NEEDS_HOOK_REVIEW'}
        self.assertEqual(issue, existing_attempt([issue], '3200-abc'))

    def test_other_build_or_partial_hash_does_not_block_candidate(self):
        self.assertIsNone(existing_attempt([{'number': 4, 'body': '<!-- wechatpad-adaptation:3200-abcd -->'}], '3200-abc'))


if __name__ == '__main__':
    unittest.main()

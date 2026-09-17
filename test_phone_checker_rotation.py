import unittest
from datetime import datetime, timezone, timedelta

from phone_checker_rotation import choose_account, mark_flood_wait, mark_assigned


class RotationTests(unittest.TestCase):
    def test_round_robin_uses_next_account(self):
        accounts = ['a', 'b', 'c']
        state = {}
        self.assertEqual(choose_account(accounts, state, 0, datetime(2026, 9, 16, tzinfo=timezone.utc)), ('a', 0))
        self.assertEqual(choose_account(accounts, state, 1, datetime(2026, 9, 16, tzinfo=timezone.utc)), ('b', 1))
        self.assertEqual(choose_account(accounts, state, 2, datetime(2026, 9, 16, tzinfo=timezone.utc)), ('c', 2))

    def test_account_is_unavailable_after_ten_assignments(self):
        now = datetime(2026, 9, 16, tzinfo=timezone.utc)
        state = {}
        for _ in range(10):
            mark_assigned(state, 'a', now)
        self.assertEqual(choose_account(['a', 'b'], state, 0, now), ('b', 1))

    def test_flood_wait_pauses_account_for_24_hours(self):
        now = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
        state = {}
        mark_flood_wait(state, 'a', now)
        self.assertEqual(choose_account(['a', 'b'], state, 0, now), ('b', 1))
        later = now + timedelta(hours=24, seconds=1)
        self.assertEqual(choose_account(['a', 'b'], state, 0, later), ('a', 0))


if __name__ == '__main__':
    unittest.main()

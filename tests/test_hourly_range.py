import unittest
from datetime import datetime, timezone

from app.api.routes import _hourly_range_from_rows


class HourlyRangeTests(unittest.TestCase):
    def test_aligned_24h_window_returns_24_buckets(self):
        since = datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc)
        until = datetime(2026, 7, 7, 21, 0, tzinfo=timezone.utc)
        rows = [
            {"period": datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc), "total": 2},
            {"period": datetime(2026, 7, 7, 20, 0, tzinfo=timezone.utc), "total": 1},
        ]

        result = _hourly_range_from_rows(rows, since, until)

        self.assertEqual(len(result), 24)
        self.assertEqual(result[0].period, since)
        self.assertEqual(result[-1].period, datetime(2026, 7, 7, 20, 0, tzinfo=timezone.utc))
        self.assertEqual(result[0].total, 2)
        self.assertEqual(result[-1].total, 1)

    def test_partial_end_uses_next_hour_bucket(self):
        since = datetime(2026, 7, 6, 21, 15, tzinfo=timezone.utc)
        until = datetime(2026, 7, 7, 21, 45, tzinfo=timezone.utc)

        result = _hourly_range_from_rows([], since, until)

        self.assertEqual(len(result), 25)
        self.assertEqual(result[0].period, datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc))
        self.assertEqual(result[-1].period, datetime(2026, 7, 7, 21, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()

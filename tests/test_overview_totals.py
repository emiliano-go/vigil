import unittest
from unittest.mock import patch

from app.api import routes


class OverviewTotalsTests(unittest.TestCase):
    def test_overview_uses_distinct_sha_count(self):
        responses = [
            [{"total_commits": 4219}],
            [{"total_authors": 7}],
            [{"total_repos": 12}],
            [{"period": "2026-07-07", "total": 1}],
            [{"repo": "emiliano-go/vigil", "total": 1}],
        ]

        with patch.object(routes, "_query_dicts", side_effect=responses) as query:
            result = routes.overview_stats()

        self.assertEqual(result.total_commits, 4219)
        self.assertIn("uniqExact(sha)", query.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()

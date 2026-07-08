import unittest
from unittest.mock import patch

from app.api import routes


class OverviewTotalsTests(unittest.TestCase):
    def test_overview_uses_github_total_contributions(self):
        responses = [
            [{"total_authors": 7}],
            [{"total_repos": 12}],
            [{"period": "2026-07-07", "total": 1}],
            [{"repo": "emiliano-go/vigil", "total": 1}],
        ]

        with patch.object(routes, "get_viewer_login", return_value="emiliano-go") as viewer_login:
            with patch.object(routes, "get_total_contributions", return_value=4800) as total_contrib:
                with patch.object(routes, "_query_dicts", side_effect=responses) as query:
                    result = routes.overview_stats()

        viewer_login.assert_called_once()
        total_contrib.assert_called_once_with("emiliano-go", start_year=2022)
        self.assertEqual(result.total_commits, 4800)
        self.assertTrue(any("uniqExactIf" in call.args[0] for call in query.call_args_list))


if __name__ == "__main__":
    unittest.main()

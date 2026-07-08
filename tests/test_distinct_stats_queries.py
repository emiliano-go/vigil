import unittest
from datetime import date, datetime
from unittest.mock import patch

from app.api import routes


class DistinctStatsQueryTests(unittest.TestCase):
    def test_stats_endpoints_use_distinct_sha_queries(self):
        seen_sql: list[str] = []

        def fake_query(sql: str, parameters=None):
            seen_sql.append(sql)
            if "total_commits" in sql:
                return [{"total_commits": 4219}]
            if "total_authors" in sql:
                return [{"total_authors": 7}]
            if "total_repos" in sql:
                return [{"total_repos": 12}]
            if "uniqExactIf" in sql and "merge_commits" in sql:
                return [{"total": 10, "merge_commits": 2, "regular_commits": 8}]
            if "toDate(committed_at) AS period, repo, uniqExact(sha) AS total" in sql:
                return [{"period": date(2026, 7, 7), "repo": "emiliano-go/vigil", "total": 1}]
            if "toStartOfMonth(committed_at) AS period, repo, uniqExact(sha) AS total" in sql:
                return [{"period": date(2026, 7, 1), "repo": "emiliano-go/vigil", "total": 1}]
            if "toStartOfWeek(committed_at) AS period, repo, uniqExact(sha) AS total" in sql:
                return [{"period": date(2026, 7, 7), "repo": "emiliano-go/vigil", "total": 1}]
            if "toStartOfYear(committed_at) AS period, repo, uniqExact(sha) AS total" in sql:
                return [{"period": date(2026, 1, 1), "repo": "emiliano-go/vigil", "total": 1}]
            if "toDate(committed_at) AS period, uniqExact(sha) AS total" in sql and "author_login" in sql:
                return [{"period": date(2026, 7, 7), "author_login": "emiliano-go", "total": 1}]
            if "toDate(committed_at) AS period, uniqExact(sha) AS total" in sql:
                return [{"period": date(2026, 7, 7), "total": 1}]
            if "toHour(committed_at) AS hour, uniqExact(sha) AS total" in sql:
                return [{"repo": "emiliano-go/vigil", "hour": 12, "total": 1}]
            if "toStartOfHour(committed_at) AS period, uniqExact(sha) AS total" in sql:
                return [{"period": datetime(2026, 7, 7, 0, 0), "total": 1}]
            if "toStartOfWeek(committed_at) AS period, uniqExact(sha) AS total" in sql:
                return [{"period": date(2026, 7, 7), "total": 1}]
            if "toStartOfYear(committed_at) AS period, uniqExact(sha) AS total" in sql:
                return [{"period": date(2026, 1, 1), "total": 1}]
            if "repo, uniqExact(sha) AS total FROM commits" in sql:
                return [{"repo": "emiliano-go/vigil", "total": 1}]
            if "uniqExact(sha) AS total_commits" in sql:
                return [{"total_commits": 4219}]
            return []

        with patch.object(routes, "get_viewer_login", return_value="emiliano-go"):
            with patch.object(routes, "get_total_contributions", return_value=4800):
                with patch.object(routes, "_query_dicts", side_effect=fake_query):
                    routes.daily_stats("emiliano-go/vigil")
                    routes.daily_author_stats(author_login="emiliano-go")
                    routes.monthly_stats("emiliano-go/vigil")
                    routes.author_stats("emiliano-go/vigil")
                    routes.hourly_stats("emiliano-go/vigil")
                    routes.hourly_stats_for_author("emiliano-go", "emiliano-go/vigil")
                    routes.hourly_stats_for_author_range("emiliano-go", datetime(2026, 7, 6), datetime(2026, 7, 7))
                    routes.weekly_stats("emiliano-go/vigil")
                    routes.yearly_stats("emiliano-go/vigil")
                    routes.top_repos()
                    routes.merge_ratio("emiliano-go/vigil")
                    routes.overview_stats()

        self.assertTrue(any("uniqExact(sha)" in sql for sql in seen_sql))
        self.assertFalse(any("commits_per_day" in sql for sql in seen_sql))
        self.assertFalse(any("commits_per_month" in sql for sql in seen_sql))
        self.assertFalse(any("hourly_activity" in sql for sql in seen_sql))
        self.assertFalse(any("author_commit_counts" in sql for sql in seen_sql))
        self.assertFalse(any("count() AS total" in sql and "commits" in sql for sql in seen_sql))
        self.assertTrue(any("today() - %(days)s" in sql for sql in seen_sql))


if __name__ == "__main__":
    unittest.main()

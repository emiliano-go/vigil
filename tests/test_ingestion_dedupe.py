import unittest
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.api import routes
from app.flow import tasks


class IngestionDedupeTests(unittest.TestCase):
    def test_fetch_commits_dedupes_and_stops_at_last_synced_sha(self):
        commits = [object(), object(), object(), object()]
        extracted = [
            {"sha": "new-1", "author_name": "A", "author_email": "a@example.com", "author_login": "emiliano-go", "committed_at": datetime(2026, 7, 8, tzinfo=timezone.utc), "message": "m1", "is_merge": False},
            {"sha": "new-1", "author_name": "A", "author_email": "a@example.com", "author_login": "emiliano-go", "committed_at": datetime(2026, 7, 8, tzinfo=timezone.utc), "message": "m1", "is_merge": False},
            {"sha": "boundary", "author_name": "A", "author_email": "a@example.com", "author_login": "emiliano-go", "committed_at": datetime(2026, 7, 7, tzinfo=timezone.utc), "message": "m2", "is_merge": False},
            {"sha": "older", "author_name": "A", "author_email": "a@example.com", "author_login": "emiliano-go", "committed_at": datetime(2026, 7, 6, tzinfo=timezone.utc), "message": "m3", "is_merge": False},
        ]

        fake_repo = SimpleNamespace(full_name="emiliano-go/vigil")
        fake_handle = SimpleNamespace(get_commits=lambda since=None: commits)

        with patch.object(tasks, "github_session", return_value=nullcontext(SimpleNamespace())):
            with patch.object(tasks, "get_repo_handle", return_value=fake_handle):
                with patch.object(tasks, "extract_commit_data", side_effect=extracted):
                    result = tasks.fetch_commits.fn("emiliano-go/vigil", datetime(2026, 7, 1, tzinfo=timezone.utc), "boundary")

        self.assertEqual([row["sha"] for row in result], ["new-1"])

    def test_activity_range_dedupes_repo_sha_rows(self):
        rows = [
            {"repo": "emiliano-go/vigil", "sha": "abc", "author_login": "emiliano-go", "author_name": "A", "author_email": "a@example.com", "message": "m1", "is_merge": False, "committed_at": datetime(2026, 7, 8, tzinfo=timezone.utc)},
            {"repo": "emiliano-go/vigil", "sha": "abc", "author_login": "emiliano-go", "author_name": "A", "author_email": "a@example.com", "message": "m1", "is_merge": False, "committed_at": datetime(2026, 7, 8, tzinfo=timezone.utc)},
        ]

        with patch.object(routes, "_query_dicts", return_value=rows):
            result = routes.activity_range(datetime(2026, 7, 1, tzinfo=timezone.utc), datetime(2026, 7, 9, tzinfo=timezone.utc))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].sha, "abc")


if __name__ == "__main__":
    unittest.main()

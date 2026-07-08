import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.flow import flow
from app.flow.tasks import RepoRecord


class FlowBoundaryTests(unittest.TestCase):
    def test_process_repo_passes_last_synced_sha_to_fetch(self):
        repo = RepoRecord(
            full_name="emiliano-go/vigil",
            name="vigil",
            owner="emiliano-go",
            is_org=False,
            private=False,
            default_branch="main",
        )
        last_synced_at = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)

        with patch.object(flow, "get_sync_state", return_value=(last_synced_at, "boundary")):
            with patch.object(flow, "get_existing_commit_shas", return_value=set()):
                with patch.object(flow, "fetch_commits", return_value=[{"sha": "new", "committed_at": datetime(2026, 7, 8, tzinfo=timezone.utc)}]) as fetch:
                    with patch.object(flow, "transform_commit", return_value=SimpleNamespace()):
                        with patch.object(flow, "insert_commits", return_value=1):
                            with patch.object(flow, "update_sync_state"):
                                flow.process_repo.fn(repo)

        fetch.assert_called_once_with("emiliano-go/vigil", last_synced_at, "boundary")


if __name__ == "__main__":
    unittest.main()

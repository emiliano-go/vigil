import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.core.config import Settings
from scripts.backfill_author_commits import _parse_since, _resolve_author_logins


class BackfillAuthorCommitsTests(unittest.TestCase):
    def test_parse_since_defaults_to_utc_midnight(self):
        self.assertEqual(_parse_since("2022-01-01"), datetime(2022, 1, 1, tzinfo=timezone.utc))

    def test_resolve_author_logins_includes_aliases(self):
        with patch.object(Settings, "author_login_aliases", return_value=["emiliano-gandini-outeda", "emiliano-go"]):
            self.assertEqual(_resolve_author_logins("emiliano-go"), ["emiliano-gandini-outeda", "emiliano-go"])


if __name__ == "__main__":
    unittest.main()

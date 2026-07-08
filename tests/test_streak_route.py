import unittest
from unittest.mock import patch

from app.api import routes
from app.core.config import Settings
from app.services.github_contributions import ContributionStreak


class StreakRouteTests(unittest.TestCase):
    def test_author_streak_delegates_to_github_helper(self):
        with patch.object(Settings, "canonical_author_login", return_value="emiliano-go") as canonical_login:
            with patch.object(
                routes,
                "get_contribution_streak",
                return_value=ContributionStreak(
                    author_login="emiliano-go",
                    current_streak=45,
                    longest_streak=60,
                    last_active_day=None,
                    active_days=123,
                ),
            ) as streak_fn:
                response = routes.author_streak("emiliano-gandini-outeda")

        canonical_login.assert_called_once_with("emiliano-gandini-outeda")
        streak_fn.assert_called_once_with("emiliano-go")
        self.assertEqual(response.current_streak, 45)
        self.assertEqual(response.author_login, "emiliano-go")


if __name__ == "__main__":
    unittest.main()

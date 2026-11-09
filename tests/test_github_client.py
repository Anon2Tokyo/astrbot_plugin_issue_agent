"""Unit tests for GitHubClient, including get_rate_limit()."""

from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from github_client import GitHubClient


class TestGitHubClient(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client_with_token = GitHubClient(token="ghp_test123456789")
        self.client_no_token = GitHubClient(token="")

    def test_headers_with_and_without_token(self):
        headers_with_token = self.client_with_token.headers
        self.assertEqual(headers_with_token["Authorization"], "Bearer ghp_test123456789")
        self.assertEqual(headers_with_token["Accept"], "application/vnd.github+json")
        self.assertEqual(headers_with_token["X-GitHub-Api-Version"], "2022-11-28")

        headers_no_token = self.client_no_token.headers
        self.assertNotIn("Authorization", headers_no_token)

    @patch("httpx.AsyncClient.get")
    async def test_get_rate_limit_success(self, mock_get):
        mock_response_data = {
            "resources": {
                "core": {
                    "limit": 5000,
                    "remaining": 4999,
                    "reset": 1700000000,
                    "used": 1,
                },
                "search": {
                    "limit": 30,
                    "remaining": 28,
                    "reset": 1700000060,
                    "used": 2,
                },
                "graphql": {
                    "limit": 5000,
                    "remaining": 5000,
                    "reset": 1700003600,
                    "used": 0,
                },
            },
            "rate": {
                "limit": 5000,
                "remaining": 4999,
                "reset": 1700000000,
                "used": 1,
            },
        }

        mock_resp = httpx.Response(
            status_code=200,
            json=mock_response_data,
            request=httpx.Request("GET", "https://api.github.com/rate_limit"),
        )
        mock_get.return_value = mock_resp

        result = await self.client_with_token.get_rate_limit()

        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args[0][0], "https://api.github.com/rate_limit")
        self.assertEqual(
            mock_get.call_args[1]["headers"]["Authorization"],
            "Bearer ghp_test123456789",
        )

        # Check raw resources & rate
        self.assertIn("resources", result)
        self.assertIn("rate", result)
        self.assertEqual(result["resources"]["core"]["limit"], 5000)

        # Check parsed core quota
        self.assertEqual(result["core"]["limit"], 5000)
        self.assertEqual(result["core"]["remaining"], 4999)
        self.assertEqual(result["core"]["reset"], 1700000000)
        expected_core_reset_iso = datetime.fromtimestamp(
            1700000000, tz=timezone.utc
        ).isoformat()
        self.assertEqual(result["core"]["reset_time"], expected_core_reset_iso)
        self.assertEqual(result["core"]["used"], 1)

        # Check parsed search quota
        self.assertEqual(result["search"]["limit"], 30)
        self.assertEqual(result["search"]["remaining"], 28)
        self.assertEqual(result["search"]["reset"], 1700000060)
        self.assertEqual(result["search"]["used"], 2)

        # Check parsed graphql quota
        self.assertEqual(result["graphql"]["limit"], 5000)
        self.assertEqual(result["graphql"]["remaining"], 5000)

    @patch("httpx.AsyncClient.get")
    async def test_get_rate_limit_fallback_core_from_rate(self, mock_get):
        mock_response_data = {
            "resources": {},
            "rate": {
                "limit": 60,
                "remaining": 55,
                "reset": 1700000000,
                "used": 5,
            },
        }
        mock_resp = httpx.Response(
            status_code=200,
            json=mock_response_data,
            request=httpx.Request("GET", "https://api.github.com/rate_limit"),
        )
        mock_get.return_value = mock_resp

        result = await self.client_no_token.get_rate_limit()

        self.assertEqual(result["core"]["limit"], 60)
        self.assertEqual(result["core"]["remaining"], 55)
        self.assertEqual(result["core"]["used"], 5)
        self.assertEqual(result["search"], {})
        self.assertEqual(result["graphql"], {})

    @patch("httpx.AsyncClient.get")
    async def test_get_rate_limit_error_handling(self, mock_get):
        mock_resp = httpx.Response(
            status_code=401,
            text='{"message": "Bad credentials"}',
            request=httpx.Request("GET", "https://api.github.com/rate_limit"),
        )
        mock_get.return_value = mock_resp

        with self.assertRaises(RuntimeError) as ctx:
            await self.client_with_token.get_rate_limit()

        self.assertIn("Failed to fetch rate limit", str(ctx.exception))
        self.assertIn("Bad credentials", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

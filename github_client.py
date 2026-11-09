"""GitHub REST API client for astrbot_plugin_issue_agent."""

from datetime import datetime, timezone
import logging
from typing import Any

import httpx

logger = logging.getLogger("astrbot_plugin_issue_agent")


class GitHubClient:
    """Async client for interacting with GitHub REST API."""

    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        self.token = token.strip()
        self.base_url = base_url.rstrip("/")

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AstrBot-IssueAgent-Bridge",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def create_issue(
        self,
        repo: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new issue in the target repository.

        Args:
            repo: Format 'owner/repo'
            title: Issue title
            body: Issue markdown description
            labels: List of label strings (e.g. ['jules'])

        Returns:
            Created issue dictionary from GitHub API.
        """
        url = f"{self.base_url}/repos/{repo}/issues"
        payload: dict[str, Any] = {
            "title": title,
            "body": body,
        }
        if labels:
            payload["labels"] = labels

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=self.headers, json=payload)
            if resp.status_code >= 400:
                logger.error(
                    f"Failed to create GitHub issue: status={resp.status_code}, body={resp.text}"
                )
                raise RuntimeError(
                    f"GitHub API Error [{resp.status_code}]: {resp.json().get('message', resp.text)}"
                )
            return resp.json()

    async def get_issue(self, repo: str, issue_number: int) -> dict[str, Any]:
        """Get issue details.

        Args:
            repo: Format 'owner/repo'
            issue_number: Issue number

        Returns:
            Issue details dictionary.
        """
        url = f"{self.base_url}/repos/{repo}/issues/{issue_number}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Failed to fetch issue #{issue_number}: {resp.text}"
                )
            return resp.json()

    async def get_issue_comments(
        self, repo: str, issue_number: int, since: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch comments for an issue, optionally since a given ISO timestamp."""
        url = f"{self.base_url}/repos/{repo}/issues/{issue_number}/comments"
        params: dict[str, Any] = {"per_page": 100}
        if since:
            params["since"] = since

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self.headers, params=params)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Failed to fetch comments for issue #{issue_number}: {resp.text}"
                )
            return resp.json()

    async def add_comment(
        self, repo: str, issue_number: int, body: str
    ) -> dict[str, Any]:
        """Post a comment to the specified issue.

        Args:
            repo: Format 'owner/repo'
            issue_number: Issue number
            body: Comment text

        Returns:
            Created comment dictionary.
        """
        url = f"{self.base_url}/repos/{repo}/issues/{issue_number}/comments"
        payload = {"body": body}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=self.headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Failed to post comment to #{issue_number}: {resp.text}"
                )
            return resp.json()

    async def check_pull_requests(
        self, repo: str, issue_number: int
    ) -> list[dict[str, Any]]:
        """Find pull requests that reference this issue (via timeline events or repo search)."""
        url = f"{self.base_url}/repos/{repo}/issues/{issue_number}/timeline"
        timeline_headers = dict(self.headers)
        timeline_headers["Accept"] = "application/vnd.github.mockingbird-preview+json"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=timeline_headers)
            if resp.status_code != 200:
                return []
            events = resp.json()
            prs = []
            for ev in events:
                if ev.get("event") == "cross-referenced" and "source" in ev:
                    issue_source = ev["source"].get("issue", {})
                    if issue_source.get("pull_request"):
                        prs.append(issue_source)
            return prs

    async def get_rate_limit(self) -> dict[str, Any]:
        """Fetch the rate limit status for the current token or IP.

        Calls GitHub REST API: GET /rate_limit

        Returns:
            Dictionary containing rate limit details parsed from GitHub API:
            - 'resources': raw resources dictionary (core, search, graphql, etc.)
            - 'rate': raw rate dictionary
            - 'core': parsed summary for core quota (limit, remaining, reset, used, reset_time)
            - 'search': parsed summary for search quota (limit, remaining, reset, used, reset_time)
            - 'graphql': parsed summary for graphql quota (limit, remaining, reset, used, reset_time)
        """
        url = f"{self.base_url}/rate_limit"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self.headers)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Failed to fetch rate limit: {resp.text}"
                )
            data = resp.json()

            def _parse_resource(res_data: dict[str, Any] | None) -> dict[str, Any]:
                if not res_data:
                    return {}
                reset_ts = res_data.get("reset", 0)
                reset_iso = (
                    datetime.fromtimestamp(reset_ts, tz=timezone.utc).isoformat()
                    if reset_ts
                    else None
                )
                return {
                    "limit": res_data.get("limit", 0),
                    "remaining": res_data.get("remaining", 0),
                    "reset": reset_ts,
                    "reset_time": reset_iso,
                    "used": res_data.get("used", 0),
                }

            resources = data.get("resources", {})
            rate = data.get("rate", {})

            return {
                "resources": resources,
                "rate": rate,
                "core": _parse_resource(resources.get("core") or rate),
                "search": _parse_resource(resources.get("search")),
                "graphql": _parse_resource(resources.get("graphql")),
            }

"""GitHub REST API client for astrbot_plugin_issue_agent."""

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

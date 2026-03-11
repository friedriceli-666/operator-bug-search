from __future__ import annotations

import json
import ssl
import time
from base64 import b64decode
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GitHubApiError(RuntimeError):
    pass


@dataclass(slots=True)
class GitHubClient:
    token: str | None = None
    base_url: str = "https://api.github.com"
    sleep_seconds: float = 1.0
    timeout_seconds: float = 30.0
    max_retries: int = 3

    def _should_retry_http(self, status_code: int) -> bool:
        return status_code in {429, 500, 502, 503, 504}

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "operator-bug-search/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            req = Request(url, headers=self._headers())
            try:
                with urlopen(req, timeout=self.timeout_seconds) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                time.sleep(self.sleep_seconds)
                return payload
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                last_error = exc
                if attempt < self.max_retries and self._should_retry_http(exc.code):
                    wait_seconds = self.sleep_seconds * attempt * 2
                    print(
                        f"[retry {attempt}/{self.max_retries}] HTTP {exc.code} for {url}; sleeping {wait_seconds:.1f}s",
                        flush=True,
                    )
                    time.sleep(wait_seconds)
                    continue
                raise GitHubApiError(f"GitHub API error {exc.code} for {url}: {body}") from exc
            except (URLError, ssl.SSLError, TimeoutError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    wait_seconds = self.sleep_seconds * attempt * 2
                    print(
                        f"[retry {attempt}/{self.max_retries}] Network error for {url}: {exc}; sleeping {wait_seconds:.1f}s",
                        flush=True,
                    )
                    time.sleep(wait_seconds)
                    continue
                raise GitHubApiError(
                    f"GitHub API request failed for {url} after {self.max_retries} attempts: {exc}"
                ) from exc

        raise GitHubApiError(f"GitHub API request failed for {url}: {last_error}")

    def search_issues(self, query: str, page: int, per_page: int = 100) -> dict[str, Any]:
        return self._request("/search/issues", {"q": query, "page": page, "per_page": per_page})

    def search_code(self, query: str, page: int, per_page: int = 100) -> dict[str, Any]:
        return self._request("/search/code", {"q": query, "page": page, "per_page": per_page})

    def get_json_url(self, url: str) -> Any:
        return self._request(url.removeprefix(self.base_url))

    def get_repo_file_content(self, owner: str, repo: str, path: str, ref: str | None = None) -> str:
        params = {"ref": ref} if ref else None
        payload = self._request(f"/repos/{owner}/{repo}/contents/{path}", params)
        encoded = payload.get("content", "")
        if not encoded:
            return ""
        return b64decode(encoded).decode("utf-8", errors="replace")

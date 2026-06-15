"""HTTP client with retry, rate-limiting, and session management."""

import time
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple token-bucket rate limiter to avoid triggering anti-bot measures."""

    def __init__(self, requests_per_second: float = 5.0):
        self.interval = 1.0 / requests_per_second
        self._last_call = 0.0

    def wait(self) -> None:
        """Block until it's safe to make the next request."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last_call = time.monotonic()


class SessionManager:
    """
    Managed HTTP session with automatic retry, rate limiting, and header management.

    Usage:
        session = SessionManager(base_url="https://api.example.com")
        session.headers.update({"Authorization": "Bearer xxx"})
        resp = session.get("/api/courts")
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 10.0,
        max_retries: int = 3,
        rate_limit: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(rate_limit)
        self.headers: dict[str, str] = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Mobile/15E148 MicroMessenger/8.0.40"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        self._client = httpx.Client(timeout=httpx.Timeout(timeout))

    # ── HTTP methods ──────────────────────────────────────

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        data: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
        timeout: float | None = None,
    ) -> httpx.Response | None:
        """Send an HTTP request with retry logic and rate limiting."""

        url = path if path.startswith("http") else f"{self.base_url}{path}"
        merged_headers = {**self.headers, **(headers or {})}
        req_timeout = timeout or self.timeout

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.wait()
                resp = self._client.request(
                    method=method,
                    url=url,
                    json=json,
                    data=data,
                    params=params,
                    headers=merged_headers,
                    timeout=req_timeout,
                )
                logger.debug(f"[{method}] {url} → {resp.status_code}")
                return resp

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Timeout on attempt {attempt + 1}/{self.max_retries}: {url}")
            except httpx.ConnectError as e:
                last_error = e
                logger.warning(f"Connection error on attempt {attempt + 1}/{self.max_retries}: {e}")
            except Exception as e:
                last_error = e
                logger.warning(f"Request error on attempt {attempt + 1}/{self.max_retries}: {e}")

            if attempt < self.max_retries - 1:
                time.sleep(0.3 * (attempt + 1))  # progressive backoff

        logger.error(f"All {self.max_retries} attempts failed for {url}: {last_error}")
        return None

    def get(self, path: str, **kwargs) -> httpx.Response | None:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response | None:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response | None:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response | None:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        """Release underlying connection pool."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

"""HTTP POST with an optional retry policy, used for both REST hops.

Retries can be switched off (RETRY_ENABLED=false) so the experiments can
compare plain REST against REST with retries (RQ2).

Retried:     connection errors, timeouts, HTTP 5xx.
Not retried: HTTP 4xx (the request itself is wrong, retrying will not help).
"""

import asyncio
from dataclasses import dataclass

import httpx

from common.config import env_bool, env_float, env_int

JSON_HEADERS = {"content-type": "application/json"}


@dataclass(frozen=True)
class RetryPolicy:
    enabled: bool
    max_retries: int
    backoff_s: float
    backoff_max_s: float

    @classmethod
    def from_env(cls) -> "RetryPolicy":
        return cls(
            enabled=env_bool("RETRY_ENABLED", False),
            max_retries=env_int("MAX_RETRIES", 5),
            backoff_s=env_float("RETRY_BACKOFF_S", 0.1),
            backoff_max_s=env_float("RETRY_BACKOFF_MAX_S", 2.0),
        )

    @property
    def max_attempts(self) -> int:
        return 1 + (self.max_retries if self.enabled else 0)

    def delay(self, attempt: int) -> float:
        """Exponential backoff after the given (1-based) failed attempt."""
        return min(self.backoff_s * 2 ** (attempt - 1), self.backoff_max_s)


@dataclass(frozen=True)
class PostResult:
    ok: bool
    attempts: int
    detail: str  # HTTP status code, or the error type for connection failures


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=env_float("REQUEST_TIMEOUT_S", 5.0),
        limits=httpx.Limits(
            max_connections=env_int("HTTP_MAX_CONNECTIONS", 200),
            max_keepalive_connections=env_int("HTTP_MAX_CONNECTIONS", 200),
        ),
    )


async def post(client: httpx.AsyncClient, url: str, body: bytes, policy: RetryPolicy) -> PostResult:
    attempt = 0
    while True:
        attempt += 1
        try:
            response = await client.post(url, content=body, headers=JSON_HEADERS)
            detail = str(response.status_code)
            if response.is_success:
                return PostResult(True, attempt, detail)
            if response.is_client_error:
                return PostResult(False, attempt, detail)
        except httpx.HTTPError as exc:
            detail = type(exc).__name__
        if attempt >= policy.max_attempts:
            return PostResult(False, attempt, detail)
        await asyncio.sleep(policy.delay(attempt))

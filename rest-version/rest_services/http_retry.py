"""HTTP POST with a bounded retry policy, used for both REST hops.

Client library: aiohttp. httpx was tried first, but at ~2 ms of CPU per
request it saturated the Sensor Simulator at ~500 msg/s, making the load
generator, not the architecture, the bottleneck.

RETRY_ENABLED=false gives the no-retry baseline; true gives bounded
exponential backoff with full jitter (a random wait between 0 and the
exponential cap), which avoids synchronised retry bursts.

Transient (retried): connection errors, timeouts, HTTP 429/500/502/503/504.
Not retried:         every other status (e.g. 422: the request itself is wrong).

The request body is built once, so msg_id and sent_mono_ns stay the same on
every attempt. Every attempt's outcome is kept in PostResult.history.
"""

import asyncio
import random
from dataclasses import dataclass

import aiohttp

from common.config import env_bool, env_float, env_int

JSON_HEADERS = {"content-type": "application/json"}
TRANSIENT_STATUSES = {429, 500, 502, 503, 504}
_JITTER_RNG = random.Random()


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

    def delay(self, failed_attempt: int, rng: random.Random | None = None) -> float:
        """Wait after the given (1-based) failed attempt: full jitter, capped."""
        cap = min(self.backoff_s * 2 ** (failed_attempt - 1), self.backoff_max_s)
        return (rng or _JITTER_RNG).uniform(0, cap)

    def as_dict(self) -> dict:
        return {"retry_enabled": self.enabled, "max_retries": self.max_retries,
                "retry_backoff_s": self.backoff_s, "retry_backoff_max_s": self.backoff_max_s}


@dataclass(frozen=True)
class PostResult:
    ok: bool
    history: tuple[str, ...]  # outcome of each attempt: HTTP status or error type

    @property
    def attempts(self) -> int:
        return len(self.history)

    @property
    def detail(self) -> str:
        return ";".join(self.history)


def make_session(timeout_s: float) -> aiohttp.ClientSession:
    """Must be called inside a running event loop."""
    # Short DNS cache: a restarted container may get a new IP address, and a long
    # cache would keep sending to the old one long after the service is back.
    connector = aiohttp.TCPConnector(limit=env_int("HTTP_MAX_CONNECTIONS", 200), ttl_dns_cache=2)
    return aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=timeout_s))


async def post(session: aiohttp.ClientSession, url: str, body: bytes, policy: RetryPolicy) -> PostResult:
    history: list[str] = []
    while True:
        try:
            async with session.post(url, data=body, headers=JSON_HEADERS) as response:
                await response.read()
                history.append(str(response.status))
                if 200 <= response.status < 300:
                    return PostResult(True, tuple(history))
                transient = response.status in TRANSIENT_STATUSES
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            history.append(type(exc).__name__)
            transient = True
        if not transient or len(history) >= policy.max_attempts:
            return PostResult(False, tuple(history))
        await asyncio.sleep(policy.delay(len(history)))

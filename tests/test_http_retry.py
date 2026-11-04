import asyncio
import random

import httpx
import pytest

from rest_services.http_retry import RetryPolicy, post

FAST = RetryPolicy(enabled=True, max_retries=3, backoff_s=0.001, backoff_max_s=0.002)
OFF = RetryPolicy(enabled=False, max_retries=3, backoff_s=0.001, backoff_max_s=0.002)


def run_post(responses, policy):
    """POST against a fake server that answers with the given sequence."""
    calls = []
    answers = iter(responses)

    def handler(request):
        calls.append(request.content)
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await post(client, "http://x/readings", b'{"msg_id":"m1"}', policy)

    return asyncio.run(go()), calls


def test_transient_errors_are_retried_with_the_same_body():
    result, calls = run_post([httpx.ConnectError("down"), 503, 204], FAST)
    assert result.ok and result.history == ("ConnectError", "503", "204")
    assert len(set(calls)) == 1   # same msg_id on every attempt


def test_client_errors_are_not_retried():
    result, calls = run_post([422, 204], FAST)
    assert not result.ok and result.history == ("422",) and len(calls) == 1


def test_attempts_are_bounded():
    result, calls = run_post([503] * 10, FAST)
    assert not result.ok and result.attempts == 4 and len(calls) == 4


def test_no_retry_baseline_makes_one_attempt():
    result, calls = run_post([503, 204], OFF)
    assert not result.ok and len(calls) == 1


@pytest.mark.parametrize("attempt,cap", [(1, 0.1), (2, 0.2), (3, 0.4), (10, 2.0)])
def test_backoff_has_full_jitter_and_a_cap(attempt, cap):
    policy = RetryPolicy(enabled=True, max_retries=10, backoff_s=0.1, backoff_max_s=2.0)
    rng = random.Random(0)
    delays = [policy.delay(attempt, rng) for _ in range(200)]
    assert all(0 <= d <= cap for d in delays)
    assert max(delays) > cap * 0.8 and min(delays) < cap * 0.2   # spread over the whole range

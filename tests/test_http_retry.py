import asyncio
import random
import socket

import pytest
from aiohttp import web

from rest_services.http_retry import RetryPolicy, make_session, post

FAST = RetryPolicy(enabled=True, max_retries=3, backoff_s=0.001, backoff_max_s=0.002)
OFF = RetryPolicy(enabled=False, max_retries=3, backoff_s=0.001, backoff_max_s=0.002)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_post(statuses, policy):
    """POST against a local server that answers with the given status sequence."""
    bodies = []
    answers = iter(statuses)

    async def handler(request):
        bodies.append(await request.read())
        return web.Response(status=next(answers))

    async def go():
        app = web.Application()
        app.router.add_post("/readings", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        port = free_port()
        await web.TCPSite(runner, "127.0.0.1", port).start()
        try:
            async with make_session(5) as session:
                return await post(session, f"http://127.0.0.1:{port}/readings", b'{"msg_id":"m1"}', policy)
        finally:
            await runner.cleanup()

    return asyncio.run(go()), bodies


def test_transient_statuses_are_retried_with_the_same_body():
    result, bodies = run_post([503, 502, 204], FAST)
    assert result.ok and result.history == ("503", "502", "204")
    assert len(bodies) == 3 and len(set(bodies)) == 1   # same msg_id on every attempt


def test_client_errors_are_not_retried():
    result, bodies = run_post([422, 204], FAST)
    assert not result.ok and result.history == ("422",) and len(bodies) == 1


def test_attempts_are_bounded():
    result, bodies = run_post([503] * 10, FAST)
    assert not result.ok and result.attempts == 4 and len(bodies) == 4


def test_no_retry_baseline_makes_one_attempt():
    result, bodies = run_post([503, 204], OFF)
    assert not result.ok and len(bodies) == 1


def test_connection_errors_are_transient():
    async def go():
        async with make_session(2) as session:
            return await post(session, f"http://127.0.0.1:{free_port()}/readings", b"{}", FAST)

    result = asyncio.run(go())
    assert not result.ok and result.attempts == 4
    # Linux refuses instantly (ClientConnectorError); Windows retries the SYN
    # and may hit the timeout first. Either way it is a transport error, not a status.
    assert all(not outcome.isdigit() for outcome in result.history)


@pytest.mark.parametrize("attempt,cap", [(1, 0.1), (2, 0.2), (3, 0.4), (10, 2.0)])
def test_backoff_has_full_jitter_and_a_cap(attempt, cap):
    policy = RetryPolicy(enabled=True, max_retries=10, backoff_s=0.1, backoff_max_s=2.0)
    rng = random.Random(0)
    delays = [policy.delay(attempt, rng) for _ in range(200)]
    assert all(0 <= d <= cap for d in delays)
    assert max(delays) > cap * 0.8 and min(delays) < cap * 0.2   # spread over the whole range

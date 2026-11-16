import httpx
import pytest

from radar_inflacao.errors import SourceError
from radar_inflacao.model import MAX_BYTES
from radar_inflacao.source import IbgeSource


def test_transient_errors_retry_and_success_is_returned():
    attempts, delays = [], []

    def handle(request):
        attempts.append(request)
        return httpx.Response(503 if len(attempts) < 3 else 200, content=b"[]")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        source = IbgeSource(client, delays.append)
        assert source.metadata().raw == b"[]"
    assert len(attempts) == 3
    assert delays == [1, 2]


@pytest.mark.parametrize("status", [400, 403, 404, 302])
def test_non_retryable_status_is_not_retried(status):
    attempts = []

    def handle(request):
        attempts.append(request)
        return httpx.Response(status, headers={"Location": "https://example.test"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SourceError, match=f"HTTP {status}"):
            IbgeSource(client, lambda _: None).metadata()
    assert len(attempts) == 1


def test_timeout_is_bounded_and_clear():
    attempts = []

    def handle(request):
        attempts.append(request)
        raise httpx.ReadTimeout("simulated")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(SourceError, match="preservada"):
            IbgeSource(client, lambda _: None).metadata()
    assert len(attempts) == 3


def test_large_body_is_rejected():
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * (MAX_BYTES + 1)))
    ) as client:
        with pytest.raises(SourceError, match="2 MiB"):
            IbgeSource(client).metadata()


def test_arbitrary_origin_is_not_accepted():
    with pytest.raises(SourceError, match="não autorizada"):
        IbgeSource().fetch("https://example.test")

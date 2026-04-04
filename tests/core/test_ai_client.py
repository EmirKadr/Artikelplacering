"""Tests for core/ai_client.py.

All HTTP calls are mocked — no network access.
Tests cover: success path, 429 rate-limit retry, 4xx no-retry,
transient error retry, stop_flag abort, and progress callbacks.
"""
import time
from typing import List
from unittest.mock import MagicMock, patch, call

import pytest

from core.ai_client import call_api, _sleep_interruptible, _RETRY_DELAYS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_response(status: int, json_data=None, text: str = ""):
    """Create a mock requests.Response."""
    r = MagicMock()
    r.status_code = status
    r.text = text
    if json_data is not None:
        r.json.return_value = json_data
    else:
        r.json.side_effect = ValueError("no json")
    r.raise_for_status = MagicMock()
    if status >= 400:
        r.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return r


GOOD_RESPONSE = {
    "choices": [{"message": {"content": "Kategori A"}}]
}

PAYLOAD = {
    "model": "test-model",
    "messages": [{"role": "user", "content": "classify this"}],
}


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------

def test_call_api_success():
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(200, GOOD_RESPONSE)
        result = call_api(PAYLOAD, api_url="http://localhost:1234/v1")
    assert result == GOOD_RESPONSE
    mock_req.post.assert_called_once()


def test_call_api_appends_chat_completions_to_base_url():
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(200, GOOD_RESPONSE)
        call_api(PAYLOAD, api_url="http://localhost:1234/v1")
    called_url = mock_req.post.call_args[0][0]
    assert called_url.endswith("/chat/completions")


def test_call_api_uses_full_url_when_already_has_chat_completions():
    full_url = "http://localhost:1234/v1/chat/completions"
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(200, GOOD_RESPONSE)
        call_api(PAYLOAD, api_url=full_url)
    called_url = mock_req.post.call_args[0][0]
    assert called_url == full_url


def test_call_api_sends_auth_header_when_api_key_provided():
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(200, GOOD_RESPONSE)
        call_api(PAYLOAD, api_url="http://localhost:1234/v1", api_key="sk-test")
    headers = mock_req.post.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer sk-test"


def test_call_api_no_auth_header_without_api_key():
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(200, GOOD_RESPONSE)
        call_api(PAYLOAD, api_url="http://localhost:1234/v1", api_key="")
    headers = mock_req.post.call_args[1]["headers"]
    assert "Authorization" not in headers


def test_call_api_passes_timeout():
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(200, GOOD_RESPONSE)
        call_api(PAYLOAD, api_url="http://localhost:1234/v1", timeout=(5, 90))
    assert mock_req.post.call_args[1]["timeout"] == (5, 90)


# ---------------------------------------------------------------------------
# progress_cb
# ---------------------------------------------------------------------------

def test_call_api_emits_wait_msg():
    messages: List[str] = []
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(200, GOOD_RESPONSE)
        call_api(PAYLOAD, api_url="http://localhost:1234/v1",
                 wait_msg="Väntar…", progress_cb=messages.append)
    assert "Väntar…" in messages


# ---------------------------------------------------------------------------
# 4xx — no retry
# ---------------------------------------------------------------------------

def test_call_api_raises_immediately_on_400():
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(
            400, {"error": {"message": "Bad request"}}, text="bad"
        )
        with pytest.raises(RuntimeError, match="HTTP 400"):
            call_api(PAYLOAD, api_url="http://localhost:1234/v1")
    # Only one attempt — no retry on 4xx
    assert mock_req.post.call_count == 1


def test_call_api_raises_immediately_on_422():
    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.return_value = make_response(422, None, text="unprocessable")
        with pytest.raises(RuntimeError, match="HTTP 422"):
            call_api(PAYLOAD, api_url="http://localhost:1234/v1")
    assert mock_req.post.call_count == 1


# ---------------------------------------------------------------------------
# 429 — rate limit retry
# ---------------------------------------------------------------------------

def test_call_api_retries_after_429(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return make_response(429, {"error": {"message": "Rate limit"}}, text="rl")
        return make_response(200, GOOD_RESPONSE)

    messages: List[str] = []
    monkeypatch.setattr("core.ai_client._sleep_interruptible", lambda s, sf=None: None)

    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.side_effect = fake_post
        result = call_api(PAYLOAD, api_url="http://localhost:1234/v1",
                          progress_cb=messages.append)

    assert result == GOOD_RESPONSE
    assert len(calls) == 2
    assert any("Rate limit" in m for m in messages)


def test_call_api_429_extracts_wait_time_from_message(monkeypatch):
    sleep_calls: List[float] = []

    def fake_sleep(secs, sf=None):
        sleep_calls.append(secs)

    monkeypatch.setattr("core.ai_client._sleep_interruptible", fake_sleep)

    def fake_post(*args, **kwargs):
        if not sleep_calls:
            return make_response(
                429,
                {"error": {"message": "Rate limit exceeded, try again in 7.5s"}},
                text=""
            )
        return make_response(200, GOOD_RESPONSE)

    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.side_effect = fake_post
        call_api(PAYLOAD, api_url="http://localhost:1234/v1")

    # Should extract 7.5 + 0.5 = 8.0, capped at 30
    assert abs(sleep_calls[0] - 8.0) < 0.01


# ---------------------------------------------------------------------------
# Transient errors — retry up to max attempts
# ---------------------------------------------------------------------------

def test_call_api_retries_on_transient_error(monkeypatch):
    monkeypatch.setattr("core.ai_client._sleep_interruptible", lambda s, sf=None: None)
    call_count = [0]

    def fake_post(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] < 3:
            raise ConnectionError("Network error")
        return make_response(200, GOOD_RESPONSE)

    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.side_effect = fake_post
        result = call_api(PAYLOAD, api_url="http://localhost:1234/v1")

    assert result == GOOD_RESPONSE
    assert call_count[0] == 3


def test_call_api_raises_after_all_retries_exhausted(monkeypatch):
    monkeypatch.setattr("core.ai_client._sleep_interruptible", lambda s, sf=None: None)

    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.side_effect = ConnectionError("always fails")
        with pytest.raises(ConnectionError):
            call_api(PAYLOAD, api_url="http://localhost:1234/v1")

    # Should have tried max retries + 1 times
    assert mock_req.post.call_count == len(_RETRY_DELAYS) + 1


# ---------------------------------------------------------------------------
# stop_flag abort
# ---------------------------------------------------------------------------

def test_call_api_aborts_when_stop_flag_set():
    stopped = [True]  # already stopped before first attempt

    with pytest.raises(RuntimeError, match="Avbruten"):
        call_api(PAYLOAD, api_url="http://localhost:1234/v1",
                 stop_flag=lambda: stopped[0])


def test_call_api_aborts_between_retries(monkeypatch):
    stopped = [False]

    def fake_sleep(secs, sf=None):
        stopped[0] = True  # set stop flag during sleep

    monkeypatch.setattr("core.ai_client._sleep_interruptible", fake_sleep)

    with patch("core.ai_client.req") as mock_req, \
         patch("core.ai_client.REQUESTS_AVAILABLE", True):
        mock_req.post.side_effect = ConnectionError("transient")
        with pytest.raises((ConnectionError, RuntimeError)):
            call_api(PAYLOAD, api_url="http://localhost:1234/v1",
                     stop_flag=lambda: stopped[0])

    # Should have stopped after at most 2 attempts (1 fail + stop during sleep)
    assert mock_req.post.call_count <= 2


# ---------------------------------------------------------------------------
# requests not available
# ---------------------------------------------------------------------------

def test_call_api_raises_when_requests_unavailable():
    with patch("core.ai_client.REQUESTS_AVAILABLE", False):
        with pytest.raises(RuntimeError, match="requests"):
            call_api(PAYLOAD, api_url="http://localhost:1234/v1")


# ---------------------------------------------------------------------------
# _sleep_interruptible
# ---------------------------------------------------------------------------

def test_sleep_interruptible_completes_normally():
    start = time.monotonic()
    _sleep_interruptible(0.1)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.09  # allow tiny timing variance


def test_sleep_interruptible_wakes_early_on_stop():
    start = time.monotonic()
    _sleep_interruptible(10.0, stop_flag=lambda: True)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0  # should return almost immediately

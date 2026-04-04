"""AI client — HTTP calls to LLM API with retry and rate-limit handling.

No PyQt6 imports — importable without Qt installed.

The key function is `call_api()`. It takes optional callables for progress
reporting and stop signalling so it can be used both from Qt workers (which
pass self.progress.emit and lambda: self._stop) and from tests (which pass
simple lambdas or None).
"""
import json
import logging
import re as _re
import time
from typing import Callable, Dict, Optional, Union

_logger = logging.getLogger(__name__)

_RETRY_DELAYS = [3, 6, 12, 24, 48]  # seconds between attempts (up to 6 tries total)

try:
    import requests as req
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def call_api(
    payload: Dict,
    api_url: str,
    api_key: str = "",
    timeout: Union[int, tuple] = (5, 60),
    wait_msg: Optional[str] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
) -> Dict:
    """POST *payload* to the LLM chat/completions endpoint.

    Args:
        payload:     JSON-serialisable request body (messages, model, etc.)
        api_url:     Base URL or full chat/completions URL.
        api_key:     Bearer token (empty string = no auth header).
        timeout:     int or (connect_timeout, read_timeout) in seconds.
        wait_msg:    Progress message emitted before each attempt.
        progress_cb: Callable that receives progress strings (e.g. signal.emit).
        stop_flag:   Callable that returns True when the caller wants to abort.

    Returns:
        Parsed JSON response dict.

    Raises:
        RuntimeError: on 4xx errors or when stop_flag fires.
        The last exception from the final retry attempt for other errors.
    """
    if not REQUESTS_AVAILABLE:
        raise RuntimeError("requests-biblioteket är inte installerat")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if "/chat/completions" in api_url:
        url = api_url
    else:
        url = f"{api_url}/chat/completions"

    def _emit(msg: str):
        if progress_cb:
            progress_cb(msg)

    def _stopped() -> bool:
        return bool(stop_flag and stop_flag())

    last_exc: Optional[Exception] = None

    for attempt in range(len(_RETRY_DELAYS) + 1):
        if _stopped():
            raise RuntimeError("Avbruten")
        if wait_msg:
            _emit(wait_msg)
        _logger.debug("API-anrop försök %d: %s", attempt + 1, url)

        try:
            resp = req.post(url, json=payload, timeout=timeout, headers=headers)

            # 429 = rate limit — extract wait time and retry
            if resp.status_code == 429:
                try:
                    detail = resp.json().get("error", {}).get("message", resp.text[:200])
                except (json.JSONDecodeError, ValueError, KeyError, AttributeError):
                    detail = resp.text[:200]
                _wait_match = _re.search(
                    r'try again in (\d+(?:\.\d+)?)\s*s', detail, _re.IGNORECASE
                )
                wait_secs = float(_wait_match.group(1)) + 0.5 if _wait_match else 5.0
                wait_secs = min(wait_secs, 30.0)
                _emit(f"    ⚠ Rate limit — väntar {wait_secs:.1f}s…")
                _sleep_interruptible(wait_secs, stop_flag)
                continue

            # 4xx = client error — don't retry
            if 400 <= resp.status_code < 500:
                try:
                    detail = resp.json().get("error", {}).get("message", resp.text[:200])
                except (json.JSONDecodeError, ValueError, KeyError, AttributeError):
                    detail = resp.text[:200]
                raise RuntimeError(f"HTTP {resp.status_code}: {detail}")

            resp.raise_for_status()
            return resp.json()

        except Exception as e:
            last_exc = e
            msg = str(e)
            # Don't retry client errors (4xx)
            if msg.startswith("HTTP 4"):
                raise
            if hasattr(e, "response") and e.response is not None:
                if 400 <= e.response.status_code < 500:
                    raise
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                _emit(
                    f"    ⚠ Försök {attempt + 1} misslyckades: {e}. "
                    f"Försöker igen om {delay}s…"
                )
                _sleep_interruptible(delay, stop_flag)

    raise last_exc  # type: ignore[misc]


def _sleep_interruptible(seconds: float, stop_flag: Optional[Callable[[], bool]] = None):
    """Sleep for *seconds* but wake up early if *stop_flag* returns True."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if stop_flag and stop_flag():
            return
        time.sleep(0.2)

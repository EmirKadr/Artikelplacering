"""Generate ignored embedded proxy config from environment variables.

This keeps the shared proxy token out of the tracked source tree while still
allowing private local builds and CI release builds to embed it when needed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_MODEL = "gemini-2.5-flash"


def _required() -> bool:
    value = os.getenv("ARTIKELPLACERING_REQUIRE_EMBEDDED_PROXY", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    target = root / "core" / "embedded_proxy_config.py"

    api_url = os.getenv("ARTIKELPLACERING_EMBEDDED_PROXY_API_URL", "").strip()
    token = os.getenv("ARTIKELPLACERING_EMBEDDED_PROXY_TOKEN", "").strip()
    model = os.getenv("ARTIKELPLACERING_EMBEDDED_PROXY_MODEL", "").strip() or DEFAULT_MODEL

    if api_url and token:
        target.write_text(
            "\n".join(
                [
                    '"""Generated during build. Do not commit."""',
                    f'EMBEDDED_PROXY_API_URL = "{api_url}"',
                    f'EMBEDDED_PROXY_MODEL = "{model}"',
                    f'EMBEDDED_PROXY_TOKEN = "{token}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"Wrote embedded proxy config to {target}")
        return 0

    if target.exists():
        print(f"Using existing local embedded proxy config: {target}")
        return 0

    if _required():
        print(
            "Missing embedded proxy config. Set ARTIKELPLACERING_EMBEDDED_PROXY_API_URL "
            "and ARTIKELPLACERING_EMBEDDED_PROXY_TOKEN.",
            file=sys.stderr,
        )
        return 1

    print("No embedded proxy config provided; app will warn when using embedded key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

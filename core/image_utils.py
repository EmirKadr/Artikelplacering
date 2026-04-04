"""Image utility functions — encode, download, validate.

No PyQt6 imports — importable without Qt installed.
"""
import base64
import logging
import tempfile
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from core.constants import SUPPORTED_EXT, _safe_name  # noqa: F401 (_safe_name re-exported)

_logger = logging.getLogger(__name__)

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import requests as req
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


def encode_image(path: str, compress: bool = False) -> Tuple[str, str]:
    """Base64-encode an image file for inclusion in an LLM API payload.

    Returns:
        (base64_data, mime_type)
    """
    suffix = Path(path).suffix.lower()
    # BMP/WebP/GIF are poorly supported by most vision models �� always convert to JPEG
    _needs_convert = suffix in (".bmp", ".webp", ".gif")
    if PIL_AVAILABLE and (compress or _needs_convert):
        img = PILImage.open(path)
        if compress:
            img.thumbnail((600, 600), PILImage.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"
    with open(path, "rb") as f:
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        return base64.b64encode(f.read()).decode(), mime_map.get(suffix, "image/jpeg")


def download_image(url: str, timeout: int = 30) -> Optional[str]:
    """Download an image from *url* to a temp file, return the local path.

    Returns None on any error (network, HTTP, IO).
    Uses the `requests` library if available, otherwise falls back to urllib.
    """
    if not url:
        return None
    try:
        suffix = Path(url.split("?")[0]).suffix.lower()
        if suffix not in SUPPORTED_EXT:
            suffix = ".jpg"

        if REQUESTS_AVAILABLE:
            resp = req.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.content
        else:
            with urllib.request.urlopen(  # noqa: S310  (URL validated by caller)
                urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}),
                timeout=timeout,
            ) as r:
                data = r.read()

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(data)
        tmp.close()
        return tmp.name
    except Exception as _e:  # noqa: BLE001
        _logger.warning("Kunde inte ladda ner bild från %s: %s", url, _e)
        return None

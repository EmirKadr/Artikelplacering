"""Tests for core/image_utils.py.

No PyQt6 — pure Python only.
"""
import base64
import io
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from core.image_utils import encode_image, download_image, SUPPORTED_EXT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png_bytes(width: int = 10, height: int = 10) -> bytes:
    """Create a minimal valid PNG in memory."""
    try:
        from PIL import Image
        buf = io.BytesIO()
        img = Image.new("RGB", (width, height), color=(128, 64, 32))
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # Minimal 1x1 red PNG (hardcoded bytes)
        return (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
            b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
            b'\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )


def _write_png(path: Path) -> Path:
    path.write_bytes(_make_png_bytes())
    return path


# ---------------------------------------------------------------------------
# encode_image — basic
# ---------------------------------------------------------------------------

def test_encode_returns_base64_string(tmp_path):
    p = _write_png(tmp_path / "test.png")
    b64, mime = encode_image(str(p))
    # Should be valid base64
    decoded = base64.b64decode(b64)
    assert len(decoded) > 0
    assert mime in ("image/png", "image/jpeg")


def test_encode_png_mime_without_compression(tmp_path):
    p = _write_png(tmp_path / "test.png")
    b64, mime = encode_image(str(p), compress=False)
    assert mime == "image/png"


def test_encode_jpeg_mime(tmp_path):
    p = tmp_path / "test.jpg"
    p.write_bytes(_make_png_bytes())  # content doesn't matter for MIME detection
    b64, mime = encode_image(str(p), compress=False)
    assert mime == "image/jpeg"


def test_encode_unknown_extension_defaults_to_jpeg(tmp_path):
    p = tmp_path / "test.xyz"
    p.write_bytes(b"fake image data")
    b64, mime = encode_image(str(p), compress=False)
    assert mime == "image/jpeg"


# ---------------------------------------------------------------------------
# encode_image — PIL compression path
# ---------------------------------------------------------------------------

def test_encode_compress_produces_jpeg(tmp_path):
    """When PIL is available and compress=True, output should be JPEG."""
    try:
        from PIL import Image  # noqa: F401
        pil_ok = True
    except ImportError:
        pil_ok = False

    if not pil_ok:
        pytest.skip("PIL not installed")

    p = _write_png(tmp_path / "large.png")
    b64, mime = encode_image(str(p), compress=True)
    assert mime == "image/jpeg"
    # Decoded bytes should start with JPEG magic
    data = base64.b64decode(b64)
    assert data[:2] == b'\xff\xd8'


def test_encode_bmp_converted_to_jpeg_with_pil(tmp_path):
    try:
        from PIL import Image
        pil_ok = True
    except ImportError:
        pil_ok = False

    if not pil_ok:
        pytest.skip("PIL not installed")

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (255, 0, 0)).save(buf, format="BMP")
    p = tmp_path / "test.bmp"
    p.write_bytes(buf.getvalue())

    b64, mime = encode_image(str(p), compress=False)
    assert mime == "image/jpeg"


# ---------------------------------------------------------------------------
# encode_image — error handling
# ---------------------------------------------------------------------------

def test_encode_missing_file_raises():
    with pytest.raises((OSError, FileNotFoundError)):
        encode_image("/nonexistent/path/image.jpg", compress=False)


# ---------------------------------------------------------------------------
# download_image
# ---------------------------------------------------------------------------

def test_download_image_returns_none_for_empty_url():
    assert download_image("") is None
    assert download_image(None) is None


def test_download_image_success_with_requests(tmp_path):
    """Mock requests.get to return fake image bytes."""
    fake_response = MagicMock()
    fake_response.content = _make_png_bytes()
    fake_response.raise_for_status = MagicMock()

    with patch("core.image_utils.REQUESTS_AVAILABLE", True), \
         patch("core.image_utils.req") as mock_req:
        mock_req.get.return_value = fake_response
        result = download_image("https://example.com/image.png")

    assert result is not None
    assert os.path.exists(result)
    os.unlink(result)  # cleanup


def test_download_image_uses_correct_suffix(tmp_path):
    fake_response = MagicMock()
    fake_response.content = _make_png_bytes()
    fake_response.raise_for_status = MagicMock()

    with patch("core.image_utils.REQUESTS_AVAILABLE", True), \
         patch("core.image_utils.req") as mock_req:
        mock_req.get.return_value = fake_response
        result = download_image("https://example.com/photo.jpg")

    assert result.endswith(".jpg")
    os.unlink(result)


def test_download_image_defaults_to_jpg_for_unknown_extension():
    fake_response = MagicMock()
    fake_response.content = b"data"
    fake_response.raise_for_status = MagicMock()

    with patch("core.image_utils.REQUESTS_AVAILABLE", True), \
         patch("core.image_utils.req") as mock_req:
        mock_req.get.return_value = fake_response
        result = download_image("https://example.com/image.xyz")

    assert result.endswith(".jpg")
    os.unlink(result)


def test_download_image_returns_none_on_http_error():
    import requests
    with patch("core.image_utils.REQUESTS_AVAILABLE", True), \
         patch("core.image_utils.req") as mock_req:
        mock_req.get.side_effect = Exception("Connection refused")
        result = download_image("https://example.com/bad.jpg")

    assert result is None


def test_download_image_returns_none_on_http_status_error():
    fake_response = MagicMock()
    fake_response.raise_for_status.side_effect = Exception("404 Not Found")

    with patch("core.image_utils.REQUESTS_AVAILABLE", True), \
         patch("core.image_utils.req") as mock_req:
        mock_req.get.return_value = fake_response
        result = download_image("https://example.com/missing.jpg")

    assert result is None


def test_download_image_falls_back_to_urllib_when_requests_unavailable():
    fake_data = _make_png_bytes()

    mock_response = MagicMock()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_response.read.return_value = fake_data

    with patch("core.image_utils.REQUESTS_AVAILABLE", False), \
         patch("core.image_utils.urllib.request.urlopen", return_value=mock_response):
        result = download_image("https://example.com/image.png")

    assert result is not None
    assert os.path.exists(result)
    os.unlink(result)


# ---------------------------------------------------------------------------
# SUPPORTED_EXT sanity
# ---------------------------------------------------------------------------

def test_supported_ext_re_exported():
    """SUPPORTED_EXT is imported from constants and available here."""
    assert ".jpg" in SUPPORTED_EXT
    assert ".png" in SUPPORTED_EXT

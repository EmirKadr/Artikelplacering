"""Tests for core/constants.py.

These tests run without PyQt6 — pure Python only.
"""
from pathlib import Path

import pytest

from core.constants import (
    DATA_DIR,
    SUPPORTED_EXT,
    CATEGORY_COLORS,
    _EMPTY,
    DEFAULT_MODEL,
    DEFAULT_AI_URL,
    MAX_EXAMPLES_PER_CAT,
    MAX_OVRIGT_EXAMPLES,
    EXT_IMAGES_PER_CAT,
    EXT_BATCH_SIZE,
    AI_JOB_MIN_PER_CAT,
    AI_PARALLEL_WORKERS,
    DEFAULT_SYFTE,
    DEFAULT_EXTERNAL_PROVIDERS,
    safe_name,
    _safe_name,
    _WIN_INVALID,
)


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------

def test_data_dir_is_path():
    assert isinstance(DATA_DIR, Path)
    assert DATA_DIR.name == "data"
    assert DATA_DIR.is_absolute()


def test_supported_ext_contains_common_formats():
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"):
        assert ext in SUPPORTED_EXT, f"{ext} missing from SUPPORTED_EXT"


def test_category_colors_are_hex_strings():
    for color in CATEGORY_COLORS:
        assert color.startswith("#"), f"{color} is not a hex color"
        assert len(color) == 7, f"{color} is not a 6-digit hex color"


def test_empty_set_contains_blank():
    assert "" in _EMPTY
    assert "0" in _EMPTY


def test_default_model_nonempty():
    assert isinstance(DEFAULT_MODEL, str) and len(DEFAULT_MODEL) > 0


def test_default_ai_url_is_localhost():
    assert DEFAULT_AI_URL.startswith("http://localhost")


def test_max_examples_positive():
    assert MAX_EXAMPLES_PER_CAT > 0
    assert MAX_OVRIGT_EXAMPLES >= MAX_EXAMPLES_PER_CAT


def test_ext_batch_size_positive():
    assert EXT_BATCH_SIZE > 0


def test_ai_parallel_workers_positive():
    assert AI_PARALLEL_WORKERS > 0


def test_ai_job_min_per_cat_nonnegative():
    assert AI_JOB_MIN_PER_CAT >= 0


def test_default_syfte_nonempty():
    assert isinstance(DEFAULT_SYFTE, str) and len(DEFAULT_SYFTE) > 10


# ---------------------------------------------------------------------------
# DEFAULT_EXTERNAL_PROVIDERS structure
# ---------------------------------------------------------------------------

def test_external_providers_have_url_and_model():
    assert len(DEFAULT_EXTERNAL_PROVIDERS) > 0
    for name, cfg in DEFAULT_EXTERNAL_PROVIDERS.items():
        assert "url" in cfg, f"Provider '{name}' missing 'url'"
        assert "model" in cfg, f"Provider '{name}' missing 'model'"
        assert cfg["url"].startswith("https://"), f"Provider '{name}' URL should use HTTPS"


# ---------------------------------------------------------------------------
# safe_name / _safe_name
# ---------------------------------------------------------------------------

def test_safe_name_replaces_gte():
    assert safe_name(">=5kg") == "gte5kg"


def test_safe_name_replaces_lte():
    assert safe_name("<=10") == "lte10"


def test_safe_name_replaces_gt():
    assert safe_name(">large") == "gtlarge"


def test_safe_name_replaces_lt():
    assert safe_name("<small") == "ltsmall"


def test_safe_name_replaces_windows_invalid_chars():
    for char in r'\/:*?"<>|':
        result = safe_name(f"test{char}name")
        assert char not in result, f"char '{char}' not replaced by safe_name"


def test_safe_name_strips_whitespace():
    assert safe_name("  hello  ") == "hello"


def test_safe_name_normal_string_unchanged():
    assert safe_name("Kök & Bad") == "Kök & Bad"


def test_safe_name_alias_equals_safe_name():
    """_safe_name must be the same function as safe_name."""
    assert _safe_name is safe_name


def test_win_invalid_regex_compiled():
    import re
    assert hasattr(_WIN_INVALID, "sub"), "_WIN_INVALID should be a compiled regex"
    assert _WIN_INVALID.sub("_", "a/b:c") == "a_b_c"

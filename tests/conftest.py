"""Shared pytest fixtures for Artikelplacering test suite."""
import csv
import os
import tempfile
from pathlib import Path
from typing import Generator, List, Dict
import pytest


# ---------------------------------------------------------------------------
# Temporary data directory helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data/ directory with minimal CSV files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def sample_items_csv(tmp_data_dir: Path) -> Path:
    """Write a minimal items CSV and return its path."""
    path = tmp_data_dir / "items.csv"
    rows = [
        ["artikelnummer", "beskrivning", "huvudkategori", "vikt"],
        ["12345", "Testprodukt A", "Kök", "0.5"],
        ["67890", "Testprodukt B", "Badrum", "1.2"],
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerows(rows)
    return path


@pytest.fixture
def sample_attributes_csv(tmp_data_dir: Path) -> Path:
    """Write a minimal attributes CSV and return its path."""
    path = tmp_data_dir / "attributes.csv"
    rows = [
        ["artikelnummer", "bolag", "url", "butiksantal"],
        ["12345", "SE", "https://example.com/12345.jpg", "10"],
        ["67890", "SE", "https://example.com/67890.jpg", "5"],
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# Minimal article row dicts (as produced by _parse_csv / DataManager)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_rows() -> List[Dict]:
    """Two article rows with all expected keys."""
    return [
        {
            "article_number": "12345",
            "url": "https://example.com/12345.jpg",
            "bolag": "SE",
            "description": "Testprodukt A",
        },
        {
            "article_number": "67890",
            "url": "https://example.com/67890.jpg",
            "bolag": "SE",
            "description": "Testprodukt B",
        },
    ]


# ---------------------------------------------------------------------------
# Mock API response helper
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_api_response():
    """Return a factory for fake LLM API responses."""
    def _make(content: str, status: int = 200):
        return {
            "choices": [{"message": {"content": content}}]
        }
    return _make

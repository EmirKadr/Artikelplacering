"""Tests for core/data_manager.py.

No PyQt6 — pure Python only.
Fixtures create temp CSV files with known data so tests are fully hermetic.
"""
import csv
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from core.data_manager import DataManager


# ---------------------------------------------------------------------------
# Helpers — write CSV files in the format DataManager expects
# ---------------------------------------------------------------------------

def write_tsv(path: Path, rows: List[List[str]]):
    """Write rows as tab-separated CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerows(rows)


def write_csv(path: Path, rows: List[List[str]]):
    """Write rows as comma-separated CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=",")
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# _read_tsv
# ---------------------------------------------------------------------------

def test_read_tsv_tab_separated(tmp_path):
    p = tmp_path / "test.csv"
    write_tsv(p, [["Artikel", "Beskrivning"], ["12345", "Testkorg"]])
    dm = DataManager.__new__(DataManager)  # skip __init__ / _load_all
    dm._init_empty()
    rows = dm._read_tsv(p)
    assert rows == [{"Artikel": "12345", "Beskrivning": "Testkorg"}]


def test_read_tsv_comma_separated(tmp_path):
    p = tmp_path / "test.csv"
    write_csv(p, [["Artikel", "Beskrivning"], ["99999", "Kommaseparerad"]])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    rows = dm._read_tsv(p)
    assert rows[0]["Artikel"] == "99999"


def test_read_tsv_missing_file(tmp_path):
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    rows = dm._read_tsv(tmp_path / "nonexistent.csv")
    assert rows == []


def test_read_tsv_empty_file(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    rows = dm._read_tsv(p)
    assert rows == []


# ---------------------------------------------------------------------------
# _load_attributes
# ---------------------------------------------------------------------------

def test_load_attributes_builds_builtin_attributes(tmp_path):
    p = tmp_path / "item_attribute.csv"
    write_tsv(p, [
        ["Artikel", "Bolag", "Namn", "Värde"],
        ["12345", "SE", "IMG", "https://example.com/img.jpg"],
        ["12345", "SE", "StoreQuantity", "42"],
    ])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm._load_attributes(p)
    assert len(dm.builtin_attributes) == 1
    assert dm.builtin_attributes[0]["article_number"] == "12345"
    assert dm.builtin_attributes[0]["url"] == "https://example.com/img.jpg"
    assert dm.store_quantity_data[("12345", "SE")] == "42"


def test_load_attributes_skips_non_http_img(tmp_path):
    p = tmp_path / "item_attribute.csv"
    write_tsv(p, [
        ["Artikel", "Bolag", "Namn", "Värde"],
        ["12345", "SE", "IMG", "ftp://invalid.com/img.jpg"],
    ])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm._load_attributes(p)
    assert dm.builtin_attributes == []


def test_load_attributes_skips_empty_artikel(tmp_path):
    p = tmp_path / "item_attribute.csv"
    write_tsv(p, [
        ["Artikel", "Bolag", "Namn", "Värde"],
        ["", "SE", "IMG", "https://example.com/img.jpg"],
    ])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm._load_attributes(p)
    assert dm.builtin_attributes == []


# ---------------------------------------------------------------------------
# _load_items
# ---------------------------------------------------------------------------

def test_load_items_populates_item_data(tmp_path):
    p = tmp_path / "item.csv"
    write_tsv(p, [
        ["Artikel", "Beskrivning", "UN nummer", "Vikt brutto", "Vikt netto",
         "Volym", "Kategori", "Robot", "Bolag"],
        ["12345", "Testkorg", "", "0.5", "0.4", "1.0", "KAT01", "N", "SE"],
    ])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm._load_items(p)
    assert "12345" in dm.item_data
    assert dm.item_data["12345"]["beskrivning"] == "Testkorg"
    assert dm.item_data["12345"]["kategori"] == "KAT01"


def test_load_items_skips_empty_artikel(tmp_path):
    p = tmp_path / "item.csv"
    write_tsv(p, [
        ["Artikel", "Beskrivning"],
        ["", "Ingen artikel"],
    ])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm._load_items(p)
    assert dm.item_data == {}


# ---------------------------------------------------------------------------
# _load_alias
# ---------------------------------------------------------------------------

def test_load_alias_populates_alias_data(tmp_path):
    p = tmp_path / "item_alias.csv"
    write_tsv(p, [
        ["Artikel", "Alias", "Enhet", "Faktor", "Längd", "Bredd", "Höjd", "Bolag"],
        ["12345", "7312345678901", "ST", "1", "30", "20", "10", "SE"],
    ])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm._load_alias(p)
    assert "12345" in dm.alias_data
    assert dm.alias_data["12345"]["ean"] == "7312345678901"
    assert dm.alias_data["12345"]["langd"] == "30"


def test_load_alias_no_duplicate(tmp_path):
    """Only first occurrence kept when same article appears twice."""
    p = tmp_path / "item_alias.csv"
    write_tsv(p, [
        ["Artikel", "Alias", "Enhet", "Faktor", "Längd", "Bredd", "Höjd", "Bolag"],
        ["12345", "EAN1", "ST", "1", "10", "10", "10", "SE"],
        ["12345", "EAN2", "ST", "1", "20", "20", "20", "SE"],
    ])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm._load_alias(p)
    assert dm.alias_data["12345"]["ean"] == "EAN1"


# ---------------------------------------------------------------------------
# _load_main_category
# ---------------------------------------------------------------------------

def test_load_main_category(tmp_path):
    p = tmp_path / "main_category.csv"
    write_tsv(p, [
        ["Kategori", "Huvudkategori"],
        ["KAT01", "Kök"],
        ["KAT02", "Badrum"],
    ])
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm._load_main_category(p)
    assert dm.category_map["KAT01"] == "Kök"
    assert dm.category_map["KAT02"] == "Badrum"


# ---------------------------------------------------------------------------
# get_meta
# ---------------------------------------------------------------------------

def make_dm_with_data() -> DataManager:
    """Return a DataManager populated with known in-memory data (no files)."""
    dm = DataManager.__new__(DataManager)
    dm._init_empty()
    dm.item_data = {
        "12345": {
            "beskrivning": "Testkorg",
            "un_nummer": "",
            "vikt_brutto": "0.5",
            "vikt_netto": "0.4",
            "volym": "1.0",
            "kategori": "KAT01",
            "robot": "N",
            "bolag": "SE",
        }
    }
    dm.alias_data = {
        "12345": {
            "ean": "7312345678901",
            "enhet": "ST",
            "faktor": "1",
            "langd": "30",
            "bredd": "20",
            "hojd": "10",
            "bolag": "SE",
        }
    }
    dm.category_map = {"KAT01": "Kök"}
    dm.store_quantity_data = {("12345", "SE"): "42"}
    dm.builtin_attributes = []
    return dm


def test_get_meta_returns_combined_data():
    dm = make_dm_with_data()
    meta = dm.get_meta("12345", "SE")
    assert meta is not None
    assert meta["beskrivning"] == "Testkorg"
    assert meta["ean"] == "7312345678901"
    assert meta["huvudkategori"] == "Kök"
    assert meta["store_quantity"] == "42"


def test_get_meta_strips_whitespace():
    dm = make_dm_with_data()
    meta = dm.get_meta("  12345  ", "SE")
    assert meta is not None
    assert meta["beskrivning"] == "Testkorg"


def test_get_meta_returns_none_for_unknown_article():
    dm = make_dm_with_data()
    assert dm.get_meta("99999") is None


def test_get_meta_store_quantity_fallback_to_any_bolag():
    """If bolag doesn't match, fall back to any matching article."""
    dm = make_dm_with_data()
    meta = dm.get_meta("12345", "NO")  # bolag "NO" has no entry
    assert meta is not None
    assert meta["store_quantity"] == "42"  # fell back to SE entry


def test_get_meta_no_store_quantity_when_article_missing():
    dm = make_dm_with_data()
    meta = dm.get_meta("12345", "SE")
    dm.store_quantity_data = {}
    meta2 = dm.get_meta("12345", "SE")
    assert "store_quantity" not in meta2


def test_get_meta_maps_kategori_to_huvudkategori():
    dm = make_dm_with_data()
    meta = dm.get_meta("12345")
    assert meta["huvudkategori"] == "Kök"


def test_get_meta_no_huvudkategori_if_no_map_entry():
    dm = make_dm_with_data()
    dm.category_map = {}
    meta = dm.get_meta("12345")
    assert "huvudkategori" not in meta


# ---------------------------------------------------------------------------
# _load_all routing (via file name conventions)
# ---------------------------------------------------------------------------

def test_load_all_routes_by_filename(tmp_path, monkeypatch):
    """_load_all routes files by filename prefix."""
    # Patch DATA_DIR to point at tmp_path
    import core.data_manager as dm_mod
    monkeypatch.setattr(dm_mod, "DATA_DIR", tmp_path)

    write_tsv(tmp_path / "item.csv", [
        ["Artikel", "Beskrivning", "UN nummer", "Vikt brutto", "Vikt netto",
         "Volym", "Kategori", "Robot", "Bolag"],
        ["77777", "RoutingTest", "", "", "", "", "", "", "SE"],
    ])
    write_tsv(tmp_path / "main_category.csv", [
        ["Kategori", "Huvudkategori"],
        ["K1", "HuvK"],
    ])

    dm = DataManager()
    assert "77777" in dm.item_data
    assert "K1" in dm.category_map


def test_load_all_tolerates_missing_data_dir(tmp_path, monkeypatch):
    """No crash if DATA_DIR doesn't exist."""
    import core.data_manager as dm_mod
    monkeypatch.setattr(dm_mod, "DATA_DIR", tmp_path / "nonexistent")
    dm = DataManager()
    assert dm.item_data == {}


# ---------------------------------------------------------------------------
# Internal helper — attach _init_empty to DataManager for tests
# ---------------------------------------------------------------------------

def _init_empty(self):
    self.builtin_attributes = []
    self.store_quantity_data = {}
    self.item_data = {}
    self.alias_data = {}
    self.category_map = {}


DataManager._init_empty = _init_empty

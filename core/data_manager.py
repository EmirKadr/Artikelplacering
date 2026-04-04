"""DataManager — loads and provides read-only access to CSV data files.

No PyQt6 imports — importable without Qt installed.
"""
import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.constants import DATA_DIR, _EMPTY

_logger = logging.getLogger(__name__)


class DataManager:
    def __init__(self):
        self.builtin_attributes: List[Dict] = []
        self.store_quantity_data: Dict[Tuple[str, str], str] = {}  # (art, bolag) -> qty
        self.item_data:    Dict[str, Dict] = {}
        self.alias_data:   Dict[str, Dict] = {}
        self.category_map: Dict[str, str]  = {}
        self._load_all()

    def _load_all(self):
        if not DATA_DIR.exists():
            return
        for f in sorted(DATA_DIR.iterdir()):
            name = f.name.lower()
            if not name.endswith(".csv"):
                continue
            if name.startswith("item_attribute"):
                self._load_attributes(f)
            elif name.startswith("item_alias"):
                self._load_alias(f)
            elif name.startswith("item") and not name.startswith("item_"):
                self._load_items(f)
            elif name.startswith("main_category"):
                self._load_main_category(f)

    def _read_tsv(self, path) -> List[Dict]:
        try:
            with open(path, newline="", encoding="utf-8-sig") as fh:
                sample = fh.read(4096); fh.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                return list(csv.DictReader(fh, dialect=dialect))
        except (OSError, csv.Error) as _e:
            _logger.warning("Kunde inte läsa fil %s: %s", path, _e)
            return []

    def _load_attributes(self, path):
        self.builtin_attributes = []
        self.store_quantity_data = {}
        art_data: Dict[Tuple[str, str], Dict] = {}
        for row in self._read_tsv(path):
            art   = row.get("Artikel", "").strip()
            bolag = row.get("Bolag",   "").strip()
            namn  = row.get("Namn",    "").strip()
            val   = row.get("Värde",   "").strip()
            if not art:
                continue
            key = (art, bolag)
            if key not in art_data:
                art_data[key] = {"bolag": bolag}
            if namn == "IMG" and val.lower().startswith("http"):
                art_data[key]["url"] = val
            elif namn == "StoreQuantity":
                art_data[key]["store_quantity"] = val
        for (art, bolag), data in art_data.items():
            if "url" in data:
                self.builtin_attributes.append({
                    "article_number": art,
                    "url": data["url"],
                    "bolag": bolag,
                })
            if "store_quantity" in data:
                self.store_quantity_data[(art, bolag)] = data["store_quantity"]

    def _load_alias(self, path):
        self.alias_data = {}
        for row in self._read_tsv(path):
            art = row.get("Artikel", "").strip()
            if not art or art in self.alias_data:
                continue
            self.alias_data[art] = {
                "ean":   row.get("Alias",  "").strip(),
                "enhet": row.get("Enhet",  "").strip(),
                "faktor":row.get("Faktor", "").strip(),
                "langd": row.get("Längd",  "").strip(),
                "bredd": row.get("Bredd",  "").strip(),
                "hojd":  row.get("Höjd",   "").strip(),
                "bolag": row.get("Bolag",  "").strip(),
            }

    def _load_items(self, path):
        self.item_data = {}
        for row in self._read_tsv(path):
            art = row.get("Artikel", "").strip()
            if not art:
                continue
            self.item_data[art] = {
                "beskrivning": row.get("Beskrivning", "").strip(),
                "un_nummer":   row.get("UN nummer",   "").strip(),
                "vikt_brutto": row.get("Vikt brutto", "").strip(),
                "vikt_netto":  row.get("Vikt netto",  "").strip(),
                "volym":       row.get("Volym",        "").strip(),
                "kategori":    row.get("Kategori",     "").strip(),
                "robot":       row.get("Robot",        "").strip(),
                "bolag":       row.get("Bolag",        "").strip(),
            }

    def _load_main_category(self, path):
        self.category_map = {}
        for row in self._read_tsv(path):
            kat  = row.get("Kategori",      "").strip()
            hkat = row.get("Huvudkategori", "").strip()
            if kat and hkat:
                self.category_map[kat] = hkat

    def get_meta(self, article_str: str, bolag: str = "") -> Optional[Dict]:
        art = article_str.strip()
        result: Dict = {}
        if art in self.item_data:
            result.update(self.item_data[art])
        if art in self.alias_data:
            result.update(self.alias_data[art])
        cat_code = result.get("kategori", "")
        if cat_code and cat_code in self.category_map:
            result["huvudkategori"] = self.category_map[cat_code]
        # Look up StoreQuantity: prefer matching bolag, fall back to any
        sq = self.store_quantity_data.get((art, bolag))
        if sq is None:
            sq = next((v for (a, _), v in self.store_quantity_data.items() if a == art), None)
        if sq is not None:
            result["store_quantity"] = sq
        return result or None

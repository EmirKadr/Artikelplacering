#!/usr/bin/env python3
"""Bildklassificering med AI-stöd — PyQt6"""

import sys
import csv
import json
import base64
import random
import shutil
import tempfile
import threading
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, List, Tuple

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QScrollArea, QTextEdit,
    QFileDialog, QMessageBox, QCheckBox, QStackedWidget, QGridLayout,
    QDialog, QDialogButtonBox, QProgressBar, QSizePolicy,
    QRadioButton, QButtonGroup, QScrollBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QPoint, QMimeData, QByteArray
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QFont, QDrag

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

try:
    import requests as req
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ── constants ──────────────────────────────────────────────────────────────────
IMAGE_DIR           = Path("bilder")
DATA_DIR            = Path("data")
SUPPORTED_EXT       = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
CATEGORY_COLORS     = [
    "#4CAF50", "#2196F3", "#FF9800", "#9C27B0",
    "#00BCD4", "#E91E63", "#795548", "#607D8B", "#FF5722",
]
_EMPTY              = {"", "0", "0,00000", "0.00000", "0,0", "0.0"}
DEFAULT_MODEL       = "qwen2.5-vl-72b-instruct"
DEFAULT_AI_URL      = "http://localhost:1234/v1"
MAX_EXAMPLES_PER_CAT = 10   # manually classified articles used per category in AI job (step 1)
AI_JOB_MIN_TOTAL     = 12   # minimum total examples to unlock AI job button

# ── global stylesheet ──────────────────────────────────────────────────────────
STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}
QLabel { color: #cdd6f4; }
QLineEdit, QTextEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 5px 10px;
}
QLineEdit:focus, QTextEdit:focus { border: 1px solid #89b4fa; }
QPushButton {
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
    border: none;
}
QPushButton:hover { opacity: 0.85; }
QPushButton:pressed { opacity: 0.7; }
QScrollArea { border: none; }
QCheckBox { color: #cdd6f4; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 3px;
                       border: 1px solid #45475a; background: #313244; }
QCheckBox::indicator:checked { background: #89b4fa; }
QMessageBox { background-color: #1e1e2e; }
QDialog { background-color: #1e1e2e; }
"""


def mk_btn(text: str, bg: str = "#4CAF50", fg: str = "white",
           min_w: int = 0, h: int = 0) -> QPushButton:
    b = QPushButton(text)
    style = f"background-color:{bg}; color:{fg}; border-radius:6px; padding:8px 16px; font-weight:bold;"
    if min_w:
        style += f" min-width:{min_w}px;"
    b.setStyleSheet(style)
    if h:
        b.setFixedHeight(h)
    return b


def sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color: #313244;")
    return f


# ── DataManager ────────────────────────────────────────────────────────────────
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
        except Exception:
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


# ── AIJobWorker ────────────────────────────────────────────────────────────────
class AIJobWorker(QThread):
    """Two-step AI classification job.

    Step 1 — Category knowledge: For each non-Övrigt category, collect up to
    MAX_EXAMPLES_PER_CAT manually classified articles and ask the LLM to
    summarise what they have in common (text metadata + 1 representative image).

    Step 2 — Classify remaining: For every article in csv_data that has not yet
    been manually classified, download its image (if needed) and ask the LLM
    which category it belongs to, using the summaries from step 1.
    """
    progress           = pyqtSignal(str)
    article_classified = pyqtSignal(str, str, str, str)  # (article_number, category, url, image_path)
    finished_all       = pyqtSignal()
    error              = pyqtSignal(str)

    def __init__(self, categories, categorized, csv_data, syfte,
                 api_url, model, compress, data_mgr, parent=None):
        super().__init__(parent)
        self.categories  = categories   # list[{name, description, knowledge}]
        self.categorized = categorized  # already manually classified items
        self.csv_data    = csv_data     # full article list
        self.syfte       = syfte
        self.api_url     = api_url
        self.model       = model
        self.compress    = compress
        self.data_mgr    = data_mgr
        self._stop       = False

    def stop(self):
        self._stop = True

    # ── main run ───────────────────────────────────────────────────────────────

    def run(self):
        if not REQUESTS_AVAILABLE:
            self.error.emit("requests ej installerat")
            return

        # ── Step 1: generate category knowledge summaries ──────────────────
        self.progress.emit("=== Steg 1: Genererar kategorikunskap ===")
        cat_knowledge: Dict[str, str] = {}
        by_cat: Dict[str, List[Dict]] = {}
        for item in self.categorized:
            cat = item.get("category", "")
            if cat and cat != "Övrigt":
                by_cat.setdefault(cat, []).append(item)

        for cat in self.categories:
            if self._stop:
                return
            name = cat["name"]
            if name == "Övrigt":
                continue
            items = by_cat.get(name, [])[:MAX_EXAMPLES_PER_CAT]
            if not items:
                self.progress.emit(f"  Hoppar {name} — inga exempelartiklar")
                cat_knowledge[name] = cat.get("description", "")
                continue
            self.progress.emit(f"  Analyserar {name} ({len(items)} artiklar)…")
            try:
                knowledge = self._generate_knowledge(name, cat.get("description", ""), items)
                cat_knowledge[name] = knowledge
                self.progress.emit(f"  ✓ {name} klar")
            except Exception as e:
                self.progress.emit(f"  ✗ {name}: {e}")
                cat_knowledge[name] = cat.get("description", "")

        # ── Step 2: classify remaining articles ────────────────────────────
        self.progress.emit("\n=== Steg 2: Klassificerar återstående artiklar ===")
        classified_numbers = {
            e.get("article_number", "") for e in self.categorized
            if e.get("article_number")
        }
        remaining = [
            row for row in self.csv_data
            if str(row.get("article_number", "")) not in classified_numbers
        ]
        if not remaining:
            self.progress.emit("Inga återstående artiklar.")
            self.finished_all.emit()
            return

        self.progress.emit(f"  {len(remaining)} artiklar att klassificera…")
        for i, row in enumerate(remaining):
            if self._stop:
                return
            art_num = str(row.get("article_number", ""))
            url     = row.get("url", "")
            bolag   = row.get("bolag", "")
            img_path = row.get("img_path", "")

            # Download image if not already on disk
            if not img_path or not Path(img_path).exists():
                img_path = self._download_image(url)

            if not img_path:
                self.progress.emit(f"  [{i+1}/{len(remaining)}] {art_num}: bild saknas — hoppar")
                continue

            meta = self.data_mgr.get_meta(art_num, bolag) or {}
            try:
                category = self._classify_article(img_path, meta, cat_knowledge)
                self.article_classified.emit(art_num, category, url, img_path)
                if (i + 1) % 20 == 0 or i == len(remaining) - 1:
                    self.progress.emit(f"  [{i+1}/{len(remaining)}] klassificerade…")
            except Exception as e:
                self.progress.emit(f"  [{i+1}/{len(remaining)}] {art_num}: {e}")

        self.finished_all.emit()

    # ── Step 1 helper ──────────────────────────────────────────────────────────

    def _generate_knowledge(self, cat_name: str, cat_desc: str,
                            items: List[Dict]) -> str:
        """Ask LLM to summarise what's common across example articles."""
        article_lines = []
        representative_img: Optional[str] = None

        for idx, item in enumerate(items):
            art_num = str(item.get("article_number", ""))
            meta    = self.data_mgr.get_meta(art_num, "") or {} if art_num else {}
            parts   = [f"Artikel {idx + 1}:"]
            if meta.get("beskrivning"):
                parts.append(f"  Beskrivning: {meta['beskrivning']}")
            dims = []
            if meta.get("langd"): dims.append(f"längd {meta['langd']} mm")
            if meta.get("bredd"): dims.append(f"bredd {meta['bredd']} mm")
            if meta.get("hojd"):  dims.append(f"höjd {meta['hojd']} mm")
            if dims:
                parts.append(f"  Mått: {', '.join(dims)}")
            if meta.get("volym"):
                parts.append(f"  Volym: {meta['volym']}")
            vikt = []
            if meta.get("vikt_brutto"): vikt.append(f"brutto {meta['vikt_brutto']} kg")
            if meta.get("vikt_netto"):  vikt.append(f"netto {meta['vikt_netto']} kg")
            if vikt:
                parts.append(f"  Vikt: {', '.join(vikt)}")
            article_lines.append("\n".join(parts))

            if representative_img is None:
                p = item.get("image_path", "")
                if p and Path(p).exists():
                    representative_img = p

        prompt = "\n".join([
            f"Syfte: {self.syfte}", "",
            f"Kategori: {cat_name}",
            f"Beskrivning: {cat_desc}" if cat_desc else "",
            "",
            f"Nedan följer {len(items)} exempelartiklar i kategorin.",
            "\n\n".join(article_lines),
            "",
            "Sammanfatta vad som är gemensamt för artiklar i denna kategori.",
            "Fokusera på: produkttyp, typiska mått, volym, vikt och utseende.",
            "Svara på svenska med 3–5 meningar.",
        ])

        content: List[Dict] = []
        if representative_img:
            b64, mime = self._encode(representative_img)
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"}})
        content.append({"type": "text", "text": prompt})

        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": content}],
                   "max_tokens": 400, "temperature": 0.3}
        resp = req.post(f"{self.api_url}/chat/completions", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    # ── Step 2 helper ──────────────────────────────────────────────────────────

    def _classify_article(self, img_path: str, meta: Dict,
                          cat_knowledge: Dict[str, str]) -> str:
        """Classify one article; returns Övrigt if uncertain."""
        cat_names = [c["name"] for c in self.categories if c["name"] != "Övrigt"]
        all_names = cat_names + ["Övrigt"]

        cat_block = "\n".join(
            f"- {name}: {cat_knowledge.get(name, '')}"
            if cat_knowledge.get(name)
            else f"- {name}"
            for name in cat_names
        )
        cat_block += "\n- Övrigt: Artikel som inte tydligt tillhör någon annan kategori."

        art_lines = []
        if meta.get("beskrivning"):
            art_lines.append(f"  Beskrivning: {meta['beskrivning']}")
        dims = []
        if meta.get("langd"): dims.append(f"längd {meta['langd']} mm")
        if meta.get("bredd"): dims.append(f"bredd {meta['bredd']} mm")
        if meta.get("hojd"):  dims.append(f"höjd {meta['hojd']} mm")
        if dims:
            art_lines.append(f"  Mått: {', '.join(dims)}")
        if meta.get("volym"):
            art_lines.append(f"  Volym: {meta['volym']}")
        vikt = []
        if meta.get("vikt_brutto"): vikt.append(f"brutto {meta['vikt_brutto']} kg")
        if meta.get("vikt_netto"):  vikt.append(f"netto {meta['vikt_netto']} kg")
        if vikt:
            art_lines.append(f"  Vikt: {', '.join(vikt)}")

        prompt = "\n".join([
            f"Syfte: {self.syfte}", "",
            "Klassificera artikeln nedan i en av följande kategorier.",
            "Välj 'Övrigt' om artikeln inte tydligt tillhör någon kategori.", "",
            "KATEGORIER:",
            cat_block, "",
            "ARTIKEL ATT KLASSIFICERA:",
            "\n".join(art_lines) if art_lines else "  (ingen metadata)",
            "",
            f"Svara ENDAST med exakt ett av dessa namn: {', '.join(all_names)}",
            "Inget annat — bara kategorinamnet.",
        ])

        b64, mime = self._encode(img_path)
        content = [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": prompt},
        ]
        payload = {"model": self.model,
                   "messages": [{"role": "user", "content": content}],
                   "max_tokens": 30, "temperature": 0.1}
        resp = req.post(f"{self.api_url}/chat/completions", json=payload, timeout=60)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        raw_lower = raw.lower()
        for name in all_names:
            if name.lower() in raw_lower:
                return name
        return "Övrigt"

    # ── utilities ──────────────────────────────────────────────────────────────

    def _download_image(self, url: str) -> Optional[str]:
        if not url:
            return None
        try:
            suffix = Path(url.split("?")[0]).suffix.lower()
            if suffix not in SUPPORTED_EXT:
                suffix = ".jpg"
            resp = req.get(url, timeout=30)
            resp.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(resp.content)
            tmp.close()
            return tmp.name
        except Exception:
            return None

    def _encode(self, path: str) -> Tuple[str, str]:
        suffix   = Path(path).suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}
        mime = mime_map.get(suffix, "image/jpeg")
        if self.compress and PIL_AVAILABLE:
            img = PILImage.open(path)
            img.thumbnail((600, 600), PILImage.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode(), mime


# ── ImageDownloader ────────────────────────────────────────────────────────────
class ImageDownloader(QThread):
    image_ready = pyqtSignal(int, str)   # (index, local_path)

    def __init__(self, rows, temp_dir, parent=None):
        super().__init__(parent)
        self.rows     = rows
        self.temp_dir = temp_dir
        self._stop    = False

    def stop(self):
        self._stop = True

    def run(self):
        for i, row in enumerate(self.rows):
            if self._stop:
                break
            dest = self._download(i, row)
            if dest:
                self.image_ready.emit(i, str(dest))

    def _download(self, i: int, row: Dict) -> Optional[Path]:
        url      = row["url"]
        url_path = url.split("?")[0].rstrip("/")
        filename = url_path.split("/")[-1] or f"img_{i+1}"
        if not Path(filename).suffix:
            filename += ".jpg"
        dest = Path(self.temp_dir) / f"{i:05d}_{filename}"
        try:
            r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(r, timeout=15) as resp:
                dest.write_bytes(resp.read())
            return dest
        except Exception:
            return None


# ── HeaderBar ──────────────────────────────────────────────────────────────────
class HeaderBar(QFrame):
    def __init__(self, test_name: str = "", right_text: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color:#181825; border-bottom:1px solid #313244;")
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        self._left = QLabel(f"Test: {test_name}" if test_name else "Bildklassificering")
        self._left.setStyleSheet("font-size:15px; font-weight:bold; color:#89b4fa;")
        lay.addWidget(self._left)
        lay.addStretch()
        self._right = QLabel(right_text)
        self._right.setStyleSheet("font-size:12px; color:#6c7086;")
        lay.addWidget(self._right)

    def set_texts(self, left: str, right: str = ""):
        self._left.setText(left)
        self._right.setText(right)


# ══════════════════════════════════════════════════════════ Screen 1: Name ══════
class NameScreen(QWidget):
    go_next = pyqtSignal(str, str)   # (test_name, syfte)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setStyleSheet("background-color:#313244; border-radius:12px;")
        card.setFixedWidth(500)
        c = QVBoxLayout(card)
        c.setContentsMargins(40, 40, 40, 40)
        c.setSpacing(12)

        title = QLabel("Bildklassificering")
        title.setStyleSheet("font-size:28px; font-weight:bold; color:#89b4fa;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c.addWidget(title)
        c.addSpacing(12)

        c.addWidget(QLabel("Namn på testet:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("t.ex. Testomgång 1")
        self.name_edit.setFixedHeight(38)
        c.addWidget(self.name_edit)

        c.addSpacing(4)
        c.addWidget(QLabel("Syfte med testet:"))
        hint = QLabel("Beskriv syftet — AI:n använder detta för att förstå sammanhanget")
        hint.setStyleSheet("color:#6c7086; font-size:11px;")
        c.addWidget(hint)
        self.syfte_edit = QTextEdit()
        self.syfte_edit.setPlaceholderText(
            'T.ex. "Kategorisera lagerartiklar för att förenkla lagerhållning.\n'
            'Fokus på att skilja farligt gods från övrigt."'
        )
        self.syfte_edit.setFixedHeight(100)
        c.addWidget(self.syfte_edit)

        c.addSpacing(8)
        go = mk_btn("Gå vidare  →", "#89b4fa", "#1e1e2e", h=44)
        go.clicked.connect(self._validate)
        c.addWidget(go)
        self.name_edit.returnPressed.connect(self._validate)

        lay.addWidget(card)

    def _validate(self):
        name  = self.name_edit.text().strip()
        syfte = self.syfte_edit.toPlainText().strip()
        if not name:
            QMessageBox.warning(self, "Fel", "Ange ett namn för testet.")
            return
        safe = "".join(c for c in name if c not in r'\/:*?"<>|').strip()
        if not safe:
            QMessageBox.warning(self, "Fel", "Namnet innehåller ogiltiga tecken.")
            return
        self.go_next.emit(safe, syfte)

    def reset(self):
        self.name_edit.clear()
        self.syfte_edit.clear()
        self.name_edit.setFocus()


# ══════════════════════════════════════════════════════ Screen 2: Categories ═══
class CategoryRow(QFrame):
    removed = pyqtSignal(object)

    def __init__(self, number: int, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.num_lbl = QLabel(f"{number}.")
        self.num_lbl.setFixedWidth(24)
        self.num_lbl.setStyleSheet("color:#6c7086;")
        lay.addWidget(self.num_lbl)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Kategorinamn")
        self.name_edit.setFixedWidth(190)
        self.name_edit.setFixedHeight(34)
        lay.addWidget(self.name_edit)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Beskrivning (valfritt — hjälper AI:n)")
        self.desc_edit.setFixedHeight(34)
        lay.addWidget(self.desc_edit)

        rm = QPushButton("✕")
        rm.setFixedSize(30, 30)
        rm.setStyleSheet("background:#f38ba8; color:#1e1e2e; border-radius:4px; font-weight:bold;")
        rm.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(rm)

    def set_number(self, n: int):
        self.num_lbl.setText(f"{n}.")

    def get_data(self) -> Tuple[str, str]:
        return self.name_edit.text().strip(), self.desc_edit.text().strip()

    def is_empty(self) -> bool:
        return not self.name_edit.text().strip()


class CategoriesScreen(QWidget):
    go_next = pyqtSignal(list)   # [{name, description}]
    go_back = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[CategoryRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = HeaderBar()
        outer.addWidget(self.header)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(48, 24, 48, 24)
        body_lay.setSpacing(10)

        title = QLabel("Kategorier")
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        body_lay.addWidget(title)

        hint = QLabel(
            '"Övrigt" läggs alltid till automatiskt. '
            'Beskrivningarna är valfria men hjälper AI:n att gissa rätt.'
        )
        hint.setStyleSheet("color:#6c7086; font-size:12px;")
        hint.setWordWrap(True)
        body_lay.addWidget(hint)

        # Column headers
        col_hdr = QFrame()
        col_hdr.setStyleSheet("background:transparent;")
        ch = QHBoxLayout(col_hdr)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(6)
        spacer = QLabel(); spacer.setFixedWidth(24); ch.addWidget(spacer)
        lbl_n = QLabel("Namn"); lbl_n.setStyleSheet("color:#6c7086; font-size:12px;"); lbl_n.setFixedWidth(190)
        ch.addWidget(lbl_n)
        lbl_d = QLabel("Beskrivning (hjälper AI:n)"); lbl_d.setStyleSheet("color:#6c7086; font-size:12px;")
        ch.addWidget(lbl_d)
        ch.addStretch()
        body_lay.addWidget(col_hdr)

        # Scrollable rows area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;")
        self.rows_widget = QWidget()
        self.rows_widget.setStyleSheet("background:transparent;")
        self.rows_lay = QVBoxLayout(self.rows_widget)
        self.rows_lay.setContentsMargins(0, 0, 0, 0)
        self.rows_lay.setSpacing(4)
        self.rows_lay.addStretch()
        scroll.setWidget(self.rows_widget)
        body_lay.addWidget(scroll, 1)

        for _ in range(3):
            self._add_row()

        btn_row = QHBoxLayout()
        add_btn = mk_btn("+ Lägg till rad", "#313244", "#cdd6f4")
        add_btn.clicked.connect(self._add_row)
        btn_row.addWidget(add_btn)
        btn_row.addStretch()
        back_btn = mk_btn("← Tillbaka", "#45475a", "#cdd6f4")
        back_btn.clicked.connect(self.go_back.emit)
        btn_row.addWidget(back_btn)
        next_btn = mk_btn("Starta klassificering  →", "#89b4fa", "#1e1e2e")
        next_btn.clicked.connect(self._validate)
        btn_row.addWidget(next_btn)
        body_lay.addLayout(btn_row)

        outer.addWidget(body)

    def _add_row(self):
        row = CategoryRow(len(self._rows) + 1)
        row.removed.connect(self._remove_row)
        self._rows.append(row)
        self.rows_lay.insertWidget(self.rows_lay.count() - 1, row)
        row.name_edit.setFocus()

    def _remove_row(self, row: CategoryRow):
        self._rows.remove(row)
        row.setParent(None)
        for i, r in enumerate(self._rows):
            r.set_number(i + 1)

    def _validate(self):
        cats = [{"name": n, "description": d}
                for r in self._rows
                for n, d in [r.get_data()] if n]
        if not cats:
            QMessageBox.warning(self, "Fel", "Ange minst en kategori.")
            return
        self.go_next.emit(cats)

    def set_test_name(self, name: str):
        self.header.set_texts(f"Test: {name}")


# ══════════════════════════════════════════════════════════ Screen 3: Source ════
class SourceScreen(QWidget):
    use_folder  = pyqtSignal()
    use_builtin = pyqtSignal()
    use_csv     = pyqtSignal()
    go_back     = pyqtSignal()

    def __init__(self, test_name: str, n_builtin: int, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(HeaderBar(test_name))

        center = QWidget()
        c = QVBoxLayout(center)
        c.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setStyleSheet("background-color:#313244; border-radius:12px;")
        card.setFixedWidth(420)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(32, 32, 32, 32)
        cl.setSpacing(10)

        title = QLabel("Välj bildkälla")
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)
        sub = QLabel("Varifrån ska bilderna hämtas?")
        sub.setStyleSheet("color:#6c7086;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(sub)
        cl.addSpacing(8)

        b1 = mk_btn("📁  Från mapp  (bilder/)", "#2196F3", h=48)
        b1.clicked.connect(self.use_folder.emit)
        cl.addWidget(b1)

        if n_builtin:
            b2 = mk_btn(f"📊  Inbyggd data  ({n_builtin} artiklar)", "#4CAF50", h=48)
            b2.clicked.connect(self.use_builtin.emit)
            cl.addWidget(b2)

        b3 = mk_btn("📄  Ladda upp CSV-fil", "#9C27B0", h=48)
        b3.clicked.connect(self.use_csv.emit)
        cl.addWidget(b3)

        cl.addSpacing(4)
        back = mk_btn("← Tillbaka", "#45475a", "#cdd6f4")
        back.clicked.connect(self.go_back.emit)
        cl.addWidget(back)

        c.addWidget(card)
        outer.addWidget(center)


# ════════════════════════════════════════════════════ Screen 3b: AI Settings ════
class AISettingsScreen(QWidget):
    go_next = pyqtSignal(dict)   # {model, api_url, compress_images} — empty dict = skip AI
    go_back = pyqtSignal()

    def __init__(self, test_name: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(HeaderBar(test_name))

        center = QWidget()
        c = QVBoxLayout(center)
        c.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setStyleSheet("background-color:#313244; border-radius:12px;")
        card.setFixedWidth(480)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(36, 36, 36, 36)
        cl.setSpacing(12)

        title = QLabel("AI-inställningar")
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)

        sub = QLabel(
            "Konfigurera LM Studio. Lämna fälten oförändrade för att använda standardvärden."
        )
        sub.setStyleSheet("color:#6c7086; font-size:12px;")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(sub)
        cl.addSpacing(4)

        cl.addWidget(QLabel("LM Studio URL:"))
        self.url_edit = QLineEdit(DEFAULT_AI_URL)
        cl.addWidget(self.url_edit)

        cl.addWidget(QLabel("Modellnamn:"))
        self.model_edit = QLineEdit(DEFAULT_MODEL)
        cl.addWidget(self.model_edit)

        self.compress_cb = QCheckBox("Komprimera bilder (snabbare, marginellt sämre precision)")
        self.compress_cb.setChecked(True)
        cl.addWidget(self.compress_cb)

        cl.addSpacing(8)
        go = mk_btn("Använd AI  →", "#89b4fa", "#1e1e2e", h=44)
        go.clicked.connect(self._go)
        cl.addWidget(go)

        skip = mk_btn("Hoppa över AI", "#45475a", "#cdd6f4")
        skip.clicked.connect(lambda: self.go_next.emit({}))
        cl.addWidget(skip)

        back = mk_btn("← Tillbaka", "#45475a", "#cdd6f4")
        back.clicked.connect(self.go_back.emit)
        cl.addWidget(back)

        c.addWidget(card)
        outer.addWidget(center)

    def _go(self):
        self.go_next.emit({
            "api_url":         self.url_edit.text().strip() or DEFAULT_AI_URL,
            "model":           self.model_edit.text().strip() or DEFAULT_MODEL,
            "compress_images": self.compress_cb.isChecked(),
        })


# ═══════════════════════════════════════════════════════ Screen 3c: Filter ══════
class FilterScreen(QWidget):
    go_next = pyqtSignal(list)   # filtered rows
    go_back = pyqtSignal()

    def __init__(self, test_name: str, rows: List[Dict], data_mgr, parent=None):
        super().__init__(parent)
        self._all_rows = rows
        self._data_mgr = data_mgr

        # Pre-compute per-row metadata for fast filtering
        self._row_meta: List[Dict] = []
        for r in rows:
            meta = data_mgr.get_meta(str(r["article_number"]), r.get("bolag", "")) or {}
            self._row_meta.append({
                "bolag":       r.get("bolag", "") or "–",
                "hkat":        meta.get("huvudkategori", "") or "Okänd",
                "robot":       meta.get("robot", "N").upper() or "N",
            })

        bolags  = sorted({m["bolag"] for m in self._row_meta})
        hkats   = sorted({m["hkat"]  for m in self._row_meta})

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(HeaderBar(test_name))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(40, 32, 40, 32)
        cl.setSpacing(20)

        title = QLabel("Filtrera artiklar")
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        cl.addWidget(title)

        self._total_lbl = QLabel()
        self._total_lbl.setStyleSheet("color:#6c7086;")
        cl.addWidget(self._total_lbl)

        cl.addWidget(sep())

        # ── Bolag ────────────────────────────────────────────────────────────
        cl.addWidget(self._section_label("Bolag"))
        self._bolag_cbs: List[QCheckBox] = []
        bolag_all = QCheckBox("Alla bolag")
        bolag_all.setChecked(True)
        bolag_all.setStyleSheet("font-weight:bold;")
        cl.addWidget(bolag_all)
        bolag_grid = QWidget()
        bg = QGridLayout(bolag_grid)
        bg.setContentsMargins(16, 0, 0, 0)
        bg.setHorizontalSpacing(16)
        bg.setVerticalSpacing(4)
        for i, b in enumerate(bolags):
            cb = QCheckBox(b)
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_count)
            self._bolag_cbs.append(cb)
            bg.addWidget(cb, i // 3, i % 3)
        cl.addWidget(bolag_grid)

        def _toggle_bolags(state):
            checked = state == Qt.CheckState.Checked.value
            for cb in self._bolag_cbs:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
            self._update_count()
        bolag_all.stateChanged.connect(_toggle_bolags)

        cl.addWidget(sep())

        # ── Huvudkategori ─────────────────────────────────────────────────────
        cl.addWidget(self._section_label("Huvudkategori"))
        self._hkat_cbs: List[QCheckBox] = []
        hkat_all = QCheckBox("Alla kategorier")
        hkat_all.setChecked(True)
        hkat_all.setStyleSheet("font-weight:bold;")
        cl.addWidget(hkat_all)
        hkat_grid = QWidget()
        hg = QGridLayout(hkat_grid)
        hg.setContentsMargins(16, 0, 0, 0)
        hg.setHorizontalSpacing(16)
        hg.setVerticalSpacing(4)
        for i, h in enumerate(hkats):
            cb = QCheckBox(h)
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_count)
            self._hkat_cbs.append(cb)
            hg.addWidget(cb, i // 2, i % 2)
        cl.addWidget(hkat_grid)

        def _toggle_hkats(state):
            checked = state == Qt.CheckState.Checked.value
            for cb in self._hkat_cbs:
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
            self._update_count()
        hkat_all.stateChanged.connect(_toggle_hkats)

        cl.addWidget(sep())

        # ── Robot ─────────────────────────────────────────────────────────────
        cl.addWidget(self._section_label("Robotartikel"))
        robot_row = QHBoxLayout()
        robot_row.setSpacing(20)
        self._robot_group = QButtonGroup(self)
        for i, (lbl, val) in enumerate([("Alla", "alla"), ("Ja (Y)", "Y"), ("Nej (N)", "N")]):
            rb = QRadioButton(lbl)
            rb.setProperty("robot_val", val)
            if i == 0:
                rb.setChecked(True)
            rb.toggled.connect(self._update_count)
            self._robot_group.addButton(rb, i)
            robot_row.addWidget(rb)
        robot_row.addStretch()
        cl.addLayout(robot_row)

        cl.addWidget(sep())

        # ── match count ───────────────────────────────────────────────────────
        self._match_lbl = QLabel()
        self._match_lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#a6e3a1;")
        cl.addWidget(self._match_lbl)

        # ── buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        back_btn = mk_btn("← Tillbaka", "#45475a", "#cdd6f4")
        back_btn.clicked.connect(self.go_back.emit)
        btn_row.addWidget(back_btn)
        btn_row.addStretch()
        self._start_btn = mk_btn("Starta  →", "#89b4fa", "#1e1e2e", h=44)
        self._start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self._start_btn)
        cl.addLayout(btn_row)

        cl.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._update_count()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#89b4fa;")
        return lbl

    def _selected_bolags(self) -> Optional[set]:
        sel = {cb.text() for cb in self._bolag_cbs if cb.isChecked()}
        return None if len(sel) == len(self._bolag_cbs) else sel

    def _selected_hkats(self) -> Optional[set]:
        sel = {cb.text() for cb in self._hkat_cbs if cb.isChecked()}
        return None if len(sel) == len(self._hkat_cbs) else sel

    def _robot_filter(self) -> str:
        checked = self._robot_group.checkedButton()
        return checked.property("robot_val") if checked else "alla"

    def _filtered_rows(self) -> List[Dict]:
        bolags = self._selected_bolags()
        hkats  = self._selected_hkats()
        robot  = self._robot_filter()
        result = []
        for row, meta in zip(self._all_rows, self._row_meta):
            if bolags and meta["bolag"] not in bolags:
                continue
            if hkats and meta["hkat"] not in hkats:
                continue
            if robot != "alla" and meta["robot"] != robot:
                continue
            result.append(row)
        return result

    def _update_count(self):
        n = len(self._filtered_rows())
        total = len(self._all_rows)
        self._total_lbl.setText(f"Totalt {total} artiklar i källan")
        self._match_lbl.setText(f"{n} artikel{'er' if n != 1 else ''} matchar filtret")
        self._start_btn.setEnabled(n > 0)

    def _on_start(self):
        self.go_next.emit(self._filtered_rows())


# ══════════════════════════════════════════════════════ Screen 4: Classify ══════
class ClassifyScreen(QWidget):
    classified   = pyqtSignal(str)
    skipped      = pyqtSignal()
    add_category = pyqtSignal()
    end_test     = pyqtSignal()
    run_ai_job   = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shortcuts: List[QShortcut] = []
        self._inner: Optional[QWidget]   = None
        self._main_lay = QVBoxLayout(self)
        self._main_lay.setContentsMargins(0, 0, 0, 0)
        self._main_lay.setSpacing(0)

    def show_image(self, test_name: str, categories: List[Dict],
                   image_path: str, meta: Optional[Dict],
                   current: int, total: int,
                   cat_counts: Optional[Dict[str, int]] = None,
                   threshold: int = 0,
                   ai_job_ready: bool = False):
        self._clear()
        self._test_name    = test_name
        self._categories   = categories
        self._image_path   = image_path
        self._meta         = meta
        self._current      = current
        self._total        = total
        self._cat_counts   = cat_counts or {}
        self._threshold    = threshold
        self._ai_job_ready = ai_job_ready
        self._build()

    def _clear(self):
        for sc in self._shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self._shortcuts.clear()
        if self._inner:
            self._main_lay.removeWidget(self._inner)
            self._inner.setParent(None)
            self._inner = None

    def _build(self):
        self._inner = QWidget()
        inner_lay = QVBoxLayout(self._inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(0)

        # ── header
        prog = f"Bild {self._current + 1} av {self._total}"
        header = HeaderBar(self._test_name, prog)
        inner_lay.addWidget(header)

        # ── threshold progress bar (shown when AI settings configured)
        if self._threshold > 0:
            inner_lay.addWidget(self._build_threshold_bar())

        # ── image + meta
        content = QFrame()
        content.setStyleSheet("background-color:#11111b;")
        content_lay = QHBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background-color:#11111b;")
        content_lay.addWidget(self._img_lbl, 1)

        if self._meta:
            content_lay.addWidget(self._build_meta_panel())

        inner_lay.addWidget(content, 1)
        self._load_image()

        # ── file info bar
        info_bar = QFrame()
        info_bar.setStyleSheet("background:#181825; border-top:1px solid #313244;")
        info_bar.setFixedHeight(26)
        ib = QHBoxLayout(info_bar)
        ib.setContentsMargins(12, 0, 12, 0)
        ib.addWidget(QLabel(str(self._image_path)))
        inner_lay.addWidget(info_bar)

        # ── category buttons
        cat_frame = QFrame()
        cat_frame.setStyleSheet("background:#1e1e2e;")
        cf = QVBoxLayout(cat_frame)
        cf.setContentsMargins(12, 8, 12, 4)
        self._build_cat_buttons(cf)
        inner_lay.addWidget(cat_frame)

        # ── control bar
        ctrl = QFrame()
        ctrl.setStyleSheet("background:#1e1e2e; border-top:1px solid #313244;")
        ctrl_lay = QHBoxLayout(ctrl)
        ctrl_lay.setContentsMargins(12, 6, 12, 6)
        skip_btn = mk_btn("Hoppa över", "#45475a", "#cdd6f4")
        skip_btn.clicked.connect(self.skipped.emit)
        ctrl_lay.addWidget(skip_btn)
        add_btn = mk_btn("+ Ny kategori", "#FF9800")
        add_btn.clicked.connect(self.add_category.emit)
        ctrl_lay.addWidget(add_btn)
        ctrl_lay.addStretch()
        if self._ai_job_ready:
            ai_btn = mk_btn("🤖  Kör AI jobb", "#1e3a5f", "#89b4fa", h=34)
            ai_btn.clicked.connect(self.run_ai_job.emit)
            ctrl_lay.addWidget(ai_btn)
        end_btn = mk_btn("Avsluta test", "#f38ba8", "#1e1e2e")
        end_btn.clicked.connect(self._confirm_end)
        ctrl_lay.addWidget(end_btn)
        inner_lay.addWidget(ctrl)

        self._main_lay.addWidget(self._inner)

    def _build_threshold_bar(self) -> QFrame:
        """Shows per-category progress toward the AI job threshold."""
        bar = QFrame()
        bar.setStyleSheet("background:#181825; border-bottom:1px solid #313244;")
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(16)
        non_ovrigt = [c for c in self._categories if c["name"] != "Övrigt"]
        for cat in non_ovrigt:
            name  = cat["name"]
            count = self._cat_counts.get(name, 0)
            done  = count >= self._threshold
            color = "#a6e3a1" if done else "#f38ba8"
            lbl = QLabel(f"{name}: {count}/{self._threshold}")
            lbl.setStyleSheet(
                f"color:{color}; font-size:11px; font-weight:{'bold' if done else 'normal'};"
            )
            lay.addWidget(lbl)
        lay.addStretch()
        if self._ai_job_ready:
            hint = QLabel("Alla kategorier klara — klicka 'Kör AI jobb'")
            hint.setStyleSheet("color:#89b4fa; font-size:11px; font-style:italic;")
            lay.addWidget(hint)
        return bar

    def _build_meta_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(220)
        panel.setStyleSheet("background:#181825; border-left:1px solid #313244;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(5)

        title = QLabel("Artikelinfo")
        title.setStyleSheet("font-size:12px; font-weight:bold; color:#6c7086;")
        lay.addWidget(title)
        lay.addWidget(sep())

        fields = [
            ("Beskrivning",   self._meta.get("beskrivning")),
            ("Huvudkategori", self._meta.get("huvudkategori")),
            ("Kategori",      self._meta.get("kategori")),
            ("UN nummer",     self._meta.get("un_nummer")),
            ("StoreQuantity", self._meta.get("store_quantity")),
            ("Robot",         self._meta.get("robot")),
            ("Vikt brutto",   self._meta.get("vikt_brutto")),
            ("Vikt netto",    self._meta.get("vikt_netto")),
            ("Volym",         self._meta.get("volym")),
            ("EAN",           self._meta.get("ean")),
            ("Längd",         self._meta.get("langd")),
            ("Bredd",         self._meta.get("bredd")),
            ("Höjd",          self._meta.get("hojd")),
        ]
        for label, value in fields:
            if not value or value in _EMPTY:
                continue
            row = QFrame(); row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(4)
            lbl_w = QLabel(f"{label}:"); lbl_w.setStyleSheet("color:#6c7086; font-size:11px;"); lbl_w.setFixedWidth(82)
            val_w = QLabel(str(value)); val_w.setStyleSheet("color:#cdd6f4; font-size:11px;"); val_w.setWordWrap(True)
            rl.addWidget(lbl_w); rl.addWidget(val_w, 1)
            lay.addWidget(row)

        lay.addStretch()
        return panel

    def _build_cat_buttons(self, parent_lay: QVBoxLayout):
        key_map: Dict[int, Tuple[str, str]] = {}
        for i, cat in enumerate(self._categories[:9]):
            key_map[i + 1] = (cat["name"], CATEGORY_COLORS[i % len(CATEGORY_COLORS)])
        key_map[0] = ("Övrigt", "#45475a")

        positions = {
            7: (0,0), 8: (0,1), 9: (0,2),
            4: (1,0), 5: (1,1), 6: (1,2),
            1: (2,0), 2: (2,1), 3: (2,2),
            0: (3,1),
        }
        grid_w = QWidget(); grid_w.setStyleSheet("background:transparent;")
        grid = QGridLayout(grid_w); grid.setSpacing(4)

        for key, (row, col) in positions.items():
            if key not in key_map:
                continue
            name, color = key_map[key]
            b = QPushButton(f"{name}  ({key})")
            b.setFixedSize(168, 40)
            b.setStyleSheet(
                f"background:{color}; color:white; border-radius:6px; "
                f"font-weight:bold; border:none;"
            )
            b.clicked.connect(lambda checked, c=name: self.classified.emit(c))
            grid.addWidget(b, row, col, Qt.AlignmentFlag.AlignCenter)

            sc = QShortcut(QKeySequence(str(key)), self)
            sc.activated.connect(lambda c=name: self.classified.emit(c))
            self._shortcuts.append(sc)

        parent_lay.addWidget(grid_w, 0, Qt.AlignmentFlag.AlignCenter)

    def _load_image(self):
        try:
            if PIL_AVAILABLE:
                img = PILImage.open(self._image_path)
                img.thumbnail((780, 370), PILImage.LANCZOS)
                buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
                px = QPixmap(); px.loadFromData(buf.read())
            else:
                px = QPixmap(self._image_path)
                px = px.scaled(780, 370, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._img_lbl.setPixmap(px)
        except Exception as e:
            self._img_lbl.setText(f"Kunde inte visa bild:\n{e}")
            self._img_lbl.setStyleSheet("color:#f38ba8;")

    def _confirm_end(self):
        if QMessageBox.question(self, "Avsluta", "Vill du avsluta testet?") == \
                QMessageBox.StandardButton.Yes:
            self.end_test.emit()


# ═══════════════════════════════════════════════ Screen 4b: AI Job Live View ════

_CARD_MIME = "application/x-article-card"


class ImageCard(QFrame):
    """Draggable thumbnail for one AI-classified article."""
    view_image = pyqtSignal(str)  # emits image_path on click

    def __init__(self, article_number: str, image_path: str,
                 category: str, parent=None):
        super().__init__(parent)
        self.article_number = article_number
        self.image_path     = image_path
        self.category       = category
        self._drag_start:   Optional[QPoint] = None

        self.setFixedHeight(120)
        self.setStyleSheet(
            "background:#313244; border-radius:6px; border:1px solid #45475a;"
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(article_number)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)

        self._img_lbl = QLabel()
        self._img_lbl.setFixedSize(150, 108)
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background:#11111b; border-radius:4px;")
        lay.addWidget(self._img_lbl)

        art_lbl = QLabel(article_number)
        art_lbl.setStyleSheet("color:#cdd6f4; font-size:10px;")
        art_lbl.setWordWrap(True)
        art_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(art_lbl, 1)

        self._load_thumbnail()

    def _load_thumbnail(self):
        if not self.image_path or not Path(self.image_path).exists():
            self._img_lbl.setText("?")
            return
        try:
            if PIL_AVAILABLE:
                img = PILImage.open(self.image_path)
                img.thumbnail((150, 108), PILImage.LANCZOS)
                buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
                px = QPixmap(); px.loadFromData(buf.read())
            else:
                px = QPixmap(self.image_path)
                px = px.scaled(150, 108,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._img_lbl.setPixmap(px)
        except Exception:
            self._img_lbl.setText("!")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()

    def mouseMoveEvent(self, event):
        if (self._drag_start is not None and
                event.buttons() & Qt.MouseButton.LeftButton):
            if (event.pos() - self._drag_start).manhattanLength() > 8:
                self._start_drag()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            if (event.pos() - self._drag_start).manhattanLength() <= 8:
                self.view_image.emit(self.image_path)
        self._drag_start = None

    def _start_drag(self):
        import json
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(
            _CARD_MIME,
            QByteArray(json.dumps({
                "article_number": self.article_number,
                "from_category":  self.category,
                "image_path":     self.image_path,
            }).encode()),
        )
        px = self._img_lbl.pixmap()
        if px and not px.isNull():
            drag.setPixmap(px.scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start = None


class CategoryColumn(QFrame):
    """Scrollable column for one category in the AI job live view."""
    card_dropped = pyqtSignal(str, str, str)  # (article_number, from_cat, to_cat)

    def __init__(self, category_name: str, color: str, parent=None):
        super().__init__(parent)
        self.category_name = category_name
        self.setAcceptDrops(True)
        self._normal_style = "background:#1e1e2e; border-right:1px solid #313244;"
        self._hover_style  = (
            "background:#1e1e2e; border-right:1px solid #313244;"
            "border:2px solid #89b4fa;"
        )
        self.setStyleSheet(self._normal_style)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── header ─────────────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(44)
        header.setStyleSheet("background:#181825; border-bottom:1px solid #313244;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 0, 10, 0)
        name_lbl = QLabel(category_name)
        name_lbl.setStyleSheet(
            f"color:{color}; font-size:12px; font-weight:bold;"
        )
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(name_lbl, 1)
        self._count_lbl = QLabel("0")
        self._count_lbl.setStyleSheet("color:#6c7086; font-size:11px;")
        hl.addWidget(self._count_lbl)
        layout.addWidget(header)

        # ── scroll area ────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("border:none;")

        self._container = QWidget()
        self._container.setStyleSheet("background:#1e1e2e;")
        self._cards_lay = QVBoxLayout(self._container)
        self._cards_lay.setContentsMargins(6, 6, 6, 6)
        self._cards_lay.setSpacing(5)
        self._cards_lay.addStretch()

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, 1)

        self._cards: List["ImageCard"] = []

    def prepend_card(self, card: "ImageCard"):
        """Insert card at the top (newest first)."""
        self._cards_lay.insertWidget(0, card)
        self._cards.insert(0, card)
        self._count_lbl.setText(str(len(self._cards)))
        QTimer.singleShot(30, lambda: self._scroll.verticalScrollBar().setValue(0))

    def remove_card_by_article(self, article_number: str) -> Optional["ImageCard"]:
        for card in self._cards:
            if card.article_number == article_number:
                self._cards_lay.removeWidget(card)
                card.setParent(None)
                self._cards.remove(card)
                self._count_lbl.setText(str(len(self._cards)))
                return card
        return None

    # ── drag & drop ────────────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_CARD_MIME):
            import json
            data = json.loads(bytes(event.mimeData().data(_CARD_MIME)))
            if data.get("from_category") != self.category_name:
                event.acceptProposedAction()
                self.setStyleSheet(self._hover_style)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._normal_style)

    def dropEvent(self, event):
        self.setStyleSheet(self._normal_style)
        if event.mimeData().hasFormat(_CARD_MIME):
            import json
            data = json.loads(bytes(event.mimeData().data(_CARD_MIME)))
            from_cat = data.get("from_category", "")
            art_num  = data.get("article_number", "")
            if from_cat != self.category_name and art_num:
                event.acceptProposedAction()
                self.card_dropped.emit(art_num, from_cat, self.category_name)
                return
        event.ignore()


class AIJobScreen(QWidget):
    """Full-screen live view while the AI job runs.

    Shows a kanban board — one column per category — updating in real time.
    Cards are draggable between columns to correct misclassifications.
    Clicking a card opens an enlarged image view.
    """
    article_added = pyqtSignal(str, str, str)   # (article_number, category, url)
    reclassified  = pyqtSignal(str, str)         # (article_number, new_category)
    finished      = pyqtSignal()

    def __init__(self, categories: List[Dict], categorized: List[Dict],
                 csv_data: List[Dict], syfte: str,
                 api_url: str, model: str, compress: bool,
                 data_mgr, test_name: str, parent=None):
        super().__init__(parent)
        self._categories = categories
        self._categorized = categorized
        self._csv_data    = csv_data
        self._syfte       = syfte
        self._api_url     = api_url
        self._model       = model
        self._compress    = compress
        self._data_mgr    = data_mgr
        self._test_name   = test_name
        self._worker: Optional[AIJobWorker] = None
        self._columns: Dict[str, CategoryColumn] = {}
        self._total_classified = 0

        # How many articles remain (step 2)
        classified_numbers = {
            e.get("article_number", "") for e in categorized if e.get("article_number")
        }
        self._remaining_count = sum(
            1 for row in csv_data
            if str(row.get("article_number", "")) not in classified_numbers
        )

        self._build()

    # ── UI ─────────────────────────────────────────────────────────────────────

    def _build(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        self._header = HeaderBar(
            self._test_name, "AI-jobb startar…"
        )
        main_lay.addWidget(self._header)

        # ── kanban columns ────────────────────────────────────────────────
        cols_widget = QWidget()
        cols_widget.setStyleSheet("background:#1e1e2e;")
        cols_lay = QHBoxLayout(cols_widget)
        cols_lay.setContentsMargins(0, 0, 0, 0)
        cols_lay.setSpacing(0)

        non_ovrigt = [c for c in self._categories if c["name"] != "Övrigt"]
        all_display = non_ovrigt + [{"name": "Övrigt"}]
        for i, cat in enumerate(all_display):
            name  = cat["name"]
            color = (CATEGORY_COLORS[i % len(CATEGORY_COLORS)]
                     if name != "Övrigt" else "#6c7086")
            col = CategoryColumn(name, color)
            col.card_dropped.connect(self._on_card_dropped)
            cols_lay.addWidget(col)
            self._columns[name] = col

        main_lay.addWidget(cols_widget, 1)

        # ── footer ────────────────────────────────────────────────────────
        footer = QFrame()
        footer.setFixedHeight(44)
        footer.setStyleSheet(
            "background:#181825; border-top:1px solid #313244;"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 0, 16, 0)

        self._progress_lbl = QLabel("Steg 1: Genererar kategorikunskap…")
        self._progress_lbl.setStyleSheet("color:#6c7086; font-size:12px;")
        fl.addWidget(self._progress_lbl, 1)

        self._done_btn = mk_btn("💾  Exportera & Avsluta", "#1B5E20", h=32)
        self._done_btn.setVisible(False)
        self._done_btn.clicked.connect(self.finished.emit)
        fl.addWidget(self._done_btn)

        main_lay.addWidget(footer)

    # ── worker management ──────────────────────────────────────────────────────

    def start(self):
        self._worker = AIJobWorker(
            self._categories, self._categorized, self._csv_data, self._syfte,
            self._api_url, self._model, self._compress, self._data_mgr,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.article_classified.connect(self._on_article_classified)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.error.connect(
            lambda msg: self._progress_lbl.setText(f"FEL: {msg}")
        )
        self._worker.start()

    def stop_worker(self):
        if self._worker:
            self._worker.stop()
            self._worker.wait()
            self._worker = None

    # ── slots ──────────────────────────────────────────────────────────────────

    def _on_progress(self, msg: str):
        # Show only the last meaningful line in the footer
        text = msg.strip()
        if text:
            self._progress_lbl.setText(text)

    def _on_article_classified(self, article_number: str, category: str,
                                url: str, image_path: str):
        self._total_classified += 1
        col = self._columns.get(category) or self._columns.get("Övrigt")
        if col:
            card = ImageCard(article_number, image_path, category)
            card.view_image.connect(self._show_image_large)
            col.prepend_card(card)

        self._header.set_texts(
            self._test_name,
            f"Klassificerar… {self._total_classified}/{self._remaining_count}",
        )
        self.article_added.emit(article_number, category, url)

    def _on_finished(self):
        self._progress_lbl.setText(
            f"✓ Klart!  {self._total_classified} artiklar klassificerade av AI."
        )
        self._header.set_texts(self._test_name, "AI-jobb klart")
        self._done_btn.setVisible(True)

    def _on_card_dropped(self, article_number: str, from_cat: str, to_cat: str):
        from_col = self._columns.get(from_cat)
        to_col   = self._columns.get(to_cat)
        if from_col and to_col:
            card = from_col.remove_card_by_article(article_number)
            if card:
                card.category = to_cat
                to_col.prepend_card(card)
        self.reclassified.emit(article_number, to_cat)

    def _show_image_large(self, image_path: str):
        if not image_path or not Path(image_path).exists():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Bildvisning")
        dlg.setStyleSheet(STYLE)
        lay = QVBoxLayout(dlg)
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        try:
            if PIL_AVAILABLE:
                img = PILImage.open(image_path)
                img.thumbnail((900, 700), PILImage.LANCZOS)
                buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
                px = QPixmap(); px.loadFromData(buf.read())
            else:
                px = QPixmap(image_path)
                px = px.scaled(900, 700,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(px)
        except Exception as e:
            lbl.setText(str(e))
        lay.addWidget(lbl)
        close_btn = mk_btn("Stäng", "#45475a")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)
        dlg.exec()


# ═══════════════════════════════════════════════════════════ Screen 5: Done ════
class DoneScreen(QWidget):
    new_test      = pyqtSignal()
    retest_ovrigt = pyqtSignal()
    export_excel  = pyqtSignal()
    quit_app      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)

    def show_results(self, test_name: str, categories: List[Dict],
                     n_processed: int, csv_mode: bool, has_results: bool,
                     ovrigt_count: int):
        # Clear old content
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        self._lay.addWidget(HeaderBar(test_name))

        center = QWidget()
        c = QVBoxLayout(center)
        c.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setStyleSheet("background-color:#313244; border-radius:12px;")
        card.setFixedWidth(500)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 40, 40, 40)
        cl.setSpacing(8)

        ok_lbl = QLabel("✓  Test avslutat!")
        ok_lbl.setStyleSheet("font-size:28px; font-weight:bold; color:#a6e3a1;")
        ok_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(ok_lbl)

        processed_lbl = QLabel(f"Behandlade bilder: {n_processed}")
        processed_lbl.setStyleSheet("color:#6c7086;")
        processed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(processed_lbl)
        cl.addSpacing(8)

        for cat in categories + [{"name": "Övrigt"}]:
            folder = Path(f"{test_name}.{cat['name']}")
            if folder.exists():
                count = len(list(folder.iterdir()))
                row = QLabel(f"📁  {folder.name}  —  {count} bild(er)")
                cl.addWidget(row)

        cl.addSpacing(12)

        if csv_mode and has_results:
            ex = mk_btn("💾  Exportera Excel", "#1B5E20", h=44)
            ex.clicked.connect(self.export_excel.emit)
            cl.addWidget(ex)

        if ovrigt_count:
            ov = mk_btn(f"Testa Övrigt igen  ({ovrigt_count} bilder)", "#FF9800", h=44)
            ov.clicked.connect(self.retest_ovrigt.emit)
            cl.addWidget(ov)

        nav = QHBoxLayout()
        new_b = mk_btn("Nytt test", "#2196F3"); new_b.clicked.connect(self.new_test.emit)
        quit_b = mk_btn("Avsluta", "#f38ba8", "#1e1e2e"); quit_b.clicked.connect(self.quit_app.emit)
        nav.addWidget(new_b); nav.addWidget(quit_b)
        cl.addLayout(nav)

        c.addWidget(card)
        self._lay.addWidget(center)


# ══════════════════════════════════════════════════════════ MainApp ════════════
class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bildklassificering")
        self.resize(1000, 700)
        self.setMinimumSize(820, 600)
        self.setStyleSheet(STYLE)

        # ── Session state
        self.test_name    = ""
        self.syfte        = ""
        self.categories: List[Dict] = []
        self.images: List[Optional[Path]] = []
        self.current_index = 0
        self.csv_mode     = False
        self.csv_data:    List[Dict] = []
        self.results:     List[Dict] = []
        self.temp_dir:    Optional[str] = None
        self.retesting_ovrigt = False
        self.categorized: List[Dict] = []

        # ── AI state
        self.ai_settings: Dict = {}
        self.ai_enabled   = False

        # ── Data
        self.data_mgr = DataManager()

        # ── Download worker
        self.dl_worker:       Optional[ImageDownloader] = None
        self._ready_images:   set = set()

        # ── Stack
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self._name_scr  = NameScreen()
        self._cat_scr   = CategoriesScreen()
        self._cl_scr    = ClassifyScreen()
        self._done_scr  = DoneScreen()

        self.stack.addWidget(self._name_scr)   # 0
        self.stack.addWidget(self._cat_scr)    # 1
        # indices 2+ are dynamic (source, ai-settings, wait screens)
        self.stack.addWidget(self._cl_scr)     # added as needed
        self.stack.addWidget(self._done_scr)

        # ── Connections
        self._name_scr.go_next.connect(self._on_name_done)
        self._cat_scr.go_next.connect(self._on_cats_done)
        self._cat_scr.go_back.connect(lambda: self.stack.setCurrentWidget(self._name_scr))

        self._cl_scr.classified.connect(self._on_classified)
        self._cl_scr.skipped.connect(self._on_skip)
        self._cl_scr.add_category.connect(self._add_cat_during_test)
        self._cl_scr.end_test.connect(self._show_done)
        self._cl_scr.run_ai_job.connect(self._run_ai_job)

        self._done_scr.new_test.connect(self._on_new_test)
        self._done_scr.retest_ovrigt.connect(self._retest_ovrigt)
        self._done_scr.export_excel.connect(self._export_excel)
        self._done_scr.quit_app.connect(self.close)

        self.stack.setCurrentWidget(self._name_scr)
        self.showMaximized()

    # ── helpers ────────────────────────────────────────────────────────────────

    def _push_screen(self, widget: QWidget):
        """Add widget to stack and show it."""
        self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)

    def _replace_top(self, new_widget: QWidget, old_widget: Optional[QWidget]):
        """Replace the top (last) dynamic screen."""
        if old_widget and self.stack.indexOf(old_widget) >= 0:
            self.stack.removeWidget(old_widget)
            old_widget.setParent(None)
        self._push_screen(new_widget)

    # ── navigation ─────────────────────────────────────────────────────────────

    def _on_name_done(self, name: str, syfte: str):
        self.test_name = name
        self.syfte     = syfte
        self._cat_scr.set_test_name(name)
        self.stack.setCurrentWidget(self._cat_scr)

    def _on_cats_done(self, cats: List[Dict]):
        self.categories = [dict(c, knowledge="") for c in cats]
        self._show_source_screen()

    def _show_source_screen(self):
        src = SourceScreen(self.test_name, len(self.data_mgr.builtin_attributes))
        src.use_folder.connect(self._load_folder)
        src.use_builtin.connect(self._show_filter_screen)
        src.use_csv.connect(self._load_csv)
        src.go_back.connect(lambda: self.stack.setCurrentWidget(self._cat_scr))
        self._src_scr = src
        self._push_screen(src)

    def _show_filter_screen(self):
        flt = FilterScreen(self.test_name, list(self.data_mgr.builtin_attributes), self.data_mgr)
        flt.go_next.connect(self._download_images)
        flt.go_back.connect(lambda: self.stack.setCurrentWidget(self._src_scr))
        self._flt_scr = flt
        self._push_screen(flt)

    def _show_ai_settings(self):
        ai = AISettingsScreen(self.test_name)
        ai.go_next.connect(self._on_ai_done)
        ai.go_back.connect(lambda: self.stack.setCurrentWidget(self._src_scr))
        self._ai_scr = ai
        self._push_screen(ai)

    def _on_ai_done(self, settings: Dict):
        self.ai_settings = settings
        self.ai_enabled  = bool(settings)
        self._show_classify()

    # ── image loading ──────────────────────────────────────────────────────────

    def _load_folder(self):
        self.csv_mode = False
        if not IMAGE_DIR.exists():
            QMessageBox.critical(self, "Mapp saknas", f'Mappen "{IMAGE_DIR}" hittades inte.')
            return
        imgs = [f for f in IMAGE_DIR.iterdir() if f.suffix.lower() in SUPPORTED_EXT]
        if not imgs:
            QMessageBox.warning(self, "Inga bilder", f'Inga bilder i "{IMAGE_DIR}".')
            return
        random.shuffle(imgs)
        self.images = imgs
        self.current_index = 0
        self._show_ai_settings()

    def _load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Välj CSV-fil", "", "CSV-filer (*.csv);;Alla filer (*)"
        )
        if not path:
            return
        rows = self._parse_csv(path)
        if rows:
            self._download_images(rows)

    def _parse_csv(self, path: str) -> Optional[List[Dict]]:
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                sample = f.read(4096); f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                all_rows = list(csv.reader(f, dialect))
            url_col = None
            for row in all_rows[:5]:
                for i, cell in enumerate(row):
                    if cell.strip().lower().startswith("http"):
                        url_col = i; break
                if url_col is not None:
                    break
            if url_col is None:
                QMessageBox.warning(self, "Ingen URL-kolumn",
                                    "Kunde inte hitta kolumn med URL:er.")
                return None
            rows = []
            for row in all_rows:
                if len(row) <= url_col: continue
                art = row[0].strip(); url = row[url_col].strip()
                if art and url.lower().startswith("http"):
                    rows.append({"article_number": art, "url": url})
            if not rows:
                QMessageBox.warning(self, "Inga rader", "Inga giltiga rader i filen.")
                return None
            return rows
        except Exception as e:
            QMessageBox.critical(self, "CSV-fel", f"Kunde inte läsa filen:\n{e}")
            return None

    def _download_images(self, rows: List[Dict]):
        random.shuffle(rows)
        self.csv_mode  = True
        self.csv_data  = [{"article_number": r["article_number"], "url": r["url"],
                           "bolag": r.get("bolag", ""), "img_path": None} for r in rows]
        self.images    = [None] * len(rows)
        self.results   = []
        self.current_index  = 0
        self._ready_images  = set()

        self.temp_dir = tempfile.mkdtemp(prefix="bildklassificering_")
        if self.dl_worker:
            self.dl_worker.stop(); self.dl_worker.wait()
        self.dl_worker = ImageDownloader(rows, self.temp_dir)
        self.dl_worker.image_ready.connect(self._on_image_ready)
        self.dl_worker.start()

        # Show a loading screen until image 0 is ready
        self._loading_scr = self._make_loading_screen(len(rows))
        self._push_screen(self._loading_scr)

        def poll():
            if 0 in self._ready_images:
                self.stack.removeWidget(self._loading_scr)
                self._loading_scr.setParent(None)
                self._show_ai_settings()
            else:
                QTimer.singleShot(200, poll)
        QTimer.singleShot(200, poll)

    def _make_loading_screen(self, total: int) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#1e1e2e;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("Hämtar bilder…")
        lbl.setStyleSheet("font-size:20px; font-weight:bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        sub = QLabel(f"{total} bilder totalt — resten hämtas i bakgrunden")
        sub.setStyleSheet("color:#6c7086;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        return w

    def _on_image_ready(self, index: int, path: str):
        self._ready_images.add(index)
        self.images[index] = Path(path)
        if index < len(self.csv_data):
            self.csv_data[index]["img_path"] = path

    def _get_meta(self, index: int) -> Optional[Dict]:
        if not self.csv_mode or index >= len(self.csv_data):
            return None
        entry = self.csv_data[index]
        return self.data_mgr.get_meta(str(entry["article_number"]), entry.get("bolag", ""))

    # ── classify screen ────────────────────────────────────────────────────────

    def _show_classify(self):
        if self.current_index >= len(self.images):
            self._show_done()
            return

        # Wait for download
        if self.csv_mode and self.current_index not in self._ready_images:
            self._show_wait_screen()
            return

        img_path = self.images[self.current_index]
        if img_path is None:
            self.current_index += 1
            self._show_classify()
            return

        meta = self._get_meta(self.current_index)
        cat_counts, threshold, ai_job_ready = self._get_threshold_data()

        self._cl_scr.show_image(
            self.test_name, self.categories,
            str(img_path), meta,
            self.current_index, len(self.images),
            cat_counts, threshold, ai_job_ready,
        )
        self.stack.setCurrentWidget(self._cl_scr)

    def _get_threshold_data(self) -> Tuple[Dict[str, int], int, bool]:
        """Return (counts_per_cat, threshold, ai_job_ready).

        threshold = ceil(AI_JOB_MIN_TOTAL / n_non_ovrigt_cats).
        ai_job_ready = True when every non-Övrigt category has >= threshold items
        AND AI settings have been configured.
        """
        import math
        non_ovrigt = [c["name"] for c in self.categories if c["name"] != "Övrigt"]
        if not non_ovrigt or not self.ai_enabled:
            return {}, 0, False
        threshold = math.ceil(AI_JOB_MIN_TOTAL / len(non_ovrigt))
        counts: Dict[str, int] = {name: 0 for name in non_ovrigt}
        for entry in self.categorized:
            cat = entry.get("category", "")
            if cat in counts:
                counts[cat] += 1
        ready = all(counts[name] >= threshold for name in non_ovrigt)
        return counts, threshold, ready

    def _show_wait_screen(self):
        w = QWidget(); w.setStyleSheet("background:#1e1e2e;")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("Väntar på nedladdning…")
        lbl.setStyleSheet("font-size:18px;"); lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        sub = QLabel(f"{len(self._ready_images)} av {len(self.images)} klara")
        sub.setStyleSheet("color:#6c7086;"); sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        self.stack.addWidget(w); self.stack.setCurrentWidget(w)

        def poll():
            if self.current_index in self._ready_images:
                self.stack.removeWidget(w); w.setParent(None)
                self._show_classify()
            else:
                QTimer.singleShot(300, poll)
        QTimer.singleShot(300, poll)

    # ── classify logic ─────────────────────────────────────────────────────────

    def _on_classified(self, category: str):
        if self.current_index >= len(self.images):
            return
        img_path = self.images[self.current_index]

        # Record
        entry: Dict = {"image_path": str(img_path), "category": category}
        if self.csv_mode and self.csv_data:
            meta = self.csv_data[self.current_index]
            entry["article_number"] = meta["article_number"]
            self.results.append({
                "article_number": meta["article_number"],
                "url": meta["url"],
                "category": category,
            })
        self.categorized.append(entry)

        # Övrigt retest — don't move file, just advance
        if self.retesting_ovrigt and category == "Övrigt":
            self.current_index += 1
            self._show_classify()
            return

        # Save to folder
        dest_dir = Path(f"{self.test_name}.{category}")
        dest_dir.mkdir(exist_ok=True)
        if self.csv_mode and self.csv_data:
            meta = self.csv_data[self.current_index]
            base_name = f"{meta['article_number']}{img_path.suffix or '.jpg'}"
        else:
            base_name = img_path.name
        dest = dest_dir / base_name
        counter = 1
        while dest.exists():
            stem, suf = Path(base_name).stem, Path(base_name).suffix
            dest = dest_dir / f"{stem}_{counter}{suf}"
            counter += 1
        try:
            if self.retesting_ovrigt:
                shutil.move(str(img_path), dest)
            else:
                shutil.copy2(img_path, dest)
        except Exception:
            pass

        self.current_index += 1
        self._show_classify()

    def _on_skip(self):
        self.current_index += 1
        self._show_classify()

    def _add_cat_during_test(self):
        if len(self.categories) >= 9:
            QMessageBox.warning(self, "Max antal", "Max 9 kategorier (tangent 1–9).")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Ny kategori")
        dlg.setStyleSheet(STYLE)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Kategorinamn:"))
        edit = QLineEdit(); lay.addWidget(edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns); edit.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = edit.text().strip()
        if not name:
            return
        if any(c["name"] == name for c in self.categories) or name == "Övrigt":
            QMessageBox.warning(self, "Dubblett", f'"{name}" finns redan.')
            return
        self.categories.append({"name": name, "description": "", "knowledge": ""})
        self._show_classify()

    # ── done screen ────────────────────────────────────────────────────────────

    def _show_done(self):
        self._cleanup_workers()
        ovrigt_dir = Path(f"{self.test_name}.Övrigt")
        ov_count = len([f for f in ovrigt_dir.iterdir()
                        if f.suffix.lower() in SUPPORTED_EXT]) \
                   if ovrigt_dir.exists() else 0
        self._done_scr.show_results(
            self.test_name, self.categories, self.current_index,
            self.csv_mode, bool(self.results), ov_count
        )
        self.stack.setCurrentWidget(self._done_scr)

    def _on_new_test(self):
        self._cleanup_workers()
        self._cleanup_temp()
        self._reset_state()
        self._name_scr.reset()
        self.stack.setCurrentWidget(self._name_scr)

    def _retest_ovrigt(self):
        ovrigt_dir = Path(f"{self.test_name}.Övrigt")
        imgs = sorted([f for f in ovrigt_dir.iterdir()
                       if f.suffix.lower() in SUPPORTED_EXT])
        if not imgs:
            QMessageBox.information(self, "Inga bilder", "Inga bilder i Övrigt-mappen.")
            return
        self.images = imgs
        self.current_index = 0
        self.retesting_ovrigt = True
        self.csv_mode = False
        self._show_classify()

    # ── AI job ─────────────────────────────────────────────────────────────────

    def _run_ai_job(self):
        if not self.ai_enabled:
            QMessageBox.information(self, "AI ej aktiv",
                                    "Konfigurera AI-inställningar för att köra AI-jobb.")
            return
        if not self.categorized:
            QMessageBox.information(self, "Inga data",
                                    "Inga manuellt klassificerade artiklar att utgå från.")
            return

        scr = AIJobScreen(
            self.categories, self.categorized, self.csv_data, self.syfte,
            self.ai_settings.get("api_url", DEFAULT_AI_URL),
            self.ai_settings.get("model", DEFAULT_MODEL),
            self.ai_settings.get("compress_images", True),
            self.data_mgr, self.test_name,
        )
        scr.article_added.connect(self._on_ai_article_classified)
        scr.reclassified.connect(self._on_ai_reclassified)
        scr.finished.connect(self._show_done)
        self._push_screen(scr)
        scr.start()

    def _on_ai_article_classified(self, article_number: str, category: str, url: str):
        """Add an AI-classified article to results (if not already there)."""
        existing = {r["article_number"] for r in self.results}
        if article_number not in existing:
            self.results.append({
                "article_number": article_number,
                "category":       category,
                "url":            url,
            })

    def _on_ai_reclassified(self, article_number: str, new_category: str):
        """Update result when user drags a card to a different column."""
        for r in self.results:
            if r["article_number"] == article_number:
                r["category"] = new_category
                break

    # ── Excel export ───────────────────────────────────────────────────────────

    def _export_excel(self):
        if not OPENPYXL_AVAILABLE:
            QMessageBox.critical(self, "openpyxl saknas",
                                 "Installera openpyxl:\n  pip install openpyxl")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Spara Excel", f"{self.test_name}_resultat.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Resultat"
        ws.append(["Artikelnummer", "Kategori", "URL"])
        for row in self.results:
            ws.append([row["article_number"], row["category"], row["url"]])
        ws.column_dimensions["A"].width = 20
        ws.column_dimensions["B"].width = 20
        ws.column_dimensions["C"].width = 60
        try:
            wb.save(path)
            QMessageBox.information(self, "Exporterat", f"Sparad:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Fel", f"Kunde inte spara:\n{e}")

    # ── cleanup ────────────────────────────────────────────────────────────────

    def _cleanup_workers(self):
        if self.dl_worker:
            self.dl_worker.stop(); self.dl_worker.wait(); self.dl_worker = None

    def _cleanup_temp(self):
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir = None

    def _reset_state(self):
        self.test_name = ""; self.syfte = ""; self.categories = []
        self.images = []; self.current_index = 0
        self.csv_mode = False; self.csv_data = []; self.results = []
        self.retesting_ovrigt = False; self.categorized = []
        self.ai_settings = {}; self.ai_enabled = False
        self._ready_images = set()

    def closeEvent(self, event):
        self._cleanup_workers()
        self._cleanup_temp()
        super().closeEvent(event)


# ── entry point ────────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

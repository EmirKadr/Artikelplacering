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
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut, QFont

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
AI_AHEAD            = 10    # images to pre-process
TAKEOVER_STREAK     = 30    # consecutive correct → AI takeover
MAX_EXAMPLES        = 5     # categorized examples per category in prompt
MAX_JOB_IMAGES      = 30    # images per category for AI-jobb

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


# ── AIWorker ───────────────────────────────────────────────────────────────────
class AIWorker(QThread):
    """Background thread: calls LM Studio for image categorization."""
    result = pyqtSignal(int, str)   # (index, category)
    error  = pyqtSignal(int, str)   # (index, error)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: List[Tuple[int, str, Optional[Dict]]] = []
        self._lock  = threading.Lock()
        self._event = threading.Event()
        self._stop  = False

        self.api_url         = DEFAULT_AI_URL
        self.model           = DEFAULT_MODEL
        self.syfte           = ""
        self.categories: List[Dict] = []
        self.categorized: List[Dict] = []
        self.compress_images = True

    def enqueue(self, index: int, image_path: str, meta: Optional[Dict] = None):
        with self._lock:
            if not any(i == index for i, _, _ in self._queue):
                self._queue.append((index, image_path, meta))
        self._event.set()

    def clear_queue(self):
        with self._lock:
            self._queue.clear()

    def stop(self):
        self._stop = True
        self._event.set()

    def run(self):
        while not self._stop:
            self._event.wait()
            self._event.clear()
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    item = self._queue.pop(0)
                idx, img_path, meta = item
                try:
                    cat = self._call_api(img_path, meta)
                    self.result.emit(idx, cat)
                except Exception as e:
                    self.error.emit(idx, str(e))

    def _call_api(self, image_path: str, meta: Optional[Dict]) -> str:
        if not REQUESTS_AVAILABLE:
            raise RuntimeError("requests ej installerat")
        prompt = self._build_prompt(meta)
        b64, mime = self._encode_image(image_path)
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            "max_tokens": 50,
            "temperature": 0.1,
        }
        resp = req.post(f"{self.api_url}/chat/completions", json=payload, timeout=60)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
        # Match to known category name
        for cat in self.categories:
            if cat["name"].lower() in text.lower():
                return cat["name"]
        return text

    def _build_prompt(self, meta: Optional[Dict]) -> str:
        lines = [f"SYFTE: {self.syfte}", ""]
        lines.append("KATEGORIER (välj EN av dessa):")
        for i, cat in enumerate(self.categories, 1):
            desc = cat.get("description", "").strip()
            know = cat.get("knowledge",   "").strip()
            line = f"{i}. {cat['name']}"
            if desc:
                line += f" – {desc}"
            if know:
                line += f"\n   Inlärd kunskap: {know}"
            lines.append(line)

        if meta:
            lines.append("")
            lines.append("ARTIKELDATA:")
            fields = [
                ("Beskrivning",   "beskrivning"),
                ("Vikt brutto",   "vikt_brutto"),
                ("Vikt netto",    "vikt_netto"),
                ("Volym",         "volym"),
                ("Kategori",      "kategori"),
                ("Huvudkategori", "huvudkategori"),
                ("UN nummer",     "un_nummer"),
                ("EAN",           "ean"),
                ("Längd",         "langd"),
                ("Bredd",         "bredd"),
                ("Höjd",          "hojd"),
                ("StoreQuantity", "store_quantity"),
                ("Robot",         "robot"),
            ]
            for label, key in fields:
                val = meta.get(key, "")
                if val and val not in _EMPTY:
                    lines.append(f"  {label}: {val}")

        # Condensed examples (only if no knowledge summaries yet)
        if self.categorized and not any(c.get("knowledge") for c in self.categories):
            by_cat: Dict[str, int] = {}
            for ex in self.categorized:
                by_cat[ex["category"]] = by_cat.get(ex["category"], 0) + 1
            if by_cat:
                lines.append("")
                lines.append(f"Antal kategoriserade (senaste {MAX_EXAMPLES} per kategori används):")
                for cname, count in by_cat.items():
                    lines.append(f"  {cname}: {count} bilder")

        lines.append("")
        lines.append("Titta på bilden och välj den bäst passande kategorin.")
        lines.append("Svara ENDAST med kategorinamnet, inget annat.")
        return "\n".join(lines)

    def _encode_image(self, image_path: str) -> Tuple[str, str]:
        suffix  = Path(image_path).suffix.lower()
        mime_map = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",
                    ".gif":"image/gif",".webp":"image/webp",".bmp":"image/bmp"}
        mime = mime_map.get(suffix, "image/jpeg")
        if self.compress_images and PIL_AVAILABLE:
            img = PILImage.open(image_path)
            img.thumbnail((800, 800), PILImage.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode(), mime


# ── AIJobWorker ────────────────────────────────────────────────────────────────
class AIJobWorker(QThread):
    """Generates knowledge summaries per category from already-categorized images."""
    progress     = pyqtSignal(str)
    cat_done     = pyqtSignal(str, str)   # (category_name, knowledge_text)
    finished_all = pyqtSignal()
    error        = pyqtSignal(str)

    def __init__(self, categories, categorized, syfte, api_url, model, compress, parent=None):
        super().__init__(parent)
        self.categories  = categories
        self.categorized = categorized
        self.syfte       = syfte
        self.api_url     = api_url
        self.model       = model
        self.compress    = compress

    def run(self):
        if not REQUESTS_AVAILABLE:
            self.error.emit("requests ej installerat")
            return
        by_cat: Dict[str, List[str]] = {}
        for item in self.categorized:
            p = item.get("image_path", "")
            if p and Path(p).exists():
                by_cat.setdefault(item["category"], []).append(p)

        for cat in self.categories:
            name   = cat["name"]
            images = by_cat.get(name, [])
            if not images:
                self.progress.emit(f"Hoppar {name} — inga bilder")
                continue
            sample = random.sample(images, min(MAX_JOB_IMAGES, len(images)))
            self.progress.emit(f"Analyserar {name} ({len(sample)} bilder)…")
            try:
                knowledge = self._generate(name, cat.get("description", ""), sample)
                self.cat_done.emit(name, knowledge)
                self.progress.emit(f"✓ {name} klar")
            except Exception as e:
                self.progress.emit(f"✗ {name}: {e}")

        self.finished_all.emit()

    def _generate(self, cat_name: str, cat_desc: str, image_paths: List[str]) -> str:
        prompt = "\n".join([
            f"SYFTE: {self.syfte}", "",
            f"KATEGORI: {cat_name}",
            f"Beskrivning: {cat_desc}" if cat_desc else "",
            "",
            f"Du ser {len(image_paths)} exempelbilder av produkter i denna kategori.",
            "",
            "Beskriv kategorin kortfattat (3–5 meningar):",
            "1. Typiska produkttyper och användningsområden",
            "2. Visuella mönster (form, färg, material)",
            "3. Hur man känner igen en produkt i denna kategori",
            "",
            "Svara på svenska med sammanhängande text.",
        ])
        content = []
        for p in image_paths:
            b64, mime = self._encode(p)
            content.append({"type":"image_url","image_url":{"url":f"data:{mime};base64,{b64}"}})
        content.append({"type":"text","text":prompt})
        payload = {"model":self.model,"messages":[{"role":"user","content":content}],
                   "max_tokens":300,"temperature":0.3}
        resp = req.post(f"{self.api_url}/chat/completions", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def _encode(self, path: str) -> Tuple[str, str]:
        suffix   = Path(path).suffix.lower()
        mime_map = {".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",
                    ".webp":"image/webp",".gif":"image/gif",".bmp":"image/bmp"}
        mime = mime_map.get(suffix, "image/jpeg")
        if self.compress and PIL_AVAILABLE:
            img = PILImage.open(path)
            img.thumbnail((600, 600), PILImage.LANCZOS)
            buf = BytesIO(); img.save(buf, format="JPEG", quality=80)
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


# ══════════════════════════════════════════════════════ Screen 4: Classify ══════
class ClassifyScreen(QWidget):
    classified   = pyqtSignal(str)
    skipped      = pyqtSignal()
    add_category = pyqtSignal()
    end_test     = pyqtSignal()

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
                   ai_suggestion: str = "", ai_active: bool = False,
                   streak: int = 0):
        self._clear()
        self._test_name    = test_name
        self._categories   = categories
        self._image_path   = image_path
        self._meta         = meta
        self._current      = current
        self._total        = total
        self._ai_sug       = ai_suggestion
        self._ai_active    = ai_active
        self._streak       = streak
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
        if self._streak > 5:
            prog += f"  |  AI-serie: {self._streak}"
        header = HeaderBar(self._test_name, prog)
        inner_lay.addWidget(header)

        # ── AI banner
        if self._ai_active:
            banner = self._make_banner(
                "🤖  AI kör automatiskt — klicka på en knapp för att korrigera",
                "#1e3a5f", "#89b4fa",
            )
            inner_lay.addWidget(banner)
        elif self._ai_sug:
            banner = self._make_banner(
                f"🤖  AI föreslår:  {self._ai_sug}",
                "#1a2e1a", "#a6e3a1",
            )
            inner_lay.addWidget(banner)

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
        end_btn = mk_btn("Avsluta test", "#f38ba8", "#1e1e2e")
        end_btn.clicked.connect(self._confirm_end)
        ctrl_lay.addWidget(end_btn)
        inner_lay.addWidget(ctrl)

        self._main_lay.addWidget(self._inner)

    def _make_banner(self, text: str, bg: str, fg: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet(f"background:{bg}; border-bottom:1px solid {fg};")
        f.setFixedHeight(36)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(16, 0, 16, 0)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{fg}; font-weight:bold; font-size:12px;")
        lay.addWidget(lbl)
        return f

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
            is_sug = (name == self._ai_sug and self._ai_sug)
            border = "border:2px solid #a6e3a1;" if is_sug else "border:none;"
            b = QPushButton(f"{name}  ({key})")
            b.setFixedSize(168, 40)
            b.setStyleSheet(
                f"background:{color}; color:white; border-radius:6px; "
                f"font-weight:bold; {border}"
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


# ═══════════════════════════════════════════════════════════ Screen 5: Done ════
class DoneScreen(QWidget):
    new_test      = pyqtSignal()
    retest_ovrigt = pyqtSignal()
    run_ai_job    = pyqtSignal()
    export_excel  = pyqtSignal()
    quit_app      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)

    def show_results(self, test_name: str, categories: List[Dict],
                     n_processed: int, csv_mode: bool, has_results: bool,
                     ovrigt_count: int, categorized_count: int):
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

        if categorized_count >= 5:
            ai_btn = mk_btn("🤖  Kör AI-jobb (generera kategorikunskap)", "#1e3a5f", "#89b4fa", h=44)
            ai_btn.clicked.connect(self.run_ai_job.emit)
            cl.addWidget(ai_btn)

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
        self.ai_cache:    Dict[int, str] = {}
        self.ai_streak    = 0
        self.ai_active    = False
        self.ai_worker:   Optional[AIWorker] = None

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

        self._done_scr.new_test.connect(self._on_new_test)
        self._done_scr.retest_ovrigt.connect(self._retest_ovrigt)
        self._done_scr.run_ai_job.connect(self._run_ai_job)
        self._done_scr.export_excel.connect(self._export_excel)
        self._done_scr.quit_app.connect(self.close)

        self.stack.setCurrentWidget(self._name_scr)

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
        src.use_builtin.connect(lambda: self._download_images(list(self.data_mgr.builtin_attributes)))
        src.use_csv.connect(self._load_csv)
        src.go_back.connect(lambda: self.stack.setCurrentWidget(self._cat_scr))
        self._src_scr = src
        self._push_screen(src)

    def _show_ai_settings(self):
        ai = AISettingsScreen(self.test_name)
        ai.go_next.connect(self._on_ai_done)
        ai.go_back.connect(lambda: self.stack.setCurrentWidget(self._src_scr))
        self._ai_scr = ai
        self._push_screen(ai)

    def _on_ai_done(self, settings: Dict):
        self.ai_settings = settings
        self.ai_enabled  = bool(settings)
        if self.ai_enabled:
            self._start_ai_worker()
        self._show_classify()

    # ── AI management ──────────────────────────────────────────────────────────

    def _start_ai_worker(self):
        if self.ai_worker:
            self.ai_worker.stop()
            self.ai_worker.wait()
        w = AIWorker()
        w.api_url         = self.ai_settings.get("api_url", DEFAULT_AI_URL)
        w.model           = self.ai_settings.get("model", DEFAULT_MODEL)
        w.syfte           = self.syfte
        w.categories      = self.categories
        w.categorized     = self.categorized
        w.compress_images = self.ai_settings.get("compress_images", True)
        w.result.connect(self._on_ai_result)
        w.error.connect(lambda idx, msg: None)   # silent
        w.start()
        self.ai_worker = w
        self._queue_ai_ahead()

    def _queue_ai_ahead(self):
        if not self.ai_enabled or not self.ai_worker:
            return
        end = min(self.current_index + AI_AHEAD, len(self.images))
        for i in range(self.current_index, end):
            if i not in self.ai_cache and self.images[i] is not None:
                self.ai_worker.enqueue(i, str(self.images[i]), self._get_meta(i))

    def _on_ai_result(self, index: int, category: str):
        self.ai_cache[index] = category
        if index == self.current_index:
            if self.ai_active:
                QTimer.singleShot(600, lambda: self._on_classified(category))
            else:
                self._refresh_classify()

    def _refresh_classify(self):
        if self.stack.currentWidget() == self._cl_scr:
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
        if self.ai_enabled and self.ai_worker:
            if index < self.current_index + AI_AHEAD:
                self.ai_worker.enqueue(index, path, self._get_meta(index))

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

        meta   = self._get_meta(self.current_index)
        ai_sug = self.ai_cache.get(self.current_index, "")

        self._cl_scr.show_image(
            self.test_name, self.categories,
            str(img_path), meta,
            self.current_index, len(self.images),
            ai_sug, self.ai_active, self.ai_streak,
        )
        self.stack.setCurrentWidget(self._cl_scr)
        self._queue_ai_ahead()

        # AI takeover: auto-classify after short delay if suggestion ready
        if self.ai_active and ai_sug:
            QTimer.singleShot(700, lambda: self._on_classified(ai_sug))

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

        # AI streak tracking
        if self.ai_enabled:
            ai_guess = self.ai_cache.get(self.current_index, "")
            if ai_guess and ai_guess == category:
                self.ai_streak += 1
                if self.ai_streak >= TAKEOVER_STREAK:
                    self.ai_active = True
            else:
                self.ai_streak = 0
                self.ai_active = False

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
        if self.ai_worker:
            self.ai_worker.categorized = self.categorized

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
            self.csv_mode, bool(self.results), ov_count, len(self.categorized)
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
                                    "Starta om testet och aktivera AI-stöd.")
            return
        if not self.categorized:
            QMessageBox.information(self, "Inga data",
                                    "Inga kategoriserade bilder att analysera.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Kör AI-jobb")
        dlg.setStyleSheet(STYLE)
        dlg.resize(460, 340)
        lay = QVBoxLayout(dlg)

        title = QLabel("AI analyserar kategoriserade bilder och genererar kategorikunskap…")
        title.setWordWrap(True)
        lay.addWidget(title)

        log = QTextEdit(); log.setReadOnly(True)
        log.setStyleSheet("background:#11111b; color:#cdd6f4; font-family:monospace;")
        lay.addWidget(log)

        close_btn = mk_btn("Stäng", "#45475a"); close_btn.setEnabled(False)
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)

        worker = AIJobWorker(
            self.categories, self.categorized, self.syfte,
            self.ai_settings.get("api_url", DEFAULT_AI_URL),
            self.ai_settings.get("model", DEFAULT_MODEL),
            self.ai_settings.get("compress_images", True),
        )
        worker.progress.connect(log.append)
        worker.cat_done.connect(self._on_job_cat_done)
        worker.finished_all.connect(lambda: (
            log.append("\n✓ Klart! Kategorikunskap sparad och aktiveras för kommande bilder."),
            close_btn.setEnabled(True),
        ))
        worker.error.connect(lambda msg: (log.append(f"FEL: {msg}"), close_btn.setEnabled(True)))
        worker.start()
        dlg.exec()

    def _on_job_cat_done(self, name: str, knowledge: str):
        for cat in self.categories:
            if cat["name"] == name:
                cat["knowledge"] = knowledge
        if self.ai_worker:
            self.ai_worker.categories = self.categories

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
        if self.ai_worker:
            self.ai_worker.stop(); self.ai_worker.wait(); self.ai_worker = None

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
        self.ai_cache = {}; self.ai_streak = 0; self.ai_active = False
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

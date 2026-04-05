"""AIJobScreen — full-screen live kanban view while the AI job runs."""
import logging
import tempfile
import time as _time
from io import BytesIO
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from core.constants import (
    AI_JOB_MIN_PER_CAT, CATEGORY_COLORS, MAX_EXAMPLES_PER_CAT,
)
from desktop.widgets._constants import CARD_MIME
from desktop.widgets.category_column import CategoryColumn
from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn
from desktop.widgets._item_thumbnail_loader import _ItemThumbnailLoader
from desktop.workers.ai_job_worker import AIJobWorker
from desktop.workers.image_downloader import ImageDownloader
from desktop.workers.new_category_worker import NewCategoryWorker
from desktop.workers.reclassify_worker import ReClassifyWorker

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

_logger = logging.getLogger(__name__)

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
QScrollArea { border: none; }
QCheckBox { color: #cdd6f4; }
QMessageBox { background-color: #1e1e2e; }
"""


class AIJobScreen(QWidget):
    """Full-screen live view while the AI job runs.

    Shows a kanban board — one column per category — updating in real time.
    Cards are draggable between columns to correct misclassifications.
    Clicking a card opens an enlarged image view.
    """
    article_added     = pyqtSignal(str, str, str)   # (article_number, category, url)
    reclassified      = pyqtSignal(str, str)         # (article_number, new_category)
    knowledge_updated = pyqtSignal(dict, dict)       # (cat_knowledge, cat_example_articles)
    finished          = pyqtSignal()

    def __init__(self, categories: List[Dict], categorized: List[Dict],
                 csv_data: List[Dict], syfte: str,
                 api_url: str, model: str, compress: bool,
                 data_mgr, test_name: str,
                 api_key: str = "",
                 pre_knowledge: Optional[Dict] = None,
                 pre_example_articles: Optional[Dict] = None,
                 parent=None):
        super().__init__(parent)
        self._categories           = categories
        self._categorized          = categorized
        self._csv_data             = csv_data
        self._syfte                = syfte
        self._api_url              = api_url
        self._model                = model
        self._compress             = compress
        self._data_mgr             = data_mgr
        self._test_name            = test_name
        self._api_key              = api_key
        self._pre_knowledge        = pre_knowledge
        self._pre_example_articles = pre_example_articles
        self._worker: Optional[AIJobWorker] = None
        self._new_cat_workers: List[NewCategoryWorker] = []
        self._new_cat_workers_by_cat: Dict[str, NewCategoryWorker] = {}
        self._reclass_workers: List[ReClassifyWorker] = []
        self._columns: Dict[str, CategoryColumn] = {}
        self._total_classified = 0
        self._cat_knowledge: Dict[str, str] = {}
        self._cat_example_articles: Dict[str, List[str]] = {}
        self._new_category_count = 0
        self._cards_by_art: Dict[str, Dict] = {}
        self._log_lines: List[str] = []
        self._log_dialog: Optional[QDialog] = None
        self._card_category: dict = {}

        # ── File logging ──────────────────────────────────────────────────────
        _log_dir = Path("data") / "logs"
        _log_dir.mkdir(parents=True, exist_ok=True)
        _ts = _time.strftime("%Y%m%d_%H%M%S")
        self._log_file_path = str(_log_dir / f"{test_name}_{_ts}.log")
        self._file_handler: Optional[RotatingFileHandler] = RotatingFileHandler(
            self._log_file_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )
        self._file_handler.setFormatter(
            logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        _logger.addHandler(self._file_handler)
        _logger.setLevel(logging.DEBUG)

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

        self._header = HeaderBar(self._test_name, "AI-jobb startar…")
        main_lay.addWidget(self._header)

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
            col.header_clicked.connect(self._show_knowledge_dialog)
            col.analyze_requested.connect(self._on_analyze_category_requested)
            col.select_all_requested.connect(self._on_select_all_in_category)
            col._view.view_image.connect(self._show_image_large)
            col._view.context_menu_signal.connect(self._on_context_menu)
            cols_lay.addWidget(col)
            self._columns[name] = col
            self._new_category_count = len(all_display)

        self._cols_lay = cols_lay
        self._cols_widget = cols_widget
        main_lay.addWidget(cols_widget, 1)

        footer = QFrame()
        footer.setFixedHeight(44)
        footer.setStyleSheet("background:#181825; border-top:1px solid #313244;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 0, 16, 0)

        self._progress_lbl = QLabel("Steg 1: Genererar kategorikunskap…")
        self._progress_lbl.setStyleSheet("color:#6c7086; font-size:12px;")
        fl.addWidget(self._progress_lbl, 1)

        log_btn = mk_btn("📋 Logg", "#313244", "#cdd6f4", h=32)
        log_btn.setToolTip(f"Visa fullständig logg\nLoggas till: {self._log_file_path}")
        log_btn.clicked.connect(self._open_log_dialog)
        fl.addWidget(log_btn)

        add_cat_btn = mk_btn("+ Ny kategori", "#FF9800", h=32)
        add_cat_btn.clicked.connect(self._open_add_category_dialog)
        fl.addWidget(add_cat_btn)

        self._run_ai_btn = mk_btn("▶ Kör AI-jobb", "#a6e3a1", "#1e1e2e", h=32)
        self._run_ai_btn.clicked.connect(self._start_ai_from_session)
        self._run_ai_btn.setVisible(False)
        fl.addWidget(self._run_ai_btn)

        self._start_classify_btn = mk_btn("▶ Starta klassificering", "#a6e3a1", "#1e1e2e", h=32)
        self._start_classify_btn.clicked.connect(self._resume_step2)
        self._start_classify_btn.setVisible(False)
        fl.addWidget(self._start_classify_btn)

        self._pause_btn = mk_btn("⏸ Pausa", "#f9e2af", "#1e1e2e", h=32)
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._pause_btn.setVisible(False)
        fl.addWidget(self._pause_btn)

        self._reanalyze_all_btn = mk_btn("🔄 Analysera om alla kategorier", "#7c3aed", h=32)
        self._reanalyze_all_btn.clicked.connect(self._reanalyze_all_categories)
        fl.addWidget(self._reanalyze_all_btn)

        self._stop_early_btn = mk_btn("⏹ Avsluta i förtid", "#b4637a", h=32)
        self._stop_early_btn.clicked.connect(self._stop_early)
        fl.addWidget(self._stop_early_btn)

        self._done_btn = mk_btn("💾  Exportera & Avsluta", "#1B5E20", h=32)
        self._done_btn.setVisible(False)
        self._done_btn.clicked.connect(self.finished.emit)
        fl.addWidget(self._done_btn)

        main_lay.addWidget(footer)

    # ── worker management ──────────────────────────────────────────────────────

    def start(self, skip_worker: bool = False):
        self._url_by_art   = {str(r.get("article_number", "")): r.get("url", "")
                               for r in self._csv_data}
        self._bolag_by_art = {str(r.get("article_number", "")): r.get("bolag", "")
                               for r in self._csv_data}

        needs_download: List[Dict] = []
        for item in self._categorized:
            cat      = item.get("category", "")
            art_num  = str(item.get("article_number", ""))
            img_path = item.get("image_path", "")
            url      = self._url_by_art.get(art_num, "")
            col = self._columns.get(cat) or self._columns.get("Övrigt")
            if col:
                article_item = {
                    "article_number": art_num,
                    "image_path":     img_path,
                    "category":       cat,
                    "url":            url,
                    "reason":         item.get("reason", ""),
                }
                col.prepend_item(article_item)
                self._cards_by_art[art_num] = article_item
                if (not img_path or not Path(img_path).exists()) and url:
                    needs_download.append({"article_number": art_num, "url": url,
                                           "index": len(needs_download)})

        if needs_download:
            self._start_image_downloads(needs_download)

        if skip_worker:
            self._progress_lbl.setText("Session inläst — klar att redigera.")
            self._stop_early_btn.setVisible(False)
            self._run_ai_btn.setVisible(True)
            self._done_btn.setVisible(True)
            return

        self._worker = AIJobWorker(
            self._categories, self._categorized, self._csv_data, self._syfte,
            self._api_url, self._model, self._compress, self._data_mgr,
            api_key=self._api_key,
            pre_knowledge=self._pre_knowledge,
            pre_example_articles=self._pre_example_articles,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.knowledge_ready.connect(self._on_knowledge_ready)
        self._worker.step1_done.connect(self._on_step1_done)
        self._worker.article_classified.connect(self._on_article_classified)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.error.connect(
            lambda msg: self._progress_lbl.setText(f"FEL: {msg}")
        )
        self._worker.start()

    def _start_image_downloads(self, rows: List[Dict]):
        self._img_dl_temp = tempfile.mkdtemp(prefix="img_dl_")
        dl_rows = [{"url": r["url"]} for r in rows]
        self._img_dl_art_nums = [r["article_number"] for r in rows]
        self._img_downloader = ImageDownloader(dl_rows, self._img_dl_temp, parent=self)
        self._img_downloader.image_ready.connect(self._on_bg_image_ready)
        self._img_downloader.start()

    def _on_bg_image_ready(self, index: int, local_path: str):
        if index < len(self._img_dl_art_nums):
            art_num = self._img_dl_art_nums[index]
            item = self._cards_by_art.get(art_num)
            if item:
                item["image_path"] = local_path
                cat = item.get("category", "")
                col = self._columns.get(cat) or self._columns.get("Övrigt")
                if col and Path(local_path).exists():
                    loader = _ItemThumbnailLoader(art_num, local_path, col)
                    loader.done.connect(col._model.set_thumbnail)
                    loader.start()
            for row in self._csv_data:
                if str(row.get("article_number", "")) == art_num:
                    row["img_path"] = local_path
                    break

    def stop_worker(self):
        if hasattr(self, '_img_downloader') and self._img_downloader:
            self._img_downloader.stop()
            self._img_downloader.wait()
        if self._worker:
            self._worker.stop()
            self._worker.wait()
            self._worker = None
        for w in self._new_cat_workers:
            w.stop()
            w.wait()
        self._new_cat_workers.clear()

    # ── add new category ───────────────────────────────────────────────────────

    def _open_add_category_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Ny kategori")
        dlg.setStyleSheet(STYLE)
        dlg.resize(420, 220)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Kategorinamn:"))
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("t.ex. Kapslar")
        lay.addWidget(name_edit)
        lay.addWidget(QLabel("Beskrivning (valfri):"))
        desc_edit = QLineEdit()
        desc_edit.setPlaceholderText("Kort beskrivning av vad som hör hit")
        lay.addWidget(desc_edit)
        hint = QLabel(
            f"Dra minst {AI_JOB_MIN_PER_CAT} bild till den nya kolumnen "
            "så startar AI-analysen automatiskt."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6c7086; font-size:11px;")
        lay.addWidget(hint)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        name_edit.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = name_edit.text().strip()
        if not name:
            return
        if name in self._columns or name == "Övrigt":
            QMessageBox.warning(self, "Dubblett", f'"{name}" finns redan.')
            return
        self._add_new_column(name, desc_edit.text().strip())

    def _add_new_column(self, name: str, desc: str):
        color = CATEGORY_COLORS[self._new_category_count % len(CATEGORY_COLORS)]
        self._new_category_count += 1

        col = CategoryColumn(name, color)
        col.card_dropped.connect(self._on_card_dropped)
        col.header_clicked.connect(self._show_knowledge_dialog)
        col.threshold_reached.connect(self._on_new_cat_threshold)
        col.analyze_requested.connect(self._on_analyze_category_requested)
        col.select_all_requested.connect(self._on_select_all_in_category)
        col._view.view_image.connect(self._show_image_large)
        col._view.context_menu_signal.connect(self._on_context_menu)
        col.mark_as_new_category()
        self._columns[name] = col
        self._categories.append({"name": name, "description": desc, "knowledge": ""})

        ovrigt_col = self._columns.get("Övrigt")
        if ovrigt_col:
            idx = self._cols_lay.indexOf(ovrigt_col)
            self._cols_lay.insertWidget(idx, col)
        else:
            self._cols_lay.addWidget(col)

        if self._worker and hasattr(self._worker, "categories"):
            self._worker.categories = self._categories

    def _on_new_cat_threshold(self, category_name: str, count: int):
        col = self._columns.get(category_name)
        if not col:
            return

        prev = self._new_cat_workers_by_cat.get(category_name)
        if prev and prev.isRunning():
            prev.stop()

        example_cards = [
            {"article_number": c["article_number"], "image_path": c["image_path"]}
            for c in col._cards[:MAX_EXAMPLES_PER_CAT]
        ]
        ovrigt_col = self._columns.get("Övrigt")
        ovrigt_cards = [
            {"article_number": c["article_number"], "image_path": c["image_path"]}
            for c in (ovrigt_col._cards if ovrigt_col else [])
        ]
        cat_desc = next(
            (c.get("description", "") for c in self._categories if c["name"] == category_name),
            ""
        )
        label = {1: "1 bild", 3: "3 bilder", MAX_EXAMPLES_PER_CAT: "10 bilder (slutgiltig)"}.get(
            count, f"{count} bilder"
        )
        w = NewCategoryWorker(
            category_name, cat_desc, example_cards,
            dict(self._cat_knowledge), ovrigt_cards,
            list(self._categories),
            self._syfte, self._api_url, self._model, self._compress, self._data_mgr,
            api_key=self._api_key,
        )
        w.progress.connect(self._on_progress)
        w.knowledge_ready.connect(self._on_knowledge_ready)
        w.knowledge_ready.connect(self._feed_knowledge_to_main_worker)
        w.article_reclassified.connect(self._on_new_cat_article_reclassified)
        w.finished_all.connect(lambda: self._progress_lbl.setText(
            f"✓ Analys av '{category_name}' klar ({label})"
        ))
        self._new_cat_workers.append(w)
        self._new_cat_workers_by_cat[category_name] = w
        self._progress_lbl.setText(f"Analyserar ny kategori '{category_name}' ({label})…")
        w.start()

    def _on_analyze_category_requested(self, category_name: str):
        col = self._columns.get(category_name)
        if not col:
            return
        max_n = len(col._cards)
        if max_n == 0:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Analysera: {category_name}")
        dlg.setStyleSheet(STYLE)
        dlg.resize(400, 180)
        lay = QVBoxLayout(dlg)

        info = QLabel(
            f"Hur många bilder ska användas vid analysen av <b>{category_name}</b>?<br>"
            f"(Det finns {max_n} artiklar i kolumnen)"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#cdd6f4; font-size:12px;")
        lay.addWidget(info)

        spin = QSpinBox()
        spin.setRange(1, max_n)
        spin.setValue(min(max_n, MAX_EXAMPLES_PER_CAT))
        spin.setStyleSheet(
            "background:#11111b; color:#cdd6f4; font-size:14px;"
            "border:1px solid #45475a; border-radius:4px; padding:4px;"
        )
        lay.addWidget(spin)

        btn_row = QHBoxLayout()
        ok_btn = mk_btn("Analysera", "#1B5E20")
        ok_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = mk_btn("Avbryt", "#45475a")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        n = spin.value()
        example_cards = [
            {"article_number": c["article_number"], "image_path": c["image_path"]}
            for c in col._cards[:n]
        ]
        ovrigt_col = self._columns.get("Övrigt")
        ovrigt_cards = [
            {"article_number": c["article_number"], "image_path": c["image_path"]}
            for c in (ovrigt_col._cards if ovrigt_col else [])
        ]
        cat_desc = next(
            (c.get("description", "") for c in self._categories if c["name"] == category_name), ""
        )
        w = NewCategoryWorker(
            category_name, cat_desc, example_cards,
            dict(self._cat_knowledge), ovrigt_cards,
            list(self._categories),
            self._syfte, self._api_url, self._model, self._compress, self._data_mgr,
            api_key=self._api_key,
        )
        w.progress.connect(self._on_progress)
        w.knowledge_ready.connect(self._on_knowledge_ready)
        w.knowledge_ready.connect(self._feed_knowledge_to_main_worker)
        w.article_reclassified.connect(self._on_new_cat_article_reclassified)
        w.finished_all.connect(lambda: self._progress_lbl.setText(
            f"✓ Analysering av '{category_name}' klar ({n} bilder)"
        ))
        self._new_cat_workers.append(w)
        self._progress_lbl.setText(f"Analyserar '{category_name}' med {n} bilder…")
        w.start()

    def _feed_knowledge_to_main_worker(self, category: str, knowledge: str):
        if self._worker and hasattr(self._worker, "cat_knowledge"):
            self._worker.cat_knowledge[category] = knowledge

    def _on_new_cat_article_reclassified(self, article_number: str,
                                          new_category: str, image_path: str):
        self._on_card_dropped(article_number, "Övrigt", new_category)
        self.reclassified.emit(article_number, new_category)

    # ── slots ──────────────────────────────────────────────────────────────────

    def _on_progress(self, msg: str):
        text = msg.strip()
        if text:
            ts = _time.strftime("%H:%M:%S")
            stamped = f"[{ts}] {text}"
            self._progress_lbl.setText(text)
            self._log_lines.append(stamped)
            _logger.info(text)
            if self._log_dialog and self._log_dialog.isVisible():
                self._log_dialog._text.appendPlainText(stamped)

    def _cleanup_file_handler(self):
        if hasattr(self, '_file_handler') and self._file_handler:
            _logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    def _on_step1_done(self):
        self._progress_lbl.setText("✓ Kategorikunskap klar — granska och klicka för att klassificera")
        self._start_classify_btn.setVisible(True)
        self.knowledge_updated.emit(dict(self._cat_knowledge), dict(self._cat_example_articles))

    def _resume_step2(self):
        self._start_classify_btn.setVisible(False)
        self._pause_btn.setVisible(True)
        if self._worker:
            self._worker.resume()

    def _reanalyze_all_categories(self):
        categorized = []
        for name, col in self._columns.items():
            for item in col._cards:
                categorized.append({
                    "article_number": item["article_number"],
                    "image_path": item["image_path"],
                    "category": name,
                })

        self._reanalyze_all_btn.setEnabled(False)
        self._reanalyze_all_btn.setText("🔄 Analyserar…")
        self._progress_lbl.setText("=== Analyserar om alla kategorier ===")

        w = AIJobWorker(
            self._categories, categorized, [],
            self._syfte, self._api_url, self._model, self._compress, self._data_mgr,
            api_key=self._api_key,
        )
        w.progress.connect(self._on_progress)
        w.knowledge_ready.connect(self._on_knowledge_ready)

        def on_step1_done():
            self._reanalyze_all_btn.setEnabled(True)
            self._reanalyze_all_btn.setText("🔄 Analysera om alla kategorier")
            self._progress_lbl.setText("✓ Alla kategorier analyserade om")
            self._cat_knowledge = dict(w.cat_knowledge)
            self.knowledge_updated.emit(dict(self._cat_knowledge), dict(self._cat_example_articles))
            w.stop()

        w.step1_done.connect(on_step1_done)
        w.error.connect(lambda msg: self._progress_lbl.setText(f"FEL: {msg}"))
        self._new_cat_workers.append(w)
        w.start()

    def _start_ai_from_session(self):
        self._run_ai_btn.setVisible(False)
        self._stop_early_btn.setVisible(True)
        self._worker = AIJobWorker(
            self._categories, self._categorized, self._csv_data, self._syfte,
            self._api_url, self._model, self._compress, self._data_mgr,
            api_key=self._api_key,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.knowledge_ready.connect(self._on_knowledge_ready)
        self._worker.step1_done.connect(self._on_step1_done)
        self._worker.article_classified.connect(self._on_article_classified)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.error.connect(
            lambda msg: self._progress_lbl.setText(f"FEL: {msg}")
        )
        self._worker.start()

    def _toggle_pause(self):
        if self._worker and self._worker.isRunning():
            if self._worker._paused:
                self._worker.resume()
                self._pause_btn.setText("⏸ Pausa")
                self._progress_lbl.setText("AI-jobb återupptaget…")
            else:
                self._worker.pause()
                self._pause_btn.setText("▶ Fortsätt")
                self._progress_lbl.setText("AI-jobb pausat")

    def _open_log_dialog(self):
        if self._log_dialog and self._log_dialog.isVisible():
            self._log_dialog.raise_()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("AI-jobblogg")
        dlg.resize(720, 480)
        dlg.setStyleSheet(STYLE)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet(
            "font-family:monospace; font-size:11px; "
            "background:#1e1e2e; color:#cdd6f4;"
        )
        text.setPlainText("\n".join(self._log_lines))
        text.verticalScrollBar().setValue(text.verticalScrollBar().maximum())
        lay.addWidget(text)
        dlg._text = text  # type: ignore[attr-defined]
        self._log_dialog = dlg
        dlg.show()

    def _on_article_classified(self, article_number: str, category: str,
                                url: str, image_path: str, reason: str = ""):
        prev_cat = self._card_category.get(article_number)
        if prev_cat is not None:
            if prev_cat != category:
                self._on_card_dropped(article_number, prev_cat, category)
                self._card_category[article_number] = category
                self.article_added.emit(article_number, category, url)
            self._retry_done = getattr(self, "_retry_done", 0) + 1
            self._header.set_texts(
                self._test_name,
                f"Omtestning… {self._retry_done}/{self._retry_total}",
            )
            return

        self._total_classified += 1
        self._card_category[article_number] = category
        col = self._columns.get(category) or self._columns.get("Övrigt")
        if col:
            article_item = {
                "article_number": article_number,
                "image_path":     image_path,
                "category":       category,
                "url":            url,
                "reason":         reason,
            }
            col.prepend_item(article_item)
            self._cards_by_art[article_number] = article_item

        self._header.set_texts(
            self._test_name,
            f"Klassificerar… {self._total_classified}/{self._remaining_count}",
        )
        self.article_added.emit(article_number, category, url)

    def _stop_early(self):
        ans = QMessageBox.question(
            self, "Avsluta i förtid",
            "Vill du avbryta AI-jobbet?\n"
            "Artiklar som redan klassificerats sparas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        if self._worker and self._worker.isRunning():
            self._worker.stop()
        for w in (self._new_cat_workers
                  + list(self._new_cat_workers_by_cat.values())
                  + self._reclass_workers):
            if w and w.isRunning():
                w.stop()
        self._progress_lbl.setText(f"Avbrutet — {self._total_classified} artiklar klassificerade.")
        self._header.set_texts(self._test_name, "AI-jobb avbrutet")
        self._stop_early_btn.setEnabled(False)
        self._pause_btn.setVisible(False)
        self._run_ai_btn.setVisible(True)
        self._done_btn.setVisible(True)

    def _on_finished(self):
        self._progress_lbl.setText(
            f"✓ Klart!  {self._total_classified} artiklar klassificerade av AI."
        )
        self._header.set_texts(self._test_name, "AI-jobb klart")
        self._stop_early_btn.setEnabled(False)
        self._pause_btn.setVisible(False)
        self._done_btn.setVisible(True)
        self._cleanup_file_handler()

    def _on_knowledge_ready(self, category: str, knowledge: str):
        self._cat_knowledge[category] = knowledge
        if self._worker:
            self._cat_example_articles = dict(getattr(self._worker, 'cat_example_articles', {}))
        col = self._columns.get(category)
        if col:
            col.set_knowledge_ready()

    # ── selection ──────────────────────────────────────────────────────────────

    def _on_select_all_in_category(self, category_name: str):
        col = self._columns.get(category_name)
        if col:
            if col._view.selectedIndexes():
                col._view.clearSelection()
            else:
                col._view.selectAll()

    def _get_selected_items_across_columns(self) -> List[Dict]:
        result = []
        for col in self._columns.values():
            result.extend(col._view.selected_items())
        return result

    def _clear_selection(self):
        for col in self._columns.values():
            col._view.clearSelection()

    # ── right-click context menu ────────────────────────────────────────────────

    def _on_context_menu(self, items: List[Dict], pos: QPoint):
        if not items:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#313244; color:#cdd6f4; border:1px solid #45475a; }"
            "QMenu::item:selected { background:#45475a; }"
        )
        n = len(items)
        label = f"Gör om ({n} artikel{'er' if n > 1 else ''})"
        action = menu.addAction(label)

        reason_action = None
        if n == 1 and items[0].get("reason"):
            reason_action = menu.addAction("Se orsak")

        chosen = menu.exec(pos)
        if chosen == action:
            self._prompt_and_reclassify(items)
        elif chosen and chosen == reason_action:
            msg = QMessageBox(self)
            msg.setWindowTitle(f"Orsak — {items[0]['article_number']}")
            msg.setText(items[0].get("reason", ""))
            msg.setStyleSheet(STYLE)
            msg.exec()

    def _prompt_and_reclassify(self, cards):
        n = len(cards)
        dlg = QDialog(self)
        dlg.setWindowTitle("Gör om")
        dlg.setStyleSheet(STYLE)
        dlg.resize(560, 280)
        lay = QVBoxLayout(dlg)

        info = QLabel(
            f"<b>{n} artikel{'er' if n > 1 else ''}</b> kommer omklassificeras av AI:n.<br>"
            "Ange gärna en orsak — det hjälper AI:n att välja rätt kategori."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#cdd6f4; font-size:12px;")
        lay.addWidget(info)

        hint_lbl = QLabel("Orsak (valfritt):")
        hint_lbl.setStyleSheet("color:#6c7086; font-size:11px; margin-top:8px;")
        lay.addWidget(hint_lbl)

        hint_edit = QTextEdit()
        hint_edit.setPlaceholderText(
            'T.ex. "Kategori \'Säck\' delades upp i \'Säck max 15 kg\' och \'Säck minst 15 kg\'"'
        )
        hint_edit.setFixedHeight(80)
        hint_edit.setStyleSheet(
            "background:#11111b; color:#cdd6f4; font-size:12px;"
            "border:1px solid #45475a; border-radius:4px;"
        )
        lay.addWidget(hint_edit)

        btn_row = QHBoxLayout()
        run_btn = mk_btn("Kör om nu", "#1B5E20")
        run_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(run_btn)
        cancel_btn = mk_btn("Avbryt", "#45475a")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        hint = hint_edit.toPlainText().strip()
        self._reclassify_cards(cards, hint)

    def _reclassify_cards(self, cards, hint: str = ""):
        articles = [
            {"article_number": c["article_number"], "image_path": c["image_path"],
             "url": c.get("url", ""), "old_category": c.get("category", "")}
            for c in cards
        ]
        for c in cards:
            col = self._columns.get(c.get("category", ""))
            if col:
                col.remove_card_by_article(c["article_number"])
        self._clear_selection()

        self._retry_done = 0
        self._retry_total = len(cards)

        if self._worker and self._worker.isRunning():
            self._worker.pause()

        w = ReClassifyWorker(
            articles, dict(self._cat_knowledge),
            list(self._categories),
            self._syfte, self._api_url, self._model, self._compress, self._data_mgr,
            hint=hint,
            api_key=self._api_key,
        )
        w.progress.connect(self._on_progress)
        w.article_classified.connect(self._on_article_classified)

        def _on_reclass_done():
            self._progress_lbl.setText(f"✓ Omklassificering klar ({len(articles)} artiklar)")
            if self._worker and self._worker.isRunning():
                self._worker.resume()

        w.finished_all.connect(_on_reclass_done)
        self._reclass_workers.append(w)
        self._progress_lbl.setText(f"Pausar jobb — gör om {len(articles)} artiklar…")
        w.start()

    def _show_knowledge_dialog(self, category: str):
        knowledge = self._cat_knowledge.get(category, "")
        dlg = QDialog(self)
        dlg.setWindowTitle(f"AI-analys: {category}")
        dlg.setStyleSheet(STYLE)
        dlg.resize(700, 540)
        lay = QVBoxLayout(dlg)

        name_row = QHBoxLayout()
        name_lbl = QLabel("Kategorinamn:")
        name_lbl.setStyleSheet("color:#6c7086; font-size:11px;")
        name_row.addWidget(name_lbl)
        name_edit = QLineEdit(category)
        name_edit.setStyleSheet(
            "background:#11111b; color:#cdd6f4; font-size:13px;"
            "border:1px solid #45475a; border-radius:4px; padding:4px 8px;"
        )
        name_row.addWidget(name_edit, 1)
        lay.addLayout(name_row)

        if not knowledge:
            info = QLabel("AI-analysen för denna kategori är inte klar ännu.")
            info.setStyleSheet("color:#6c7086; font-style:italic;")
            lay.addWidget(info)
            editor = None
        else:
            lbl = QLabel(
                "AI:ns analys av kategorin. "
                "Du kan justera texten — den används vid klassificering av återstående artiklar."
            )
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#6c7086; font-size:11px;")
            lay.addWidget(lbl)

            editor = QTextEdit()
            editor.setPlainText(knowledge)
            editor.setStyleSheet(
                "background:#11111b; color:#cdd6f4; font-family:monospace;"
                "border:1px solid #45475a; border-radius:4px;"
            )
            lay.addWidget(editor)

        example_arts = list(self._cat_example_articles.get(category, []))
        card_map: Dict[str, str] = {}
        for _col in self._columns.values():
            for _card in _col._cards:
                card_map[_card["article_number"]] = _card["image_path"]

        ex_lbl = QLabel(f"Exempelartiklar ({len(example_arts)} st):")
        ex_lbl.setStyleSheet("color:#6c7086; font-size:11px; margin-top:8px;")
        lay.addWidget(ex_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(155)
        scroll.setStyleSheet("border:none; background:transparent;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_widget = QWidget()
        img_row = QHBoxLayout(scroll_widget)
        img_row.setSpacing(8)
        img_row.setContentsMargins(0, 0, 0, 0)

        def _rebuild_examples():
            while img_row.count():
                item = img_row.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for art_num in example_arts:
                img_frame = QFrame()
                img_frame.setFixedSize(110, 130)
                img_frame.setStyleSheet(
                    "background:#11111b; border-radius:6px; border:1px solid #45475a;"
                )
                frame_lay = QVBoxLayout(img_frame)
                frame_lay.setContentsMargins(4, 4, 4, 2)
                frame_lay.setSpacing(2)
                thumb = QLabel()
                thumb.setFixedSize(100, 80)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb.setStyleSheet("border:none;")
                img_p = card_map.get(art_num, "")
                if img_p and Path(img_p).exists():
                    try:
                        if PIL_AVAILABLE:
                            pimg = PILImage.open(img_p)
                            pimg.thumbnail((100, 80), PILImage.LANCZOS)
                            buf = BytesIO()
                            pimg.save(buf, format="PNG")
                            buf.seek(0)
                            qpix = QPixmap()
                            qpix.loadFromData(buf.getvalue())
                            thumb.setPixmap(qpix)
                        else:
                            qpix = QPixmap(img_p).scaled(
                                100, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
                            thumb.setPixmap(qpix)
                    except Exception as _e:
                        _logger.warning("Kunde inte ladda thumbnail %s: %s", img_p, _e)
                        thumb.setText("?")
                else:
                    thumb.setText("?")
                frame_lay.addWidget(thumb)
                bottom = QHBoxLayout()
                bottom.setContentsMargins(0, 0, 0, 0)
                art_lbl = QLabel(art_num)
                art_lbl.setStyleSheet("color:#6c7086; font-size:9px; border:none;")
                bottom.addWidget(art_lbl)
                rm_btn = QPushButton("✕")
                rm_btn.setFixedSize(18, 18)
                rm_btn.setStyleSheet(
                    "background:#b4637a; color:white; border:none; border-radius:9px;"
                    "font-size:10px; font-weight:bold;"
                )
                _an = art_num
                rm_btn.clicked.connect(lambda _, a=_an: _remove_example(a))
                bottom.addWidget(rm_btn)
                frame_lay.addLayout(bottom)
                img_row.addWidget(img_frame)

            drop_frame = QFrame()
            drop_frame.setFixedSize(110, 130)
            drop_frame.setStyleSheet(
                "background:#181825; border:2px dashed #45475a; border-radius:6px;"
            )
            drop_lay = QVBoxLayout(drop_frame)
            drop_lbl = QLabel("Dra hit\nartikel")
            drop_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            drop_lbl.setStyleSheet("color:#585b70; font-size:10px; border:none;")
            drop_lay.addWidget(drop_lbl)
            drop_frame.setAcceptDrops(True)

            def _drag_enter(e):
                if e.mimeData().hasFormat(CARD_MIME):
                    e.acceptProposedAction()
                    drop_frame.setStyleSheet(
                        "background:#1e1e2e; border:2px dashed #a6e3a1; border-radius:6px;"
                    )

            def _drag_leave(e):
                drop_frame.setStyleSheet(
                    "background:#181825; border:2px dashed #45475a; border-radius:6px;"
                )

            def _drop(e):
                import json as _j
                drop_frame.setStyleSheet(
                    "background:#181825; border:2px dashed #45475a; border-radius:6px;"
                )
                if e.mimeData().hasFormat(CARD_MIME):
                    data = _j.loads(bytes(e.mimeData().data(CARD_MIME)))
                    a = data.get("article_number", "")
                    if a and a not in example_arts:
                        example_arts.append(a)
                        ex_lbl.setText(f"Exempelartiklar ({len(example_arts)} st):")
                        _rebuild_examples()
                    e.acceptProposedAction()

            drop_frame.dragEnterEvent = _drag_enter
            drop_frame.dragLeaveEvent = _drag_leave
            drop_frame.dropEvent = _drop
            img_row.addWidget(drop_frame)
            img_row.addStretch()

        def _remove_example(art_num):
            if art_num in example_arts:
                example_arts.remove(art_num)
                ex_lbl.setText(f"Exempelartiklar ({len(example_arts)} st):")
                _rebuild_examples()

        _rebuild_examples()
        scroll.setWidget(scroll_widget)
        lay.addWidget(scroll)

        btn_row = QHBoxLayout()
        save_btn = mk_btn("Spara ändringar", "#1B5E20")

        def _save():
            new_name = name_edit.text().strip()
            new_knowledge = editor.toPlainText().strip() if editor else ""

            if new_name and new_name != category:
                col = self._columns.get(category)
                if col:
                    col.set_name(new_name)
                    self._columns[new_name] = self._columns.pop(category)
                    for c in col._cards:
                        c["category"] = new_name
                    for cat in self._categories:
                        if cat["name"] == category:
                            cat["name"] = new_name
                            break
                    self._cat_knowledge[new_name] = new_knowledge
                    self._cat_knowledge.pop(category, None)
                    self._cat_example_articles[new_name] = list(example_arts)
                    self._cat_example_articles.pop(category, None)
                    for wkr in ([self._worker]
                                + self._new_cat_workers
                                + list(self._new_cat_workers_by_cat.values())):
                        if wkr and hasattr(wkr, "cat_knowledge"):
                            if category in wkr.cat_knowledge:
                                wkr.cat_knowledge[new_name] = wkr.cat_knowledge.pop(category)
                    dlg.accept()
                    return

            if knowledge and editor:
                self._cat_knowledge[category] = new_knowledge
                for wkr in [self._worker] + self._new_cat_workers:
                    if wkr and hasattr(wkr, "cat_knowledge"):
                        wkr.cat_knowledge[category] = new_knowledge
            self._cat_example_articles[category] = list(example_arts)
            dlg.accept()

        save_btn.clicked.connect(_save)
        btn_row.addWidget(save_btn)
        cancel_btn = mk_btn("Stäng", "#45475a")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    def _on_card_dropped(self, article_number: str, from_cat: str, to_cat: str):
        from_col = self._columns.get(from_cat)
        to_col   = self._columns.get(to_cat)
        if from_col and to_col:
            item = from_col.remove_card_by_article(article_number)
            if item:
                item["category"] = to_cat
                to_col.prepend_item(item)
                if article_number in self._cards_by_art:
                    self._cards_by_art[article_number]["category"] = to_cat
        self.reclassified.emit(article_number, to_cat)

    def _show_image_large(self, image_path: str, article_number: str = "",
                          category: str = "", url: str = ""):
        if not image_path or not Path(image_path).exists():
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Bildvisning — {article_number}" if article_number else "Bildvisning")
        dlg.setStyleSheet(STYLE)
        dlg.setMinimumWidth(900)

        main_lay = QHBoxLayout(dlg)
        main_lay.setContentsMargins(12, 12, 12, 12)
        main_lay.setSpacing(16)

        img_lbl = QLabel()
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_lbl.setStyleSheet("background:#11111b; border-radius:8px;")
        img_lbl.setMinimumSize(500, 500)
        try:
            if PIL_AVAILABLE:
                img = PILImage.open(image_path)
                img.thumbnail((700, 600), PILImage.LANCZOS)
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                px = QPixmap()
                px.loadFromData(buf.read())
            else:
                px = QPixmap(image_path)
                px = px.scaled(700, 600,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            img_lbl.setPixmap(px)
        except Exception as e:
            img_lbl.setText(str(e))
        main_lay.addWidget(img_lbl, 3)

        info_widget = QWidget()
        info_widget.setStyleSheet("background:#313244; border-radius:8px;")
        info_lay = QVBoxLayout(info_widget)
        info_lay.setContentsMargins(16, 16, 16, 16)
        info_lay.setSpacing(10)

        def add_field(label: str, value: str):
            if not value:
                return
            lbl = QLabel(
                f"<span style='color:#6c7086;font-size:11px;'>{label}</span><br>"
                f"<span style='color:#cdd6f4;font-size:13px;'>{value}</span>"
            )
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setStyleSheet("background:transparent;")
            info_lay.addWidget(lbl)
            s = QFrame()
            s.setFrameShape(QFrame.Shape.HLine)
            s.setStyleSheet("color:#45475a;")
            info_lay.addWidget(s)

        add_field("Artikelnummer", article_number)
        add_field("AI-kategori", category)

        meta = {}
        if article_number and self._data_mgr:
            meta = self._data_mgr.get_meta(article_number) or {}

        add_field("Beskrivning", meta.get("beskrivning", ""))
        add_field("Kategori (original)", meta.get("kategori", ""))
        add_field("Huvudkategori", meta.get("huvudkategori", ""))
        add_field("Vikt brutto", meta.get("vikt_brutto", ""))
        add_field("Vikt netto", meta.get("vikt_netto", ""))
        add_field("Volym", meta.get("volym", ""))
        add_field("Bolag", meta.get("bolag", ""))
        add_field("UN-nummer", meta.get("un_nummer", ""))
        if url:
            add_field("URL", url)

        info_lay.addStretch()

        close_btn = mk_btn("Stäng", "#45475a")
        close_btn.clicked.connect(dlg.accept)
        info_lay.addWidget(close_btn)

        main_lay.addWidget(info_widget, 2)
        dlg.exec()

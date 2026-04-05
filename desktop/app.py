"""desktop/app.py — MainApp (QMainWindow) and main() entry point."""
import csv
import json
import logging
import random
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout,
    QWidget,
)

from core.constants import (
    AI_JOB_MIN_PER_CAT, DEFAULT_AI_URL, DEFAULT_EXTERNAL_PROVIDERS,
    DEFAULT_MODEL, DEFAULT_SYFTE,
)
from core.data_manager import DataManager
from desktop.screens.ai_job_screen import AIJobScreen
from desktop.screens.ai_settings_screen import AISettingsScreen
from desktop.screens.article_overview_screen import ArticleOverviewScreen
from desktop.screens.categories_screen import CategoriesScreen
from desktop.screens.classify_screen import ClassifyScreen
from desktop.screens.done_screen import DoneScreen
from desktop.screens.filter_screen import FilterScreen
from desktop.screens.name_screen import NameScreen
from desktop.screens.source_screen import SourceScreen
from desktop.workers.image_downloader import ImageDownloader
from desktop.widgets.helpers import mk_btn

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

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


class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bildklassificering")
        self.resize(1000, 700)
        self.setMinimumSize(820, 600)
        self.setStyleSheet(STYLE)

        # ── Session state
        self.test_name     = ""
        self.syfte         = ""
        self.categories: List[Dict] = []
        self.images: List[Optional[Path]] = []
        self.current_index = 0
        self.csv_data:    List[Dict] = []
        self.results:     List[Dict] = []
        self.temp_dir:    Optional[str] = None
        self.categorized: List[Dict] = []

        # ── AI state
        self.ai_settings: Dict = {}
        self.ai_enabled   = False
        self.cat_knowledge: Dict[str, str] = {}
        self.cat_example_articles: Dict[str, List[str]] = {}

        # ── Data
        self.data_mgr = DataManager()

        # ── Download worker
        self.dl_worker:     Optional[ImageDownloader] = None
        self._ready_images: set = set()

        # ── Stack
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self._name_scr = NameScreen()
        self._cat_scr  = CategoriesScreen()
        self._cl_scr   = ClassifyScreen()
        self._done_scr = DoneScreen()

        self.stack.addWidget(self._name_scr)
        self.stack.addWidget(self._cat_scr)
        self.stack.addWidget(self._cl_scr)
        self.stack.addWidget(self._done_scr)

        # ── Connections
        self._name_scr.go_next.connect(self._on_name_done)
        self._name_scr.load_excel.connect(self._import_excel)
        self._cat_scr.go_next.connect(self._on_cats_done)
        self._cat_scr.go_back.connect(lambda: self.stack.setCurrentWidget(self._name_scr))

        self._cl_scr.classified.connect(self._on_classified)
        self._cl_scr.skipped.connect(self._on_skip)
        self._cl_scr.go_back.connect(self._on_go_back)
        self._cl_scr.add_category.connect(self._add_cat_during_test)
        self._cl_scr.category_renamed.connect(self._rename_cat_during_test)
        self._cl_scr.end_test.connect(self._show_done)
        self._cl_scr.run_ai_job.connect(self._run_ai_job)

        self._done_scr.new_test.connect(self._on_new_test)
        self._done_scr.retest_ovrigt.connect(self._retest_ovrigt)
        self._done_scr.export_excel.connect(self._export_excel)
        self._done_scr.resume_job.connect(self._open_resumed_session)
        self._done_scr.quit_app.connect(self.close)

        self.stack.setCurrentWidget(self._name_scr)
        self.showMaximized()

    # ── helpers ────────────────────────────────────────────────────────────────

    def _push_screen(self, widget: QWidget):
        self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)

    def _replace_top(self, new_widget: QWidget, old_widget: Optional[QWidget]):
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
        src.use_builtin.connect(self._show_filter_screen)
        src.use_csv.connect(self._stage_csv)
        src.go_back.connect(lambda: self.stack.setCurrentWidget(self._cat_scr))
        self._src_scr = src
        self._push_screen(src)

    def _show_filter_screen(self):
        flt = FilterScreen(self.test_name, list(self.data_mgr.builtin_attributes), self.data_mgr)
        flt.go_next.connect(self._stage_download)
        flt.go_back.connect(lambda: self.stack.setCurrentWidget(self._src_scr))
        self._flt_scr = flt
        self._push_screen(flt)

    def _stage_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Välj CSV-fil", "", "CSV-filer (*.csv);;Alla filer (*)"
        )
        if not path:
            return
        rows = self._parse_csv(path)
        if rows:
            self._pending_rows = rows
            self._pending_start = lambda: self._download_images(self._pending_rows)
            self._show_article_overview(rows)

    def _stage_download(self, rows: List[Dict]):
        self._pending_rows  = rows
        self._pending_start = lambda: self._download_images(self._pending_rows)
        self._show_article_overview(rows)

    def _show_article_overview(self, rows: List[Dict]):
        back_target = getattr(self, "_flt_scr", None) or getattr(self, "_src_scr", self._name_scr)
        overview = ArticleOverviewScreen(self.test_name, rows, self.data_mgr)
        overview.go_next.connect(self._show_ai_settings)
        overview.go_back.connect(lambda: self.stack.setCurrentWidget(back_target))
        self._overview_scr = overview
        self._push_screen(overview)

    def _show_ai_settings(self):
        overview = getattr(self, "_overview_scr", None)
        if overview:
            overview.cleanup()
        back_target = overview or getattr(self, "_flt_scr", None) or getattr(self, "_src_scr", self._name_scr)
        ai = AISettingsScreen(self.test_name)
        ai.go_next.connect(self._on_ai_done)
        ai.go_back.connect(lambda: self.stack.setCurrentWidget(back_target))
        self._ai_scr = ai
        self._push_screen(ai)

    def _on_ai_done(self, settings: Dict):
        self.ai_settings = settings
        self.ai_enabled  = bool(settings)
        pending = getattr(self, "_pending_start", None)
        self._pending_start = None
        if pending:
            pending()
        else:
            self._show_classify()

    # ── image loading ──────────────────────────────────────────────────────────

    def _parse_csv(self, path: str) -> Optional[List[Dict]]:
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                except csv.Error:
                    dialect = csv.excel
                all_rows = list(csv.reader(f, dialect))
            url_col = None
            for row in all_rows[:5]:
                for i, cell in enumerate(row):
                    if cell.strip().lower().startswith("http"):
                        url_col = i
                        break
                if url_col is not None:
                    break
            if url_col is None:
                QMessageBox.warning(self, "Ingen URL-kolumn",
                                    "Kunde inte hitta kolumn med URL:er.")
                return None
            rows = []
            for row in all_rows:
                if len(row) <= url_col:
                    continue
                art = row[0].strip()
                url = row[url_col].strip()
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
        self.csv_data = [{"article_number": r["article_number"], "url": r["url"],
                          "bolag": r.get("bolag", ""), "img_path": None} for r in rows]
        self.images        = [None] * len(rows)
        self.results       = []
        self.current_index = 0
        self._ready_images = set()

        self.temp_dir = tempfile.mkdtemp(prefix="bildklassificering_")
        if self.dl_worker:
            self.dl_worker.stop()
            self.dl_worker.wait()
        self.dl_worker = ImageDownloader(rows, self.temp_dir)
        self.dl_worker.image_ready.connect(self._on_image_ready)
        self.dl_worker.start()

        self._loading_scr = self._make_loading_screen(len(rows))
        self._push_screen(self._loading_scr)

        def poll():
            if 0 in self._ready_images:
                self.stack.removeWidget(self._loading_scr)
                self._loading_scr.setParent(None)
                self._show_classify()
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
        if index >= len(self.csv_data):
            return None
        entry = self.csv_data[index]
        return self.data_mgr.get_meta(str(entry["article_number"]), entry.get("bolag", ""))

    # ── classify screen ────────────────────────────────────────────────────────

    def _show_classify(self):
        if self.current_index >= len(self.images):
            self._show_done()
            return
        if self.current_index not in self._ready_images:
            self._show_wait_screen()
            return
        img_path = self.images[self.current_index]
        if img_path is None:
            self.current_index += 1
            self._show_classify()
            return

        meta = self._get_meta(self.current_index)
        cat_counts, threshold, ai_job_ready = self._get_threshold_data()

        prev_cat = ""
        if self.csv_data:
            art_num = str(self.csv_data[self.current_index].get("article_number", ""))
            for e in self.categorized:
                if str(e.get("article_number", "")) == art_num:
                    prev_cat = e.get("category", "")
                    break

        self._cl_scr.show_image(
            self.test_name, self.categories,
            str(img_path), meta,
            self.current_index, len(self.images),
            cat_counts, threshold, ai_job_ready,
            prev_category=prev_cat,
        )
        self.stack.setCurrentWidget(self._cl_scr)

    def _get_threshold_data(self) -> Tuple[Dict[str, int], int, bool]:
        non_ovrigt = [c["name"] for c in self.categories if c["name"] != "Övrigt"]
        if not non_ovrigt or not self.ai_enabled:
            return {}, 0, False
        threshold = AI_JOB_MIN_PER_CAT
        counts: Dict[str, int] = {name: 0 for name in non_ovrigt}
        for entry in self.categorized:
            cat = entry.get("category", "")
            if cat in counts:
                counts[cat] += 1
        ready = all(counts[name] >= threshold for name in non_ovrigt)
        return counts, threshold, ready

    def _show_wait_screen(self):
        w = QWidget()
        w.setStyleSheet("background:#1e1e2e;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("Väntar på nedladdning…")
        lbl.setStyleSheet("font-size:18px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        sub = QLabel(f"{len(self._ready_images)} av {len(self.images)} klara")
        sub.setStyleSheet("color:#6c7086;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        self.stack.addWidget(w)
        self.stack.setCurrentWidget(w)

        def poll():
            if self.current_index in self._ready_images:
                self.stack.removeWidget(w)
                w.setParent(None)
                self._show_classify()
            else:
                QTimer.singleShot(300, poll)
        QTimer.singleShot(300, poll)

    # ── classify logic ─────────────────────────────────────────────────────────

    def _on_classified(self, category: str):
        if self.current_index >= len(self.images):
            return
        img_path = self.images[self.current_index]
        art_num = str(self.csv_data[self.current_index]["article_number"])
        for e in self.categorized:
            if str(e.get("article_number", "")) == art_num:
                e["category"] = category
                break
        else:
            self.categorized.append({
                "image_path":     str(img_path),
                "category":       category,
                "article_number": art_num,
            })
        for r in self.results:
            if str(r.get("article_number", "")) == art_num:
                r["category"] = category
                break
        else:
            self.results.append({
                "article_number": art_num,
                "url":            self.csv_data[self.current_index]["url"],
                "category":       category,
            })
        self.current_index += 1
        self._show_classify()

    def _on_skip(self):
        self.current_index += 1
        self._show_classify()

    def _on_go_back(self):
        if self.current_index <= 0:
            return
        self.current_index -= 1
        self._show_classify()

    def _add_cat_during_test(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Ny kategori")
        dlg.setStyleSheet(STYLE)
        dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Kategorinamn:"))
        edit = QLineEdit()
        lay.addWidget(edit)
        lay.addWidget(QLabel("Syfte / beskrivning:"))
        desc_edit = QLineEdit()
        desc_edit.setPlaceholderText("Beskriv syftet med kategorin (valfritt)")
        lay.addWidget(desc_edit)
        if len(self.categories) >= 9:
            hint = QLabel("OBS: Fler än 9 kategorier — ingen tangent tilldelas.")
            hint.setStyleSheet("color:#fab387; font-size:11px; font-style:italic;")
            lay.addWidget(hint)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        edit.setFocus()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = edit.text().strip()
        if not name:
            return
        if any(c["name"] == name for c in self.categories) or name == "Övrigt":
            QMessageBox.warning(self, "Dubblett", f'"{name}" finns redan.')
            return
        self.categories.append({"name": name, "description": desc_edit.text().strip(), "knowledge": ""})
        self._show_classify()

    def _rename_cat_during_test(self, cat_idx: int, new_name: str, new_desc: str):
        old_name = self.categories[cat_idx]["name"]
        self.categories[cat_idx]["name"] = new_name
        self.categories[cat_idx]["description"] = new_desc
        if old_name != new_name:
            for entry in self.categorized:
                if entry.get("category") == old_name:
                    entry["category"] = new_name
            for entry in self.results:
                if entry.get("category") == old_name:
                    entry["category"] = new_name
        self._show_classify()

    # ── done screen ────────────────────────────────────────────────────────────

    def _show_done(self):
        self._cleanup_workers()
        ov_count = sum(1 for r in self.results if r.get("category") == "Övrigt")
        self._done_scr.show_results(
            self.test_name, self.categories, self.current_index,
            bool(self.results), ov_count,
            results=self.results,
        )
        self.stack.setCurrentWidget(self._done_scr)

    def _on_new_test(self):
        self._cleanup_workers()
        self._cleanup_temp()
        self._reset_state()
        self._name_scr.reset()
        self.stack.setCurrentWidget(self._name_scr)

    def _retest_ovrigt(self):
        ovrigt_rows = [r for r in self.results if r.get("category") == "Övrigt"]
        if not ovrigt_rows:
            QMessageBox.information(self, "Inga bilder", "Inga Övrigt-artiklar att testa om.")
            return
        art_set = {str(r["article_number"]) for r in ovrigt_rows}
        retest_data = [d for d in self.csv_data if str(d["article_number"]) in art_set]
        missing = [d for d in retest_data
                   if not d.get("img_path") or not Path(d["img_path"]).exists()]
        if missing:
            self._download_images([{"article_number": d["article_number"],
                                    "url": d["url"],
                                    "bolag": d.get("bolag", "")} for d in missing])
            return
        self.current_index = 0
        self.csv_data = retest_data
        self.images = [Path(d["img_path"]) for d in retest_data]
        self._show_classify()

    # ── AI job ─────────────────────────────────────────────────────────────────

    def _run_ai_job(self):
        if not self.ai_enabled:
            dlg = QDialog(self)
            dlg.setWindowTitle("AI-inställningar")
            dlg.setStyleSheet(STYLE)
            dlg.setFixedWidth(480)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(28, 24, 28, 24)
            lay.setSpacing(0)

            t = QLabel("AI-inställningar")
            t.setStyleSheet("font-size:18px; font-weight:bold; color:#89b4fa;")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(t)
            sub = QLabel("Välj mellan lokal LLM eller extern API-leverantör.")
            sub.setStyleSheet("font-size:10px; color:#6c7086;")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            lay.addWidget(sub)
            lay.addSpacing(20)

            provider_group = QButtonGroup(dlg)
            rb_local = QRadioButton("Lokal (LM Studio)")
            rb_local.setChecked(True)
            rb_external = QRadioButton("Extern API")
            provider_group.addButton(rb_local, 0)
            provider_group.addButton(rb_external, 1)
            prow = QHBoxLayout()
            prow.addWidget(rb_local)
            prow.addWidget(rb_external)
            prow.addStretch()
            lay.addLayout(prow)
            lay.addSpacing(12)

            local_frame = QFrame()
            local_frame.setStyleSheet("background:transparent;")
            lf = QVBoxLayout(local_frame)
            lf.setContentsMargins(0, 0, 0, 0)
            lf.setSpacing(4)
            lf.addWidget(QLabel("LM Studio URL:"))
            url_edit = QLineEdit(self.ai_settings.get("api_url", DEFAULT_AI_URL))
            url_edit.setFixedHeight(34)
            lf.addWidget(url_edit)
            lf.addSpacing(8)
            lf.addWidget(QLabel("Modell:"))
            model_edit = QLineEdit(self.ai_settings.get("model", DEFAULT_MODEL))
            model_edit.setFixedHeight(34)
            lf.addWidget(model_edit)
            lay.addWidget(local_frame)

            ext_frame = QFrame()
            ext_frame.setStyleSheet("background:transparent;")
            ext_frame.setVisible(False)
            ef = QVBoxLayout(ext_frame)
            ef.setContentsMargins(0, 0, 0, 0)
            ef.setSpacing(4)
            ef.addWidget(QLabel("Leverantör:"))
            ext_provider_group = QButtonGroup(dlg)
            ext_provider_buttons = {}
            for i, name in enumerate(DEFAULT_EXTERNAL_PROVIDERS):
                rb = QRadioButton(name)
                if i == 0:
                    rb.setChecked(True)
                ext_provider_group.addButton(rb, i)
                ext_provider_buttons[name] = rb
                ef.addWidget(rb)
            ef.addSpacing(4)
            ef.addWidget(QLabel("API-nyckel:"))
            api_key_edit = QLineEdit()
            api_key_edit.setPlaceholderText("Klistra in din API-nyckel här")
            api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            api_key_edit.setFixedHeight(34)
            ef.addWidget(api_key_edit)
            ef.addWidget(QLabel("API URL:"))
            ext_url_edit = QLineEdit()
            ext_url_edit.setFixedHeight(34)
            ef.addWidget(ext_url_edit)
            ef.addWidget(QLabel("Modell:"))
            ext_model_edit = QLineEdit()
            ext_model_edit.setFixedHeight(34)
            ef.addWidget(ext_model_edit)
            lay.addWidget(ext_frame)

            def _fill_ext_defaults():
                for n, rb in ext_provider_buttons.items():
                    if rb.isChecked():
                        info = DEFAULT_EXTERNAL_PROVIDERS[n]
                        ext_url_edit.setText(info["url"])
                        ext_model_edit.setText(info["model"])
                        break
            _fill_ext_defaults()
            for rb in ext_provider_buttons.values():
                rb.toggled.connect(lambda _: _fill_ext_defaults())

            def _toggle(local_checked):
                local_frame.setVisible(local_checked)
                ext_frame.setVisible(not local_checked)
            rb_local.toggled.connect(_toggle)

            lay.addSpacing(8)
            compress_cb = QCheckBox("Komprimera bilder (snabbare, marginellt sämre precision)")
            compress_cb.setChecked(self.ai_settings.get("compress_images", True))
            lay.addWidget(compress_cb)
            lay.addSpacing(20)

            go = mk_btn("Kör AI jobb  →", "#89b4fa", "#1e1e2e", h=40)
            go.clicked.connect(dlg.accept)
            lay.addWidget(go)
            lay.addSpacing(6)
            cancel = mk_btn("Avbryt", "#45475a", "#cdd6f4", h=34)
            cancel.clicked.connect(dlg.reject)
            lay.addWidget(cancel)

            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            if rb_local.isChecked():
                self.ai_settings = {
                    "api_url":         url_edit.text().strip() or DEFAULT_AI_URL,
                    "model":           model_edit.text().strip() or DEFAULT_MODEL,
                    "compress_images": compress_cb.isChecked(),
                    "api_key":         "",
                }
            else:
                key = api_key_edit.text().strip()
                if not key:
                    QMessageBox.warning(self, "API-nyckel saknas",
                                        "Du måste ange en API-nyckel för extern leverantör.")
                    return
                self.ai_settings = {
                    "api_url":         ext_url_edit.text().strip(),
                    "model":           ext_model_edit.text().strip(),
                    "compress_images": compress_cb.isChecked(),
                    "api_key":         key,
                }
            self.ai_enabled = True

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
            api_key=self.ai_settings.get("api_key", ""),
        )
        scr.article_added.connect(self._on_ai_article_classified)
        scr.reclassified.connect(self._on_ai_reclassified)
        scr.knowledge_updated.connect(self._on_knowledge_updated)
        scr.finished.connect(self._show_done)
        self._push_screen(scr)
        scr.start()

    def _on_ai_article_classified(self, article_number: str, category: str, url: str):
        existing = {r["article_number"] for r in self.results}
        if article_number not in existing:
            bolag = next(
                (r.get("bolag", "") for r in self.csv_data
                 if str(r.get("article_number", "")) == article_number),
                ""
            )
            self.results.append({
                "article_number": article_number,
                "category":       category,
                "url":            url,
                "bolag":          bolag,
            })

    def _on_ai_reclassified(self, article_number: str, new_category: str):
        for r in self.results:
            if r["article_number"] == article_number:
                r["category"] = new_category
                break

    def _on_knowledge_updated(self, knowledge: Dict, example_articles: Dict):
        self.cat_knowledge         = knowledge
        self.cat_example_articles  = example_articles

    def _open_resumed_session(self):
        img_by_art  = {str(r.get("article_number", "")): r.get("img_path", "")
                       for r in self.csv_data}
        art_in_cat  = {str(c.get("article_number", "")) for c in self.categorized}

        merged = list(self.categorized)
        for r in self.results:
            art = str(r.get("article_number", ""))
            if art not in art_in_cat:
                merged.append({
                    "article_number": art,
                    "category":   r.get("category", "Övrigt"),
                    "image_path": img_by_art.get(art, ""),
                    "url":        r.get("url", ""),
                    "bolag":      r.get("bolag", ""),
                })

        classified_nums = {str(c.get("article_number", "")) for c in merged}
        has_unclassified = any(
            str(row.get("article_number", "")) not in classified_nums
            for row in self.csv_data
        )

        scr = AIJobScreen(
            self.categories, merged, self.csv_data, self.syfte,
            self.ai_settings.get("api_url", DEFAULT_AI_URL),
            self.ai_settings.get("model", DEFAULT_MODEL),
            self.ai_settings.get("compress_images", True),
            self.data_mgr, self.test_name,
            api_key=self.ai_settings.get("api_key", ""),
            pre_knowledge=self.cat_knowledge if self.cat_knowledge else None,
            pre_example_articles=self.cat_example_articles if self.cat_example_articles else None,
        )
        scr.article_added.connect(self._on_ai_article_classified)
        scr.reclassified.connect(self._on_ai_reclassified)
        scr.knowledge_updated.connect(self._on_knowledge_updated)
        scr.finished.connect(self._show_done)
        self._push_screen(scr)
        if self.cat_knowledge:
            scr._cat_knowledge         = dict(self.cat_knowledge)
            scr._cat_example_articles  = dict(self.cat_example_articles)
        scr.start(skip_worker=not has_unclassified)

    # ── Excel import ───────────────────────────────────────────────────────────

    def _import_excel(self):
        if not OPENPYXL_AVAILABLE:
            QMessageBox.critical(self, "openpyxl saknas",
                                 "Installera openpyxl:\n  pip install openpyxl")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Öppna Excel-session", "", "Excel (*.xlsx *.xls)"
        )
        if not path:
            return
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

            session: Dict = {}
            if "Session" in wb.sheetnames:
                for row in wb["Session"].iter_rows(min_row=2, values_only=True):
                    if row[0] and row[1] is not None:
                        session[str(row[0])] = str(row[1])

            test_name = session.get("test_name", Path(path).stem)
            syfte     = DEFAULT_SYFTE
            try:
                categories = json.loads(session.get("categories_json", "[]"))
            except json.JSONDecodeError as _e:
                _logger.warning("Kunde inte tolka categories_json: %s", _e)
                categories = []
            try:
                cat_knowledge = json.loads(session.get("cat_knowledge_json", "{}"))
            except json.JSONDecodeError as _e:
                _logger.warning("Kunde inte tolka cat_knowledge_json: %s", _e)
                cat_knowledge = {}
            try:
                cat_example_articles = json.loads(session.get("cat_example_articles_json", "{}"))
            except json.JSONDecodeError as _e:
                _logger.warning("Kunde inte tolka cat_example_articles_json: %s", _e)
                cat_example_articles = {}

            results: List[Dict]    = []
            csv_data: List[Dict]   = []
            categorized: List[Dict] = []
            images: List           = []

            if "Resultat" in wb.sheetnames:
                ws = wb["Resultat"]
                headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
                h = {str(v).strip(): i for i, v in enumerate(headers) if v}

                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not any(row):
                        continue

                    def _cell(key, default=""):
                        idx = h.get(key)
                        return str(row[idx]).strip() if idx is not None and row[idx] is not None else default

                    art   = _cell("Artikelnummer")
                    cat   = _cell("Resultat kategori")
                    url   = _cell("Bild (URL)")
                    bolag = _cell("Bolag", "")
                    if not art:
                        continue
                    results.append({"article_number": art, "category": cat,
                                    "url": url, "bolag": bolag})
                    csv_data.append({"article_number": art, "url": url,
                                     "bolag": bolag, "img_path": None})
                    categorized.append({"article_number": art, "category": cat,
                                        "image_path": ""})
                    images.append(None)

            if "Oklassificerade" in wb.sheetnames:
                ws_u = wb["Oklassificerade"]
                u_headers = [c.value for c in next(ws_u.iter_rows(min_row=1, max_row=1))]
                u_h = {str(v).strip(): i for i, v in enumerate(u_headers) if v}
                for row in ws_u.iter_rows(min_row=2, values_only=True):
                    if not any(row):
                        continue

                    def _ucell(key, default=""):
                        idx = u_h.get(key)
                        return str(row[idx]).strip() if idx is not None and row[idx] is not None else default

                    art   = _ucell("Artikelnummer")
                    url   = _ucell("Bild (URL)")
                    bolag = _ucell("Bolag", "")
                    if not art:
                        continue
                    csv_data.append({"article_number": art, "url": url,
                                     "bolag": bolag, "img_path": None})

            wb.close()

            self._cleanup_workers()
            self._cleanup_temp()
            self._reset_state()

            self.test_name           = test_name
            self.syfte               = syfte
            self.categories          = categories
            self.csv_data            = csv_data
            self.categorized         = categorized
            self.results             = results
            self.images              = images
            self.current_index       = len(images)
            self.cat_knowledge       = cat_knowledge
            self.cat_example_articles = cat_example_articles

            self._name_scr.name_edit.setText(test_name)
            self._cat_scr.set_test_name(test_name)

            if results:
                self._pending_start = self._open_resumed_session
                self._show_ai_settings()
            else:
                QMessageBox.information(self, "Tom session", "Inga resultat hittades i filen.")

        except Exception as e:
            QMessageBox.critical(self, "Fel", f"Kunde inte läsa Excel-filen:\n{e}")

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
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Resultat"
        headers = [
            "Artikelnummer", "Resultat kategori", "Huvudkategori",
            "Beskrivning", "Längd (mm)", "Bredd (mm)", "Höjd (mm)",
            "Volym", "Vikt brutto (kg)", "Vikt netto (kg)",
            "Robot (Y/N)", "StoreQuantity", "Bild (URL)",
        ]
        ws.append(headers)
        for row in self.results:
            art  = str(row.get("article_number", ""))
            meta = self.data_mgr.get_meta(art, row.get("bolag", "")) or {}
            ws.append([
                art,
                row.get("category", ""),
                meta.get("huvudkategori", ""),
                meta.get("beskrivning", ""),
                meta.get("langd", ""),
                meta.get("bredd", ""),
                meta.get("hojd", ""),
                meta.get("volym", ""),
                meta.get("vikt_brutto", ""),
                meta.get("vikt_netto", ""),
                meta.get("robot", ""),
                meta.get("store_quantity", ""),
                row.get("url", ""),
            ])
        col_widths = [20, 25, 25, 40, 12, 12, 12, 12, 18, 18, 12, 15, 60]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

        classified_nums = {str(r.get("article_number", "")) for r in self.results}
        unclassified = [
            row for row in self.csv_data
            if str(row.get("article_number", "")) not in classified_nums
        ]
        if unclassified:
            ws_u = wb.create_sheet("Oklassificerade")
            ws_u.append(["Artikelnummer", "Bild (URL)", "Bolag"])
            for row in unclassified:
                ws_u.append([
                    str(row.get("article_number", "")),
                    row.get("url", ""),
                    row.get("bolag", ""),
                ])
            ws_u.column_dimensions["A"].width = 20
            ws_u.column_dimensions["B"].width = 60
            ws_u.column_dimensions["C"].width = 15

        ws_s = wb.create_sheet("Session")
        ws_s.append(["Nyckel", "Värde"])
        ws_s.append(["test_name", self.test_name])
        ws_s.append(["syfte", self.syfte])
        ws_s.append(["categories_json", json.dumps(self.categories, ensure_ascii=False)])
        if self.cat_knowledge:
            ws_s.append(["cat_knowledge_json",
                         json.dumps(self.cat_knowledge, ensure_ascii=False)])
        if self.cat_example_articles:
            ws_s.append(["cat_example_articles_json",
                         json.dumps(self.cat_example_articles, ensure_ascii=False)])
        ws_s.column_dimensions["A"].width = 30
        ws_s.column_dimensions["B"].width = 80

        if self.cat_knowledge:
            ws_k = wb.create_sheet("Kategorianalys")
            ws_k.append(["Kategori", "AI-analys", "Exempelartiklar"])
            for cat_name, knowledge in self.cat_knowledge.items():
                example_arts = self.cat_example_articles.get(cat_name, [])
                ws_k.append([cat_name, knowledge, ", ".join(example_arts)])
            ws_k.column_dimensions["A"].width = 25
            ws_k.column_dimensions["B"].width = 80
            ws_k.column_dimensions["C"].width = 40

        try:
            wb.save(path)
            QMessageBox.information(self, "Exporterat", f"Sparad:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Fel", f"Kunde inte spara:\n{e}")

    # ── cleanup ────────────────────────────────────────────────────────────────

    def _cleanup_workers(self):
        if self.dl_worker:
            self.dl_worker.stop()
            self.dl_worker.wait()
            self.dl_worker = None

    def _cleanup_temp(self):
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir = None

    def _reset_state(self):
        self.test_name     = ""
        self.syfte         = ""
        self.categories    = []
        self.images        = []
        self.current_index = 0
        self.csv_data      = []
        self.results       = []
        self.categorized   = []
        self.ai_settings   = {}
        self.ai_enabled    = False
        self._ready_images = set()
        self.cat_knowledge         = {}
        self.cat_example_articles  = {}

    def closeEvent(self, event):
        self._cleanup_workers()
        self._cleanup_temp()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainApp()
    win.show()
    sys.exit(app.exec())

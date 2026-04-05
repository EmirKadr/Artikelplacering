"""ClassifyScreen — manual image classification screen."""
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from core.constants import CATEGORY_COLORS, _EMPTY
from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn, sep

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

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


class ClassifyScreen(QWidget):
    classified       = pyqtSignal(str)
    skipped          = pyqtSignal()
    go_back          = pyqtSignal()
    add_category     = pyqtSignal()
    end_test         = pyqtSignal()
    run_ai_job       = pyqtSignal()
    category_renamed = pyqtSignal(int, str, str)  # (index, new_name, new_description)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shortcuts: List[QShortcut] = []
        self._inner: Optional[QWidget] = None
        self._main_lay = QVBoxLayout(self)
        self._main_lay.setContentsMargins(0, 0, 0, 0)
        self._main_lay.setSpacing(0)

    def show_image(self, test_name: str, categories: List[Dict],
                   image_path: str, meta: Optional[Dict],
                   current: int, total: int,
                   cat_counts: Optional[Dict[str, int]] = None,
                   threshold: int = 0,
                   ai_job_ready: bool = False,
                   prev_category: str = ""):
        self._clear()
        self._test_name     = test_name
        self._categories    = categories
        self._image_path    = image_path
        self._meta          = meta
        self._current       = current
        self._total         = total
        self._cat_counts    = cat_counts or {}
        self._threshold     = threshold
        self._ai_job_ready  = ai_job_ready
        self._prev_category = prev_category
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

        prog = f"Bild {self._current + 1} av {self._total}"
        header = HeaderBar(self._test_name, prog)
        inner_lay.addWidget(header)

        if self._threshold > 0:
            inner_lay.addWidget(self._build_threshold_bar())

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

        info_bar = QFrame()
        info_bar.setStyleSheet("background:#181825; border-top:1px solid #313244;")
        info_bar.setFixedHeight(26)
        ib = QHBoxLayout(info_bar)
        ib.setContentsMargins(12, 0, 12, 0)
        ib.addWidget(QLabel(str(self._image_path)))
        inner_lay.addWidget(info_bar)

        cat_frame = QFrame()
        cat_frame.setStyleSheet("background:#1e1e2e;")
        cf = QVBoxLayout(cat_frame)
        cf.setContentsMargins(12, 8, 12, 4)
        self._build_cat_buttons(cf)
        inner_lay.addWidget(cat_frame)

        ctrl = QFrame()
        ctrl.setStyleSheet("background:#1e1e2e; border-top:1px solid #313244;")
        ctrl_lay = QHBoxLayout(ctrl)
        ctrl_lay.setContentsMargins(12, 6, 12, 6)

        back_btn = mk_btn("← Tillbaka", "#45475a", "#cdd6f4")
        back_btn.setEnabled(self._current > 0)
        back_btn.clicked.connect(self.go_back.emit)
        ctrl_lay.addWidget(back_btn)

        skip_btn = mk_btn("Hoppa över  →", "#45475a", "#cdd6f4")
        skip_btn.clicked.connect(self.skipped.emit)
        ctrl_lay.addWidget(skip_btn)

        add_btn = mk_btn("+ Ny kategori", "#FF9800")
        add_btn.clicked.connect(self.add_category.emit)
        ctrl_lay.addWidget(add_btn)
        ctrl_lay.addStretch()

        if self._prev_category:
            prev_lbl = QLabel(f"Klassificerades som: {self._prev_category}")
            prev_lbl.setStyleSheet("color:#fab387; font-size:11px; font-style:italic;")
            ctrl_lay.addWidget(prev_lbl)

        if self._ai_job_ready:
            ai_btn = mk_btn("🤖  Kör AI jobb", "#1e3a5f", "#89b4fa", h=34)
            ai_btn.clicked.connect(self.run_ai_job.emit)
            ctrl_lay.addWidget(ai_btn)
        end_btn = mk_btn("Avsluta test", "#f38ba8", "#1e1e2e")
        end_btn.clicked.connect(self._confirm_end)
        ctrl_lay.addWidget(end_btn)
        inner_lay.addWidget(ctrl)

        sc_back = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        if self._current > 0:
            sc_back.activated.connect(self.go_back.emit)
        else:
            sc_back.setEnabled(False)
        self._shortcuts.append(sc_back)

        sc_skip = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        sc_skip.activated.connect(self.skipped.emit)
        self._shortcuts.append(sc_skip)

        self._main_lay.addWidget(self._inner)

    def _build_threshold_bar(self) -> QFrame:
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
            row = QFrame()
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            lbl_w = QLabel(f"{label}:")
            lbl_w.setStyleSheet("color:#6c7086; font-size:11px;")
            lbl_w.setFixedWidth(82)
            val_w = QLabel(str(value))
            val_w.setStyleSheet("color:#cdd6f4; font-size:11px;")
            val_w.setWordWrap(True)
            val_w.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse |
                Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            rl.addWidget(lbl_w)
            rl.addWidget(val_w, 1)
            lay.addWidget(row)

        lay.addStretch()
        return panel

    def _build_cat_buttons(self, parent_lay: QVBoxLayout):
        key_map: Dict[int, Tuple[str, str, int]] = {}
        for i, cat in enumerate(self._categories[:9]):
            key_map[i + 1] = (cat["name"], CATEGORY_COLORS[i % len(CATEGORY_COLORS)], i)
        key_map[0] = ("Övrigt", "#45475a", -1)

        positions = {
            7: (0, 0), 8: (0, 1), 9: (0, 2),
            4: (1, 0), 5: (1, 1), 6: (1, 2),
            1: (2, 0), 2: (2, 1), 3: (2, 2),
            0: (3, 1),
        }
        grid_w = QWidget()
        grid_w.setStyleSheet("background:transparent;")
        grid = QGridLayout(grid_w)
        grid.setSpacing(4)

        for key, (row, col) in positions.items():
            if key not in key_map:
                continue
            name, color, cat_idx = key_map[key]
            b = QPushButton(f"{name}  ({key})")
            b.setFixedSize(168, 40)
            b.setStyleSheet(
                f"background:{color}; color:white; border-radius:6px; "
                f"font-weight:bold; border:none;"
            )
            b.clicked.connect(lambda checked, c=name: self.classified.emit(c))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(
                lambda pos, btn=b, idx=cat_idx, n=name: self._show_cat_context_menu(btn, idx, n)
            )
            grid.addWidget(b, row, col, Qt.AlignmentFlag.AlignCenter)

            sc = QShortcut(QKeySequence(str(key)), self)
            sc.activated.connect(lambda c=name: self.classified.emit(c))
            self._shortcuts.append(sc)

        parent_lay.addWidget(grid_w, 0, Qt.AlignmentFlag.AlignCenter)

        extra_cats = self._categories[9:]
        if extra_cats:
            extra_w = QWidget()
            extra_w.setStyleSheet("background:transparent;")
            extra_lay = QGridLayout(extra_w)
            extra_lay.setSpacing(4)
            for j, cat in enumerate(extra_cats):
                real_idx = 9 + j
                color = CATEGORY_COLORS[real_idx % len(CATEGORY_COLORS)]
                b = QPushButton(cat["name"])
                b.setFixedSize(168, 40)
                b.setStyleSheet(
                    f"background:{color}; color:white; border-radius:6px; "
                    f"font-weight:bold; border:none;"
                )
                b.clicked.connect(lambda checked, c=cat["name"]: self.classified.emit(c))
                b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(
                    lambda pos, btn=b, idx=real_idx, n=cat["name"]: self._show_cat_context_menu(btn, idx, n)
                )
                extra_lay.addWidget(b, j // 3, j % 3, Qt.AlignmentFlag.AlignCenter)
            parent_lay.addWidget(extra_w, 0, Qt.AlignmentFlag.AlignCenter)

    def _show_cat_context_menu(self, btn: QPushButton, cat_idx: int, cat_name: str):
        if cat_name == "Övrigt":
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#313244; color:#cdd6f4; border:1px solid #45475a; }"
            "QMenu::item:selected { background:#45475a; }"
        )
        rename_action = menu.addAction("Byt namn / ändra syfte")
        chosen = menu.exec(btn.mapToGlobal(btn.rect().center()))
        if chosen == rename_action:
            self._rename_category(cat_idx, cat_name)

    def _rename_category(self, cat_idx: int, cat_name: str):
        cat = self._categories[cat_idx]
        dlg = QDialog(self)
        dlg.setWindowTitle("Redigera kategori")
        dlg.setStyleSheet(STYLE)
        dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg)

        lay.addWidget(QLabel("Kategorinamn:"))
        name_edit = QLineEdit(cat["name"])
        lay.addWidget(name_edit)

        lay.addWidget(QLabel("Syfte / beskrivning:"))
        desc_edit = QLineEdit(cat.get("description", ""))
        desc_edit.setPlaceholderText("Beskriv syftet med kategorin (valfritt)")
        lay.addWidget(desc_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        name_edit.setFocus()

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_name = name_edit.text().strip()
        new_desc = desc_edit.text().strip()
        if not new_name:
            return
        if new_name != cat_name and (
            any(c["name"] == new_name for c in self._categories) or new_name == "Övrigt"
        ):
            QMessageBox.warning(self, "Dubblett", f'"{new_name}" finns redan.')
            return
        self.category_renamed.emit(cat_idx, new_name, new_desc)

    def _load_image(self):
        try:
            if PIL_AVAILABLE:
                img = PILImage.open(self._image_path)
                img.thumbnail((780, 370), PILImage.LANCZOS)
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                px = QPixmap()
                px.loadFromData(buf.read())
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

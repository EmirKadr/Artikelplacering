"""SetupScreen — kombinerad skärm för testnamn, kategorier och artikelöversikt.

Visas efter SourceScreen/FilterScreen så artikellistan är laddad. Vänster panel
låter användaren ange namn och redigera kategorier; höger panel visar artiklar
med miniatyrer i en tabell.
"""
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QScrollArea, QVBoxLayout, QWidget,
)

from core.constants import DEFAULT_SYFTE
from desktop.widgets._thumbnail_loader import _ThumbnailLoader
from desktop.widgets.category_row import CategoryRow
from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn, sep


class SetupScreen(QWidget):
    """Kombinerad setup-skärm: namn + kategorier + artikelöversikt."""
    go_next = pyqtSignal(str, str, list)  # (test_name, syfte, categories)
    go_back = pyqtSignal()

    def __init__(self, rows: List[Dict], data_mgr,
                 prefill_name: str = "",
                 prefill_cats: Optional[List[Dict]] = None,
                 parent=None):
        super().__init__(parent)
        self._data_mgr = data_mgr
        self._rows_data: List[Dict] = list(rows or [])
        self._cat_rows: List[CategoryRow] = []
        self._thumb_loader: Optional[_ThumbnailLoader] = None
        self._thumb_labels: Dict[int, QLabel] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = HeaderBar("", f"{len(self._rows_data)} artiklar i urvalet")
        outer.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        body.addWidget(self._build_left_panel(), 0)
        body.addWidget(self._build_right_panel(), 1)

        body_wrapper = QWidget()
        body_wrapper.setLayout(body)
        outer.addWidget(body_wrapper, 1)

        outer.addWidget(self._build_button_bar())

        # Prefill if anything provided
        if prefill_name:
            self.name_edit.setText(prefill_name)
        if prefill_cats:
            self._set_category_rows(prefill_cats)
        else:
            for _ in range(3):
                self._add_row()

        # Start thumbnail loader
        self._start_thumb_loader()

    # ── Left panel (name + categories) ──────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("setup_left_panel")
        panel.setFixedWidth(460)
        panel.setStyleSheet("background:#1e1e2e; border-right:1px solid #313244;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(10)

        title = QLabel("Nytt test")
        title.setStyleSheet("font-size:20px; font-weight:bold; color:#89b4fa;")
        lay.addWidget(title)

        name_lbl = QLabel("Namn på testet")
        name_lbl.setStyleSheet("font-size:11px; font-weight:600; color:#a6adc8;")
        lay.addWidget(name_lbl)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("t.ex. Testomgång 1")
        self.name_edit.setFixedHeight(34)
        self.name_edit.returnPressed.connect(self._validate)
        lay.addWidget(self.name_edit)

        lay.addSpacing(6)
        lay.addWidget(sep())
        lay.addSpacing(4)

        cats_title = QLabel("Kategorier")
        cats_title.setStyleSheet("font-size:14px; font-weight:bold; color:#cdd6f4;")
        lay.addWidget(cats_title)

        hint = QLabel(
            '"Övrigt" läggs alltid till automatiskt. '
            'Beskrivningarna är valfria men hjälper AI:n att gissa rätt.'
        )
        hint.setStyleSheet("color:#6c7086; font-size:11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        col_hdr = QFrame()
        col_hdr.setStyleSheet("background:transparent;")
        ch = QHBoxLayout(col_hdr)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(6)
        spacer = QLabel()
        spacer.setFixedWidth(24)
        ch.addWidget(spacer)
        lbl_n = QLabel("Namn")
        lbl_n.setStyleSheet("color:#6c7086; font-size:11px;")
        lbl_n.setFixedWidth(140)
        ch.addWidget(lbl_n)
        lbl_d = QLabel("Beskrivning")
        lbl_d.setStyleSheet("color:#6c7086; font-size:11px;")
        ch.addWidget(lbl_d)
        ch.addStretch()
        lay.addWidget(col_hdr)

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
        lay.addWidget(scroll, 1)

        add_btn = mk_btn("+ Lägg till rad", "#313244", "#cdd6f4")
        add_btn.clicked.connect(self._add_row)
        lay.addWidget(add_btn)

        return panel

    # ── Right panel (article overview) ──────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("setup_article_scroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(40, 24, 40, 24)
        cl.setSpacing(12)

        title = QLabel("Artikelöversikt")
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        cl.addWidget(title)

        subtitle = QLabel(f"{len(self._rows_data)} artiklar valda för klassificering")
        subtitle.setStyleSheet("color:#6c7086; font-size:13px;")
        cl.addWidget(subtitle)

        cl.addWidget(sep())

        # Summary statistics
        hkat_counts: Dict[str, int] = {}
        bolag_counts: Dict[str, int] = {}
        for r in self._rows_data:
            meta = (self._data_mgr.get_meta(str(r["article_number"]), r.get("bolag", ""))
                    if self._data_mgr else None)
            hkat = (meta or {}).get("huvudkategori", "") or "Okänd"
            bolag = r.get("bolag", "") or "–"
            hkat_counts[hkat] = hkat_counts.get(hkat, 0) + 1
            bolag_counts[bolag] = bolag_counts.get(bolag, 0) + 1

        if len(hkat_counts) > 1 or (len(hkat_counts) == 1 and "Okänd" not in hkat_counts):
            sec = QLabel("Huvudkategorier")
            sec.setStyleSheet("font-size:14px; font-weight:bold; color:#89b4fa;")
            cl.addWidget(sec)
            for hk, cnt in sorted(hkat_counts.items(), key=lambda x: -x[1]):
                lbl = QLabel(f"  {hk}: {cnt}")
                lbl.setStyleSheet("color:#cdd6f4; font-size:12px;")
                cl.addWidget(lbl)
            cl.addWidget(sep())

        if len(bolag_counts) > 1:
            sec = QLabel("Bolag")
            sec.setStyleSheet("font-size:14px; font-weight:bold; color:#89b4fa;")
            cl.addWidget(sec)
            for b, cnt in sorted(bolag_counts.items(), key=lambda x: -x[1]):
                lbl = QLabel(f"  {b}: {cnt}")
                lbl.setStyleSheet("color:#cdd6f4; font-size:12px;")
                cl.addWidget(lbl)
            cl.addWidget(sep())

        tbl_label = QLabel("Artiklar")
        tbl_label.setStyleSheet("font-size:14px; font-weight:bold; color:#89b4fa;")
        cl.addWidget(tbl_label)

        hdr_frame = QFrame()
        hdr_frame.setStyleSheet("background:#313244; border-radius:4px;")
        hdr_lay = QHBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(8, 4, 8, 4)
        hdr_lay.setSpacing(8)
        img_hdr = QLabel("Bild")
        img_hdr.setFixedWidth(68)
        img_hdr.setStyleSheet("color:#89b4fa; font-weight:bold; font-size:11px;")
        hdr_lay.addWidget(img_hdr)
        for text, w in [("Artikelnr", 120), ("Beskrivning", 260),
                        ("Huvudkategori", 140), ("Bolag", 90)]:
            lbl = QLabel(text)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet("color:#89b4fa; font-weight:bold; font-size:11px;")
            hdr_lay.addWidget(lbl)
        hdr_lay.addStretch()
        cl.addWidget(hdr_frame)

        display_rows = self._rows_data[:200]
        for i, r in enumerate(display_rows):
            art = str(r.get("article_number", ""))
            meta = (self._data_mgr.get_meta(art, r.get("bolag", ""))
                    if self._data_mgr else None) or {}
            row_frame = QFrame()
            row_frame.setStyleSheet(
                "QFrame { background:transparent; border-bottom:1px solid #313244; }"
                "QFrame:hover { background:#313244; }"
            )
            rl = QHBoxLayout(row_frame)
            rl.setContentsMargins(8, 2, 8, 2)
            rl.setSpacing(8)

            thumb_lbl = QLabel()
            thumb_lbl.setFixedSize(60, 60)
            thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb_lbl.setStyleSheet("background:#313244; border-radius:4px; color:#6c7086; font-size:9px;")
            thumb_lbl.setText("…")
            rl.addWidget(thumb_lbl)
            self._thumb_labels[i] = thumb_lbl

            art_lbl = QLabel(art)
            art_lbl.setFixedWidth(120)
            art_lbl.setStyleSheet("color:#cdd6f4; font-size:11px;")
            rl.addWidget(art_lbl)

            desc_lbl = QLabel(str(meta.get("beskrivning", "") or ""))
            desc_lbl.setFixedWidth(260)
            desc_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
            desc_lbl.setWordWrap(True)
            rl.addWidget(desc_lbl)

            hkat_lbl = QLabel(str(meta.get("huvudkategori", "") or ""))
            hkat_lbl.setFixedWidth(140)
            hkat_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
            rl.addWidget(hkat_lbl)

            bolag_lbl = QLabel(str(r.get("bolag", "") or ""))
            bolag_lbl.setFixedWidth(90)
            bolag_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
            rl.addWidget(bolag_lbl)

            rl.addStretch()
            cl.addWidget(row_frame)

        if len(self._rows_data) > 200:
            more = QLabel(f"… och {len(self._rows_data) - 200} fler artiklar")
            more.setStyleSheet("color:#6c7086; font-size:11px; font-style:italic;")
            cl.addWidget(more)

        if not self._rows_data:
            empty = QLabel("Inga artiklar att visa")
            empty.setStyleSheet("color:#6c7086; font-size:12px; font-style:italic;")
            cl.addWidget(empty)

        cl.addStretch()
        scroll.setWidget(content)
        return scroll

    # ── Button bar ──────────────────────────────────────────────────────────

    def _build_button_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet("background:#1e1e2e; border-top:1px solid #313244;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(40, 8, 40, 8)
        back_btn = mk_btn("← Tillbaka", "#45475a", "#cdd6f4")
        back_btn.clicked.connect(self.go_back.emit)
        bar_lay.addWidget(back_btn)
        bar_lay.addStretch()
        start_btn = mk_btn("Starta klassificering  →", "#89b4fa", "#1e1e2e", h=44)
        start_btn.clicked.connect(self._validate)
        bar_lay.addWidget(start_btn)
        return bar

    # ── Category row management ─────────────────────────────────────────────

    def _add_row(self) -> None:
        row = CategoryRow(len(self._cat_rows) + 1)
        row.removed.connect(self._remove_row)
        self._cat_rows.append(row)
        self.rows_lay.insertWidget(self.rows_lay.count() - 1, row)
        row.name_edit.setFocus()

    def _remove_row(self, row: CategoryRow) -> None:
        self._cat_rows.remove(row)
        row.setParent(None)
        for i, r in enumerate(self._cat_rows):
            r.set_number(i + 1)

    def _set_category_rows(self, cats: List[Dict]) -> None:
        for row in list(self._cat_rows):
            row.setParent(None)
        self._cat_rows.clear()
        for cat in cats:
            self._add_row()
            self._cat_rows[-1].name_edit.setText(cat.get("name", ""))
            self._cat_rows[-1].desc_edit.setText(cat.get("description", ""))
        if not self._cat_rows:
            for _ in range(3):
                self._add_row()

    # ── Validation ──────────────────────────────────────────────────────────

    def _validate(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Fel", "Ange ett namn för testet.")
            return
        safe = "".join(ch for ch in name if ch not in r'\/:*?"<>|').strip()
        if not safe:
            QMessageBox.warning(self, "Fel", "Namnet innehåller ogiltiga tecken.")
            return
        cats = [
            {"name": n, "description": d}
            for r in self._cat_rows
            for n, d in [r.get_data()] if n
        ]
        if not cats:
            QMessageBox.warning(self, "Fel", "Ange minst en kategori.")
            return
        self.go_next.emit(safe, DEFAULT_SYFTE, cats)

    # ── Thumbnail loader ────────────────────────────────────────────────────

    def _start_thumb_loader(self) -> None:
        display_rows = self._rows_data[:200]
        if not display_rows:
            return
        # Skippa tråd om ingen rad har URL (inga nedladdningar behövs)
        if not any(r.get("url") for r in display_rows):
            return
        self._thumb_loader = _ThumbnailLoader(display_rows)
        self._thumb_loader.thumb_ready.connect(self._on_thumb_ready)
        self._thumb_loader.start()

    def _on_thumb_ready(self, index: int, px: QPixmap) -> None:
        lbl = self._thumb_labels.get(index)
        if lbl:
            lbl.setPixmap(px)
            lbl.setText("")

    # ── Public API ──────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        if self._thumb_loader and self._thumb_loader.isRunning():
            self._thumb_loader.stop()
            self._thumb_loader.wait(2000)

    def reset(self) -> None:
        self.name_edit.clear()
        self._set_category_rows([])
        self.cleanup()
        self.name_edit.setFocus()

    def prefill(self, name: str, cats: Optional[List[Dict]]) -> None:
        self.name_edit.setText(name or "")
        if cats:
            self._set_category_rows(cats)

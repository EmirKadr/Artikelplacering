"""FilterScreen — user filters articles before classification."""
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QRadioButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget,
)

from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn, sep


class FilterScreen(QWidget):
    go_next = pyqtSignal(list)  # filtered rows
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
                "bolag": r.get("bolag", "") or "–",
                "hkat":  meta.get("huvudkategori", "") or "Okänd",
                "robot": meta.get("robot", "N").upper() or "N",
            })

        bolags = sorted({m["bolag"] for m in self._row_meta})
        hkats  = sorted({m["hkat"]  for m in self._row_meta})

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

        # ── Article number filter ─────────────────────────────────────────────
        cl.addWidget(self._section_label("Begränsa till artikelnummer (valfritt)"))
        art_hint = QLabel(
            "Klistra in ett artikelnummer per rad. Lämnas tomt används alla artiklar."
        )
        art_hint.setStyleSheet("color:#6c7086; font-size:11px;")
        cl.addWidget(art_hint)
        self._art_filter = QTextEdit()
        self._art_filter.setPlaceholderText("artikel1\nartikel2\nartikel3")
        self._art_filter.setFixedHeight(100)
        self._art_filter.setStyleSheet(
            "background:#11111b; color:#cdd6f4; font-family:monospace;"
            "border:1px solid #45475a; border-radius:4px;"
        )
        self._art_filter.textChanged.connect(self._update_count)
        cl.addWidget(self._art_filter)

        cl.addWidget(sep())

        self._match_lbl = QLabel()
        self._match_lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#a6e3a1;")
        cl.addWidget(self._match_lbl)

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

    # ── helpers ─────────────────────────────────────────────────────────────

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

    def _art_number_filter(self) -> Optional[set]:
        text = self._art_filter.toPlainText().strip()
        if not text:
            return None
        return {line.strip() for line in text.splitlines() if line.strip()}

    def _filtered_rows(self) -> List[Dict]:
        bolags   = self._selected_bolags()
        hkats    = self._selected_hkats()
        robot    = self._robot_filter()
        art_nums = self._art_number_filter()
        result = []
        for row, meta in zip(self._all_rows, self._row_meta):
            if art_nums and str(row.get("article_number", "")) not in art_nums:
                continue
            if bolags and meta["bolag"] not in bolags:
                continue
            if hkats and meta["hkat"] not in hkats:
                continue
            if robot != "alla" and meta["robot"] != robot:
                continue
            result.append(row)
        return result

    def _update_count(self) -> None:
        n = len(self._filtered_rows())
        total = len(self._all_rows)
        self._total_lbl.setText(f"Totalt {total} artiklar i källan")
        self._match_lbl.setText(f"{n} artikel{'er' if n != 1 else ''} matchar filtret")
        self._start_btn.setEnabled(n > 0)

    def _on_start(self) -> None:
        self.go_next.emit(self._filtered_rows())

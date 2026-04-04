"""CategoriesScreen — screen where the user defines classification categories."""
from typing import List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox,
    QScrollArea, QVBoxLayout, QWidget,
)

from desktop.widgets.category_row import CategoryRow
from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn


class CategoriesScreen(QWidget):
    go_next = pyqtSignal(list)  # [{name, description}]
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
        spacer = QLabel()
        spacer.setFixedWidth(24)
        ch.addWidget(spacer)
        lbl_n = QLabel("Namn")
        lbl_n.setStyleSheet("color:#6c7086; font-size:12px;")
        lbl_n.setFixedWidth(190)
        ch.addWidget(lbl_n)
        lbl_d = QLabel("Beskrivning (hjälper AI:n)")
        lbl_d.setStyleSheet("color:#6c7086; font-size:12px;")
        ch.addWidget(lbl_d)
        ch.addStretch()
        body_lay.addWidget(col_hdr)

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

    def _add_row(self) -> None:
        row = CategoryRow(len(self._rows) + 1)
        row.removed.connect(self._remove_row)
        self._rows.append(row)
        self.rows_lay.insertWidget(self.rows_lay.count() - 1, row)
        row.name_edit.setFocus()

    def _remove_row(self, row: CategoryRow) -> None:
        self._rows.remove(row)
        row.setParent(None)
        for i, r in enumerate(self._rows):
            r.set_number(i + 1)

    def _validate(self) -> None:
        cats = [
            {"name": n, "description": d}
            for r in self._rows
            for n, d in [r.get_data()] if n
        ]
        if not cats:
            QMessageBox.warning(self, "Fel", "Ange minst en kategori.")
            return
        self.go_next.emit(cats)

    def set_test_name(self, name: str) -> None:
        self.header.set_texts(f"Test: {name}")

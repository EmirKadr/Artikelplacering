"""CategoryRow — one editable row in the categories setup screen."""
from typing import Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton


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

    def set_number(self, n: int) -> None:
        self.num_lbl.setText(f"{n}.")

    def get_data(self) -> Tuple[str, str]:
        return self.name_edit.text().strip(), self.desc_edit.text().strip()

    def is_empty(self) -> bool:
        return not self.name_edit.text().strip()

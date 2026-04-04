"""NameScreen — landing screen where the user names the test session."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QVBoxLayout, QWidget,
)

from core.constants import DEFAULT_SYFTE
from desktop.widgets.helpers import mk_btn


class NameScreen(QWidget):
    go_next    = pyqtSignal(str, str)  # (test_name, syfte)
    load_excel = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()

        card = QFrame()
        card.setStyleSheet(
            "background-color:#313244; border-radius:14px;"
            "border: 1px solid #45475a;"
        )
        card.setFixedWidth(460)
        c = QVBoxLayout(card)
        c.setContentsMargins(36, 32, 36, 32)
        c.setSpacing(0)

        title = QLabel("Bildklassificering")
        title.setStyleSheet("font-size:24px; font-weight:bold; color:#89b4fa; border:none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c.addWidget(title)

        sub = QLabel("Skapa ett nytt klassificeringstest")
        sub.setStyleSheet("font-size:11px; color:#6c7086; border:none;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c.addWidget(sub)
        c.addSpacing(24)

        lbl_name = QLabel("Namn på testet")
        lbl_name.setStyleSheet("font-size:11px; font-weight:600; color:#a6adc8; border:none;")
        c.addWidget(lbl_name)
        c.addSpacing(4)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("t.ex. Testomgång 1")
        self.name_edit.setFixedHeight(36)
        c.addWidget(self.name_edit)
        c.addSpacing(16)
        c.addSpacing(24)

        go = mk_btn("Gå vidare  →", "#89b4fa", "#1e1e2e", h=40)
        go.clicked.connect(self._validate)
        c.addWidget(go)
        self.name_edit.returnPressed.connect(self._validate)

        sep_line = QFrame()
        sep_line.setFrameShape(QFrame.Shape.HLine)
        sep_line.setStyleSheet("color:#45475a; border:none; border-top:1px solid #45475a;")
        c.addSpacing(12)
        c.addWidget(sep_line)
        c.addSpacing(8)

        load_btn = mk_btn("📊  Öppna Excel-session", "#313244", "#585b70", h=36)
        load_btn.setStyleSheet(
            load_btn.styleSheet() + "border:1px solid #45475a; font-size:11px;"
        )
        load_btn.clicked.connect(self.load_excel.emit)
        c.addWidget(load_btn)

        lay.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch()

    def _validate(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Fel", "Ange ett namn för testet.")
            return
        safe = "".join(ch for ch in name if ch not in r'\/:*?"<>|').strip()
        if not safe:
            QMessageBox.warning(self, "Fel", "Namnet innehåller ogiltiga tecken.")
            return
        self.go_next.emit(safe, DEFAULT_SYFTE)

    def reset(self) -> None:
        self.name_edit.clear()
        self.name_edit.setFocus()

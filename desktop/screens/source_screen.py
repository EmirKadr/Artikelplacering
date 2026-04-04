"""SourceScreen — user chooses between built-in data or CSV upload."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget

from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn


class SourceScreen(QWidget):
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

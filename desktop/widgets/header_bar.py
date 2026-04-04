"""HeaderBar — top bar shown on every screen except the landing screen."""
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel


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

    def set_texts(self, left: str, right: str = "") -> None:
        self._left.setText(left)
        self._right.setText(right)

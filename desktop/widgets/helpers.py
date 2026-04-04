"""Shared Qt helper functions for desktop widgets."""
from PyQt6.QtWidgets import QFrame, QPushButton


def mk_btn(text: str, bg: str = "#4CAF50", fg: str = "white",
           min_w: int = 0, h: int = 0) -> QPushButton:
    b = QPushButton(text)
    style = (f"background-color:{bg}; color:{fg}; border-radius:6px;"
             " padding:8px 16px; font-weight:bold;")
    if min_w:
        style += f" min-width:{min_w}px;"
    b.setStyleSheet(style)
    if h:
        b.setFixedHeight(h)
    return b


def sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("color: #313244;")
    return f

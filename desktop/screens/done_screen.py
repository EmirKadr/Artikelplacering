"""DoneScreen — shown after the AI job finishes, with export and navigation options."""
from collections import Counter
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn


class DoneScreen(QWidget):
    new_test      = pyqtSignal()
    retest_ovrigt = pyqtSignal()
    export_excel  = pyqtSignal()
    resume_job    = pyqtSignal()
    quit_app      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)

    def show_results(self, test_name: str, categories: List[Dict],
                     n_processed: int, has_results: bool,
                     ovrigt_count: int, results: Optional[List[Dict]] = None) -> None:
        # Clear previous content
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        self._lay.addWidget(HeaderBar(test_name))

        center = QWidget()
        c = QVBoxLayout(center)
        c.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setStyleSheet("background-color:#313244; border-radius:12px;")
        card.setFixedWidth(500)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 40, 40, 40)
        cl.setSpacing(8)

        ok_lbl = QLabel("✓  Test avslutat!")
        ok_lbl.setStyleSheet("font-size:28px; font-weight:bold; color:#a6e3a1;")
        ok_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(ok_lbl)

        processed_lbl = QLabel(f"Behandlade bilder: {n_processed}")
        processed_lbl.setStyleSheet("color:#6c7086;")
        processed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(processed_lbl)
        cl.addSpacing(8)

        if results:
            counts = Counter(r.get("category", "Övrigt") for r in results)
            for cat in categories + [{"name": "Övrigt"}]:
                n = counts.get(cat["name"], 0)
                if n:
                    row_lbl = QLabel(f"  {cat['name']}  —  {n} artikel(er)")
                    cl.addWidget(row_lbl)

        cl.addSpacing(12)

        if has_results:
            ex = mk_btn("💾  Exportera Excel", "#1B5E20", h=40)
            ex.clicked.connect(self.export_excel.emit)
            cl.addWidget(ex)

        if ovrigt_count:
            ov = mk_btn(f"Testa Övrigt igen  ({ovrigt_count} bilder)", "#FF9800", h=40)
            ov.clicked.connect(self.retest_ovrigt.emit)
            cl.addWidget(ov)

        resume_b = mk_btn("🔀  Fortsätt redigera i AI-vyn", "#6c7086", "#cdd6f4", h=40)
        resume_b.clicked.connect(self.resume_job.emit)
        cl.addWidget(resume_b)

        cl.addSpacing(4)
        nav = QHBoxLayout()
        nav.setSpacing(8)
        new_b = mk_btn("Nytt test", "#2196F3")
        new_b.clicked.connect(self.new_test.emit)
        quit_b = mk_btn("Avsluta", "#f38ba8", "#1e1e2e")
        quit_b.clicked.connect(self.quit_app.emit)
        nav.addWidget(new_b)
        nav.addWidget(quit_b)
        cl.addLayout(nav)

        c.addWidget(card)
        self._lay.addWidget(center)

"""ArticleOverviewScreen — shows article overview before classification starts."""
import urllib.error
import urllib.request
import logging
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.helpers import mk_btn, sep

_logger = logging.getLogger(__name__)


class _ThumbnailLoader(QThread):
    """Downloads thumbnails in background and emits them as ready."""
    thumb_ready = pyqtSignal(int, QPixmap)  # (row_index, pixmap)

    def __init__(self, rows: List[Dict], parent=None):
        super().__init__(parent)
        self._rows = rows
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        for i, row in enumerate(self._rows):
            if self._stop:
                break
            url = row.get("url", "")
            if not url:
                continue
            try:
                rq = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(rq, timeout=10) as resp:
                    data = resp.read()
                img = QImage()
                img.loadFromData(data)
                del data  # frigör råbytes direkt
                if not img.isNull():
                    img = img.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                    px = QPixmap.fromImage(img)
                    self.thumb_ready.emit(i, px)
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as _e:
                _logger.warning("Thumbnail-hämtning misslyckades för %s: %s", url, _e)


class ArticleOverviewScreen(QWidget):
    """Shows an overview of articles in the selection before classification."""
    go_next = pyqtSignal()
    go_back = pyqtSignal()

    def __init__(self, test_name: str, rows: List[Dict], data_mgr, parent=None):
        super().__init__(parent)
        self._thumb_loader: Optional[_ThumbnailLoader] = None
        self._thumb_labels: Dict[int, QLabel] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(HeaderBar(test_name, f"{len(rows)} artiklar i urvalet"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(40, 24, 40, 24)
        cl.setSpacing(12)

        title = QLabel("Artikelöversikt")
        title.setStyleSheet("font-size:22px; font-weight:bold;")
        cl.addWidget(title)

        subtitle = QLabel(f"{len(rows)} artiklar valda för klassificering")
        subtitle.setStyleSheet("color:#6c7086; font-size:13px;")
        cl.addWidget(subtitle)

        cl.addWidget(sep())

        # ── Summary statistics
        hkat_counts: Dict[str, int] = {}
        bolag_counts: Dict[str, int] = {}
        for r in rows:
            meta = data_mgr.get_meta(str(r["article_number"]), r.get("bolag", "")) if data_mgr else None
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

        # ── Article table
        tbl_label = QLabel("Artiklar")
        tbl_label.setStyleSheet("font-size:14px; font-weight:bold; color:#89b4fa;")
        cl.addWidget(tbl_label)

        # Header row
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet("background:#313244; border-radius:4px;")
        hdr_lay = QHBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(8, 4, 8, 4)
        hdr_lay.setSpacing(8)
        img_hdr = QLabel("Bild")
        img_hdr.setFixedWidth(68)
        img_hdr.setStyleSheet("color:#89b4fa; font-weight:bold; font-size:11px;")
        hdr_lay.addWidget(img_hdr)
        for text, w in [("Artikelnr", 120), ("Beskrivning", 300), ("Huvudkategori", 150), ("Bolag", 100)]:
            lbl = QLabel(text)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet("color:#89b4fa; font-weight:bold; font-size:11px;")
            hdr_lay.addWidget(lbl)
        hdr_lay.addStretch()
        cl.addWidget(hdr_frame)

        # Article rows (show max 200 to avoid slowness)
        display_rows = rows[:200]
        for i, r in enumerate(display_rows):
            art = str(r.get("article_number", ""))
            meta = data_mgr.get_meta(art, r.get("bolag", "")) if data_mgr else None
            meta = meta or {}
            row_frame = QFrame()
            row_frame.setStyleSheet(
                "QFrame { background:transparent; border-bottom:1px solid #313244; }"
                "QFrame:hover { background:#313244; }"
            )
            rl = QHBoxLayout(row_frame)
            rl.setContentsMargins(8, 2, 8, 2)
            rl.setSpacing(8)

            # Thumbnail placeholder
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
            desc_lbl.setFixedWidth(300)
            desc_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
            desc_lbl.setWordWrap(True)
            rl.addWidget(desc_lbl)

            hkat_lbl = QLabel(str(meta.get("huvudkategori", "") or ""))
            hkat_lbl.setFixedWidth(150)
            hkat_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
            rl.addWidget(hkat_lbl)

            bolag_lbl = QLabel(str(r.get("bolag", "") or ""))
            bolag_lbl.setFixedWidth(100)
            bolag_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
            rl.addWidget(bolag_lbl)

            rl.addStretch()
            cl.addWidget(row_frame)

        if len(rows) > 200:
            more = QLabel(f"… och {len(rows) - 200} fler artiklar")
            more.setStyleSheet("color:#6c7086; font-size:11px; font-style:italic;")
            cl.addWidget(more)

        cl.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # ── Button bar
        bar = QFrame()
        bar.setStyleSheet("background:#1e1e2e; border-top:1px solid #313244;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(40, 8, 40, 8)
        back_btn = mk_btn("← Tillbaka", "#45475a", "#cdd6f4")
        back_btn.clicked.connect(self.go_back.emit)
        bar_lay.addWidget(back_btn)
        bar_lay.addStretch()
        start_btn = mk_btn("Starta klassificering  →", "#89b4fa", "#1e1e2e", h=44)
        start_btn.clicked.connect(self.go_next.emit)
        bar_lay.addWidget(start_btn)
        outer.addWidget(bar)

        # Start thumbnail downloads
        self._thumb_loader = _ThumbnailLoader(display_rows)
        self._thumb_loader.thumb_ready.connect(self._on_thumb_ready)
        self._thumb_loader.start()

    def _on_thumb_ready(self, index: int, px: QPixmap):
        lbl = self._thumb_labels.get(index)
        if lbl:
            lbl.setPixmap(px)
            lbl.setText("")

    def cleanup(self):
        if self._thumb_loader and self._thumb_loader.isRunning():
            self._thumb_loader.stop()
            self._thumb_loader.wait(2000)

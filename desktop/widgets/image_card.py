"""ImageCard — draggable thumbnail widget for a single classified article."""
import logging
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QDrag, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from desktop.widgets._constants import CARD_MIME

_logger = logging.getLogger(__name__)

try:
    from PIL import Image as PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


class ImageCard(QFrame):
    """Draggable thumbnail for one AI-classified article."""

    view_image             = pyqtSignal(str, str, str, str)  # (image_path, article_number, category, url)
    ctrl_clicked           = pyqtSignal(object)               # emits self
    shift_clicked          = pyqtSignal(object)               # emits self (Shift+click range select)
    context_menu_requested = pyqtSignal(object)               # emits self

    def __init__(self, article_number: str, image_path: str,
                 category: str, url: str = "",
                 meta: Optional[Dict] = None, reason: str = "", parent=None):
        super().__init__(parent)
        self.article_number = article_number
        self.image_path     = image_path
        self.category       = category
        self.url            = url
        self.reason         = reason
        self._drag_start:   Optional[QPoint] = None
        self._selected:     bool = False

        self.setFixedHeight(120)
        self._normal_style   = "background:#313244; border-radius:6px; border:1px solid #45475a;"
        self._selected_style = "background:#313244; border-radius:6px; border:2px solid #89b4fa;"
        self.setStyleSheet(self._normal_style)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(article_number)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)

        self._img_lbl = QLabel()
        self._img_lbl.setFixedSize(90, 108)
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background:#11111b; border-radius:4px;")
        lay.addWidget(self._img_lbl)

        # info panel
        info_lay = QVBoxLayout()
        info_lay.setContentsMargins(0, 2, 0, 2)
        info_lay.setSpacing(2)

        art_lbl = QLabel(article_number)
        art_lbl.setStyleSheet("color:#cdd6f4; font-size:10px; font-weight:bold;")
        info_lay.addWidget(art_lbl)

        m = meta or {}
        beskr = m.get("beskrivning", "")
        if beskr:
            d_lbl = QLabel(beskr[:70] + ("…" if len(beskr) > 70 else ""))
            d_lbl.setStyleSheet("color:#a6adc8; font-size:9px;")
            d_lbl.setWordWrap(True)
            info_lay.addWidget(d_lbl)

        dims = []
        if m.get("langd"): dims.append(f"L {m['langd']} mm")
        if m.get("bredd"): dims.append(f"B {m['bredd']} mm")
        if m.get("hojd"):  dims.append(f"H {m['hojd']} mm")
        if dims:
            dim_lbl = QLabel("  ".join(dims))
            dim_lbl.setStyleSheet("color:#6c7086; font-size:9px;")
            info_lay.addWidget(dim_lbl)

        wv = []
        if m.get("vikt_brutto"): wv.append(f"Vikt {m['vikt_brutto']} kg")
        if m.get("volym"):       wv.append(f"Vol {m['volym']}")
        if wv:
            wv_lbl = QLabel("  ".join(wv))
            wv_lbl.setStyleSheet("color:#6c7086; font-size:9px;")
            info_lay.addWidget(wv_lbl)

        info_lay.addStretch()
        lay.addLayout(info_lay, 1)

        self._load_thumbnail()

    def update_image(self, new_path: str) -> None:
        self.image_path = new_path
        self._load_thumbnail()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setStyleSheet(self._selected_style if selected else self._normal_style)

    def _load_thumbnail(self) -> None:
        if not self.image_path or not Path(self.image_path).exists():
            self._img_lbl.setText("?")
            return
        try:
            if _PIL_AVAILABLE:
                from io import BytesIO
                img = PILImage.open(self.image_path)
                img.thumbnail((90, 108), PILImage.LANCZOS)
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                px = QPixmap()
                px.loadFromData(buf.read())
            else:
                px = QPixmap(self.image_path)
                px = px.scaled(90, 108,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self._img_lbl.setPixmap(px)
        except Exception as _e:
            _logger.warning("Kunde inte ladda thumbnail för %s: %s", self.image_path, _e)
            self._img_lbl.setText("!")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()

    def mouseMoveEvent(self, event) -> None:
        if (self._drag_start is not None and
                event.buttons() & Qt.MouseButton.LeftButton):
            if (event.pos() - self._drag_start).manhattanLength() > 8:
                self._start_drag()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            if (event.pos() - self._drag_start).manhattanLength() <= 8:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.shift_clicked.emit(self)
                elif event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self.ctrl_clicked.emit(self)
                else:
                    self.view_image.emit(
                        self.image_path, self.article_number, self.category, self.url
                    )
        self._drag_start = None

    def contextMenuEvent(self, event) -> None:
        self.context_menu_requested.emit(self)

    def _start_drag(self) -> None:
        import json
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag = QDrag(self)
        from PyQt6.QtCore import QByteArray, QMimeData
        mime = QMimeData()
        mime.setData(
            CARD_MIME,
            QByteArray(json.dumps({
                "article_number": self.article_number,
                "from_category":  self.category,
                "image_path":     self.image_path,
            }).encode()),
        )
        px = self._img_lbl.pixmap()
        if px and not px.isNull():
            drag.setPixmap(px.scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio))
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start = None

"""_ItemThumbnailLoader — loads a thumbnail for an article card in the background."""
import logging

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

from desktop.widgets._constants import THUMB_W, THUMB_H

_logger = logging.getLogger(__name__)

try:
    from PIL import Image as PILImage
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


class _ItemThumbnailLoader(QThread):
    """Loads a thumbnail image for an article card in the background."""

    done = pyqtSignal(str, QPixmap)  # (article_number, pixmap)

    def __init__(self, article_number: str, image_path: str, parent=None):
        super().__init__(parent)
        self._art_num = article_number
        self._path    = image_path

    def run(self) -> None:
        try:
            if _PIL_AVAILABLE:
                from io import BytesIO
                img = PILImage.open(self._path)
                img.thumbnail((THUMB_W, THUMB_H), PILImage.LANCZOS)
                buf = BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                px = QPixmap()
                px.loadFromData(buf.read())
            else:
                qi = QImage()
                qi.load(self._path)
                qi = qi.scaled(THUMB_W, THUMB_H,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                px = QPixmap.fromImage(qi)
            if not px.isNull():
                self.done.emit(self._art_num, px)
        except Exception as _e:
            _logger.warning("Tumnagelsladdning misslyckades %s: %s", self._path, _e)

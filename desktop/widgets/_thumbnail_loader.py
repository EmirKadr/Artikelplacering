"""_ThumbnailLoader — QThread som laddar ner artikelbilder asynkront."""
import logging
import urllib.error
import urllib.request
from typing import Dict, List

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

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
                del data
                if not img.isNull():
                    img = img.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                    px = QPixmap.fromImage(img)
                    self.thumb_ready.emit(i, px)
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as _e:
                _logger.warning("Thumbnail-hämtning misslyckades för %s: %s", url, _e)

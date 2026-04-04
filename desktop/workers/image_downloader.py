"""ImageDownloader — QThread that downloads article images to a temp directory."""
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

_logger = logging.getLogger(__name__)


class ImageDownloader(QThread):
    """Downloads article images to a local temp directory, one by one."""

    image_ready = pyqtSignal(int, str)  # (index, local_path)

    def __init__(self, rows: List[Dict], temp_dir: str, parent=None):
        super().__init__(parent)
        self.rows     = rows
        self.temp_dir = temp_dir
        self._stop    = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        for i, row in enumerate(self.rows):
            if self._stop:
                break
            dest = self._download(i, row)
            if dest:
                self.image_ready.emit(i, str(dest))

    def _download(self, i: int, row: Dict) -> Optional[Path]:
        url      = row["url"]
        url_path = url.split("?")[0].rstrip("/")
        filename = url_path.split("/")[-1] or f"img_{i + 1}"
        if not Path(filename).suffix:
            filename += ".jpg"
        dest = Path(self.temp_dir) / f"{i:05d}_{filename}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                dest.write_bytes(resp.read())
            return dest
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as _e:
            _logger.warning("Bildnedladdning misslyckades för %s: %s", url, _e)
            return None

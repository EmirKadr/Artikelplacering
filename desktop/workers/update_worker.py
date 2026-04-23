"""Background workers for application updates."""
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.app_info import APP_VERSION
from services.update_service import (
    UpdateInfo,
    check_for_update,
    download_update_installer,
)


class UpdateCheckWorker(QThread):
    update_available = pyqtSignal(object)
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, current_version: str = APP_VERSION, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self):
        try:
            info = check_for_update(current_version=self.current_version)
        except Exception as exc:
            self.error.emit(str(exc))
            return
        if info is None:
            self.no_update.emit()
        else:
            self.update_available.emit(info)


class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int)
    downloaded = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, info: UpdateInfo, target_dir: Path, parent=None):
        super().__init__(parent)
        self.info = info
        self.target_dir = target_dir
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            path = download_update_installer(
                self.info,
                target_dir=self.target_dir,
                progress_cb=self.progress.emit,
                stop_flag=lambda: self._stop,
            )
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.downloaded.emit(str(path))

"""ArticleListView — virtualised list with drag-drop and context menu."""
import json
from typing import Dict, List

from PyQt6.QtCore import QByteArray, QModelIndex, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import QAbstractItemView, QListView

from desktop.widgets._constants import CARD_MIME
from desktop.widgets.article_list_model import ArticleListModel


class ArticleListView(QListView):
    """Virtualised list view with drag-drop and context menu."""

    view_image          = pyqtSignal(str, str, str, str)   # (image_path, art_num, cat, url)
    context_menu_signal = pyqtSignal(list, QPoint)          # (items, global_pos)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context_menu)
        self.doubleClicked.connect(self._on_double_click)
        self.setSpacing(4)
        self.setUniformItemSizes(True)
        self.setStyleSheet(
            "QListView { background:#1e1e2e; border:none; outline:none; }"
            "QListView::item { padding:0; margin:0; }"
            "QListView::item:selected { background:transparent; }"
        )

    def _emit_context_menu(self, pos: QPoint) -> None:
        items = self.selected_items()
        if not items:
            idx = self.indexAt(pos)
            if idx.isValid():
                item = self.model().data(idx, ArticleListModel.DATA_ROLE)
                if item:
                    items = [item]
        if items:
            self.context_menu_signal.emit(items, self.mapToGlobal(pos))

    def _on_double_click(self, index: QModelIndex) -> None:
        item = self.model().data(index, ArticleListModel.DATA_ROLE)
        if item:
            self.view_image.emit(
                item.get("image_path", ""), item.get("article_number", ""),
                item.get("category", ""), item.get("url", "")
            )

    def selected_items(self) -> List[Dict]:
        return [
            self.model().data(idx, ArticleListModel.DATA_ROLE)
            for idx in self.selectedIndexes()
            if self.model().data(idx, ArticleListModel.DATA_ROLE)
        ]

    def startDrag(self, supportedActions) -> None:
        indexes = self.selectedIndexes()
        if not indexes:
            return
        item = self.model().data(indexes[0], ArticleListModel.DATA_ROLE)
        if not item:
            return
        mime_data = __import__("PyQt6.QtCore", fromlist=["QMimeData"]).QMimeData()
        mime_data.setData(
            CARD_MIME,
            QByteArray(json.dumps({
                "article_number": item.get("article_number", ""),
                "from_category":  item.get("category", ""),
                "image_path":     item.get("image_path", ""),
            }).encode())
        )
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        thumb = self.model().data(indexes[0], ArticleListModel.THUMB_ROLE)
        if thumb and not thumb.isNull():
            drag.setPixmap(thumb.scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio))
        drag.exec(supportedActions)

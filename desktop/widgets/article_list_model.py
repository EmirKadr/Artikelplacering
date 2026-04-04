"""ArticleListModel — QAbstractListModel for the virtualised article list."""
from typing import Dict, List, Optional

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt
from PyQt6.QtGui import QPixmap


class ArticleListModel(QAbstractListModel):
    """Model for virtualised article card list — no QWidget per article."""

    THUMB_ROLE = Qt.ItemDataRole.UserRole + 1
    DATA_ROLE  = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Dict] = []
        self._thumbs: Dict[str, QPixmap] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return item.get("article_number", "")
        if role == self.DATA_ROLE:
            return item
        if role == self.THUMB_ROLE:
            return self._thumbs.get(item.get("article_number", ""))
        return None

    def prepend(self, item: Dict) -> None:
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._items.insert(0, item)
        self.endInsertRows()

    def remove_by_article(self, article_number: str) -> Optional[Dict]:
        for i, item in enumerate(self._items):
            if item.get("article_number") == article_number:
                self.beginRemoveRows(QModelIndex(), i, i)
                removed = self._items.pop(i)
                self.endRemoveRows()
                return removed
        return None

    def set_thumbnail(self, article_number: str, pixmap: QPixmap) -> None:
        self._thumbs[article_number] = pixmap
        for i, item in enumerate(self._items):
            if item.get("article_number") == article_number:
                idx = self.index(i)
                self.dataChanged.emit(idx, idx, [self.THUMB_ROLE])
                break

    def update_item(self, article_number: str, **kwargs) -> None:
        for i, item in enumerate(self._items):
            if item.get("article_number") == article_number:
                item.update(kwargs)
                idx = self.index(i)
                self.dataChanged.emit(idx, idx)
                break

    def all_items(self) -> List[Dict]:
        return list(self._items)

    def find(self, article_number: str) -> Optional[Dict]:
        for item in self._items:
            if item.get("article_number") == article_number:
                return item
        return None

    def item_count(self) -> int:
        return len(self._items)

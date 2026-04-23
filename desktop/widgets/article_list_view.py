"""ArticleListView — virtualised list with drag-drop and context menu."""
import json
from typing import Dict, List

from PyQt6.QtCore import QByteArray, QModelIndex, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QFontMetrics, QKeySequence
from PyQt6.QtWidgets import QApplication, QAbstractItemView, QListView

from desktop.widgets._constants import CARD_MIME, THUMB_W
from desktop.widgets.article_list_model import ArticleListModel


class ArticleListView(QListView):
    """Virtualised list view with drag-drop and context menu."""

    view_image          = pyqtSignal(str, str, str, str)   # (image_path, art_num, cat, url)
    context_menu_signal = pyqtSignal(list, QPoint)          # (items, global_pos)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._article_text_selection = None
        self._article_text_dragging = False
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
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

    def article_number_selection_for(self, article_number: str):
        selection = self._article_text_selection
        if not selection or selection["article_number"] != article_number:
            return None
        start, end = selection["anchor"], selection["cursor"]
        if start == end:
            return None
        return start, end

    def selected_article_number_text(self) -> str:
        selection = self._article_text_selection
        if not selection:
            return ""
        article_number = selection["article_number"]
        start, end = sorted((selection["anchor"], selection["cursor"]))
        return article_number[start:end]

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._begin_article_text_selection(event.pos()):
                event.accept()
                return
            self._clear_article_text_selection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (self._article_text_dragging and
                event.buttons() & Qt.MouseButton.LeftButton):
            self._update_article_text_selection(event.pos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._article_text_dragging:
            self._update_article_text_selection(event.pos())
            self._article_text_dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            selected_text = self.selected_article_number_text()
            if selected_text:
                QApplication.clipboard().setText(selected_text)
                event.accept()
                return
        super().keyPressEvent(event)

    def startDrag(self, supportedActions) -> None:
        if self.selected_article_number_text():
            return
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

    def _begin_article_text_selection(self, pos: QPoint) -> bool:
        idx = self.indexAt(pos)
        if not idx.isValid():
            return False
        item = self.model().data(idx, ArticleListModel.DATA_ROLE)
        if not item:
            return False
        art_num = item.get("article_number", "")
        text_rect = self._article_number_rect(idx)
        if not art_num or not text_rect.contains(pos):
            return False

        char_pos = self._char_index_at(art_num, text_rect, pos.x())
        self._article_text_selection = {
            "article_number": art_num,
            "anchor": char_pos,
            "cursor": char_pos,
        }
        self._article_text_dragging = True
        self.setFocus()
        self._update_article_selection_paint(art_num)
        return True

    def _update_article_text_selection(self, pos: QPoint) -> None:
        selection = self._article_text_selection
        if not selection:
            return
        art_num = selection["article_number"]
        idx = self._index_for_article_number(art_num)
        if not idx.isValid():
            return
        text_rect = self._article_number_rect(idx)
        selection["cursor"] = self._char_index_at(art_num, text_rect, pos.x())
        self._update_article_selection_paint(art_num)

    def _clear_article_text_selection(self) -> None:
        selection = self._article_text_selection
        if not selection:
            return
        art_num = selection["article_number"]
        self._article_text_selection = None
        self._article_text_dragging = False
        self._update_article_selection_paint(art_num)

    def _article_number_rect(self, index: QModelIndex) -> QRect:
        item_rect = self.visualRect(index)
        tx = item_rect.left() + THUMB_W + 14
        return QRect(tx, item_rect.top() + 8, max(0, item_rect.right() - tx - 6), 16)

    def _char_index_at(self, text: str, text_rect: QRect, x_pos: int) -> int:
        if x_pos <= text_rect.left():
            return 0
        font = self.font()
        font.setPointSize(9)
        font.setBold(True)
        metrics = QFontMetrics(font)
        rel_x = min(x_pos - text_rect.left(), metrics.horizontalAdvance(text))
        prev_w = 0
        for i, _ch in enumerate(text):
            cur_w = metrics.horizontalAdvance(text[:i + 1])
            if rel_x < prev_w + ((cur_w - prev_w) / 2):
                return i
            prev_w = cur_w
        return len(text)

    def _index_for_article_number(self, article_number: str) -> QModelIndex:
        model = self.model()
        if not model:
            return QModelIndex()
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            item = model.data(idx, ArticleListModel.DATA_ROLE)
            if item and item.get("article_number") == article_number:
                return idx
        return QModelIndex()

    def _update_article_selection_paint(self, article_number: str) -> None:
        idx = self._index_for_article_number(article_number)
        if idx.isValid():
            self.viewport().update(self.visualRect(idx))

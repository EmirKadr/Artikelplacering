"""CategoryColumn — scrollable column for one category in the AI job live view."""
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from PyQt6.QtCore import QByteArray, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from core.constants import MAX_EXAMPLES_PER_CAT
from desktop.widgets._constants import CARD_MIME
from desktop.widgets.article_delegate import ArticleDelegate
from desktop.widgets.article_list_model import ArticleListModel
from desktop.widgets.article_list_view import ArticleListView

if TYPE_CHECKING:
    from desktop.widgets.image_card import ImageCard

_logger = logging.getLogger(__name__)

try:
    from desktop.widgets._item_thumbnail_loader import _ItemThumbnailLoader
    _LOADER_AVAILABLE = True
except ImportError:
    _LOADER_AVAILABLE = False


class CategoryColumn(QFrame):
    """Scrollable column for one category in the AI job live view."""

    card_dropped         = pyqtSignal(str, str, str)   # (article_number, from_cat, to_cat)
    header_clicked       = pyqtSignal(str)              # (category_name)
    threshold_reached    = pyqtSignal(str, int)          # (category_name, count)
    analyze_requested    = pyqtSignal(str)              # (category_name)
    select_all_requested = pyqtSignal(str)              # (category_name)

    def __init__(self, category_name: str, color: str, parent=None):
        super().__init__(parent)
        self.category_name = category_name
        self.setAcceptDrops(True)
        self._normal_style = "background:#1e1e2e; border-right:1px solid #313244;"
        self._hover_style  = (
            "background:#1e1e2e; border-right:1px solid #313244;"
            "border:2px solid #89b4fa;"
        )
        self.setStyleSheet(self._normal_style)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header (clickable)
        header = QFrame()
        header.setFixedHeight(44)
        header.setStyleSheet("background:#181825; border-bottom:1px solid #313244;")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setToolTip("Klicka för att visa/redigera AI-analysen")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 0, 10, 0)
        name_lbl = QLabel(category_name)
        name_lbl.setStyleSheet(f"color:{color}; font-size:12px; font-weight:bold;")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(name_lbl, 1)
        self._count_lbl = QLabel("0")
        self._count_lbl.setStyleSheet("color:#6c7086; font-size:11px;")
        hl.addWidget(self._count_lbl)
        self._knowledge_dot = QLabel("●")
        self._knowledge_dot.setStyleSheet("color:#45475a; font-size:8px;")
        self._knowledge_dot.setToolTip("AI-analys ej klar ännu")
        hl.addWidget(self._knowledge_dot)
        layout.addWidget(header)

        def _header_mouse(e):
            if e.button() == Qt.MouseButton.RightButton:
                self.analyze_requested.emit(self.category_name)
            elif e.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.select_all_requested.emit(self.category_name)
            else:
                self.header_clicked.emit(self.category_name)
        header.mousePressEvent = _header_mouse

        # Virtualised list view
        self._model = ArticleListModel()
        self._view  = ArticleListView()
        self._view.setModel(self._model)
        self._view.setItemDelegate(ArticleDelegate())
        layout.addWidget(self._view, 1)

        self._is_new_category = False
        self._thresholds_emitted: set = set()
        self._name_lbl = name_lbl
        self._thumb_loaders: List = []

    @property
    def _cards(self) -> List[Dict]:
        """Backward-compat: returns all articles as dicts."""
        return self._model.all_items()

    def mark_as_new_category(self) -> None:
        self._is_new_category = True

    def set_name(self, new_name: str, color: str = "") -> None:
        self.category_name = new_name
        style = self._name_lbl.styleSheet()
        if color:
            style = re.sub(r"color:[^;]+;", f"color:{color};", style)
        self._name_lbl.setText(new_name)
        self._name_lbl.setStyleSheet(style)

    def set_knowledge_ready(self) -> None:
        self._knowledge_dot.setStyleSheet("color:#a6e3a1; font-size:8px;")
        self._knowledge_dot.setToolTip("AI-analys klar — klicka för att visa")

    def prepend_item(self, item: Dict) -> None:
        """Add article data at the top (newest first)."""
        self._model.prepend(item)
        n = self._model.item_count()
        self._count_lbl.setText(str(n))
        QTimer.singleShot(30, lambda: self._view.scrollToTop())

        img_path = item.get("image_path", "")
        if _LOADER_AVAILABLE and img_path and Path(img_path).exists():
            from desktop.widgets._item_thumbnail_loader import _ItemThumbnailLoader
            loader = _ItemThumbnailLoader(item["article_number"], img_path, self)
            loader.done.connect(self._model.set_thumbnail)
            loader.finished.connect(
                lambda l=loader: self._thumb_loaders.remove(l) if l in self._thumb_loaders else None
            )
            self._thumb_loaders.append(loader)
            loader.start()

        if self._is_new_category:
            for milestone in (1, 3, MAX_EXAMPLES_PER_CAT):
                if n == milestone and milestone not in self._thresholds_emitted:
                    self._thresholds_emitted.add(milestone)
                    self.threshold_reached.emit(self.category_name, milestone)

    def prepend_card(self, card: "ImageCard") -> None:
        """Backward-compat: extract dict from ImageCard and call prepend_item."""
        item = {
            "article_number": card.article_number,
            "image_path":     card.image_path,
            "category":       card.category,
            "url":            card.url,
            "reason":         getattr(card, "reason", ""),
        }
        self.prepend_item(item)

    def remove_card_by_article(self, article_number: str) -> Optional[Dict]:
        item = self._model.remove_by_article(article_number)
        if item is not None:
            self._count_lbl.setText(str(self._model.item_count()))
        return item

    # ── drag & drop ─────────────────────────────────────────────────────────

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(CARD_MIME):
            data = json.loads(bytes(event.mimeData().data(CARD_MIME)))
            if data.get("from_category") != self.category_name:
                event.acceptProposedAction()
                self.setStyleSheet(self._hover_style)
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setStyleSheet(self._normal_style)

    def dropEvent(self, event) -> None:
        self.setStyleSheet(self._normal_style)
        if event.mimeData().hasFormat(CARD_MIME):
            data = json.loads(bytes(event.mimeData().data(CARD_MIME)))
            from_cat = data.get("from_category", "")
            art_num  = data.get("article_number", "")
            if from_cat != self.category_name and art_num:
                event.acceptProposedAction()
                self.card_dropped.emit(art_num, from_cat, self.category_name)
                return
        event.ignore()

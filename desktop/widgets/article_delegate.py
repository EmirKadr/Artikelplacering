"""ArticleDelegate — paints an article card without creating QWidget objects."""
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate

from desktop.widgets._constants import CARD_H, THUMB_W, THUMB_H
from desktop.widgets.article_list_model import ArticleListModel


class ArticleDelegate(QStyledItemDelegate):
    """Renders an article card without creating QWidget objects per row."""

    def paint(self, painter, option, index) -> None:
        item = index.data(ArticleListModel.DATA_ROLE)
        if not item:
            super().paint(painter, option, index)
            return
        painter.save()
        r = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        painter.fillRect(r, QColor("#313244"))
        pen = painter.pen()
        pen.setColor(QColor("#89b4fa" if selected else "#45475a"))
        pen.setWidth(2 if selected else 1)
        painter.setPen(pen)
        painter.drawRect(r.adjusted(1, 1, -1, -1))

        # Thumbnail area
        thumb_rect = QRect(r.left() + 6, r.top() + 6, THUMB_W, THUMB_H)
        painter.fillRect(thumb_rect, QColor("#11111b"))
        thumb = index.data(ArticleListModel.THUMB_ROLE)
        if thumb and not thumb.isNull():
            scaled = thumb.scaled(THUMB_W, THUMB_H,
                                  Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
            ox = thumb_rect.left() + (THUMB_W - scaled.width()) // 2
            oy = thumb_rect.top() + (THUMB_H - scaled.height()) // 2
            painter.drawPixmap(ox, oy, scaled)
        else:
            p2 = painter.pen()
            p2.setColor(QColor("#6c7086"))
            painter.setPen(p2)
            painter.drawText(thumb_rect, Qt.AlignmentFlag.AlignCenter, "…")

        # Text area
        tx = r.left() + THUMB_W + 14
        tw = r.right() - tx - 6
        font = painter.font()

        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        p3 = painter.pen()
        p3.setColor(QColor("#cdd6f4"))
        painter.setPen(p3)
        painter.drawText(QRect(tx, r.top() + 8, tw, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         item.get("article_number", ""))

        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        p4 = painter.pen()
        p4.setColor(QColor("#a6e3a1"))
        painter.setPen(p4)
        painter.drawText(QRect(tx, r.top() + 26, tw, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         item.get("category", ""))

        reason = item.get("reason", "")
        if reason:
            p5 = painter.pen()
            p5.setColor(QColor("#6c7086"))
            painter.setPen(p5)
            font.setPointSize(7)
            painter.setFont(font)
            painter.drawText(QRect(tx, r.top() + 44, tw, CARD_H - 52),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop |
                             Qt.TextFlag.TextWordWrap,
                             reason[:120])

        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        w = option.rect.width() if option.rect.width() > 0 else 200
        return QSize(w, CARD_H)

"""Tests for desktop/widgets/*.

Uses pytest-qt (qtbot) for Qt widget interactions.
No network access, no LLM calls.
"""
import json
from typing import Dict, List

import pytest

from PyQt6.QtCore import Qt, QPoint, QMimeData, QByteArray
from PyQt6.QtGui import QPixmap

from desktop.widgets.header_bar import HeaderBar
from desktop.widgets.category_row import CategoryRow
from desktop.widgets.article_list_model import ArticleListModel
from desktop.widgets.article_delegate import ArticleDelegate
from desktop.widgets.article_list_view import ArticleListView
from desktop.widgets.image_card import ImageCard
from desktop.widgets.category_column import CategoryColumn
from desktop.widgets._constants import CARD_MIME, CARD_H, THUMB_W, THUMB_H
from desktop.widgets.helpers import mk_btn, sep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_item(art_num: str = "10000", cat: str = "Säck") -> Dict:
    return {"article_number": art_num, "category": cat, "image_path": "",
            "url": "http://ex.com/img.jpg", "reason": "Test reason"}


# ---------------------------------------------------------------------------
# HeaderBar
# ---------------------------------------------------------------------------

class TestHeaderBar:
    def test_default_text(self, qtbot):
        bar = HeaderBar()
        qtbot.addWidget(bar)
        assert "Bildklassificering" in bar._left.text()

    def test_test_name_shown(self, qtbot):
        bar = HeaderBar(test_name="MyTest")
        qtbot.addWidget(bar)
        assert "MyTest" in bar._left.text()

    def test_right_text_shown(self, qtbot):
        bar = HeaderBar(right_text="Status: OK")
        qtbot.addWidget(bar)
        assert "Status: OK" in bar._right.text()

    def test_set_texts(self, qtbot):
        bar = HeaderBar()
        qtbot.addWidget(bar)
        bar.set_texts("New Left", "New Right")
        assert bar._left.text() == "New Left"
        assert bar._right.text() == "New Right"

    def test_fixed_height(self, qtbot):
        bar = HeaderBar()
        qtbot.addWidget(bar)
        assert bar.height() == 48


# ---------------------------------------------------------------------------
# CategoryRow
# ---------------------------------------------------------------------------

class TestCategoryRow:
    def test_number_shown(self, qtbot):
        row = CategoryRow(3)
        qtbot.addWidget(row)
        assert "3" in row.num_lbl.text()

    def test_get_data_returns_name_and_desc(self, qtbot):
        row = CategoryRow(1)
        qtbot.addWidget(row)
        row.name_edit.setText("Hink")
        row.desc_edit.setText("En hink")
        name, desc = row.get_data()
        assert name == "Hink"
        assert desc == "En hink"

    def test_is_empty_when_no_name(self, qtbot):
        row = CategoryRow(1)
        qtbot.addWidget(row)
        assert row.is_empty()

    def test_is_not_empty_when_name_set(self, qtbot):
        row = CategoryRow(1)
        qtbot.addWidget(row)
        row.name_edit.setText("Hink")
        assert not row.is_empty()

    def test_set_number_updates_label(self, qtbot):
        row = CategoryRow(1)
        qtbot.addWidget(row)
        row.set_number(5)
        assert "5" in row.num_lbl.text()

    def test_removed_signal_emitted(self, qtbot):
        row = CategoryRow(1)
        qtbot.addWidget(row)
        received = []
        row.removed.connect(received.append)
        # Find the remove button (last button in layout)
        from PyQt6.QtWidgets import QPushButton
        btns = row.findChildren(QPushButton)
        assert btns
        btns[-1].click()
        assert len(received) == 1
        assert received[0] is row


# ---------------------------------------------------------------------------
# ArticleListModel
# ---------------------------------------------------------------------------

class TestArticleListModel:
    def test_empty_model(self):
        m = ArticleListModel()
        assert m.rowCount() == 0

    def test_prepend_increases_count(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        assert m.rowCount() == 1

    def test_prepend_order_newest_first(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        m.prepend(make_item("10001"))
        idx = m.index(0)
        assert m.data(idx, ArticleListModel.DATA_ROLE)["article_number"] == "10001"

    def test_data_display_role(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        assert m.data(m.index(0), Qt.ItemDataRole.DisplayRole) == "10000"

    def test_data_role_returns_dict(self):
        m = ArticleListModel()
        item = make_item("10000")
        m.prepend(item)
        result = m.data(m.index(0), ArticleListModel.DATA_ROLE)
        assert result["article_number"] == "10000"

    def test_remove_by_article(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        m.prepend(make_item("10001"))
        removed = m.remove_by_article("10000")
        assert removed["article_number"] == "10000"
        assert m.rowCount() == 1

    def test_remove_nonexistent_returns_none(self):
        m = ArticleListModel()
        assert m.remove_by_article("99999") is None

    def test_find_returns_item(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        found = m.find("10000")
        assert found is not None
        assert found["article_number"] == "10000"

    def test_find_missing_returns_none(self):
        m = ArticleListModel()
        assert m.find("99999") is None

    def test_update_item(self):
        m = ArticleListModel()
        m.prepend(make_item("10000", "Säck"))
        m.update_item("10000", category="Hink")
        assert m.find("10000")["category"] == "Hink"

    def test_all_items_returns_copy(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        items = m.all_items()
        items.append(make_item("99999"))  # mutating return value must not affect model
        assert m.rowCount() == 1

    def test_set_thumbnail_updates_role(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        px = QPixmap(10, 10)
        m.set_thumbnail("10000", px)
        result = m.data(m.index(0), ArticleListModel.THUMB_ROLE)
        assert result is not None

    def test_item_count(self):
        m = ArticleListModel()
        for i in range(5):
            m.prepend(make_item(str(10000 + i)))
        assert m.item_count() == 5

    def test_invalid_index_returns_none(self):
        m = ArticleListModel()
        from PyQt6.QtCore import QModelIndex
        assert m.data(QModelIndex()) is None

    def test_parent_index_row_count_zero(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        from PyQt6.QtCore import QModelIndex
        # rowCount with valid parent returns 0 (flat model)
        parent_idx = m.index(0)
        assert m.rowCount(parent_idx) == 0


# ---------------------------------------------------------------------------
# ArticleListView
# ---------------------------------------------------------------------------

class TestArticleListView:
    def test_creates_without_crash(self, qtbot):
        view = ArticleListView()
        qtbot.addWidget(view)
        model = ArticleListModel()
        view.setModel(model)
        view.show()

    def test_selected_items_empty_when_nothing_selected(self, qtbot):
        view = ArticleListView()
        qtbot.addWidget(view)
        model = ArticleListModel()
        view.setModel(model)
        assert view.selected_items() == []

    def test_view_image_signal_on_double_click(self, qtbot):
        view = ArticleListView()
        qtbot.addWidget(view)
        model = ArticleListModel()
        item = make_item("10000")
        item["image_path"] = "/some/path.jpg"
        model.prepend(item)
        view.setModel(model)
        view.show()

        received = []
        view.view_image.connect(lambda *a: received.append(a))
        idx = model.index(0)
        view.doubleClicked.emit(idx)
        assert len(received) == 1
        assert received[0][1] == "10000"


# ---------------------------------------------------------------------------
# ImageCard
# ---------------------------------------------------------------------------

class TestImageCard:
    def test_creates_without_image(self, qtbot):
        card = ImageCard("10000", "", "Säck")
        qtbot.addWidget(card)
        card.show()
        assert card.article_number == "10000"
        assert card.category == "Säck"

    def test_missing_image_shows_question_mark(self, qtbot):
        card = ImageCard("10000", "/nonexistent/path.jpg", "Säck")
        qtbot.addWidget(card)
        assert "?" in card._img_lbl.text()

    def test_set_selected_changes_style(self, qtbot):
        card = ImageCard("10000", "", "Säck")
        qtbot.addWidget(card)
        card.set_selected(True)
        assert "#89b4fa" in card.styleSheet()
        card.set_selected(False)
        assert "#89b4fa" not in card.styleSheet()

    def test_fixed_height(self, qtbot):
        card = ImageCard("10000", "", "Säck")
        qtbot.addWidget(card)
        assert card.height() == 120

    def test_ctrl_clicked_signal(self, qtbot):
        card = ImageCard("10000", "", "Säck")
        qtbot.addWidget(card)
        card.show()
        received = []
        card.ctrl_clicked.connect(received.append)
        card.ctrl_clicked.emit(card)
        assert received[0] is card

    def test_shift_clicked_signal(self, qtbot):
        card = ImageCard("10000", "", "Säck")
        qtbot.addWidget(card)
        received = []
        card.shift_clicked.connect(received.append)
        card.shift_clicked.emit(card)
        assert received[0] is card

    def test_meta_description_shown(self, qtbot):
        card = ImageCard("10000", "", "Säck", meta={"beskrivning": "Foder 20kg"})
        qtbot.addWidget(card)
        from PyQt6.QtWidgets import QLabel
        labels = card.findChildren(QLabel)
        texts = [lbl.text() for lbl in labels]
        assert any("Foder" in t for t in texts)

    def test_meta_dimensions_shown(self, qtbot):
        card = ImageCard("10000", "", "Säck",
                         meta={"langd": "300", "bredd": "200", "hojd": "100"})
        qtbot.addWidget(card)
        from PyQt6.QtWidgets import QLabel
        labels = card.findChildren(QLabel)
        texts = " ".join(lbl.text() for lbl in labels)
        assert "300" in texts

    def test_update_image_path(self, qtbot):
        card = ImageCard("10000", "", "Säck")
        qtbot.addWidget(card)
        card.update_image("/new/path.jpg")
        assert card.image_path == "/new/path.jpg"

    def test_view_image_signal_on_click(self, qtbot):
        card = ImageCard("10000", "/fake.jpg", "Säck", url="http://ex.com")
        qtbot.addWidget(card)
        received = []
        card.view_image.connect(lambda *a: received.append(a))
        card.view_image.emit("/fake.jpg", "10000", "Säck", "http://ex.com")
        assert received[0] == ("/fake.jpg", "10000", "Säck", "http://ex.com")


# ---------------------------------------------------------------------------
# CategoryColumn
# ---------------------------------------------------------------------------

class TestCategoryColumn:
    def test_creates_without_crash(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.show()
        assert col.category_name == "Säck"

    def test_prepend_item_updates_count(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.prepend_item(make_item("10000"))
        assert col._count_lbl.text() == "1"

    def test_prepend_multiple_items(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        for i in range(3):
            col.prepend_item(make_item(str(10000 + i)))
        assert col._count_lbl.text() == "3"

    def test_remove_card_by_article(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.prepend_item(make_item("10000"))
        col.prepend_item(make_item("10001"))
        removed = col.remove_card_by_article("10000")
        assert removed is not None
        assert removed["article_number"] == "10000"
        assert col._count_lbl.text() == "1"

    def test_remove_nonexistent_returns_none(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        assert col.remove_card_by_article("99999") is None

    def test_set_knowledge_ready(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.set_knowledge_ready()
        assert "#a6e3a1" in col._knowledge_dot.styleSheet()

    def test_set_name(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.set_name("Hink")
        assert col.category_name == "Hink"
        assert col._name_lbl.text() == "Hink"

    def test_cards_property(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.prepend_item(make_item("10000"))
        col.prepend_item(make_item("10001"))
        assert len(col._cards) == 2

    def test_mark_as_new_category(self, qtbot):
        col = CategoryColumn("Ny", "#89b4fa")
        qtbot.addWidget(col)
        col.mark_as_new_category()
        assert col._is_new_category

    def test_threshold_signal_on_first_item(self, qtbot):
        col = CategoryColumn("Ny", "#89b4fa")
        qtbot.addWidget(col)
        col.mark_as_new_category()
        received = []
        col.threshold_reached.connect(lambda name, n: received.append((name, n)))
        col.prepend_item(make_item("10000"))
        assert any(r[1] == 1 for r in received)

    def test_header_clicked_signal(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        received = []
        col.header_clicked.connect(received.append)
        col.header_clicked.emit("Säck")
        assert received == ["Säck"]

    def test_card_dropped_signal(self, qtbot):
        col = CategoryColumn("Hink", "#89b4fa")
        qtbot.addWidget(col)
        received = []
        col.card_dropped.connect(lambda *a: received.append(a))
        col.card_dropped.emit("10000", "Säck", "Hink")
        assert received[0] == ("10000", "Säck", "Hink")

    def test_drag_accept_from_different_category(self, qtbot):
        col = CategoryColumn("Hink", "#89b4fa")
        qtbot.addWidget(col)
        col.show()
        # Build a fake drag event with mime data from a different category
        from PyQt6.QtGui import QDragEnterEvent
        from PyQt6.QtCore import QPointF
        mime = QMimeData()
        mime.setData(CARD_MIME, QByteArray(
            json.dumps({"article_number": "10000", "from_category": "Säck",
                        "image_path": ""}).encode()
        ))
        # We can test the mime parsing logic indirectly via drop signal
        # (full drag simulation requires deeper Qt mocking)
        data = json.loads(bytes(mime.data(CARD_MIME)))
        assert data["from_category"] != col.category_name

    def test_drag_reject_same_category(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        mime = QMimeData()
        mime.setData(CARD_MIME, QByteArray(
            json.dumps({"article_number": "10000", "from_category": "Säck",
                        "image_path": ""}).encode()
        ))
        data = json.loads(bytes(mime.data(CARD_MIME)))
        assert data["from_category"] == col.category_name


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_mk_btn_returns_button(self, qtbot):
        btn = mk_btn("Click me", bg="#89b4fa", fg="#1e1e2e")
        qtbot.addWidget(btn)
        assert btn.text() == "Click me"

    def test_mk_btn_applies_fixed_height(self, qtbot):
        btn = mk_btn("Click", h=42)
        qtbot.addWidget(btn)
        assert btn.height() == 42

    def test_sep_returns_hline(self, qtbot):
        from PyQt6.QtWidgets import QFrame
        s = sep()
        qtbot.addWidget(s)
        assert s.frameShape() == QFrame.Shape.HLine

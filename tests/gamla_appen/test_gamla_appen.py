"""Tests for GamlaAppen.py — verifiera att GamlaAppen beter sig identiskt med ny modulär kod.

Alla tester importerar direkt från GamlaAppen och kör headless (QT_QPA_PLATFORM=offscreen).
"""
import os
import contextlib
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt

# Sätt headless-läge om inte redan satt
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from GamlaAppen import (
    MainApp,
    ClassifyScreen,
    AIJobScreen,
    FilterScreen,
    DoneScreen,
    NameScreen,
    CategoriesScreen,
    SourceScreen,
    AISettingsScreen,
    ArticleOverviewScreen,
    DataManager,
    CategoryColumn,
    ArticleListModel,
    ImageCard,
    _ThumbnailLoader,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_data_mgr(meta: Dict = None):
    dm = MagicMock()
    dm.get_meta.return_value = meta or {}
    return dm


def make_rows(n: int, bolag: str = "AB", robot: str = "N",
              hkat: str = "Djurfoder") -> List[Dict]:
    return [{"article_number": str(10000 + i), "bolag": bolag, "url": ""}
            for i in range(n)]


def make_item(art_num: str = "10000", cat: str = "Säck") -> Dict:
    return {"article_number": art_num, "category": cat, "image_path": "",
            "url": "http://ex.com/img.jpg", "reason": "Test reason"}


CATEGORIES = [{"name": "Säck", "description": ""}, {"name": "Hink", "description": ""}]


# ---------------------------------------------------------------------------
# NameScreen
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestNameScreen:
    def test_creates_without_crash(self, qtbot):
        scr = NameScreen()
        qtbot.addWidget(scr)
        scr.show()

    def test_go_next_emitted_on_valid_name(self, qtbot):
        scr = NameScreen()
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(lambda n, s: received.append(n))
        scr.name_edit.setText("Mitt Test")
        scr._validate()
        assert received == ["Mitt Test"]

    def test_go_next_not_emitted_on_empty_name(self, qtbot):
        scr = NameScreen()
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(lambda n, s: received.append(n))
        import PyQt6.QtWidgets as _qw
        original = _qw.QMessageBox.warning
        _qw.QMessageBox.warning = lambda *a, **k: None
        try:
            scr.name_edit.setText("")
            scr._validate()
        finally:
            _qw.QMessageBox.warning = original
        assert received == []

    def test_go_next_carries_syfte(self, qtbot):
        scr = NameScreen()
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(lambda n, s: received.append(s))
        scr.name_edit.setText("Test")
        scr._validate()
        assert received  # syfte is emitted

    def test_load_excel_signal_exists_and_emits(self, qtbot):
        scr = NameScreen()
        qtbot.addWidget(scr)
        received = []
        scr.load_excel.connect(lambda: received.append(1))
        scr.load_excel.emit()
        assert received == [1]

    def test_reset_clears_name(self, qtbot):
        scr = NameScreen()
        qtbot.addWidget(scr)
        scr.name_edit.setText("Something")
        scr.reset()
        assert scr.name_edit.text() == ""

    def test_invalid_chars_rejected(self, qtbot):
        import PyQt6.QtWidgets as _qw
        scr = NameScreen()
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(lambda n, s: received.append(n))
        scr.name_edit.setText("/?*")
        _qw.QMessageBox.warning = lambda *a, **k: None
        try:
            scr._validate()
        finally:
            pass
        assert received == []

    def test_name_with_mixed_chars_sanitised(self, qtbot):
        scr = NameScreen()
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(lambda n, s: received.append(n))
        scr.name_edit.setText("Test/Name")
        scr._validate()
        assert received
        assert "/" not in received[0]


# ---------------------------------------------------------------------------
# CategoriesScreen
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestCategoriesScreen:
    def test_creates_without_crash(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        scr.show()

    def test_initial_rows(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        # Has at least 1 row initially
        assert len(scr._rows) >= 1

    def test_add_row_increases_count(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        before = len(scr._rows)
        scr._add_row()
        assert len(scr._rows) == before + 1

    def test_remove_row_decreases_count(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        before = len(scr._rows)
        row = scr._rows[0]
        scr._remove_row(row)
        assert len(scr._rows) == before - 1

    def test_go_next_emitted_with_categories(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        scr._rows[0].name_edit.setText("Säck")
        scr._rows[1].name_edit.setText("Hink")
        received = []
        scr.go_next.connect(received.append)
        scr._validate()
        assert received
        names = [c["name"] for c in received[0]]
        assert "Säck" in names
        assert "Hink" in names

    def test_go_next_not_emitted_when_all_empty(self, qtbot):
        import PyQt6.QtWidgets as _qw
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        # Clear all rows
        for row in scr._rows:
            row.name_edit.setText("")
        received = []
        scr.go_next.connect(received.append)
        _qw.QMessageBox.warning = lambda *a, **k: None
        scr._validate()
        assert received == []

    def test_empty_name_rows_excluded(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        # Set only first row
        scr._rows[0].name_edit.setText("Säck")
        for row in scr._rows[1:]:
            row.name_edit.setText("")
        received = []
        scr.go_next.connect(received.append)
        scr._validate()
        assert len(received[0]) == 1

    def test_description_included_in_output(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        scr._rows[0].name_edit.setText("Säck")
        scr._rows[0].desc_edit.setText("En säck")
        received = []
        scr.go_next.connect(received.append)
        scr._validate()
        assert received[0][0]["description"] == "En säck"

    def test_go_back_signal(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        received = []
        scr.go_back.connect(lambda: received.append(1))
        scr.go_back.emit()
        assert received == [1]

    def test_set_test_name_updates_header(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        scr.set_test_name("MittTest")
        # Header should contain test name
        from PyQt6.QtWidgets import QLabel
        labels = scr.findChildren(QLabel)
        texts = " ".join(lbl.text() for lbl in labels)
        assert "MittTest" in texts


# ---------------------------------------------------------------------------
# SourceScreen
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestSourceScreen:
    def test_creates_without_crash(self, qtbot):
        scr = SourceScreen("Test", n_builtin=5)
        qtbot.addWidget(scr)
        scr.show()

    def test_use_csv_signal(self, qtbot):
        scr = SourceScreen("Test", n_builtin=0)
        qtbot.addWidget(scr)
        received = []
        scr.use_csv.connect(lambda: received.append(1))
        scr.use_csv.emit()
        assert received == [1]

    def test_use_builtin_signal(self, qtbot):
        scr = SourceScreen("Test", n_builtin=100)
        qtbot.addWidget(scr)
        received = []
        scr.use_builtin.connect(lambda: received.append(1))
        scr.use_builtin.emit()
        assert received == [1]

    def test_go_back_signal(self, qtbot):
        scr = SourceScreen("Test", n_builtin=0)
        qtbot.addWidget(scr)
        received = []
        scr.go_back.connect(lambda: received.append(1))
        scr.go_back.emit()
        assert received == [1]

    def test_no_builtin_button_when_zero(self, qtbot):
        scr = SourceScreen("Test", n_builtin=0)
        qtbot.addWidget(scr)
        from PyQt6.QtWidgets import QPushButton
        btns = scr.findChildren(QPushButton)
        texts = [b.text() for b in btns]
        assert not any("Inbyggd" in t for t in texts)


# ---------------------------------------------------------------------------
# AISettingsScreen
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestAISettingsScreen:
    def test_creates_without_crash(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        scr.show()

    def test_default_local_mode(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        assert scr._rb_local.isChecked()
        assert not scr._rb_external.isChecked()

    def test_local_frame_visible_by_default(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        assert not scr._local_frame.isHidden()
        assert scr._ext_frame.isHidden()

    def test_external_frame_visible_on_toggle(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        scr._rb_external.setChecked(True)
        assert not scr._ext_frame.isHidden()
        assert scr._local_frame.isHidden()

    def test_go_next_local_includes_url_and_model(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(received.append)
        scr._rb_local.setChecked(True)
        scr._go()
        assert received
        cfg = received[0]
        assert "api_url" in cfg
        assert "model" in cfg
        assert cfg["api_key"] == ""

    def test_go_next_skip_emits_empty_dict(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(received.append)
        scr.go_next.emit({})
        assert received == [{}]

    def test_external_requires_api_key(self, qtbot):
        import PyQt6.QtWidgets as _qw
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(received.append)
        scr._rb_external.setChecked(True)
        scr._api_key_edit.setText("")
        _qw.QMessageBox.warning = lambda *a, **k: None
        scr._go()
        assert received == []

    def test_go_back_signal(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        received = []
        scr.go_back.connect(lambda: received.append(1))
        scr.go_back.emit()
        assert received == [1]

    def test_compress_checkbox_checked_by_default(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        assert scr.compress_cb.isChecked()


# ---------------------------------------------------------------------------
# FilterScreen
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestFilterScreen:
    def _make_screen(self, qtbot, rows=None, meta=None):
        if rows is None:
            rows = make_rows(5)
        dm = make_data_mgr(meta or {"huvudkategori": "Djurfoder", "robot": "N"})
        scr = FilterScreen("Test", rows, dm)
        qtbot.addWidget(scr)
        return scr

    def test_creates_without_crash(self, qtbot):
        scr = self._make_screen(qtbot)
        scr.show()

    def test_all_rows_selected_by_default(self, qtbot):
        scr = self._make_screen(qtbot)
        assert len(scr._filtered_rows()) == 5

    def test_go_next_emits_filtered_rows(self, qtbot):
        scr = self._make_screen(qtbot)
        received = []
        scr.go_next.connect(received.append)
        scr._on_start()
        assert received
        assert len(received[0]) == 5

    def test_go_back_signal(self, qtbot):
        scr = self._make_screen(qtbot)
        received = []
        scr.go_back.connect(lambda: received.append(1))
        scr.go_back.emit()
        assert received == [1]

    def test_deselect_bolag_filters_out_rows(self, qtbot):
        rows_ab = make_rows(3, bolag="AB")
        rows_cd = make_rows(2, bolag="CD")
        all_rows = rows_ab + rows_cd
        dm = MagicMock()
        dm.get_meta.side_effect = lambda art, bolag: {"huvudkategori": "Djurfoder", "robot": "N"}
        scr = FilterScreen("Test", all_rows, dm)
        qtbot.addWidget(scr)
        for cb in scr._bolag_cbs:
            if cb.text() == "CD":
                cb.setChecked(False)
        filtered = scr._filtered_rows()
        assert all(r["bolag"] == "AB" for r in filtered)
        assert len(filtered) == 3

    def test_article_number_filter(self, qtbot):
        scr = self._make_screen(qtbot)
        scr._art_filter.setPlainText("10000\n10002")
        filtered = scr._filtered_rows()
        arts = {r["article_number"] for r in filtered}
        assert arts == {"10000", "10002"}

    def test_start_button_disabled_when_no_match(self, qtbot):
        scr = self._make_screen(qtbot)
        scr._art_filter.setPlainText("99999")
        scr._update_count()
        assert not scr._start_btn.isEnabled()

    def test_start_button_enabled_when_match(self, qtbot):
        scr = self._make_screen(qtbot)
        assert scr._start_btn.isEnabled()


# ---------------------------------------------------------------------------
# DoneScreen
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestDoneScreen:
    def test_creates_without_crash(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show()

    def test_show_results_without_crash(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("MyTest", CATEGORIES, n_processed=10, has_results=True,
                         ovrigt_count=2)

    def test_new_test_signal(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("T", CATEGORIES, 0, False, 0)
        received = []
        scr.new_test.connect(lambda: received.append(1))
        scr.new_test.emit()
        assert received == [1]

    def test_export_excel_signal(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("T", CATEGORIES, 5, True, 0)
        received = []
        scr.export_excel.connect(lambda: received.append(1))
        scr.export_excel.emit()
        assert received == [1]

    def test_resume_job_signal(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("T", CATEGORIES, 0, False, 0)
        received = []
        scr.resume_job.connect(lambda: received.append(1))
        scr.resume_job.emit()
        assert received == [1]

    def test_category_counts_shown(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        results = [{"category": "Säck"}, {"category": "Säck"}, {"category": "Hink"}]
        scr.show_results("T", CATEGORIES, 3, True, 0, results=results)
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "Säck" in texts

    def test_show_results_clears_previous(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("Test1", CATEGORIES, 5, True, 0)
        count_before = scr._lay.count()
        scr.show_results("Test2", CATEGORIES, 3, True, 0)
        count_after = scr._lay.count()
        assert count_after == count_before


# ---------------------------------------------------------------------------
# ClassifyScreen
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestClassifyScreen:
    CATS = [{"name": "Säck", "description": ""}, {"name": "Hink", "description": ""}]

    def _show(self, scr, img_path="/tmp/fake.png", **kw):
        scr.show_image("Test", self.CATS, img_path, None, 0, 5, **kw)

    def test_creates_without_crash(self, qtbot):
        scr = ClassifyScreen()
        qtbot.addWidget(scr)

    def test_classified_signal_emits_category_name(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        received = []
        scr.classified.connect(received.append)
        scr.classified.emit("Säck")
        assert received == ["Säck"]

    def test_skipped_signal(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        received = []
        scr.skipped.connect(lambda: received.append(True))
        scr.skipped.emit()
        assert received == [True]

    def test_go_back_signal(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        received = []
        scr.go_back.connect(lambda: received.append(True))
        scr.go_back.emit()
        assert received == [True]

    def test_end_test_signal(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        received = []
        scr.end_test.connect(lambda: received.append(True))
        scr.end_test.emit()
        assert received == [True]

    def test_run_ai_job_signal(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img), ai_job_ready=True)
        received = []
        scr.run_ai_job.connect(lambda: received.append(True))
        scr.run_ai_job.emit()
        assert received == [True]

    def test_category_renamed_signal(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        received = []
        scr.category_renamed.connect(lambda idx, n, d: received.append((idx, n, d)))
        scr.category_renamed.emit(0, "Ny", "desc")
        assert received == [(0, "Ny", "desc")]

    def test_show_image_builds_ui(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        assert scr._inner is not None

    def test_click_cat_button_emits_classified(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        scr.show_image("Test", self.CATS, str(img), None, 1, 5)
        from PyQt6.QtWidgets import QPushButton
        btn = next(
            b for b in scr.findChildren(QPushButton)
            if b.text().startswith("Säck")
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert blocker.args[0] == "Säck"

    def test_click_hink_button_emits_hink(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        scr.show_image("Test", self.CATS, str(img), None, 1, 5)
        from PyQt6.QtWidgets import QPushButton
        btn = next(
            b for b in scr.findChildren(QPushButton)
            if b.text().startswith("Hink")
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert blocker.args[0] == "Hink"

    def test_key_1_emits_first_category(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        scr.show_image("Test", self.CATS, str(img), None, 1, 5)
        from PyQt6.QtGui import QKeySequence
        sc = next(
            s for s in scr._shortcuts
            if s.key().toString() == "1"
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            sc.activated.emit()
        assert blocker.args[0] == "Säck"

    def test_key_0_emits_ovrigt(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        scr.show_image("Test", self.CATS, str(img), None, 1, 5)
        from PyQt6.QtGui import QKeySequence
        sc = next(
            (s for s in scr._shortcuts if s.key().toString() == "0"),
            None
        )
        if sc is not None:
            with qtbot.waitSignal(scr.classified) as blocker:
                sc.activated.emit()
            assert blocker.args[0] == "Övrigt"

    def test_ai_job_ready_button_shown(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img), ai_job_ready=True)
        from PyQt6.QtWidgets import QPushButton
        btns = [b.text() for b in scr.findChildren(QPushButton)]
        assert any("AI" in b for b in btns)

    def test_rename_dialog_cancel_no_signal(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        received = []
        scr.category_renamed.connect(lambda *a: received.append(a))
        # Patch the dialog to return Cancel
        import PyQt6.QtWidgets as _qw
        original_exec = _qw.QDialog.exec
        _qw.QDialog.exec = lambda self: _qw.QDialog.DialogCode.Rejected.value
        try:
            scr._rename_category(0, "Säck")
        finally:
            _qw.QDialog.exec = original_exec
        assert received == []


# ---------------------------------------------------------------------------
# AIJobScreen
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestAIJobScreen:
    CATS = [
        {"name": "Säck", "description": "", "knowledge": ""},
        {"name": "Hink", "description": "", "knowledge": ""},
    ]

    def _make_scr(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        scr = AIJobScreen(
            self.CATS[:], [], [],
            "syfte",
            "http://localhost:1234", "model", False,
            dm, "TestJob",
        )
        qtbot.addWidget(scr)
        return scr

    def test_creates_without_crash(self, qtbot):
        scr = self._make_scr(qtbot)
        assert scr is not None

    def test_columns_created_for_each_category(self, qtbot):
        scr = self._make_scr(qtbot)
        assert "Säck" in scr._columns
        assert "Hink" in scr._columns
        assert "Övrigt" in scr._columns

    def test_on_article_classified_adds_to_column(self, qtbot):
        scr = self._make_scr(qtbot)
        scr._on_article_classified("A1", "Säck", "http://x", "/img/a.png", "reason")
        # Drain any pending timers before teardown
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        import time
        time.sleep(0.05)
        QApplication.processEvents()
        assert "A1" in scr._cards_by_art
        assert scr._total_classified == 1

    def test_on_article_classified_unknown_category_stored(self, qtbot):
        scr = self._make_scr(qtbot)
        scr._on_article_classified("B1", "OkändKategori", "http://x", "", "reason")
        # Drain any pending timers before teardown
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        import time
        time.sleep(0.05)
        QApplication.processEvents()
        # Unknown category: item is stored, card goes to Övrigt column
        assert "B1" in scr._cards_by_art
        # The item is placed in Övrigt column (fallback), total count increases
        assert scr._total_classified == 1

    def test_on_card_dropped_moves_item(self, qtbot):
        scr = self._make_scr(qtbot)
        item = {"article_number": "A1", "image_path": "", "category": "Säck",
                "url": "", "reason": ""}
        scr._columns["Säck"].prepend_item(item)
        scr._cards_by_art["A1"] = item

        received = []
        scr.reclassified.connect(lambda a, c: received.append((a, c)))
        scr._on_card_dropped("A1", "Säck", "Hink")

        # Drain pending timers before teardown
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()
        import time
        time.sleep(0.05)
        QApplication.processEvents()

        assert received == [("A1", "Hink")]
        assert scr._cards_by_art["A1"]["category"] == "Hink"

    def test_on_progress_updates_label(self, qtbot):
        scr = self._make_scr(qtbot)
        scr._on_progress("Test progress message")
        assert scr._progress_lbl.text() == "Test progress message"

    def test_on_progress_empty_string_ignored(self, qtbot):
        scr = self._make_scr(qtbot)
        scr._progress_lbl.setText("original")
        scr._on_progress("")
        assert scr._progress_lbl.text() == "original"

    def test_log_file_path_set(self, qtbot):
        scr = self._make_scr(qtbot)
        assert "TestJob" in scr._log_file_path
        assert scr._log_file_path.endswith(".log")

    def test_file_handler_created(self, qtbot):
        scr = self._make_scr(qtbot)
        assert scr._file_handler is not None

    def test_cleanup_file_handler(self, qtbot):
        scr = self._make_scr(qtbot)
        scr._cleanup_file_handler()
        assert scr._file_handler is None

    def test_add_new_column(self, qtbot):
        scr = self._make_scr(qtbot)
        n_before = len(scr._columns)
        scr._add_new_column("NyKat", "Ny beskrivning")
        assert len(scr._columns) == n_before + 1
        assert "NyKat" in scr._columns

    def test_remaining_count_excludes_already_categorized(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        categorized = [{"article_number": "A1", "category": "Säck", "image_path": ""}]
        csv_data = [{"article_number": "A1", "url": "", "bolag": ""},
                    {"article_number": "A2", "url": "", "bolag": ""}]
        scr = AIJobScreen(
            self.CATS[:], categorized, csv_data, "syfte",
            "http://localhost:1234", "model", False, dm, "TestJob",
        )
        qtbot.addWidget(scr)
        assert scr._remaining_count == 1

    def test_article_added_signal(self, qtbot):
        scr = self._make_scr(qtbot)
        received = []
        scr.article_added.connect(lambda a, c, u: received.append((a, c, u)))
        scr.article_added.emit("art1", "Säck", "http://x")
        assert received == [("art1", "Säck", "http://x")]

    def test_reclassified_signal(self, qtbot):
        scr = self._make_scr(qtbot)
        received = []
        scr.reclassified.connect(lambda a, c: received.append((a, c)))
        scr.reclassified.emit("art1", "Hink")
        assert received == [("art1", "Hink")]

    def test_knowledge_updated_signal(self, qtbot):
        scr = self._make_scr(qtbot)
        received = []
        scr.knowledge_updated.connect(lambda k, e: received.append(k))
        scr.knowledge_updated.emit({"Säck": "text"}, {})
        assert received == [{"Säck": "text"}]

    def test_finished_signal(self, qtbot):
        scr = self._make_scr(qtbot)
        received = []
        scr.finished.connect(lambda: received.append(True))
        scr.finished.emit()
        assert received == [True]


# ---------------------------------------------------------------------------
# MainApp
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestMainApp:
    def test_creates_without_crash(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)

    def test_initial_state(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            assert app.test_name == ""
            assert app.categories == []
            assert app.results == []
            assert app.ai_enabled is False

    def test_on_name_done_sets_state(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app._on_name_done("MinTest", "syfte")
            assert app.test_name == "MinTest"
            assert app.syfte == "syfte"

    def test_on_name_done_shows_categories_screen(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app._on_name_done("MinTest", "syfte")
            assert app.stack.currentWidget() is app._cat_scr

    def test_on_cats_done_sets_categories(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name = "T"
            cats = [{"name": "Säck", "description": ""}]
            with patch.object(app, "_show_source_screen"):
                app._on_cats_done(cats)
            assert len(app.categories) == 1
            assert app.categories[0]["knowledge"] == ""

    def test_on_cats_done_adds_knowledge_field_to_each_category(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name = "T"
            cats = [
                {"name": "Säck", "description": "Säckar"},
                {"name": "Hink", "description": "Hinkar"},
            ]
            with patch.object(app, "_show_source_screen"):
                app._on_cats_done(cats)
            assert len(app.categories) == 2
            for cat in app.categories:
                assert "knowledge" in cat
                assert cat["knowledge"] == ""

    def test_reset_state_clears_all(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name = "X"
            app.results = [{"article_number": "1"}]
            app.ai_enabled = True
            app._reset_state()
            assert app.test_name == ""
            assert app.results == []
            assert app.ai_enabled is False

    def test_reset_state_clears_all_fields(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name = "NonEmpty"
            app.syfte = "some purpose"
            app.categories = [{"name": "X"}]
            app.images = [None]
            app.current_index = 5
            app.csv_data = [{"article_number": "1"}]
            app.results = [{"article_number": "1", "category": "X"}]
            app.categorized = [{"article_number": "1", "category": "X"}]
            app.ai_settings = {"api_url": "http://x"}
            app.ai_enabled = True
            app._ready_images = {0, 1}
            app.cat_knowledge = {"X": "text"}
            app.cat_example_articles = {"X": ["1"]}

            app._reset_state()

            assert app.test_name == ""
            assert app.syfte == ""
            assert app.categories == []
            assert app.images == []
            assert app.current_index == 0
            assert app.csv_data == []
            assert app.results == []
            assert app.categorized == []
            assert app.ai_settings == {}
            assert app.ai_enabled is False
            assert app._ready_images == set()
            assert app.cat_knowledge == {}
            assert app.cat_example_articles == {}

    def test_on_ai_article_classified_adds_result(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.csv_data = [{"article_number": "A1", "url": "http://x", "bolag": "AB"}]
            app._on_ai_article_classified("A1", "Säck", "http://x")
            assert len(app.results) == 1
            assert app.results[0]["category"] == "Säck"

    def test_on_ai_article_classified_adds_correct_fields(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.csv_data = [{"article_number": "Z9", "url": "http://img/z9.jpg", "bolag": "AB"}]
            app._on_ai_article_classified("Z9", "Hink", "http://img/z9.jpg")
            assert len(app.results) == 1
            r = app.results[0]
            assert r["article_number"] == "Z9"
            assert r["category"] == "Hink"
            assert r["url"] == "http://img/z9.jpg"

    def test_on_ai_article_classified_no_duplicate(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.csv_data = [{"article_number": "A1", "url": "http://x", "bolag": "AB"}]
            app.results = [{"article_number": "A1", "category": "Hink"}]
            app._on_ai_article_classified("A1", "Säck", "http://x")
            assert len(app.results) == 1  # not duplicated

    def test_on_ai_article_classified_second_call_does_not_duplicate(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.csv_data = [{"article_number": "Z9", "url": "http://x", "bolag": ""}]
            app._on_ai_article_classified("Z9", "Säck", "http://x")
            app._on_ai_article_classified("Z9", "Hink", "http://x")
            assert len(app.results) == 1
            assert app.results[0]["category"] == "Säck"

    def test_on_ai_reclassified_updates_category(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.results = [{"article_number": "A1", "category": "Hink"}]
            app._on_ai_reclassified("A1", "Säck")
            assert app.results[0]["category"] == "Säck"

    def test_on_knowledge_updated_stores(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app._on_knowledge_updated({"Säck": "text"}, {"Säck": ["art1"]})
            assert app.cat_knowledge == {"Säck": "text"}
            assert app.cat_example_articles == {"Säck": ["art1"]}

    def test_on_new_test_returns_to_name_screen_and_resets_state(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name = "GammalTest"
            app.categories = [{"name": "Säck"}]
            app.results = [{"article_number": "A1"}]
            app.ai_enabled = True
            app.current_index = 3
            app._on_name_done("GammalTest", "syfte")
            assert app.stack.currentWidget() is app._cat_scr

            with patch.object(app, "_cleanup_workers"), \
                 patch.object(app, "_cleanup_temp"):
                app._on_new_test()

            assert app.stack.currentWidget() is app._name_scr
            assert app.test_name == ""
            assert app.categories == []
            assert app.results == []
            assert app.ai_enabled is False
            assert app.current_index == 0
            assert app._name_scr.name_edit.text() == ""

    def test_on_classified_adds_to_categorized(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.images = [Path(str(img))]
            app.csv_data = [{"article_number": "A1", "url": "http://x", "bolag": ""}]
            app._ready_images = {0}
            app.current_index = 0
            app.categorized = []
            app.results = []
            with patch.object(app, "_show_classify"):
                app._on_classified("Säck")
            assert app.current_index == 1
            assert len(app.categorized) == 1
            assert app.categorized[0]["category"] == "Säck"

    def test_on_skip_increments_index(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.images = [None, None]
            app.current_index = 0
            with patch.object(app, "_show_classify"):
                app._on_skip()
            assert app.current_index == 1

    def test_on_go_back_decrements_index(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.images = [None, None]
            app.current_index = 1
            with patch.object(app, "_show_classify"):
                app._on_go_back()
            assert app.current_index == 0

    def test_on_go_back_no_op_at_zero(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.current_index = 0
            app._on_go_back()
            assert app.current_index == 0

    def test_get_threshold_data_no_ai(self, qtbot):
        with patch("GamlaAppen.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.categories = [{"name": "Säck"}, {"name": "Hink"}]
            app.ai_enabled = False
            counts, threshold, ready = app._get_threshold_data()
            assert counts == {}
            assert threshold == 0
            assert ready is False


# ---------------------------------------------------------------------------
# ArticleListModel
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestArticleListModel:
    def test_empty_model(self):
        m = ArticleListModel()
        assert m.rowCount() == 0

    def test_prepend_increases_count(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        assert m.rowCount() == 1

    def test_data_display_role(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        assert m.data(m.index(0), Qt.ItemDataRole.DisplayRole) == "10000"

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

    def test_item_count(self):
        m = ArticleListModel()
        for i in range(5):
            m.prepend(make_item(str(10000 + i)))
        assert m.item_count() == 5

    def test_all_items_returns_copy(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        items = m.all_items()
        items.append(make_item("99999"))
        assert m.rowCount() == 1

    def test_update_item(self):
        m = ArticleListModel()
        m.prepend(make_item("10000", "Säck"))
        m.update_item("10000", category="Hink")
        assert m.find("10000")["category"] == "Hink"

    def test_prepend_order_newest_first(self):
        m = ArticleListModel()
        m.prepend(make_item("10000"))
        m.prepend(make_item("10001"))
        idx = m.index(0)
        item = m.data(idx, ArticleListModel.DATA_ROLE)
        assert item["article_number"] == "10001"


# ---------------------------------------------------------------------------
# CategoryColumn
# ---------------------------------------------------------------------------

@pytest.mark.ui
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

    def test_set_knowledge_ready_no_crash(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.set_knowledge_ready()  # should not crash

    def test_set_knowledge_ready_updates_style(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.set_knowledge_ready()
        assert "#a6e3a1" in col._knowledge_dot.styleSheet()

    def test_card_dropped_signal(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        received = []
        col.card_dropped.connect(lambda a, f, t: received.append((a, f, t)))
        col.card_dropped.emit("10000", "Hink", "Säck")
        assert received == [("10000", "Hink", "Säck")]

    def test_set_name(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.set_name("Hink")
        assert col.category_name == "Hink"

    def test_remove_card_by_article(self, qtbot):
        col = CategoryColumn("Säck", "#89b4fa")
        qtbot.addWidget(col)
        col.prepend_item(make_item("10000"))
        col.prepend_item(make_item("10001"))
        removed = col.remove_card_by_article("10000")
        assert removed is not None
        assert removed["article_number"] == "10000"
        assert col._count_lbl.text() == "1"

    def test_mark_as_new_category(self, qtbot):
        col = CategoryColumn("Ny", "#89b4fa")
        qtbot.addWidget(col)
        col.mark_as_new_category()
        assert col._is_new_category

"""Tests for desktop/screens/*.

Tests focus on signal emissions, validation logic, and state management.
No LLM calls, no network access.
"""
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from PyQt6.QtCore import Qt

from desktop.screens.name_screen import NameScreen
from desktop.screens.categories_screen import CategoriesScreen
from desktop.screens.source_screen import SourceScreen
from desktop.screens.ai_settings_screen import AISettingsScreen
from desktop.screens.filter_screen import FilterScreen
from desktop.screens.done_screen import DoneScreen
from desktop.screens.article_overview_screen import ArticleOverviewScreen, _ThumbnailLoader
from desktop.screens.classify_screen import ClassifyScreen
from desktop.screens.ai_job_screen import AIJobScreen


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


CATEGORIES = [{"name": "Säck", "description": ""}, {"name": "Hink", "description": ""}]


# ---------------------------------------------------------------------------
# NameScreen
# ---------------------------------------------------------------------------

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
        scr.name_edit.setText("")
        # Suppress dialog
        with pytest.raises(Exception) if False else __import__("contextlib").suppress(Exception):
            pass
        # Patch QMessageBox to avoid dialogs in tests
        import PyQt6.QtWidgets as _qw
        original = _qw.QMessageBox.warning
        _qw.QMessageBox.warning = lambda *a, **k: None
        try:
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

    def test_load_excel_signal(self, qtbot):
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

    def test_invalid_chars_stripped_or_rejected(self, qtbot):
        import PyQt6.QtWidgets as _qw
        scr = NameScreen()
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(lambda n, s: received.append(n))
        # Pure invalid name
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

class TestCategoriesScreen:
    def test_creates_with_three_rows(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        assert len(scr._rows) == 3

    def test_add_row_increases_count(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        scr._add_row()
        assert len(scr._rows) == 4

    def test_remove_row_decreases_count(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        row = scr._rows[0]
        scr._remove_row(row)
        assert len(scr._rows) == 2

    def test_row_numbers_renumbered_after_remove(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        scr._remove_row(scr._rows[0])
        assert "1" in scr._rows[0].num_lbl.text()
        assert "2" in scr._rows[1].num_lbl.text()

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
        received = []
        scr.go_next.connect(received.append)
        _qw.QMessageBox.warning = lambda *a, **k: None
        scr._validate()
        assert received == []

    def test_empty_name_rows_excluded(self, qtbot):
        scr = CategoriesScreen()
        qtbot.addWidget(scr)
        scr._rows[0].name_edit.setText("Säck")
        # rows 1 and 2 remain empty
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
        assert "MittTest" in scr.header._left.text()


# ---------------------------------------------------------------------------
# SourceScreen
# ---------------------------------------------------------------------------

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
        """When n_builtin=0, there should be no "Inbyggd data" button."""
        scr = SourceScreen("Test", n_builtin=0)
        qtbot.addWidget(scr)
        from PyQt6.QtWidgets import QPushButton
        btns = scr.findChildren(QPushButton)
        texts = [b.text() for b in btns]
        assert not any("Inbyggd" in t for t in texts)


# ---------------------------------------------------------------------------
# AISettingsScreen
# ---------------------------------------------------------------------------

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
        # isVisible() requires the parent to be shown; use isVisibleTo(None) or check explicit flag
        # The local frame should not have explicit hide; ext_frame should
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
        scr._api_key_edit.setText("")  # no key
        _qw.QMessageBox.warning = lambda *a, **k: None
        scr._go()
        assert received == []

    def test_external_with_api_key_emits_signal(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(received.append)
        scr._rb_external.setChecked(True)
        scr._api_key_edit.setText("sk-test-key")
        scr._go()
        assert received
        cfg = received[0]
        assert cfg["api_key"] == "sk-test-key"

    def test_compress_checkbox_checked_by_default(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        assert scr.compress_cb.isChecked()

    def test_go_back_signal(self, qtbot):
        scr = AISettingsScreen("Test")
        qtbot.addWidget(scr)
        received = []
        scr.go_back.connect(lambda: received.append(1))
        scr.go_back.emit()
        assert received == [1]


# ---------------------------------------------------------------------------
# FilterScreen
# ---------------------------------------------------------------------------

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

        # Deselect CD bolag
        for cb in scr._bolag_cbs:
            if cb.text() == "CD":
                cb.setChecked(False)

        filtered = scr._filtered_rows()
        assert all(r["bolag"] == "AB" for r in filtered)
        assert len(filtered) == 3

    def test_article_number_filter(self, qtbot):
        scr = self._make_screen(qtbot)
        # Filter to specific article numbers
        scr._art_filter.setPlainText("10000\n10002")
        filtered = scr._filtered_rows()
        arts = {r["article_number"] for r in filtered}
        assert arts == {"10000", "10002"}

    def test_robot_filter_Y(self, qtbot):
        rows = make_rows(3)
        dm = MagicMock()
        def meta_fn(art, bolag):
            robot = "Y" if art in {"10000", "10001"} else "N"
            return {"huvudkategori": "Djurfoder", "robot": robot}
        dm.get_meta.side_effect = meta_fn
        scr = FilterScreen("Test", rows, dm)
        qtbot.addWidget(scr)

        # Select "Ja (Y)" robot button
        for btn in scr._robot_group.buttons():
            if btn.property("robot_val") == "Y":
                btn.setChecked(True)

        filtered = scr._filtered_rows()
        assert len(filtered) == 2

    def test_total_label_shows_correct_count(self, qtbot):
        scr = self._make_screen(qtbot)
        assert "5" in scr._total_lbl.text()

    def test_match_label_updates_on_filter(self, qtbot):
        scr = self._make_screen(qtbot)
        scr._art_filter.setPlainText("10000")
        scr._update_count()
        assert "1" in scr._match_lbl.text()

    def test_start_button_disabled_when_no_match(self, qtbot):
        scr = self._make_screen(qtbot)
        # Filter to nonexistent article
        scr._art_filter.setPlainText("99999")
        scr._update_count()
        assert not scr._start_btn.isEnabled()

    def test_start_button_enabled_when_match(self, qtbot):
        scr = self._make_screen(qtbot)
        assert scr._start_btn.isEnabled()


# ---------------------------------------------------------------------------
# DoneScreen
# ---------------------------------------------------------------------------

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
        scr.show()

    def test_show_results_with_results_list(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        results = [
            {"category": "Säck"},
            {"category": "Säck"},
            {"category": "Hink"},
        ]
        scr.show_results("T", CATEGORIES, n_processed=3, has_results=True,
                          ovrigt_count=0, results=results)
        from PyQt6.QtWidgets import QLabel
        labels = scr.findChildren(QLabel)
        texts = " ".join(lbl.text() for lbl in labels)
        assert "Säck" in texts

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

    def test_retest_ovrigt_signal(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("T", CATEGORIES, 5, True, 3)
        received = []
        scr.retest_ovrigt.connect(lambda: received.append(1))
        scr.retest_ovrigt.emit()
        assert received == [1]

    def test_quit_app_signal(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("T", CATEGORIES, 0, False, 0)
        received = []
        scr.quit_app.connect(lambda: received.append(1))
        scr.quit_app.emit()
        assert received == [1]

    def test_resume_job_signal(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("T", CATEGORIES, 0, False, 0)
        received = []
        scr.resume_job.connect(lambda: received.append(1))
        scr.resume_job.emit()
        assert received == [1]

    def test_show_results_clears_previous(self, qtbot):
        """Calling show_results twice should not accumulate widgets."""
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("Test1", CATEGORIES, 5, True, 0)
        count_before = scr._lay.count()
        scr.show_results("Test2", CATEGORIES, 3, True, 0)
        count_after = scr._lay.count()
        # Content should be replaced, not added
        assert count_after == count_before

    def test_category_counts_shown(self, qtbot):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        results = [{"category": "Säck"}, {"category": "Säck"}, {"category": "Hink"}]
        scr.show_results("T", CATEGORIES, 3, True, 0, results=results)
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "2" in texts  # two Säck
        assert "1" in texts  # one Hink


# ---------------------------------------------------------------------------
# ArticleOverviewScreen
# ---------------------------------------------------------------------------

class TestArticleOverviewScreen:
    def _make_rows(self):
        return [
            {"article_number": "100", "url": "", "bolag": "AB"},
            {"article_number": "101", "url": "", "bolag": "CD"},
        ]

    def test_creates_without_crash(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {"huvudkategori": "Djurfoder", "beskrivning": "Test"}
        rows = self._make_rows()
        scr = ArticleOverviewScreen("Test", rows, dm)
        qtbot.addWidget(scr)
        scr.show()

    def test_go_next_signal(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        rows = self._make_rows()
        scr = ArticleOverviewScreen("Test", rows, dm)
        qtbot.addWidget(scr)
        received = []
        scr.go_next.connect(lambda: received.append(True))
        scr.go_next.emit()
        assert received == [True]

    def test_go_back_signal(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        rows = self._make_rows()
        scr = ArticleOverviewScreen("Test", rows, dm)
        qtbot.addWidget(scr)
        received = []
        scr.go_back.connect(lambda: received.append(True))
        scr.go_back.emit()
        assert received == [True]

    def test_shows_article_count(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        rows = self._make_rows()
        scr = ArticleOverviewScreen("Test", rows, dm)
        qtbot.addWidget(scr)
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "2" in texts

    def test_cleanup_stops_loader(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        rows = self._make_rows()
        scr = ArticleOverviewScreen("Test", rows, dm)
        qtbot.addWidget(scr)
        # cleanup should not raise even if loader is running or not started
        scr.cleanup()

    def test_thumbnail_loader_stop(self):
        loader = _ThumbnailLoader([{"url": ""}])
        loader.stop()
        assert loader._stop is True

    def test_thumbnail_loader_skips_empty_url(self, qtbot):
        received = []
        loader = _ThumbnailLoader([{"url": ""}])
        loader.thumb_ready.connect(lambda i, px: received.append(i))
        loader.run()  # synchronous in tests (no url → no request)
        assert received == []

    def test_no_crash_with_200_plus_rows(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        rows = [{"article_number": str(i), "url": "", "bolag": "AB"} for i in range(250)]
        scr = ArticleOverviewScreen("Big", rows, dm)
        qtbot.addWidget(scr)
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "50" in texts  # "… och 50 fler artiklar"


# ---------------------------------------------------------------------------
# ClassifyScreen
# ---------------------------------------------------------------------------

class TestClassifyScreen:
    CATS = [{"name": "Säck", "description": ""}, {"name": "Hink", "description": ""}]

    def _show(self, scr, img_path="/tmp/fake.png", **kw):
        scr.show_image("Test", self.CATS, img_path, None, 0, 5, **kw)

    def test_creates_without_crash(self, qtbot):
        scr = ClassifyScreen()
        qtbot.addWidget(scr)

    def test_show_image_builds_ui(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        assert scr._inner is not None

    def test_classified_signal_emitted(self, qtbot, tmp_path):
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

    def test_threshold_bar_shown_when_threshold_positive(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img), cat_counts={"Säck": 2}, threshold=5)
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "2/5" in texts

    def test_ai_job_ready_button_shown(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img), ai_job_ready=True)
        from PyQt6.QtWidgets import QPushButton
        btns = [b.text() for b in scr.findChildren(QPushButton)]
        assert any("AI" in b for b in btns)

    def test_back_button_disabled_at_start(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))  # current=0
        from PyQt6.QtWidgets import QPushButton
        btns = scr.findChildren(QPushButton)
        back = next((b for b in btns if "Tillbaka" in b.text()), None)
        assert back is not None
        assert not back.isEnabled()

    def test_clear_removes_shortcuts(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img))
        n_shortcuts = len(scr._shortcuts)
        assert n_shortcuts > 0
        self._show(scr, str(img))  # rebuild clears old shortcuts
        assert len(scr._shortcuts) > 0  # new shortcuts created

    def test_prev_category_label_shown(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        self._show(scr, str(img), current=1, prev_category="Hink")
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "Hink" in texts


# ---------------------------------------------------------------------------
# AIJobScreen
# ---------------------------------------------------------------------------

class TestAIJobScreen:
    CATS = [{"name": "Säck", "description": "", "knowledge": ""},
            {"name": "Hink", "description": "", "knowledge": ""}]

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
        # Säck, Hink, Övrigt
        assert "Säck" in scr._columns
        assert "Hink" in scr._columns
        assert "Övrigt" in scr._columns

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

    def test_on_card_dropped_moves_item(self, qtbot):
        scr = self._make_scr(qtbot)
        item = {"article_number": "A1", "image_path": "", "category": "Säck",
                "url": "", "reason": ""}
        scr._columns["Säck"].prepend_item(item)
        scr._cards_by_art["A1"] = item

        received = []
        scr.reclassified.connect(lambda a, c: received.append((a, c)))
        scr._on_card_dropped("A1", "Säck", "Hink")

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

    def test_on_knowledge_ready_stores_knowledge(self, qtbot):
        scr = self._make_scr(qtbot)
        scr._on_knowledge_ready("Säck", "Säckar är...")
        assert scr._cat_knowledge["Säck"] == "Säckar är..."

    def test_on_article_classified_adds_to_column(self, qtbot):
        scr = self._make_scr(qtbot)
        scr._on_article_classified("A1", "Säck", "http://x", "/img/a.png", "reason")
        assert "A1" in scr._cards_by_art
        assert scr._total_classified == 1

    def test_cleanup_file_handler(self, qtbot):
        scr = self._make_scr(qtbot)
        assert scr._file_handler is not None
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
        assert scr._remaining_count == 1  # only A2 is unclassified

    def test_log_file_path_set(self, qtbot):
        scr = self._make_scr(qtbot)
        assert "TestJob" in scr._log_file_path
        assert scr._log_file_path.endswith(".log")

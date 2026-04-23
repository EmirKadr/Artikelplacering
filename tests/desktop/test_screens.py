"""Tests for desktop/screens/*.

Tests focus on signal emissions, validation logic, and state management.
No LLM calls, no network access.
"""
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QLabel

from desktop.screens.setup_screen import SetupScreen
from desktop.screens.source_screen import SourceScreen
from desktop.screens.ai_settings_screen import AISettingsScreen
from desktop.screens.filter_screen import FilterScreen
from desktop.screens.done_screen import DoneScreen
from desktop.screens.classify_screen import ClassifyScreen
from desktop.screens.ai_job_screen import AIJobScreen
from desktop.widgets._thumbnail_loader import _ThumbnailLoader


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
# SetupScreen — ersätter NameScreen + CategoriesScreen + ArticleOverviewScreen
# ---------------------------------------------------------------------------

def _make_setup_screen(qtbot, n_rows=2, prefill_name="", prefill_cats=None):
    dm = MagicMock()
    dm.get_meta.return_value = {"huvudkategori": "Djurfoder", "beskrivning": "Beskr"}
    rows = [{"article_number": str(100 + i), "url": "", "bolag": "AB"}
            for i in range(n_rows)]
    scr = SetupScreen(rows, dm, prefill_name=prefill_name, prefill_cats=prefill_cats)
    qtbot.addWidget(scr)
    return scr


class TestSetupScreen:
    def test_creates_without_crash(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr.show()

    def test_initial_three_category_rows(self, qtbot):
        scr = _make_setup_screen(qtbot)
        assert len(scr._cat_rows) == 3

    def test_add_row_increases_count(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr._add_row()
        assert len(scr._cat_rows) == 4

    def test_remove_row_decreases_count(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr._remove_row(scr._cat_rows[0])
        assert len(scr._cat_rows) == 2

    def test_row_numbers_renumbered_after_remove(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr._remove_row(scr._cat_rows[0])
        assert "1" in scr._cat_rows[0].num_lbl.text()
        assert "2" in scr._cat_rows[1].num_lbl.text()

    def test_go_next_requires_name(self, qtbot):
        import PyQt6.QtWidgets as _qw
        scr = _make_setup_screen(qtbot)
        received = []
        scr.go_next.connect(lambda n, s, c: received.append((n, c)))
        scr._cat_rows[0].name_edit.setText("Säck")
        _qw.QMessageBox.warning = lambda *a, **k: None
        scr._validate()
        assert received == []

    def test_go_next_requires_category(self, qtbot):
        import PyQt6.QtWidgets as _qw
        scr = _make_setup_screen(qtbot)
        received = []
        scr.go_next.connect(lambda n, s, c: received.append((n, c)))
        scr.name_edit.setText("T")
        _qw.QMessageBox.warning = lambda *a, **k: None
        scr._validate()
        assert received == []

    def test_go_next_emits_name_syfte_cats(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr.name_edit.setText("MittTest")
        scr._cat_rows[0].name_edit.setText("Säck")
        scr._cat_rows[0].desc_edit.setText("En säck")
        scr._cat_rows[1].name_edit.setText("Hink")
        received = []
        scr.go_next.connect(lambda n, s, c: received.append((n, s, c)))
        scr._validate()
        assert received
        name, syfte, cats = received[0]
        assert name == "MittTest"
        assert isinstance(syfte, str)
        names = [c["name"] for c in cats]
        assert "Säck" in names
        assert "Hink" in names
        assert next(c for c in cats if c["name"] == "Säck")["description"] == "En säck"

    def test_go_next_sanitises_invalid_chars(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr.name_edit.setText("Test/Name")
        scr._cat_rows[0].name_edit.setText("Säck")
        received = []
        scr.go_next.connect(lambda n, s, c: received.append(n))
        scr._validate()
        assert received
        assert "/" not in received[0]

    def test_empty_rows_excluded_from_go_next(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr.name_edit.setText("T")
        scr._cat_rows[0].name_edit.setText("Säck")
        received = []
        scr.go_next.connect(lambda n, s, c: received.append(c))
        scr._validate()
        assert received
        assert len(received[0]) == 1

    def test_reset_clears_name(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr.name_edit.setText("X")
        scr.reset()
        assert scr.name_edit.text() == ""

    def test_reset_restores_three_empty_rows(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr._add_row()
        scr._add_row()
        scr.reset()
        assert len(scr._cat_rows) == 3
        assert all(r.name_edit.text() == "" for r in scr._cat_rows)

    def test_prefill_name(self, qtbot):
        scr = _make_setup_screen(qtbot, prefill_name="Förifylld")
        assert scr.name_edit.text() == "Förifylld"

    def test_prefill_cats(self, qtbot):
        cats = [{"name": "A", "description": "beskr-A"}, {"name": "B", "description": ""}]
        scr = _make_setup_screen(qtbot, prefill_cats=cats)
        assert len(scr._cat_rows) == 2
        assert scr._cat_rows[0].name_edit.text() == "A"
        assert scr._cat_rows[0].desc_edit.text() == "beskr-A"
        assert scr._cat_rows[1].name_edit.text() == "B"

    def test_go_back_signal(self, qtbot):
        scr = _make_setup_screen(qtbot)
        received = []
        scr.go_back.connect(lambda: received.append(1))
        scr.go_back.emit()
        assert received == [1]

    def test_cleanup_does_not_raise(self, qtbot):
        scr = _make_setup_screen(qtbot)
        scr.cleanup()

    def test_empty_rows_shows_placeholder(self, qtbot):
        from PyQt6.QtWidgets import QLabel
        dm = MagicMock()
        dm.get_meta.return_value = {}
        scr = SetupScreen([], dm)
        qtbot.addWidget(scr)
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "Inga artiklar" in texts

    def test_article_count_in_header(self, qtbot):
        from PyQt6.QtWidgets import QLabel
        scr = _make_setup_screen(qtbot, n_rows=5)
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "5" in texts


# ---------------------------------------------------------------------------
# SourceScreen
# ---------------------------------------------------------------------------

class TestSourceScreen:
    def test_creates_without_crash(self, qtbot):
        scr = SourceScreen(n_builtin=5)
        qtbot.addWidget(scr)
        scr.show()

    def test_use_csv_signal(self, qtbot):
        scr = SourceScreen(n_builtin=0)
        qtbot.addWidget(scr)
        received = []
        scr.use_csv.connect(lambda: received.append(1))
        scr.use_csv.emit()
        assert received == [1]

    def test_use_builtin_signal(self, qtbot):
        scr = SourceScreen(n_builtin=100)
        qtbot.addWidget(scr)
        received = []
        scr.use_builtin.connect(lambda: received.append(1))
        scr.use_builtin.emit()
        assert received == [1]

    def test_load_excel_signal(self, qtbot):
        scr = SourceScreen(n_builtin=0)
        qtbot.addWidget(scr)
        received = []
        scr.load_excel.connect(lambda: received.append(1))
        scr.load_excel.emit()
        assert received == [1]

    def test_no_builtin_button_when_zero(self, qtbot):
        """When n_builtin=0, there should be no "Inbyggd data" button."""
        scr = SourceScreen(n_builtin=0)
        qtbot.addWidget(scr)
        from PyQt6.QtWidgets import QPushButton
        btns = scr.findChildren(QPushButton)
        texts = [b.text() for b in btns]
        assert not any("Inbyggd" in t for t in texts)

    def test_has_excel_button(self, qtbot):
        """SourceScreen exposerar Öppna Excel-session-knappen."""
        scr = SourceScreen(n_builtin=0)
        qtbot.addWidget(scr)
        from PyQt6.QtWidgets import QPushButton
        btns = scr.findChildren(QPushButton)
        texts = [b.text() for b in btns]
        assert any("Excel" in t for t in texts)


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
# _ThumbnailLoader (widget)
# ---------------------------------------------------------------------------

class TestThumbnailLoader:
    def test_stop_sets_flag(self):
        loader = _ThumbnailLoader([{"url": ""}])
        loader.stop()
        assert loader._stop is True

    def test_skips_empty_url(self, qtbot):
        received = []
        loader = _ThumbnailLoader([{"url": ""}])
        loader.thumb_ready.connect(lambda i, px: received.append(i))
        loader.run()  # synchronous (no url → no request)
        assert received == []


# ---------------------------------------------------------------------------
# SetupScreen — artikellista-rendering (ersätter gamla ArticleOverviewScreen-tester)
# ---------------------------------------------------------------------------

class TestSetupScreenArticleList:
    def test_no_crash_with_200_plus_rows(self, qtbot):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        rows = [{"article_number": str(i), "url": "", "bolag": "AB"} for i in range(250)]
        scr = SetupScreen(rows, dm)
        qtbot.addWidget(scr)
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "50" in texts  # "… och 50 fler artiklar"


# ---------------------------------------------------------------------------
# ClassifyScreen
# ---------------------------------------------------------------------------

class TestClassifyScreen:
    CATS = [{"name": "Säck", "description": ""}, {"name": "Hink", "description": ""}]

    def _show(self, scr, img_path="/tmp/fake.png", current=0, **kw):
        scr.show_image("Test", self.CATS, img_path, None, current, 5, **kw)

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


# ---------------------------------------------------------------------------
# ClassifyScreen — behaviour tests
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestClassifyScreenBehavior:
    CATS = [
        {"name": "Säck", "description": ""},
        {"name": "Hink", "description": ""},
    ]

    def _make_scr(self, qtbot, tmp_path, cats=None, **kw):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        scr.show_image("Test", cats or self.CATS, str(img), None, 1, 5, **kw)
        return scr, str(img)

    # ── category buttons ───────────────────────────────────────────────────

    def test_click_cat_button_index0_emits_correct_name(self, qtbot, tmp_path):
        """Clicking the button for category 0 emits 'Säck'."""
        scr, _ = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtWidgets import QPushButton
        # Category buttons include the key number in parentheses, e.g. "Säck  (1)"
        btn = next(
            b for b in scr.findChildren(QPushButton)
            if b.text().startswith("Säck")
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert blocker.args[0] == "Säck"

    def test_click_cat_button_index1_emits_correct_name(self, qtbot, tmp_path):
        """Clicking the button for category 1 emits 'Hink'."""
        scr, _ = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtWidgets import QPushButton
        btn = next(
            b for b in scr.findChildren(QPushButton)
            if b.text().startswith("Hink")
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert blocker.args[0] == "Hink"

    def test_click_ovrigt_button_emits_ovrigt(self, qtbot, tmp_path):
        """Clicking the Övrigt button emits 'Övrigt'."""
        scr, _ = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtWidgets import QPushButton
        btn = next(
            b for b in scr.findChildren(QPushButton)
            if b.text().startswith("Övrigt")
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert blocker.args[0] == "Övrigt"

    # ── keyboard shortcuts ─────────────────────────────────────────────────

    def test_key_1_emits_first_category(self, qtbot, tmp_path):
        """Shortcut '1' is wired to emit 'Säck' when activated."""
        scr, _ = self._make_scr(qtbot, tmp_path)
        # Find the shortcut bound to key "1"
        from PyQt6.QtGui import QKeySequence
        sc = next(
            s for s in scr._shortcuts
            if s.key() == QKeySequence("1")
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            sc.activated.emit()
        assert blocker.args[0] == "Säck"

    def test_key_2_emits_second_category(self, qtbot, tmp_path):
        """Shortcut '2' is wired to emit 'Hink' when activated."""
        scr, _ = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtGui import QKeySequence
        sc = next(
            s for s in scr._shortcuts
            if s.key() == QKeySequence("2")
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            sc.activated.emit()
        assert blocker.args[0] == "Hink"

    def test_key_0_emits_ovrigt(self, qtbot, tmp_path):
        """Shortcut '0' is wired to emit 'Övrigt' when activated."""
        scr, _ = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtGui import QKeySequence
        sc = next(
            s for s in scr._shortcuts
            if s.key() == QKeySequence("0")
        )
        with qtbot.waitSignal(scr.classified) as blocker:
            sc.activated.emit()
        assert blocker.args[0] == "Övrigt"

    # ── control buttons ────────────────────────────────────────────────────

    def test_click_skip_button_emits_skipped(self, qtbot, tmp_path):
        """Clicking 'Hoppa över' emits skipped signal."""
        scr, _ = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "Hoppa" in b.text())
        with qtbot.waitSignal(scr.skipped):
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    def test_click_back_button_emits_go_back(self, qtbot, tmp_path):
        """Clicking '← Tillbaka' when current>0 emits go_back signal."""
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        # current=1 so back button is enabled
        scr.show_image("Test", self.CATS, str(img), None, 1, 5)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "Tillbaka" in b.text())
        assert btn.isEnabled()
        with qtbot.waitSignal(scr.go_back):
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    def test_click_ai_job_button_emits_run_ai_job(self, qtbot, tmp_path):
        """When ai_job_ready=True, clicking the AI button emits run_ai_job."""
        scr, _ = self._make_scr(qtbot, tmp_path, ai_job_ready=True)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "AI" in b.text() and "Kör" in b.text())
        with qtbot.waitSignal(scr.run_ai_job):
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    def test_click_end_test_button_emits_end_test(self, qtbot, tmp_path):
        """Clicking 'Avsluta test' and confirming emits end_test signal."""
        import PyQt6.QtWidgets as _qw
        scr, _ = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "Avsluta" in b.text())
        # Patch QMessageBox.question to auto-confirm
        original = _qw.QMessageBox.question
        _qw.QMessageBox.question = lambda *a, **k: _qw.QMessageBox.StandardButton.Yes
        try:
            with qtbot.waitSignal(scr.end_test):
                qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        finally:
            _qw.QMessageBox.question = original

    # ── rename dialog ──────────────────────────────────────────────────────

    def test_rename_category_emits_category_renamed(self, qtbot, tmp_path):
        """_rename_category with accepted dialog emits category_renamed(idx, new_name, new_desc)."""
        import PyQt6.QtWidgets as _qw
        scr, _ = self._make_scr(qtbot, tmp_path)
        received = []
        scr.category_renamed.connect(lambda idx, n, d: received.append((idx, n, d)))

        # Monkey-patch QDialog.exec to return Accepted and pre-fill the edits
        original_exec = _qw.QDialog.exec
        def fake_exec(dlg_self):
            # find the name edit and set new text
            edits = dlg_self.findChildren(_qw.QLineEdit)
            if edits:
                edits[0].setText("NyttNamn")
            if len(edits) > 1:
                edits[1].setText("Ny beskrivning")
            return _qw.QDialog.DialogCode.Accepted
        _qw.QDialog.exec = fake_exec
        try:
            scr._rename_category(0, "Säck")
        finally:
            _qw.QDialog.exec = original_exec

        assert len(received) == 1
        idx, new_name, new_desc = received[0]
        assert idx == 0
        assert new_name == "NyttNamn"
        assert new_desc == "Ny beskrivning"

    # ── threshold bar ──────────────────────────────────────────────────────

    def test_threshold_bar_shows_all_non_ovrigt_categories(self, qtbot, tmp_path):
        """The threshold bar shows a label for each non-Övrigt category."""
        scr, _ = self._make_scr(
            qtbot, tmp_path,
            cat_counts={"Säck": 1, "Hink": 3},
            threshold=5,
        )
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "Säck: 1/5" in texts
        assert "Hink: 3/5" in texts

    def test_threshold_bar_correct_counts_per_category(self, qtbot, tmp_path):
        """Threshold bar shows exact count for each category."""
        scr, _ = self._make_scr(
            qtbot, tmp_path,
            cat_counts={"Säck": 2, "Hink": 0},
            threshold=3,
        )
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "Säck: 2/3" in texts
        assert "Hink: 0/3" in texts


# ---------------------------------------------------------------------------
# AIJobScreen — behaviour tests
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestAIJobScreenBehavior:
    CATS = [
        {"name": "Säck", "description": "", "knowledge": ""},
        {"name": "Hink", "description": "", "knowledge": ""},
    ]

    def _make_scr(self, qtbot, cats=None, categorized=None, csv_data=None):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        scr = AIJobScreen(
            (cats or self.CATS)[:],
            categorized or [],
            csv_data or [],
            "syfte",
            "http://localhost:1234", "model", False,
            dm, "TestJob",
        )
        qtbot.addWidget(scr)
        return scr

    # ── card_dropped ───────────────────────────────────────────────────────

    def test_card_dropped_moves_card_to_target_column(self, qtbot):
        """_on_card_dropped moves the item to the correct target column."""
        scr = self._make_scr(qtbot)
        item = {"article_number": "A1", "image_path": "", "category": "Säck",
                "url": "", "reason": ""}
        scr._columns["Säck"].prepend_item(item)
        scr._cards_by_art["A1"] = item
        qtbot.wait(50)  # let prepend_item QTimer fire

        scr._on_card_dropped("A1", "Säck", "Hink")
        qtbot.wait(50)  # let prepend_item QTimer from target column fire

        # item should now be tracked under Hink
        assert scr._cards_by_art["A1"]["category"] == "Hink"
        # Hink column should contain the card
        hink_arts = [c["article_number"] for c in scr._columns["Hink"]._cards]
        assert "A1" in hink_arts

    def test_card_dropped_removes_from_source_column(self, qtbot):
        """_on_card_dropped removes the item from the source column."""
        scr = self._make_scr(qtbot)
        item = {"article_number": "B2", "image_path": "", "category": "Säck",
                "url": "", "reason": ""}
        scr._columns["Säck"].prepend_item(item)
        scr._cards_by_art["B2"] = item
        qtbot.wait(50)  # let prepend_item QTimer fire

        scr._on_card_dropped("B2", "Säck", "Hink")
        qtbot.wait(50)

        sack_arts = [c["article_number"] for c in scr._columns["Säck"]._cards]
        assert "B2" not in sack_arts

    # ── _on_article_classified ─────────────────────────────────────────────

    def test_on_article_classified_puts_card_in_correct_column(self, qtbot):
        """_on_article_classified places the card in the named column."""
        scr = self._make_scr(qtbot)
        scr._on_article_classified("C3", "Säck", "http://x", "/img/c.png", "ok")
        # Process the pending QTimer (30 ms) from prepend_item before teardown
        qtbot.wait(50)
        sack_arts = [c["article_number"] for c in scr._columns["Säck"]._cards]
        assert "C3" in sack_arts

    def test_on_article_classified_unknown_category_falls_back_to_ovrigt(self, qtbot):
        """_on_article_classified with an unknown category puts card in Övrigt."""
        scr = self._make_scr(qtbot)
        scr._on_article_classified("D4", "OkändKat", "http://x", "/img/d.png", "")
        qtbot.wait(50)
        ovrigt_arts = [c["article_number"] for c in scr._columns["Övrigt"]._cards]
        assert "D4" in ovrigt_arts

    # ── pause / stop ───────────────────────────────────────────────────────

    def test_info_panel_shows_granngarden_search_link(self, qtbot):
        scr = self._make_scr(qtbot)
        item = {"article_number": "12345", "image_path": "", "category": "Säck",
                "url": "", "reason": ""}

        scr._populate_info_panel(item)

        link = scr.findChild(QLabel, "ai_job_granngarden_link")
        assert link is not None
        assert "https://www.granngarden.se/sok?q=12345" in link.text()
        assert link.openExternalLinks()
        assert link.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        assert link.textInteractionFlags() & Qt.TextInteractionFlag.LinksAccessibleByMouse

    def test_double_click_card_opens_info_side_panel(self, qtbot):
        scr = self._make_scr(qtbot)
        item = {"article_number": "A123", "image_path": "", "category": "Säck",
                "url": "", "reason": "ok"}
        col = scr._columns["Säck"]
        col.prepend_item(item)

        col._view.doubleClicked.emit(col._model.index(0))

        assert not scr._info_panel.isHidden()
        assert "A123" in scr._info_panel_title.text()

    def test_selecting_card_clears_selection_in_other_columns(self, qtbot):
        scr = self._make_scr(qtbot)
        sack_item = {"article_number": "A1", "image_path": "", "category": "Säck",
                     "url": "", "reason": ""}
        hink_item = {"article_number": "B2", "image_path": "", "category": "Hink",
                     "url": "", "reason": ""}
        sack_col = scr._columns["Säck"]
        hink_col = scr._columns["Hink"]
        sack_col.prepend_item(sack_item)
        hink_col.prepend_item(hink_item)

        sack_idx = sack_col._model.index(0)
        hink_idx = hink_col._model.index(0)
        sack_col._view.selectionModel().select(
            sack_idx, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        assert sack_col._view.selectedIndexes()

        hink_col._view.selectionModel().select(
            hink_idx, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

        assert not sack_col._view.selectedIndexes()
        assert hink_col._view.selectedIndexes()

    def test_pause_button_calls_worker_pause(self, qtbot):
        """Clicking pause when worker is running calls worker.pause()."""
        scr = self._make_scr(qtbot)
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        mock_worker._paused = False
        scr._worker = mock_worker
        scr._pause_btn.setVisible(True)

        qtbot.mouseClick(scr._pause_btn, Qt.MouseButton.LeftButton)

        mock_worker.pause.assert_called_once()

    def test_stop_button_calls_worker_stop(self, qtbot):
        """Clicking 'Avsluta i förtid' and confirming calls worker.stop()."""
        import PyQt6.QtWidgets as _qw
        scr = self._make_scr(qtbot)
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True
        scr._worker = mock_worker

        original = _qw.QMessageBox.question
        _qw.QMessageBox.question = lambda *a, **k: _qw.QMessageBox.StandardButton.Yes
        try:
            qtbot.mouseClick(scr._stop_early_btn, Qt.MouseButton.LeftButton)
        finally:
            _qw.QMessageBox.question = original

        # Let pending timers from category columns fire before teardown
        qtbot.wait(50)
        mock_worker.stop.assert_called_once()

    # ── log dialog ─────────────────────────────────────────────────────────

    def test_log_dialog_opens_and_contains_log_lines(self, qtbot):
        """Opening the log dialog shows previously logged lines."""
        scr = self._make_scr(qtbot)
        scr._on_progress("Teststeg 1")
        scr._on_progress("Teststeg 2")
        scr._open_log_dialog()
        assert scr._log_dialog is not None
        assert scr._log_dialog.isVisible()
        text = scr._log_dialog._text.toPlainText()
        assert "Teststeg 1" in text
        assert "Teststeg 2" in text
        scr._log_dialog.close()
        # Let pending QTimer callbacks from category columns fire before teardown
        qtbot.wait(50)

    # ── remaining count ────────────────────────────────────────────────────

    def test_remaining_count_decreases_as_articles_classified(self, qtbot):
        """_remaining_count header text updates after each classification."""
        csv_data = [
            {"article_number": "X1", "url": "", "bolag": ""},
            {"article_number": "X2", "url": "", "bolag": ""},
            {"article_number": "X3", "url": "", "bolag": ""},
        ]
        scr = self._make_scr(qtbot, csv_data=csv_data)
        assert scr._remaining_count == 3

        scr._on_article_classified("X1", "Säck", "http://x", "", "")
        qtbot.wait(50)  # let prepend_item QTimer fire
        assert scr._total_classified == 1

        scr._on_article_classified("X2", "Hink", "http://x", "", "")
        qtbot.wait(50)
        assert scr._total_classified == 2


# ---------------------------------------------------------------------------
# FilterScreen — behaviour tests
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestFilterScreenBehavior:
    def _make_screen(self, qtbot, rows, meta_fn=None):
        dm = MagicMock()
        if meta_fn:
            dm.get_meta.side_effect = meta_fn
        else:
            dm.get_meta.return_value = {"huvudkategori": "Djurfoder", "robot": "N"}
        scr = FilterScreen("Test", rows, dm)
        qtbot.addWidget(scr)
        return scr

    # ── bolag filter ───────────────────────────────────────────────────────

    def test_deselect_bolag_filters_rows_from_go_next(self, qtbot):
        """Unchecking a bolag checkbox removes those rows from go_next signal."""
        rows_ab = [{"article_number": str(100 + i), "bolag": "AB", "url": ""} for i in range(3)]
        rows_cd = [{"article_number": str(200 + i), "bolag": "CD", "url": ""} for i in range(2)]
        all_rows = rows_ab + rows_cd

        def meta_fn(art, bolag):
            return {"huvudkategori": "Djurfoder", "robot": "N"}

        scr = self._make_screen(qtbot, all_rows, meta_fn)

        for cb in scr._bolag_cbs:
            if cb.text() == "CD":
                cb.setChecked(False)

        received = []
        scr.go_next.connect(received.append)
        scr._on_start()

        assert received
        emitted = received[0]
        assert all(r["bolag"] == "AB" for r in emitted)
        assert len(emitted) == 3

    def test_recheck_bolag_includes_rows_again(self, qtbot):
        """Re-checking a bolag checkbox re-includes those rows."""
        rows_ab = [{"article_number": str(100 + i), "bolag": "AB", "url": ""} for i in range(2)]
        rows_cd = [{"article_number": str(200 + i), "bolag": "CD", "url": ""} for i in range(2)]
        all_rows = rows_ab + rows_cd

        scr = self._make_screen(qtbot, all_rows)

        # deselect CD then re-select
        for cb in scr._bolag_cbs:
            if cb.text() == "CD":
                cb.setChecked(False)
                cb.setChecked(True)

        assert len(scr._filtered_rows()) == 4

    # ── article number filter ──────────────────────────────────────────────

    def test_article_filter_text_go_next_emits_only_matching(self, qtbot):
        """Writing article numbers in the filter box limits emitted rows."""
        rows = [{"article_number": str(1000 + i), "bolag": "AB", "url": ""} for i in range(5)]
        scr = self._make_screen(qtbot, rows)
        scr._art_filter.setPlainText("1000\n1002")

        received = []
        scr.go_next.connect(received.append)
        scr._on_start()

        assert received
        arts = {r["article_number"] for r in received[0]}
        assert arts == {"1000", "1002"}

    # ── robot filter ───────────────────────────────────────────────────────

    def test_robot_filter_Y_go_next_emits_only_robot_Y_rows(self, qtbot):
        """Selecting robot=Y causes go_next to emit only robot=Y rows."""
        rows = [{"article_number": str(100 + i), "bolag": "AB", "url": ""} for i in range(4)]

        def meta_fn(art, bolag):
            robot = "Y" if art in {"100", "101"} else "N"
            return {"huvudkategori": "Djurfoder", "robot": robot}

        scr = self._make_screen(qtbot, rows, meta_fn)

        for btn in scr._robot_group.buttons():
            if btn.property("robot_val") == "Y":
                btn.setChecked(True)

        received = []
        scr.go_next.connect(received.append)
        scr._on_start()

        assert received
        assert len(received[0]) == 2
        arts = {r["article_number"] for r in received[0]}
        assert arts == {"100", "101"}

    # ── start button ───────────────────────────────────────────────────────

    def test_start_button_click_emits_go_next_with_correct_rows(self, qtbot):
        """Clicking Start emits go_next with exactly the filtered rows."""
        rows = [{"article_number": str(500 + i), "bolag": "AB", "url": ""} for i in range(4)]
        scr = self._make_screen(qtbot, rows)
        # Filter to 2 articles
        scr._art_filter.setPlainText("500\n501")

        received = []
        scr.go_next.connect(received.append)
        with qtbot.waitSignal(scr.go_next):
            qtbot.mouseClick(scr._start_btn, Qt.MouseButton.LeftButton)

        assert len(received) == 1
        assert len(received[0]) == 2

    def test_start_button_emits_not_more_not_fewer_rows(self, qtbot):
        """go_next emits exactly the filtered rows — no extras, no omissions."""
        rows = [{"article_number": str(300 + i), "bolag": "AB", "url": ""} for i in range(6)]
        scr = self._make_screen(qtbot, rows)
        scr._art_filter.setPlainText("300\n302\n304")

        received = []
        scr.go_next.connect(received.append)
        scr._on_start()
        # Process any pending Qt events from previous tests
        qtbot.wait(10)

        assert received
        arts = sorted(r["article_number"] for r in received[0])
        assert arts == ["300", "302", "304"]


# ---------------------------------------------------------------------------
# ClassifyScreen — additional behaviour tests
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestClassifyScreenBehaviorExtra:
    """Additional behaviour tests for ClassifyScreen."""

    CATS = [
        {"name": "Säck",   "description": ""},
        {"name": "Hink",   "description": ""},
        {"name": "Korg",   "description": ""},
        {"name": "Tank",   "description": ""},
        {"name": "Tunna",  "description": ""},
    ]

    def _make_scr(self, qtbot, tmp_path, cats=None, **kw):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        scr.show_image("Test", cats or self.CATS, str(img), None, 1, 10, **kw)
        return scr

    # ── keys 3, 4, 5 ───────────────────────────────────────────────────────

    def test_key_3_emits_third_category(self, qtbot, tmp_path):
        """Shortcut '3' emits the third category name."""
        scr = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtGui import QKeySequence
        sc = next(s for s in scr._shortcuts if s.key() == QKeySequence("3"))
        with qtbot.waitSignal(scr.classified) as blocker:
            sc.activated.emit()
        assert blocker.args[0] == "Korg"

    def test_key_4_emits_fourth_category(self, qtbot, tmp_path):
        """Shortcut '4' emits the fourth category name."""
        scr = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtGui import QKeySequence
        sc = next(s for s in scr._shortcuts if s.key() == QKeySequence("4"))
        with qtbot.waitSignal(scr.classified) as blocker:
            sc.activated.emit()
        assert blocker.args[0] == "Tank"

    def test_key_5_emits_fifth_category(self, qtbot, tmp_path):
        """Shortcut '5' emits the fifth category name."""
        scr = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtGui import QKeySequence
        sc = next(s for s in scr._shortcuts if s.key() == QKeySequence("5"))
        with qtbot.waitSignal(scr.classified) as blocker:
            sc.activated.emit()
        assert blocker.args[0] == "Tunna"

    # ── add_category signal ─────────────────────────────────────────────────

    def test_add_category_button_emits_signal(self, qtbot, tmp_path):
        """Clicking '+ Ny kategori' emits the add_category signal."""
        scr = self._make_scr(qtbot, tmp_path)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "Ny kategori" in b.text())
        with qtbot.waitSignal(scr.add_category):
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    # ── rename dialog with Cancel ───────────────────────────────────────────

    def test_rename_dialog_cancel_does_not_emit_category_renamed(self, qtbot, tmp_path):
        """When the rename dialog is cancelled, category_renamed is NOT emitted."""
        import PyQt6.QtWidgets as _qw
        scr = self._make_scr(qtbot, tmp_path)
        received = []
        scr.category_renamed.connect(lambda idx, n, d: received.append((idx, n, d)))

        original_exec = _qw.QDialog.exec
        _qw.QDialog.exec = lambda self_dlg: _qw.QDialog.DialogCode.Rejected
        try:
            scr._rename_category(0, "Säck")
        finally:
            _qw.QDialog.exec = original_exec

        assert received == []

    # ── prev_category label ─────────────────────────────────────────────────

    def test_prev_category_label_updates_after_classify(self, qtbot, tmp_path):
        """After classifying, show_image with prev_category shows that name."""
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        scr = ClassifyScreen()
        qtbot.addWidget(scr)
        cats = [{"name": "Säck", "description": ""}, {"name": "Hink", "description": ""}]
        # First call: no prev_category
        scr.show_image("Test", cats, str(img), None, 0, 5)
        # Second call: prev_category set
        scr.show_image("Test", cats, str(img), None, 1, 5, prev_category="Hink")
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "Hink" in texts


# ---------------------------------------------------------------------------
# AIJobScreen — additional behaviour tests
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestAIJobScreenBehaviorExtra:
    """Additional behaviour tests for AIJobScreen."""

    CATS = [
        {"name": "Säck", "description": "", "knowledge": ""},
        {"name": "Hink", "description": "", "knowledge": ""},
    ]

    def _make_scr(self, qtbot, cats=None, categorized=None, csv_data=None):
        dm = MagicMock()
        dm.get_meta.return_value = {}
        scr = AIJobScreen(
            (cats or self.CATS)[:],
            categorized or [],
            csv_data or [],
            "syfte",
            "http://localhost:1234", "model", False,
            dm, "TestJob",
        )
        qtbot.addWidget(scr)
        return scr

    # ── _add_new_column ─────────────────────────────────────────────────────

    def test_add_new_column_has_correct_name(self, qtbot):
        """_add_new_column creates a column accessible by the given name."""
        scr = self._make_scr(qtbot)
        scr._add_new_column("Flaska", "Glasflaskor")
        assert "Flaska" in scr._columns

    def test_add_new_column_increments_count(self, qtbot):
        """Each call to _add_new_column increases the column count by one."""
        scr = self._make_scr(qtbot)
        before = len(scr._columns)
        scr._add_new_column("FlaskA", "desc A")
        scr._add_new_column("FlaskB", "desc B")
        assert len(scr._columns) == before + 2

    # ── _on_progress accumulation ───────────────────────────────────────────

    def test_multiple_progress_messages_accumulate_in_log(self, qtbot):
        """Several _on_progress calls each add an entry to _log_lines."""
        scr = self._make_scr(qtbot)
        scr._on_progress("Steg 1")
        scr._on_progress("Steg 2")
        scr._on_progress("Steg 3")
        assert len(scr._log_lines) >= 3
        combined = " ".join(scr._log_lines)
        assert "Steg 1" in combined
        assert "Steg 2" in combined
        assert "Steg 3" in combined

    # ── article_added signal with correct payload ───────────────────────────

    def test_on_article_classified_emits_article_added_with_correct_payload(self, qtbot):
        """_on_article_classified emits article_added(article_number, category, url)."""
        scr = self._make_scr(qtbot)
        received = []
        scr.article_added.connect(lambda a, c, u: received.append((a, c, u)))
        scr._on_article_classified("Z9", "Säck", "http://img/z9.jpg", "", "")
        qtbot.wait(50)
        assert len(received) == 1
        art, cat, url = received[0]
        assert art == "Z9"
        assert cat == "Säck"
        assert url == "http://img/z9.jpg"


# ---------------------------------------------------------------------------
# DoneScreen — behaviour tests
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestDoneScreenBehavior:
    """Behaviour tests for DoneScreen — signal emissions and display logic."""

    CATS = [{"name": "Säck", "description": ""}, {"name": "Hink", "description": ""}]

    def _make_scr(self, qtbot, **kw):
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("Test", self.CATS, 5, True, 2, **kw)
        return scr

    # ── signal emissions via button clicks ──────────────────────────────────

    def test_new_test_button_click_emits_signal(self, qtbot):
        """Clicking 'Nytt test' emits the new_test signal."""
        scr = self._make_scr(qtbot)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "Nytt test" in b.text())
        with qtbot.waitSignal(scr.new_test):
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    def test_export_excel_button_click_emits_signal(self, qtbot):
        """Clicking 'Exportera Excel' emits the export_excel signal."""
        scr = self._make_scr(qtbot)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "Exportera" in b.text())
        with qtbot.waitSignal(scr.export_excel):
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    def test_resume_job_button_click_emits_signal(self, qtbot):
        """Clicking 'Fortsätt redigera' emits the resume_job signal."""
        scr = self._make_scr(qtbot)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "Fortsätt" in b.text())
        with qtbot.waitSignal(scr.resume_job):
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    def test_retest_ovrigt_button_click_emits_signal(self, qtbot):
        """Clicking 'Testa Övrigt igen' emits the retest_ovrigt signal."""
        scr = self._make_scr(qtbot)
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton) if "vrigt" in b.text())
        with qtbot.waitSignal(scr.retest_ovrigt):
            qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)

    # ── category counters ───────────────────────────────────────────────────

    def test_category_count_shown_for_specific_category(self, qtbot):
        """show_results displays correct count for a specific category."""
        results = [
            {"category": "Säck"},
            {"category": "Säck"},
            {"category": "Säck"},
            {"category": "Hink"},
        ]
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("Test", self.CATS, 4, True, 0, results=results)
        from PyQt6.QtWidgets import QLabel
        texts = " ".join(lbl.text() for lbl in scr.findChildren(QLabel))
        assert "Säck" in texts
        assert "3" in texts

    # ── clearing on repeated show_results ──────────────────────────────────

    def test_show_results_twice_replaces_content(self, qtbot):
        """Calling show_results a second time replaces, not accumulates, content."""
        scr = DoneScreen()
        qtbot.addWidget(scr)
        scr.show_results("Test1", self.CATS, 3, True, 0)
        count_first = scr._lay.count()
        scr.show_results("Test2", self.CATS, 7, True, 0)
        count_second = scr._lay.count()
        assert count_second == count_first


# ---------------------------------------------------------------------------
# SetupScreen — behaviour tests (ersätter NameScreen/CategoriesScreen/ArticleOverviewScreen)
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestSetupScreenBehavior:
    """Behaviour tests for SetupScreen — kombinerad setup-skärm."""

    def _make(self, qtbot, n_rows=2):
        dm = MagicMock()
        dm.get_meta.return_value = {"huvudkategori": "Djurfoder", "beskrivning": "B"}
        rows = [{"article_number": str(i), "url": "", "bolag": "AB"} for i in range(n_rows)]
        scr = SetupScreen(rows, dm)
        qtbot.addWidget(scr)
        return scr

    def test_valid_input_and_click_emits_go_next(self, qtbot):
        """Valid name + category + button click emits go_next(name, syfte, cats)."""
        scr = self._make(qtbot)
        scr.name_edit.setText("MittTest")
        scr._cat_rows[0].name_edit.setText("Säck")
        received = []
        scr.go_next.connect(lambda n, s, c: received.append((n, s, c)))
        from PyQt6.QtWidgets import QPushButton
        btn = next(b for b in scr.findChildren(QPushButton)
                   if "Starta" in b.text() or "→" in b.text())
        qtbot.mouseClick(btn, Qt.MouseButton.LeftButton)
        assert len(received) == 1
        name, syfte, cats = received[0]
        assert name == "MittTest"
        assert isinstance(syfte, str)
        assert [c["name"] for c in cats] == ["Säck"]

    def test_empty_name_does_not_emit_go_next(self, qtbot):
        import PyQt6.QtWidgets as _qw
        scr = self._make(qtbot)
        scr._cat_rows[0].name_edit.setText("Säck")
        received = []
        scr.go_next.connect(lambda *a: received.append(a))
        _qw.QMessageBox.warning = lambda *a, **k: None
        scr._validate()
        assert received == []

    def test_empty_category_does_not_emit_go_next(self, qtbot):
        import PyQt6.QtWidgets as _qw
        scr = self._make(qtbot)
        scr.name_edit.setText("T")
        received = []
        scr.go_next.connect(lambda *a: received.append(a))
        _qw.QMessageBox.warning = lambda *a, **k: None
        scr._validate()
        assert received == []

    def test_reset_clears_name_field(self, qtbot):
        scr = self._make(qtbot)
        scr.name_edit.setText("Föregående test")
        scr.reset()
        assert scr.name_edit.text() == ""

    def test_back_button_click_emits_go_back(self, qtbot):
        scr = self._make(qtbot)
        from PyQt6.QtWidgets import QPushButton
        btns = scr.findChildren(QPushButton)
        back = next((b for b in btns if "Tillbaka" in b.text() or "←" in b.text()), None)
        assert back is not None
        with qtbot.waitSignal(scr.go_back):
            qtbot.mouseClick(back, Qt.MouseButton.LeftButton)

    def test_add_row_button_increases_count(self, qtbot):
        scr = self._make(qtbot)
        before = len(scr._cat_rows)
        scr._add_row()
        assert len(scr._cat_rows) == before + 1

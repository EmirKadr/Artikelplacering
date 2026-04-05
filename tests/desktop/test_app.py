"""Tests for desktop/app.py — MainApp construction and navigation logic.

Tests avoid launching the full event loop and skip any network/AI operations.
"""
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

from desktop.app import MainApp


# ---------------------------------------------------------------------------
# MainApp
# ---------------------------------------------------------------------------

class TestMainApp:
    def test_creates_without_crash(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)

    def test_initial_state(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            assert app.test_name == ""
            assert app.categories == []
            assert app.results == []
            assert app.ai_enabled is False

    def test_on_name_done_sets_state(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app._on_name_done("MinTest", "syfte")
            assert app.test_name == "MinTest"
            assert app.syfte == "syfte"

    def test_on_cats_done_sets_categories(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name = "T"
            cats = [{"name": "Säck", "description": ""}]
            with patch.object(app, "_show_source_screen"):
                app._on_cats_done(cats)
            assert len(app.categories) == 1
            assert app.categories[0]["knowledge"] == ""

    def test_reset_state_clears_all(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name   = "X"
            app.results     = [{"article_number": "1"}]
            app.ai_enabled  = True
            app._reset_state()
            assert app.test_name == ""
            assert app.results == []
            assert app.ai_enabled is False

    def test_get_threshold_data_no_ai(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.categories = [{"name": "Säck"}, {"name": "Hink"}]
            app.ai_enabled = False
            counts, threshold, ready = app._get_threshold_data()
            assert counts == {}
            assert threshold == 0
            assert ready is False

    def test_get_threshold_data_with_ai(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.categories = [{"name": "Säck"}, {"name": "Hink"}]
            app.ai_enabled = True
            app.categorized = [
                {"article_number": "1", "category": "Säck"},
                {"article_number": "2", "category": "Säck"},
            ]
            counts, threshold, ready = app._get_threshold_data()
            assert counts["Säck"] == 2
            assert counts["Hink"] == 0
            # ready depends on AI_JOB_MIN_PER_CAT — with 0 it's always True
            from core.constants import AI_JOB_MIN_PER_CAT
            expected_ready = all(v >= AI_JOB_MIN_PER_CAT for v in counts.values())
            assert ready is expected_ready

    def test_on_ai_article_classified_adds_result(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.csv_data = [{"article_number": "A1", "url": "http://x", "bolag": "AB"}]
            app._on_ai_article_classified("A1", "Säck", "http://x")
            assert len(app.results) == 1
            assert app.results[0]["category"] == "Säck"

    def test_on_ai_article_classified_no_duplicate(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.csv_data = [{"article_number": "A1", "url": "http://x", "bolag": "AB"}]
            app.results  = [{"article_number": "A1", "category": "Hink"}]
            app._on_ai_article_classified("A1", "Säck", "http://x")
            assert len(app.results) == 1  # not duplicated

    def test_on_ai_reclassified_updates_result(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.results = [{"article_number": "A1", "category": "Hink"}]
            app._on_ai_reclassified("A1", "Säck")
            assert app.results[0]["category"] == "Säck"

    def test_on_knowledge_updated_stores(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app._on_knowledge_updated({"Säck": "text"}, {"Säck": ["art1"]})
            assert app.cat_knowledge == {"Säck": "text"}
            assert app.cat_example_articles == {"Säck": ["art1"]}

    def test_on_classified_adds_to_categorized(self, qtbot, tmp_path):
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            from pathlib import Path
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
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.images = [None, None]
            app.current_index = 0
            with patch.object(app, "_show_classify"):
                app._on_skip()
            assert app.current_index == 1

    def test_on_go_back_decrements_index(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.images = [None, None]
            app.current_index = 1
            with patch.object(app, "_show_classify"):
                app._on_go_back()
            assert app.current_index == 0

    def test_on_go_back_no_op_at_zero(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.current_index = 0
            app._on_go_back()  # should not crash or change index
            assert app.current_index == 0


# ---------------------------------------------------------------------------
# MainApp — navigation behaviour tests
# ---------------------------------------------------------------------------

@pytest.mark.ui
class TestMainAppNavigation:
    """Tests for screen transitions and state management in MainApp."""

    def _make_app(self, qtbot):
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            return app

    # ── screen transitions ─────────────────────────────────────────────────

    def test_on_name_done_shows_categories_screen(self, qtbot):
        """_on_name_done switches the stacked widget to CategoriesScreen."""
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app._on_name_done("MinTest", "syfte")
            assert app.stack.currentWidget() is app._cat_scr

    def test_on_cats_done_shows_source_screen(self, qtbot):
        """_on_cats_done pushes a SourceScreen onto the stack."""
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name = "T"
            cats = [{"name": "Säck", "description": ""}]
            app._on_cats_done(cats)
            from desktop.screens.source_screen import SourceScreen
            assert isinstance(app.stack.currentWidget(), SourceScreen)

    def test_on_source_csv_creates_image_downloader(self, qtbot, tmp_path):
        """_download_images creates an ImageDownloader instance."""
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name = "T"
            app.categories = [{"name": "Säck", "description": "", "knowledge": ""}]

            rows = [{"article_number": "A1", "url": "http://x/img.jpg", "bolag": ""}]
            with patch("desktop.app.ImageDownloader") as MockDL:
                mock_dl_instance = MagicMock()
                mock_dl_instance.start = MagicMock()
                MockDL.return_value = mock_dl_instance
                app._download_images(rows)
                MockDL.assert_called_once()

    def test_on_classified_last_article_shows_done_screen(self, qtbot, tmp_path):
        """Classifying the last article leads to DoneScreen being displayed."""
        img = tmp_path / "a.png"
        img.write_bytes(b"")
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            from pathlib import Path
            app.images = [Path(str(img))]
            app.csv_data = [{"article_number": "A1", "url": "http://x", "bolag": ""}]
            app._ready_images = {0}
            app.current_index = 0
            app.categorized = []
            app.results = []
            app.categories = [{"name": "Säck", "description": "", "knowledge": ""}]
            # After classify, current_index becomes 1 == len(images), so _show_done is called
            app._on_classified("Säck")
            from desktop.screens.done_screen import DoneScreen
            assert isinstance(app.stack.currentWidget(), DoneScreen)

    def test_reset_state_clears_all_fields(self, qtbot):
        """_reset_state zeros out every session field."""
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.test_name    = "NonEmpty"
            app.syfte        = "some purpose"
            app.categories   = [{"name": "X"}]
            app.images       = [None]
            app.current_index = 5
            app.csv_data     = [{"article_number": "1"}]
            app.results      = [{"article_number": "1", "category": "X"}]
            app.categorized  = [{"article_number": "1", "category": "X"}]
            app.ai_settings  = {"api_url": "http://x"}
            app.ai_enabled   = True
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

    def test_reset_state_then_name_screen_is_current(self, qtbot):
        """After _reset_state and _on_new_test, NameScreen is shown."""
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            # Simulate being at a later screen
            app._on_name_done("Test", "syfte")
            assert app.stack.currentWidget() is app._cat_scr

            with patch.object(app, "_cleanup_workers"), \
                 patch.object(app, "_cleanup_temp"):
                app._on_new_test()

            assert app.stack.currentWidget() is app._name_scr

    # ── _on_ai_article_classified ──────────────────────────────────────────

    def test_on_ai_article_classified_adds_result_with_correct_fields(self, qtbot):
        """_on_ai_article_classified appends a result with correct article_number, category, url."""
        with patch("desktop.app.DataManager") as MockDM:
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

    def test_on_ai_article_classified_second_call_does_not_duplicate(self, qtbot):
        """Calling _on_ai_article_classified twice for the same article does not duplicate it.

        The method only inserts if the article is not already in results; a second
        call for an existing article is silently ignored (use _on_ai_reclassified to
        update an existing entry).
        """
        with patch("desktop.app.DataManager") as MockDM:
            MockDM.return_value.builtin_attributes = []
            app = MainApp()
            qtbot.addWidget(app)
            app.csv_data = [{"article_number": "Z9", "url": "http://x", "bolag": ""}]
            app._on_ai_article_classified("Z9", "Säck", "http://x")
            app._on_ai_article_classified("Z9", "Hink", "http://x")
            # Second call is ignored — still exactly one entry
            assert len(app.results) == 1
            # The first category wins (no update on second call)
            assert app.results[0]["category"] == "Säck"

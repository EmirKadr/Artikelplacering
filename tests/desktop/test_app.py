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

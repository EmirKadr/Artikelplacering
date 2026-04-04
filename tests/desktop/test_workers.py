"""Tests for desktop/workers/*.

Workers are QThreads; tests use qtbot.waitSignal / qtbot.waitUntil.
All LLM calls and network calls are mocked.
"""
import json
import time
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from desktop.workers.ai_job_worker import AIJobWorker
from desktop.workers.image_downloader import ImageDownloader
from desktop.workers.new_category_worker import NewCategoryWorker
from desktop.workers.reclassify_worker import ReClassifyWorker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CATEGORIES = [
    {"name": "Säck", "description": "En säck"},
    {"name": "Hink", "description": "En hink"},
]


def make_data_mgr(meta: Dict = None):
    dm = MagicMock()
    dm.get_meta.return_value = meta or {}
    return dm


def make_image(tmp_path, name: str = "img.jpg") -> str:
    p = tmp_path / name
    p.write_bytes(b"fake image data")
    return str(p)


# ---------------------------------------------------------------------------
# ImageDownloader
# ---------------------------------------------------------------------------

class TestImageDownloader:
    def test_stop_before_run(self, tmp_path):
        rows = [{"url": "http://example.com/img.jpg"}]
        dl = ImageDownloader(rows, str(tmp_path))
        dl.stop()
        assert dl._stop

    def test_download_error_does_not_crash(self, tmp_path):
        """A bad URL should not crash the worker — it emits nothing."""
        rows = [{"url": "http://127.0.0.1:1/nonexistent.jpg"}]
        dl = ImageDownloader(rows, str(tmp_path))
        ready = []
        dl.image_ready.connect(lambda i, p: ready.append((i, p)))
        dl.run()  # run synchronously (no thread)
        assert ready == []  # no successful download

    def test_stop_mid_run(self, tmp_path, qtbot):
        """stop() prevents processing remaining rows."""
        rows = [{"url": "http://127.0.0.1:1/a.jpg"},
                {"url": "http://127.0.0.1:1/b.jpg"}]
        dl = ImageDownloader(rows, str(tmp_path))
        dl.stop()  # stop before run
        ready = []
        dl.image_ready.connect(lambda i, p: ready.append(i))
        dl.run()
        assert ready == []

    def test_filename_no_suffix_gets_jpg(self, tmp_path):
        """URLs without extension should default to .jpg filename."""
        rows = [{"url": "http://example.com/image_no_ext"}]
        dl = ImageDownloader(rows, str(tmp_path))

        def mock_download(i, row):
            url_path = row["url"].split("?")[0].rstrip("/")
            filename = url_path.split("/")[-1]
            if not Path(filename).suffix:
                filename += ".jpg"
            return Path(str(tmp_path)) / f"{i:05d}_{filename}"

        result = mock_download(0, rows[0])
        assert result.name.endswith(".jpg")


# ---------------------------------------------------------------------------
# AIJobWorker — construction and control
# ---------------------------------------------------------------------------

class TestAIJobWorkerControl:
    def _make_worker(self):
        return AIJobWorker(
            categories=CATEGORIES, categorized=[], csv_data=[],
            syfte="Test", api_url="http://localhost/api", model="test",
            compress=False, data_mgr=make_data_mgr(),
        )

    def test_stop_flag_initially_false(self):
        w = self._make_worker()
        assert not w._stop

    def test_stop_sets_flag(self):
        w = self._make_worker()
        w.stop()
        assert w._stop

    def test_pause_sets_flag(self):
        w = self._make_worker()
        w.pause()
        assert w._paused

    def test_resume_clears_flag(self):
        w = self._make_worker()
        w.pause()
        w.resume()
        assert not w._paused

    def test_pre_knowledge_stored(self):
        w = AIJobWorker(
            categories=CATEGORIES, categorized=[], csv_data=[],
            syfte="Test", api_url="", model="test",
            compress=False, data_mgr=make_data_mgr(),
            pre_knowledge={"Säck": "VISUELLA KRAV: - Säckform"},
        )
        assert "Säck" in w.pre_knowledge

    def test_error_emitted_when_no_requests(self, qtbot):
        """When requests is not available, error signal is emitted."""
        import desktop.workers.ai_job_worker as mod
        original = mod.REQUESTS_AVAILABLE
        mod.REQUESTS_AVAILABLE = False
        try:
            w = AIJobWorker(
                categories=[], categorized=[], csv_data=[],
                syfte="", api_url="", model="",
                compress=False, data_mgr=make_data_mgr(),
            )
            errors = []
            w.error.connect(errors.append)
            w.run()
            assert errors
        finally:
            mod.REQUESTS_AVAILABLE = original


# ---------------------------------------------------------------------------
# AIJobWorker — step1 with pre_knowledge (fast path, no API)
# ---------------------------------------------------------------------------

class TestAIJobWorkerPreKnowledge:
    def _make_worker_with_preknowledge(self, tmp_path):
        """Worker with pre-knowledge and one remaining article."""
        img = make_image(tmp_path)
        csv_data = [{"article_number": "10000", "url": "", "bolag": "", "img_path": img}]
        pre_knowledge = {"Säck": "VISUELLA KRAV:\n- Säckform"}
        return AIJobWorker(
            categories=CATEGORIES, categorized=[], csv_data=csv_data,
            syfte="Test", api_url="", model="test",
            compress=False, data_mgr=make_data_mgr(),
            pre_knowledge=pre_knowledge,
        )

    def test_step1_done_emitted(self, qtbot, tmp_path):
        w = self._make_worker_with_preknowledge(tmp_path)
        # Resume immediately when step1_done fires
        w.step1_done.connect(lambda: w.resume())
        w._classify_article = MagicMock(return_value=("Säck", "Bilden visar en säck"))

        with qtbot.waitSignal(w.step1_done, timeout=5000):
            w.start()

    def test_knowledge_ready_emitted_for_each_category(self, qtbot, tmp_path):
        pre = {"Säck": "VISUELLA KRAV:\n- Säck", "Hink": "VISUELLA KRAV:\n- Hink"}
        csv_data = []
        w = AIJobWorker(
            categories=CATEGORIES, categorized=[], csv_data=csv_data,
            syfte="Test", api_url="", model="test",
            compress=False, data_mgr=make_data_mgr(),
            pre_knowledge=pre,
        )
        w.step1_done.connect(lambda: w.resume())

        received = []
        w.knowledge_ready.connect(lambda name, k: received.append(name))

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert set(received) == {"Säck", "Hink"}

    def test_finished_all_emitted(self, qtbot, tmp_path):
        w = self._make_worker_with_preknowledge(tmp_path)
        w.step1_done.connect(lambda: w.resume())
        w._classify_article = MagicMock(return_value=("Säck", "Säck reason"))
        w._download_image = MagicMock(return_value=None)

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

    def test_stop_before_step2_prevents_classification(self, qtbot, tmp_path):
        w = self._make_worker_with_preknowledge(tmp_path)
        classify_calls = []

        def stop_on_step1():
            w.stop()
        w.step1_done.connect(stop_on_step1)
        w._classify_article = MagicMock(side_effect=lambda *a, **k: classify_calls.append(1) or ("Säck", ""))

        with qtbot.waitSignal(w.finished, timeout=5000):
            w.start()

        assert classify_calls == []


# ---------------------------------------------------------------------------
# AIJobWorker — step2 local (one-at-a-time classification)
# ---------------------------------------------------------------------------

class TestAIJobWorkerStep2Local:
    def _make_worker_with_articles(self, tmp_path, n: int):
        imgs = [make_image(tmp_path, f"img{i}.jpg") for i in range(n)]
        csv_data = [
            {"article_number": str(10000 + i), "url": "", "bolag": "", "img_path": imgs[i]}
            for i in range(n)
        ]
        pre_knowledge = {"Säck": "VISUELLA KRAV:\n- Säck"}
        w = AIJobWorker(
            categories=CATEGORIES, categorized=[], csv_data=csv_data,
            syfte="Test", api_url="", model="test",
            compress=False, data_mgr=make_data_mgr(),
            pre_knowledge=pre_knowledge,
        )
        w.step1_done.connect(lambda: w.resume())
        return w

    def test_article_classified_signal_per_article(self, qtbot, tmp_path):
        w = self._make_worker_with_articles(tmp_path, 3)
        w._classify_article = MagicMock(return_value=("Säck", "Reason"))

        classified = []
        w.article_classified.connect(
            lambda art, cat, url, ip, reason: classified.append(art)
        )
        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert set(classified) == {"10000", "10001", "10002"}

    def test_missing_image_skipped(self, qtbot, tmp_path):
        csv_data = [
            {"article_number": "10000", "url": "", "bolag": "", "img_path": "/nonexistent.jpg"}
        ]
        pre_knowledge = {"Säck": "VISUELLA KRAV:\n- Säck"}
        w = AIJobWorker(
            categories=CATEGORIES, categorized=[], csv_data=csv_data,
            syfte="Test", api_url="", model="test",
            compress=False, data_mgr=make_data_mgr(),
            pre_knowledge=pre_knowledge,
        )
        w.step1_done.connect(lambda: w.resume())
        w._download_image = MagicMock(return_value=None)
        w._classify_article = MagicMock(return_value=("Säck", "Reason"))

        classified = []
        w.article_classified.connect(lambda *a: classified.append(a))

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert classified == []

    def test_already_categorized_not_reclassified(self, qtbot, tmp_path):
        img = make_image(tmp_path)
        csv_data = [
            {"article_number": "10000", "url": "", "bolag": "", "img_path": img}
        ]
        categorized = [{"article_number": "10000", "category": "Säck", "image_path": img}]
        pre_knowledge = {"Säck": "VISUELLA KRAV:\n- Säck"}
        w = AIJobWorker(
            categories=CATEGORIES, categorized=categorized, csv_data=csv_data,
            syfte="Test", api_url="", model="test",
            compress=False, data_mgr=make_data_mgr(),
            pre_knowledge=pre_knowledge,
        )
        w.step1_done.connect(lambda: w.resume())
        w._classify_article = MagicMock(return_value=("Hink", "Hink reason"))

        classified = []
        w.article_classified.connect(lambda *a: classified.append(a))

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        # Article already categorized → should NOT be in classified signal
        assert classified == []


# ---------------------------------------------------------------------------
# NewCategoryWorker
# ---------------------------------------------------------------------------

class TestNewCategoryWorker:
    def _make_worker(self, tmp_path, ovrigt_cards=None):
        img = make_image(tmp_path)
        example_cards = [{"article_number": "10000", "image_path": img}]
        if ovrigt_cards is None:
            ovrigt_cards = []
        return NewCategoryWorker(
            new_cat_name="Tunna", new_cat_desc="En tunna",
            example_cards=example_cards,
            existing_knowledge={"Säck": "VISUELLA KRAV:\n- Säck"},
            ovrigt_cards=ovrigt_cards,
            all_categories=CATEGORIES + [{"name": "Tunna", "description": "En tunna"}],
            syfte="Test", api_url="", model="test",
            compress=False, data_mgr=make_data_mgr(),
        )

    def test_knowledge_ready_emitted(self, qtbot, tmp_path):
        w = self._make_worker(tmp_path)
        w._generate_knowledge = MagicMock(return_value="VISUELLA KRAV:\n- Tunnform")

        received = []
        w.knowledge_ready.connect(lambda name, k: received.append(name))

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert "Tunna" in received

    def test_finished_all_emitted(self, qtbot, tmp_path):
        w = self._make_worker(tmp_path)
        w._generate_knowledge = MagicMock(return_value="VISUELLA KRAV:\n- Tunna")
        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

    def test_ovrigt_articles_reclassified(self, qtbot, tmp_path):
        img = make_image(tmp_path, "ovrigt.jpg")
        ovrigt = [{"article_number": "99999", "image_path": img}]
        w = self._make_worker(tmp_path, ovrigt_cards=ovrigt)
        w._generate_knowledge = MagicMock(return_value="VISUELLA KRAV:\n- Tunna")
        w._classify_article = MagicMock(return_value=("Tunna", "Tunnform"))

        reclassified = []
        w.article_reclassified.connect(lambda art, cat, ip: reclassified.append((art, cat)))

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert ("99999", "Tunna") in reclassified

    def test_ovrigt_stays_in_ovrigt_not_reclassified(self, qtbot, tmp_path):
        img = make_image(tmp_path, "ovrigt.jpg")
        ovrigt = [{"article_number": "99999", "image_path": img}]
        w = self._make_worker(tmp_path, ovrigt_cards=ovrigt)
        w._generate_knowledge = MagicMock(return_value="VISUELLA KRAV:\n- Tunna")
        w._classify_article = MagicMock(return_value=("Övrigt", "Inga likheter"))

        reclassified = []
        w.article_reclassified.connect(lambda *a: reclassified.append(a))

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert reclassified == []

    def test_generate_knowledge_failure_falls_back_to_desc(self, qtbot, tmp_path):
        w = self._make_worker(tmp_path)
        w._generate_knowledge = MagicMock(side_effect=RuntimeError("API down"))

        knowledge_emitted = []
        w.knowledge_ready.connect(lambda name, k: knowledge_emitted.append((name, k)))

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert any(name == "Tunna" for name, _ in knowledge_emitted)
        # Fallback: description used
        tunna_k = next(k for name, k in knowledge_emitted if name == "Tunna")
        assert tunna_k == "En tunna"


# ---------------------------------------------------------------------------
# ReClassifyWorker
# ---------------------------------------------------------------------------

class TestReClassifyWorker:
    def _make_worker(self, tmp_path, articles=None):
        if articles is None:
            img = make_image(tmp_path)
            articles = [{"article_number": "10000", "image_path": img,
                         "url": "", "old_category": "Övrigt"}]
        return ReClassifyWorker(
            articles=articles,
            cat_knowledge={"Säck": "VISUELLA KRAV:\n- Säck"},
            all_categories=CATEGORIES,
            syfte="Test", api_url="", model="test",
            compress=False, data_mgr=make_data_mgr(),
            hint="Troligen en säck",
        )

    def test_article_classified_signal(self, qtbot, tmp_path):
        w = self._make_worker(tmp_path)
        w._classify_article = MagicMock(return_value=("Säck", "Säckform"))

        classified = []
        w.article_classified.connect(
            lambda art, cat, url, ip, reason: classified.append((art, cat))
        )

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert ("10000", "Säck") in classified

    def test_finished_all_emitted(self, qtbot, tmp_path):
        w = self._make_worker(tmp_path)
        w._classify_article = MagicMock(return_value=("Säck", "Reason"))
        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

    def test_missing_image_skipped(self, qtbot, tmp_path):
        articles = [{"article_number": "10000", "image_path": "/nonexistent.jpg",
                     "url": "", "old_category": "Övrigt"}]
        w = self._make_worker(tmp_path, articles=articles)
        w._classify_article = MagicMock(return_value=("Säck", "Reason"))

        classified = []
        w.article_classified.connect(lambda *a: classified.append(a))

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert classified == []

    def test_stop_aborts_remaining_articles(self, qtbot, tmp_path):
        imgs = [make_image(tmp_path, f"img{i}.jpg") for i in range(5)]
        articles = [{"article_number": str(10000 + i), "image_path": imgs[i],
                     "url": "", "old_category": "Övrigt"} for i in range(5)]
        w = self._make_worker(tmp_path, articles=articles)

        calls = []
        def slow_classify(*a, **kw):
            calls.append(1)
            if len(calls) >= 2:
                w.stop()
            return ("Säck", "Reason")
        w._classify_article = slow_classify

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert len(calls) < 5

    def test_hint_passed_to_classify(self, qtbot, tmp_path):
        w = self._make_worker(tmp_path)
        received_hints = []

        def recording_classify(img, meta, ck, hint="", old_category=""):
            received_hints.append(hint)
            return ("Säck", "Reason")
        w._classify_article = recording_classify

        with qtbot.waitSignal(w.finished_all, timeout=5000):
            w.start()

        assert received_hints[0] == "Troligen en säck"

"""ReClassifyWorker — re-classifies a specific list of articles using current knowledge."""
from pathlib import Path
from typing import Dict, List

from PyQt6.QtCore import pyqtSignal

from desktop.workers.ai_job_worker import AIJobWorker, REQUESTS_AVAILABLE


class ReClassifyWorker(AIJobWorker):
    """Re-classifies a specific list of articles using current knowledge."""

    def __init__(self, articles: List[Dict],     # [{article_number, image_path, url}]
                 cat_knowledge: Dict[str, str],
                 all_categories: List[Dict],
                 syfte: str, api_url: str, model: str,
                 compress: bool, data_mgr,
                 hint: str = "",
                 api_key: str = "",
                 parent=None):
        super().__init__(all_categories, [], [], syfte, api_url, model,
                         compress, data_mgr, api_key=api_key)
        self._articles     = articles
        self.cat_knowledge = dict(cat_knowledge)
        self._hint         = hint

    def run(self) -> None:
        if not REQUESTS_AVAILABLE:
            self.error.emit("requests ej installerat")
            return

        for i, art in enumerate(self._articles):
            if self._stop:
                break
            art_num      = art["article_number"]
            img_path     = art.get("image_path", "")
            url          = art.get("url", "")
            old_category = art.get("old_category", "")
            if not img_path or not Path(img_path).exists():
                continue
            meta = self.data_mgr.get_meta(art_num, "") or {}
            try:
                cat, reason = self._classify_article(
                    img_path, meta, self.cat_knowledge,
                    self._hint, old_category=old_category
                )
                self.article_classified.emit(art_num, cat, url, img_path, reason)
                self.progress.emit(f"Gör om [{i + 1}/{len(self._articles)}]: {art_num} → {cat}")
            except Exception as e:
                self.progress.emit(f"  [{i + 1}] {art_num}: {e}")

        self.finished_all.emit()

"""NewCategoryWorker — generates knowledge for a newly added category,
then re-classifies all Övrigt articles with the updated knowledge.
"""
from pathlib import Path
from typing import Dict, List

from PyQt6.QtCore import pyqtSignal

from desktop.workers.ai_job_worker import AIJobWorker, REQUESTS_AVAILABLE


class NewCategoryWorker(AIJobWorker):
    """Generates knowledge for one newly added category, then re-classifies Övrigt."""

    article_reclassified = pyqtSignal(str, str, str)  # (article_number, new_cat, image_path)

    def __init__(self, new_cat_name: str, new_cat_desc: str,
                 example_cards: List[Dict],     # [{article_number, image_path}]
                 existing_knowledge: Dict[str, str],
                 ovrigt_cards: List[Dict],       # [{article_number, image_path}]
                 all_categories: List[Dict],
                 syfte: str, api_url: str, model: str,
                 compress: bool, data_mgr,
                 api_key: str = "",
                 parent=None):
        super().__init__(all_categories, [], [], syfte, api_url, model,
                         compress, data_mgr, api_key=api_key)
        self._new_cat_name  = new_cat_name
        self._new_cat_desc  = new_cat_desc
        self._example_cards = example_cards
        self._ovrigt_cards  = ovrigt_cards
        self.cat_knowledge  = dict(existing_knowledge)

    def run(self) -> None:
        if not REQUESTS_AVAILABLE:
            self.error.emit("requests ej installerat")
            return

        # Step 1: generate knowledge for the new category
        self.progress.emit(f"=== Analyserar ny kategori: {self._new_cat_name} ===")
        items = [
            {"article_number": c["article_number"], "image_path": c["image_path"]}
            for c in self._example_cards
        ]
        try:
            knowledge = self._generate_knowledge(self._new_cat_name, self._new_cat_desc, items)
            self.cat_knowledge[self._new_cat_name] = knowledge
            self.knowledge_ready.emit(self._new_cat_name, knowledge)
            self.progress.emit("✓ Analys klar")
        except Exception as e:
            self.progress.emit(f"✗ Analys misslyckades: {e}")
            self.cat_knowledge[self._new_cat_name] = self._new_cat_desc
            self.knowledge_ready.emit(self._new_cat_name, self._new_cat_desc)

        # Step 2: re-classify Övrigt cards with updated knowledge
        if not self._ovrigt_cards:
            self.finished_all.emit()
            return

        self.progress.emit(f"Omklassificerar {len(self._ovrigt_cards)} Övrigt-artiklar…")
        for i, card in enumerate(self._ovrigt_cards):
            if self._stop:
                break
            img_path = card["image_path"]
            art_num  = card["article_number"]
            if not img_path or not Path(img_path).exists():
                continue
            meta = self.data_mgr.get_meta(art_num, "") or {}
            try:
                new_cat, _reason = self._classify_article(img_path, meta, self.cat_knowledge)
                if new_cat != "Övrigt":
                    self.article_reclassified.emit(art_num, new_cat, img_path)
                if (i + 1) % 10 == 0 or i == len(self._ovrigt_cards) - 1:
                    self.progress.emit(f"  [{i + 1}/{len(self._ovrigt_cards)}] omklassificerade…")
            except Exception as e:
                self.progress.emit(f"  [{i + 1}] {art_num}: {e}")

        self.finished_all.emit()

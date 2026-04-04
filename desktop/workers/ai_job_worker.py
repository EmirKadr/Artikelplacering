"""AIJobWorker — QThread that runs the two-step AI classification job.

Step 1: Generate category knowledge summaries via LLM.
Step 2: Classify remaining articles using those summaries.

All heavy logic is delegated to core.* modules; this class is responsible
only for threading, signal emission, and orchestration.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from PyQt6.QtCore import QThread, pyqtSignal

from core.constants import (
    AI_PARALLEL_WORKERS, EXT_BATCH_SIZE, MAX_EXAMPLES_PER_CAT, MAX_OVRIGT_EXAMPLES
)

_logger = logging.getLogger(__name__)

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class AIJobWorker(QThread):
    """Two-step AI classification job thread.

    Step 1 — Category knowledge: For each non-Övrigt category, collect up to
    MAX_EXAMPLES_PER_CAT manually classified articles and ask the LLM to
    summarise what they have in common.

    Step 2 — Classify remaining: For every article in csv_data that has not
    yet been manually classified, download its image and classify it using the
    summaries from step 1.
    """

    progress           = pyqtSignal(str)
    knowledge_ready    = pyqtSignal(str, str)             # (category_name, knowledge_text)
    step1_done         = pyqtSignal()
    article_classified = pyqtSignal(str, str, str, str, str)  # (art_num, cat, url, img_path, reason)
    finished_all       = pyqtSignal()
    error              = pyqtSignal(str)

    def __init__(self, categories, categorized, csv_data, syfte,
                 api_url, model, compress, data_mgr,
                 api_key: str = "",
                 pre_knowledge: Optional[Dict] = None,
                 pre_example_articles: Optional[Dict] = None,
                 parent=None):
        super().__init__(parent)
        self.categories          = categories
        self.categorized         = categorized
        self.csv_data            = csv_data
        self.syfte               = syfte
        self.api_url             = api_url
        self.model               = model
        self.compress            = compress
        self.data_mgr            = data_mgr
        self.api_key             = api_key
        self.pre_knowledge       = pre_knowledge or {}
        self.pre_example_articles = pre_example_articles or {}
        self._stop               = False
        self._paused             = False

    # ── control ─────────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._stop = True

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def _wait_if_paused(self) -> None:
        while self._paused and not self._stop:
            time.sleep(0.1)

    # ── API helpers ─────────────────────────────────────────────────────────

    def _call_api(self, payload: Dict,
                  timeout: Union[int, Tuple] = (5, 60),
                  wait_msg: Optional[str] = None) -> Dict:
        from core.ai_client import call_api
        return call_api(
            payload,
            api_url=self.api_url,
            api_key=self.api_key,
            timeout=timeout,
            wait_msg=wait_msg,
            progress_cb=self.progress.emit,
            stop_flag=lambda: self._stop,
        )

    def _sleep_interruptible(self, seconds: float) -> None:
        from core.ai_client import _sleep_interruptible
        _sleep_interruptible(seconds, stop_flag=lambda: self._stop)

    def _encode(self, path: str) -> Tuple[str, str]:
        from core.image_utils import encode_image
        return encode_image(path, compress=self.compress)

    def _download_image(self, url: str) -> Optional[str]:
        from core.image_utils import download_image
        return download_image(url)

    # ── knowledge helpers ────────────────────────────────────────────────────

    def _generate_knowledge(self, cat_name: str, cat_desc: str,
                             items: List[Dict]) -> str:
        from core.knowledge_gen import generate_knowledge
        return generate_knowledge(
            cat_name, cat_desc, items, self.syfte, self.model,
            self.data_mgr,
            call_api_fn=lambda p, **kw: self._call_api(p, **kw),
            encode_fn=lambda path, compress: self._encode(path),
            compress=self.compress,
        )

    def _generate_ovrigt_knowledge(self, items: List[Dict]) -> str:
        from core.knowledge_gen import generate_ovrigt_knowledge
        return generate_ovrigt_knowledge(
            items, self.syfte, self.model, self.data_mgr,
            call_api_fn=lambda p, **kw: self._call_api(p, **kw),
            encode_fn=lambda path, compress: self._encode(path),
            compress=self.compress,
        )

    def _generate_all_knowledge_external(self, by_cat: Dict[str, List[Dict]],
                                          categories: List[Dict]) -> Dict[str, str]:
        from core.knowledge_gen import generate_all_knowledge_external
        return generate_all_knowledge_external(
            by_cat, categories, self.syfte, self.model, self.data_mgr,
            call_api_fn=lambda p, **kw: self._call_api(p, **kw),
            encode_fn=lambda path, compress: self._encode(path),
            compress=self.compress,
            progress_cb=self.progress.emit,
            stop_flag=lambda: self._stop,
        )

    # ── classification helpers ───────────────────────────────────────────────

    def _classify_batch(self, articles: List[Tuple[int, str, str, Dict]],
                        cat_knowledge: Dict[str, str]) -> List[Tuple[int, str, str, str]]:
        from core.classifier_core import classify_batch
        return classify_batch(
            articles, cat_knowledge, self.categories, self.syfte, self.model,
            call_api_fn=lambda p, **kw: self._call_api(p, **kw),
            encode_fn=lambda path, compress: self._encode(path),
            cat_example_images=getattr(self, "cat_example_images", {}),
            progress_cb=self.progress.emit,
        )

    def _classify_article(self, img_path: str, meta: Dict,
                           cat_knowledge: Dict[str, str],
                           hint: str = "",
                           old_category: str = "") -> Tuple[str, str]:
        from core.classifier_core import classify_article
        return classify_article(
            img_path, meta, self.categories, cat_knowledge,
            self.syfte, self.model,
            call_api_fn=lambda p, **kw: self._call_api(p, **kw),
            encode_fn=lambda path, compress: self._encode(path),
            cat_example_images=getattr(self, "cat_example_images", {}),
            hint=hint,
            old_category=old_category,
        )

    # ── main run ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        if not REQUESTS_AVAILABLE:
            self.error.emit("requests ej installerat")
            return

        self.cat_knowledge: Dict[str, str] = {}
        self.cat_example_images: Dict[str, List[str]] = {}
        self.cat_example_articles: Dict[str, List[str]] = {}
        cat_knowledge = self.cat_knowledge

        # Collect example images from categorized items
        by_cat: Dict[str, List[Dict]] = {}
        for item in self.categorized:
            cat = item.get("category", "")
            if cat and cat != "Övrigt":
                by_cat.setdefault(cat, []).append(item)
            if cat:
                imgs = self.cat_example_images.setdefault(cat, [])
                arts = self.cat_example_articles.setdefault(cat, [])
                if len(imgs) < 2:
                    p = item.get("image_path", "")
                    if p and Path(p).exists():
                        imgs.append(p)
                        arts.append(str(item.get("article_number", "")))

        # ── Step 1: category knowledge ─────────────────────────────────────
        if self.pre_knowledge:
            self.progress.emit("=== Steg 1: Använder sparad kategorikunskap ===")
            for name, knowledge in self.pre_knowledge.items():
                cat_knowledge[name] = knowledge
                self.knowledge_ready.emit(name, knowledge)
                self.progress.emit(f"  ✓ {name} (importerad)")
            if self.pre_example_articles:
                self.cat_example_articles = dict(self.pre_example_articles)
        elif self.api_key:
            self._run_step1_external(by_cat, cat_knowledge)
        else:
            self._run_step1_local(by_cat, cat_knowledge)

        self.progress.emit("\n✓ Kategorikunskap klar — väntar på godkännande…")
        self.step1_done.emit()
        self._paused = True
        self._wait_if_paused()
        if self._stop:
            return

        # ── Step 2: classify remaining articles ────────────────────────────
        self.progress.emit("\n=== Steg 2: Klassificerar återstående artiklar ===")
        classified_numbers = {
            e.get("article_number", "") for e in self.categorized
            if e.get("article_number")
        }
        remaining = [
            row for row in self.csv_data
            if str(row.get("article_number", "")) not in classified_numbers
        ]
        if not remaining:
            self.progress.emit("Inga återstående artiklar.")
            self.finished_all.emit()
            return

        if self.api_key:
            self._run_step2_external(remaining, cat_knowledge)
        else:
            self._run_step2_local(remaining, cat_knowledge)

        self.finished_all.emit()

    # ── Step 1 implementations ───────────────────────────────────────────────

    def _run_step1_external(self, by_cat: Dict, cat_knowledge: Dict) -> None:
        self.progress.emit("=== Steg 1: Genererar kategorikunskap (externt API) ===")
        cats_for_analysis = []
        for cat in self.categories:
            name = cat["name"]
            if name == "Övrigt":
                continue
            items = by_cat.get(name, [])[:MAX_EXAMPLES_PER_CAT]
            has_img = any(
                item.get("image_path") and Path(item["image_path"]).exists()
                for item in items
            ) if items else False
            if has_img:
                cats_for_analysis.append(cat)
                self.progress.emit(f"  ✓ {name} — {len(items)} artiklar med bilder")
            else:
                cat_knowledge[name] = cat.get("description", "")
                self.progress.emit(f"  ⏭ {name} — inga bilder ännu")

        if cats_for_analysis:
            self.progress.emit(f"  Skickar {len(cats_for_analysis)} kategorier…")
            try:
                result = self._generate_all_knowledge_external(by_cat, cats_for_analysis)
                for name, knowledge in result.items():
                    cat_knowledge[name] = knowledge
                    self.knowledge_ready.emit(name, knowledge)
                    self.progress.emit(f"  ✓ {name} klar")
                for cat in cats_for_analysis:
                    if cat["name"] not in result:
                        cat_knowledge[cat["name"]] = cat.get("description", "")
                        self.progress.emit(f"  ⚠ {cat['name']} — inget svar")
            except Exception as e:
                self.progress.emit(f"  ✗ Fel: {e}")
                for cat in cats_for_analysis:
                    cat_knowledge[cat["name"]] = cat.get("description", "")

        ovrigt_items = by_cat.get("Övrigt", [])[:MAX_OVRIGT_EXAMPLES]
        if ovrigt_items:
            self.progress.emit(f"  Analyserar Övrigt ({len(ovrigt_items)} artiklar)…")
            try:
                knowledge = self._generate_ovrigt_knowledge(ovrigt_items)
                cat_knowledge["Övrigt"] = knowledge
                self.knowledge_ready.emit("Övrigt", knowledge)
                self.progress.emit("  ✓ Övrigt klar")
            except Exception as e:
                self.progress.emit(f"  ✗ Övrigt: {e}")

    def _run_step1_local(self, by_cat: Dict, cat_knowledge: Dict) -> None:
        self.progress.emit("=== Steg 1: Genererar kategorikunskap ===")
        for cat in self.categories:
            if self._stop:
                return
            name = cat["name"]
            if name == "Övrigt":
                ovrigt_items = by_cat.get("Övrigt", [])[:MAX_OVRIGT_EXAMPLES]
                if ovrigt_items:
                    self.progress.emit(f"  Analyserar Övrigt ({len(ovrigt_items)} artiklar)…")
                    try:
                        knowledge = self._generate_ovrigt_knowledge(ovrigt_items)
                        cat_knowledge["Övrigt"] = knowledge
                        self.knowledge_ready.emit("Övrigt", knowledge)
                        self.progress.emit("  ✓ Övrigt klar")
                    except Exception as e:
                        self.progress.emit(f"  ✗ Övrigt: {e}")
                        cat_knowledge["Övrigt"] = cat.get("description", "")
                continue
            items = by_cat.get(name, [])[:MAX_EXAMPLES_PER_CAT]
            if not items:
                self.progress.emit(f"  Hoppar {name} — inga exempelartiklar")
                cat_knowledge[name] = cat.get("description", "")
                continue
            self.progress.emit(f"  Analyserar {name} ({len(items)} artiklar)…")
            try:
                knowledge = self._generate_knowledge(name, cat.get("description", ""), items)
                cat_knowledge[name] = knowledge
                self.knowledge_ready.emit(name, knowledge)
                self.progress.emit(f"  ✓ {name} klar")
            except Exception as e:
                self.progress.emit(f"  ✗ {name}: {e}")
                cat_knowledge[name] = cat.get("description", "")

    # ── Step 2 implementations ───────────────────────────────────────────────

    def _run_step2_external(self, remaining: List[Dict], cat_knowledge: Dict) -> None:
        self.progress.emit(f"  {len(remaining)} artiklar (batch om {EXT_BATCH_SIZE})…")
        done_count = 0
        total = len(remaining)
        batch: List[Tuple[int, str, str, Dict]] = []

        for i, row in enumerate(remaining):
            if self._stop:
                return
            self._wait_if_paused()
            art_num  = str(row.get("article_number", ""))
            url      = row.get("url", "")
            bolag    = row.get("bolag", "")
            img_path = row.get("img_path", "")
            if not img_path or not Path(img_path).exists():
                img_path = self._download_image(url)
            if not img_path:
                done_count += 1
                self.progress.emit(f"  [{done_count}/{total}] {art_num}: bild saknas — hoppar")
                continue
            meta = self.data_mgr.get_meta(art_num, bolag) or {}
            batch.append((i, art_num, img_path, meta))

            if len(batch) >= EXT_BATCH_SIZE:
                if self._stop:
                    return
                self._flush_batch(batch, remaining, cat_knowledge, done_count, total)
                done_count += len(batch)
                batch = []

        if batch and not self._stop:
            self._flush_batch(batch, remaining, cat_knowledge, done_count, total)

    def _flush_batch(self, batch, remaining, cat_knowledge, done_count, total):
        try:
            batch_img = {art_num_b: ip_b for _, art_num_b, ip_b, _ in batch}
            results = self._classify_batch(batch, cat_knowledge)
            for idx, art_num_r, category, reason in results:
                row_r = remaining[idx]
                url_r = row_r.get("url", "")
                ip_r  = batch_img.get(art_num_r, row_r.get("img_path", ""))
                self.article_classified.emit(art_num_r, category, url_r, ip_r, reason)
                done_count += 1
                self.progress.emit(f"  [{done_count}/{total}] {art_num_r} → {category}")
        except Exception as e:
            self.progress.emit(f"  batch-fel: {e}")

    def _run_step2_local(self, remaining: List[Dict], cat_knowledge: Dict) -> None:
        self.progress.emit(f"  {len(remaining)} artiklar ({AI_PARALLEL_WORKERS} parallella)…")
        done_count = 0
        total = len(remaining)

        def _classify_one(i: int, row: Dict):
            if self._stop:
                return None
            art_num  = str(row.get("article_number", ""))
            url      = row.get("url", "")
            bolag    = row.get("bolag", "")
            img_path = row.get("img_path", "")
            if not img_path or not Path(img_path).exists():
                img_path = self._download_image(url)
            if not img_path:
                return ("skip", i, art_num, None, None, url, None)
            meta = self.data_mgr.get_meta(art_num, bolag) or {}
            category, reason = self._classify_article(img_path, meta, cat_knowledge)
            return ("ok", i, art_num, category, reason, url, img_path)

        with ThreadPoolExecutor(max_workers=AI_PARALLEL_WORKERS) as executor:
            futures = {}
            for i, row in enumerate(remaining):
                if self._stop:
                    break
                self._wait_if_paused()
                f = executor.submit(_classify_one, i, row)
                futures[f] = i

            for future in as_completed(futures):
                if self._stop:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return
                try:
                    result = future.result()
                    if result is None:
                        continue
                    status, i, art_num, category, reason, url, img_path = result
                    done_count += 1
                    if status == "skip":
                        self.progress.emit(f"  [{done_count}/{total}] {art_num}: bild saknas")
                    else:
                        self.article_classified.emit(art_num, category, url, img_path, reason)
                        if done_count % 20 == 0 or done_count == total:
                            self.progress.emit(f"  [{done_count}/{total}] klassificerade…")
                except Exception as e:
                    done_count += 1
                    self.progress.emit(f"  [{done_count}/{total}] fel: {e}")

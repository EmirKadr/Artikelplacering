"""Category knowledge generation — asks LLM to summarise what articles have in common.

No PyQt6 imports — importable without Qt installed.

All functions take explicit parameters instead of `self` so they can be called
from both Qt workers and pure-Python services/tests.
"""
import logging
import re as _re
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.constants import EXT_IMAGES_PER_CAT, MAX_EXAMPLES_PER_CAT

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_think_blocks(text: str) -> str:
    """Remove <think>…</think> reasoning blocks from LLM output."""
    text = _re.sub(r'<think>[\s\S]*?</think>', '', text).strip()
    if '<think>' in text:
        text = text.split('</think>')[-1] if '</think>' in text else ''
    return text.strip()


def _article_meta_lines(item: Dict, idx: int, data_mgr, indent: str = "  ") -> str:
    """Format a single article's metadata as a human-readable string block."""
    art_num = str(item.get("article_number", ""))
    meta = data_mgr.get_meta(art_num, "") or {} if art_num else {}
    parts = [f"Artikel {idx + 1}:"]
    if meta.get("beskrivning"):
        parts.append(f"{indent}Beskrivning: {meta['beskrivning']}")
    dims = []
    if meta.get("langd"): dims.append(f"längd {meta['langd']} mm")
    if meta.get("bredd"): dims.append(f"bredd {meta['bredd']} mm")
    if meta.get("hojd"):  dims.append(f"höjd {meta['hojd']} mm")
    if dims:
        parts.append(f"{indent}Mått: {', '.join(dims)}")
    if meta.get("volym"):
        parts.append(f"{indent}Volym: {meta['volym']}")
    vikt = []
    if meta.get("vikt_brutto"): vikt.append(f"brutto {meta['vikt_brutto']} kg")
    if meta.get("vikt_netto"):  vikt.append(f"netto {meta['vikt_netto']} kg")
    if vikt:
        parts.append(f"{indent}Vikt: {', '.join(vikt)}")
    if meta.get("ean"):
        parts.append(f"{indent}EAN: {meta['ean']}")
    if meta.get("enhet"):
        parts.append(f"{indent}Enhet: {meta['enhet']}")
    if meta.get("faktor"):
        parts.append(f"{indent}Faktor: {meta['faktor']}")
    if meta.get("store_quantity"):
        parts.append(f"{indent}Butikskvantitet: {meta['store_quantity']}")
    return "\n".join(parts)


def _category_prompt(cat_name: str, cat_desc: str, syfte: str,
                     article_lines: List[str], n_imgs: int) -> str:
    return "\n".join([
        f"Syfte: {syfte}", "",
        f"Kategori: {cat_name}",
        f"Beskrivning: {cat_desc}" if cat_desc else "",
        "",
        f"OBS: Kategorinamnet '{cat_name}' är viktigt — det beskriver direkt vad som tillhör kategorin.",
        "Ta hänsyn till vad namnet bokstavligen säger (t.ex. vikt, storlek, förpackningstyp).",
        "",
        f"Nedan följer {len(article_lines)} exempelartiklar i kategorin.",
        f"Bilderna nedan visar {n_imgs} representativa artiklar ur kategorin.",
        "\n\n".join(article_lines),
        "",
        "UPPGIFT: Beskriv denna kategoris visuella krav, stödjande metadata och tydliga uteslutningar.",
        "",
        "VIKTIGA PRINCIPER:",
        "- Identifiera först vilken FYSISK FORM eller förpackningstyp som är mest typisk.",
        "- Beskriv sedan vilka metadata som ofta förekommer som stöd.",
        "- Undvik att definiera kategorin främst utifrån vikt, volym eller innehåll — den visuella formen väger tyngst.",
        "- Produktens INNEHÅLL (foder, salt, godis, kemikalier etc.) är INTE ett krav för kategorin.",
        "  Kategorin bestäms av förpackningstyp, inte av vad som är i förpackningen.",
        "- Skriv vad som KRÄVS, inte bara vad som är vanligt. Använd ordet 'måste' för visuella krav.",
        "- Om underlaget är litet (1-2 exempel), generalisera försiktigt.",
        "  Utgå främst från tydlig fysisk form. Undvik snäva slutsatser baserade enbart på vikt eller produktnamn.",
        "",
        "Svara i EXAKT detta format:",
        "",
        "VISUELLA KRAV:",
        "- [vad som måste synas i bilden för att artikeln ska höra hit]",
        "- ...",
        "STÖDJANDE METADATA:",
        "- [vikt, mått, volym, text som ofta förekommer men inte får styra ensam]",
        "- ...",
        "FÅR INTE INKLUDERA:",
        "- [vad som INTE hör hit även om metadata liknar]",
        "- ...",
        "KORT REGEL:",
        "- [en mening som sammanfattar kategorin]",
    ])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_knowledge(
    cat_name: str,
    cat_desc: str,
    items: List[Dict],
    syfte: str,
    model: str,
    data_mgr,
    call_api_fn: Callable,
    encode_fn: Callable,
    compress: bool = False,
) -> str:
    """Generate AI knowledge summary for one category.

    Args:
        cat_name:    Category name.
        cat_desc:    Category description (may be empty).
        items:       Example article dicts with 'article_number' and 'image_path'.
        syfte:       Classification purpose string.
        model:       LLM model name.
        data_mgr:    DataManager instance for metadata lookup.
        call_api_fn: Callable matching core.ai_client.call_api signature.
        encode_fn:   Callable(path, compress) → (b64, mime).
        compress:    Whether to compress images.

    Returns:
        Knowledge text string.
    """
    article_lines = []
    representative_imgs: List[str] = []

    for idx, item in enumerate(items):
        article_lines.append(_article_meta_lines(item, idx, data_mgr))
        if len(representative_imgs) < EXT_IMAGES_PER_CAT:
            p = item.get("image_path", "")
            if p and Path(p).exists():
                representative_imgs.append(p)

    prompt = _category_prompt(cat_name, cat_desc, syfte, article_lines,
                              len(representative_imgs))

    content: List[Dict] = []
    for img_path in representative_imgs:
        try:
            b64, mime = encode_fn(img_path, compress)
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"}})
        except (IOError, OSError, ValueError) as _e:
            _logger.warning("Kunde inte koda bild %s: %s", img_path, _e)
    content.append({"type": "text", "text": prompt})

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2000,
        "temperature": 0.3,
    }
    raw = call_api_fn(payload, timeout=(5, 120),
                      wait_msg="    ⏳ Väntar på svar från AI (kunskapsgenerering)…"
                      )["choices"][0]["message"]["content"].strip()
    return _strip_think_blocks(raw)


def generate_ovrigt_knowledge(
    items: List[Dict],
    syfte: str,
    model: str,
    data_mgr,
    call_api_fn: Callable,
    encode_fn: Callable,
    compress: bool = False,
) -> str:
    """Generate a description of what makes articles belong to 'Övrigt'."""
    article_lines = []
    representative_imgs: List[str] = []

    for idx, item in enumerate(items):
        article_lines.append(_article_meta_lines(item, idx, data_mgr))
        p = item.get("image_path", "")
        if p and Path(p).exists() and len(representative_imgs) < 3:
            representative_imgs.append(p)

    prompt = "\n".join([
        f"Syfte: {syfte}", "",
        "Kategori: Övrigt",
        "",
        f"Nedan följer {len(items)} artiklar som klassificerats som 'Övrigt' —",
        "dvs. artiklar som INTE passade in i någon annan specifik kategori.",
        "",
        "\n\n".join(article_lines),
        "",
        "Analysera dessa artiklar och beskriv:",
        "1. Vilka TYPER av artiklar som hamnar i Övrigt (t.ex. produktkategorier, storlekar, förpackningstyper).",
        "2. Vad som UTMÄRKER Övrigt-artiklar — varför passar de inte i de andra kategorierna?",
        "3. Konkreta VARNINGSSIGNALER — vilka egenskaper hos en artikel tyder på att den bör klassas som Övrigt",
        "   snarare än i en specifik kategori?",
        "",
        "Svara på svenska med 8–12 meningar. Var konkret och specifik.",
    ])

    content: List[Dict] = []
    for img_path in representative_imgs:
        try:
            b64, mime = encode_fn(img_path, compress)
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"}})
        except (IOError, OSError, ValueError) as _e:
            _logger.warning("Kunde inte koda bild %s: %s", img_path, _e)
    content.append({"type": "text", "text": prompt})

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 900,
        "temperature": 0.3,
    }
    return call_api_fn(
        payload, timeout=(5, 120),
        wait_msg="    ⏳ Väntar på svar från AI (Övrigt-kunskapsgenerering)…"
    )["choices"][0]["message"]["content"].strip()


def generate_all_knowledge_external(
    by_cat: Dict[str, List[Dict]],
    categories: List[Dict],
    syfte: str,
    model: str,
    data_mgr,
    call_api_fn: Callable,
    encode_fn: Callable,
    compress: bool = False,
    progress_cb: Optional[Callable[[str], None]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
) -> Dict[str, str]:
    """Generate knowledge for each category with one API call per category.

    Returns:
        dict of {cat_name: knowledge_text} — only categories with images included.
    """
    def _emit(msg: str):
        if progress_cb:
            progress_cb(msg)

    cats_with_images = []
    for cat in categories:
        name = cat["name"]
        items = by_cat.get(name, [])[:MAX_EXAMPLES_PER_CAT]
        if not items:
            continue
        has_img = any(
            item.get("image_path") and Path(item["image_path"]).exists()
            for item in items
        )
        if has_img:
            cats_with_images.append((cat, items))

    if not cats_with_images:
        return {}

    result: Dict[str, str] = {}

    for cat_idx, (cat, items) in enumerate(cats_with_images, start=1):
        if stop_flag and stop_flag():
            break

        name = cat["name"]
        desc = cat.get("description", "")
        _emit(f"  Steg 1 ({cat_idx}/{len(cats_with_images)}): genererar kunskap för '{name}'…")
        _logger.info("Extern kunskapsgenerering kategori %d/%d: %s", cat_idx, len(cats_with_images), name)

        article_lines = []
        representative_imgs: List[str] = []
        for idx, item in enumerate(items):
            article_lines.append(_article_meta_lines(item, idx, data_mgr, indent="    "))
            if len(representative_imgs) < EXT_IMAGES_PER_CAT:
                p = item.get("image_path", "")
                if p and Path(p).exists():
                    representative_imgs.append(p)

        prompt = _category_prompt(name, desc, syfte, article_lines, len(representative_imgs))

        content: List[Dict] = []
        for img_path in representative_imgs:
            try:
                b64, mime = encode_fn(img_path, compress)
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"}})
            except (IOError, OSError, ValueError) as _e:
                _logger.warning("Kunde inte koda bild %s: %s", img_path, _e)
        content.append({"type": "text", "text": prompt})

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Svara direkt med analysen i det begärda formatet. "
                 "Ingen inledning, inga resonemang, tänk INTE högt."},
                {"role": "user", "content": content},
            ],
            "max_tokens": 2000,
            "temperature": 0.3,
        }

        try:
            resp = call_api_fn(
                payload, timeout=(5, 120),
                wait_msg=f"    ⏳ Väntar på svar för '{name}'…"
            )
            finish_reason = resp["choices"][0].get("finish_reason", "unknown")
            raw = resp["choices"][0]["message"]["content"].strip()
            raw = _strip_think_blocks(raw)
            _logger.debug("Steg 1 '%s' svar (%d tecken, finish_reason=%s)",
                          name, len(raw), finish_reason)
            result[name] = raw
            _emit(f"    ✓ '{name}' klar ({len(raw)} tecken)")
        except Exception as _e:
            _logger.warning("Kunskapsgenerering misslyckades för '%s': %s", name, _e)
            _emit(f"    ⚠ '{name}' misslyckades: {_e}")

    return result

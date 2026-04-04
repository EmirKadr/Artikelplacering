"""Article classification — calls LLM to assign categories to articles.

No PyQt6 imports — importable without Qt installed.

Functions take explicit parameters (DI) so they are testable without Qt.
"""
import logging
import re as _re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from core.knowledge_gen import _strip_think_blocks

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# classify_batch
# ---------------------------------------------------------------------------

def classify_batch(
    articles: List[Tuple[int, str, str, Dict]],
    cat_knowledge: Dict[str, str],
    categories: List[Dict],
    syfte: str,
    model: str,
    call_api_fn: Callable,
    encode_fn: Callable,
    cat_example_images: Optional[Dict[str, List[str]]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> List[Tuple[int, str, str, str]]:
    """Classify a batch of articles in a single API call.

    Args:
        articles:           List of (index, article_number, image_path, meta_dict).
        cat_knowledge:      {cat_name: knowledge_text}.
        categories:         List of {name, description} dicts.
        syfte:              Classification purpose string.
        model:              LLM model name.
        call_api_fn:        core.ai_client.call_api-compatible callable.
        encode_fn:          (path, compress) → (b64, mime).
        cat_example_images: {cat_name: [image_path, ...]}.
        progress_cb:        Callable for progress messages.

    Returns:
        List of (index, article_number, category, reason).
    """
    cat_example_images = cat_example_images or {}

    def _emit(msg: str):
        if progress_cb:
            progress_cb(msg)

    cat_names = [c["name"] for c in categories if c["name"] != "Övrigt"]
    all_names = cat_names + ["Övrigt"]
    names_str = ", ".join(all_names)

    cat_parts = []
    for name in cat_names:
        knowledge = cat_knowledge.get(name, "")
        if knowledge:
            cat_parts.append(f"KATEGORI: {name}\n{knowledge}")
        else:
            cat_parts.append(f"KATEGORI: {name}")
    cat_parts.append("KATEGORI: Övrigt\nKORT REGEL:\n- Artikel som inte tydligt tillhör någon annan kategori.")
    cat_block = "\n\n".join(cat_parts)

    intro = "\n".join([
        "DU ÄR EN KLASSIFICERARE. Svara BARA med klassificeringsrader, INGEN annan text.",
        "",
        f"Syfte: {syfte}", "",
        f"Klassificera {len(articles)} artiklar. Varje artikel har en bild och metadata.",
        "",
        "KATEGORIER:",
        cat_block, "",
        "PRIORITETSORDNING:",
        "1. Bildens visuella form och fysiska typ/förpackning",
        "2. Produktbeskrivning och titel",
        "3. Vikt",
        "4. Mått och volym",
        "5. Övrig metadata",
        "",
        "GENERELLA REGLER:",
        "- Välj exakt en kategori per artikel.",
        "- Om bilden tydligt visar en viss fysisk typ eller förpackning ska den väga tyngst.",
        "- Metadata används främst för att bekräfta klassificeringen eller skilja mellan liknande kategorier.",
        "- Om flera kategorier liknar varandra ska den mest specifika kategorin väljas.",
        "- Om flera kategorier beskriver samma huvudtyp men delas upp av vikt, storlek eller annan metadata:",
        "  1. identifiera först huvudtypen från bilden",
        "  2. välj sedan rätt underkategori med hjälp av metadata",
        "- Tolka INTE varumärken eller produktnamn som beskrivning av förpackningstyp.",
        "  T.ex. 'LIKIT' är ett varumärke, inte 'flytande'. Utgå från bilden och enheten (kg = fast, liter = vätska).",
        "- Om vikten anges i kg är produkten sannolikt fast/torr, inte flytande.",
        "- Produktens innehåll (foder, salt, godis etc.) ska INTE styra kategori — det är FÖRPACKNINGSTYPEN som avgör.",
        "  En säck med salt hör till samma kategori som en säck med foder om förpackningen ser likadan ut.",
        "- STÖDJANDE METADATA i kategorikunskapen är just stödjande — inte krav. Bryt aldrig mot det visuella valet",
        "  bara för att innehållet eller användningsområdet skiljer sig från exemplen.",
        "- Om ingen kategori passar tydligt, välj Övrigt.",
        "- ORSAK ska ALLTID börja med \"Bilden visar [förpackningsform].\"",
        "  Om bilden inte visar en förpackning (t.ex. råvara, växt, löst innehåll, djur),",
        "  skriv \"Bilden visar ej förpackning.\" och använd metadata som fallback.",
        "",
        "KLASSIFICERINGSMETOD:",
        "1. TITTA PÅ BILDEN FÖRST — identifiera artikelns fysiska typ, form eller förpackning utifrån det som syns i bilden.",
        "2. Använd produktbeskrivning och titel för att bekräfta eller förtydliga.",
        "3. Använd vikt, mått och övrig metadata för att välja rätt underkategori om det finns flera liknande.",
        "4. Om bilden tydligt visar en viss produkttyp, klassificera den som det",
        "   ÄVEN OM vikten eller måtten bättre matchar en annan kategori.",
        "",
        "SVARSFORMAT (exakt en rad per artikel, inget annat):",
        f"ARTIKEL 1: KATEGORI: [ett av: {names_str}] | ORSAK: Bilden visar [förpackningsform]. [Kort motivering]",
        f"ARTIKEL 2: KATEGORI: [ett av: {names_str}] | ORSAK: Bilden visar [förpackningsform]. [Kort motivering]",
        "...osv för alla artiklar.",
        "",
        "Artiklarna följer nedan:",
        "---",
    ])
    content: List[Dict] = [{"type": "text", "text": intro}]

    # Add example images per category
    _ex_count = 0
    for name in cat_names:
        for ep in cat_example_images.get(name, []):
            try:
                b64_ex, mime_ex = encode_fn(ep, False)
                content.append({"type": "text", "text": f"[Exempelbild — {name}]"})
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:{mime_ex};base64,{b64_ex}"}})
                _ex_count += 1
            except (IOError, OSError, ValueError) as _e:
                _logger.warning("Kunde inte koda exempelbild %s: %s", ep, _e)
    if _ex_count:
        content.append({"type": "text",
                        "text": f"\nOvan visades {_ex_count} exempelbilder från kategorierna. "
                                "Använd dem som visuell referens.\n---"})

    for seq, (idx, art_num, img_path, meta) in enumerate(articles, 1):
        art_lines = [f"ARTIKEL {seq} (artikelnr: {art_num}):"]
        if meta.get("beskrivning"):
            art_lines.append(f"  Beskrivning: {meta['beskrivning']}")
        dims = []
        if meta.get("langd"): dims.append(f"längd {meta['langd']} mm")
        if meta.get("bredd"): dims.append(f"bredd {meta['bredd']} mm")
        if meta.get("hojd"):  dims.append(f"höjd {meta['hojd']} mm")
        if dims:
            art_lines.append(f"  Mått: {', '.join(dims)}")
        if meta.get("volym"):
            art_lines.append(f"  Volym: {meta['volym']}")
        vikt = []
        if meta.get("vikt_brutto"): vikt.append(f"brutto {meta['vikt_brutto']} kg")
        if meta.get("vikt_netto"):  vikt.append(f"netto {meta['vikt_netto']} kg")
        if vikt:
            art_lines.append(f"  Vikt: {', '.join(vikt)}")

        content.append({"type": "text", "text": f"\n--- ARTIKEL {seq} ({art_num}) ---"})
        content.append({"type": "text",
                        "text": "TITTA PÅ BILDEN NEDAN — beskriv förpackningens fysiska form "
                                "(säck, hink, burk, kartong, flaska, etc.):"})
        _img_ok = False
        if img_path and Path(img_path).exists() and Path(img_path).stat().st_size > 0:
            try:
                b64, mime = encode_fn(img_path, False)
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"}})
                _img_ok = True
            except Exception as _img_err:
                _emit(f"    ⚠ Kunde inte läsa bild för {art_num}: {img_path} ({_img_err})")
        if not _img_ok:
            _reason = ("saknas" if not img_path
                       else "0 bytes" if Path(img_path).exists() else "fil borta")
            _emit(f"    ⚠ Ingen bild för {art_num}: {_reason} ({img_path})")
            content.append({"type": "text", "text": "  (bild saknas)"})
        content.append({"type": "text", "text": "\n".join(art_lines)})

    outro = "\n".join([
        "", "---", "",
        f"Ovan visades {len(articles)} artiklar med bilder och metadata.",
        "Svara NU med exakt en rad per artikel:",
        f"ARTIKEL 1: KATEGORI: [ett av: {names_str}] | ORSAK: [kort]",
        "...osv. INGEN annan text, BARA klassificeringsraderna.",
    ])
    content.append({"type": "text", "text": outro})

    _n_imgs = sum(1 for c in content if isinstance(c, dict) and c.get("type") == "image_url")
    _n_text = sum(1 for c in content if isinstance(c, dict) and c.get("type") == "text")
    _total_b64 = sum(len(c.get("image_url", {}).get("url", ""))
                     for c in content if isinstance(c, dict) and c.get("type") == "image_url")
    _emit(f"    [Batch] {len(articles)} artiklar, {_n_imgs} bilder, {_n_text} textblock, "
          f"~{_total_b64 // 1024} KB base64")

    payload = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "Du är en klassificerare. Svara BARA med klassificeringsrader i exakt det "
             "format som efterfrågas. Ingen analys, inga resonemang, ingen förklaring. "
             "Tänk INTE högt."},
            {"role": "user", "content": content},
        ],
        "max_tokens": 2500,
        "temperature": 0.0,
    }

    raw = ""
    for _attempt in range(3):
        resp = call_api_fn(
            payload, timeout=(5, 90),
            wait_msg=f"    ⏳ Väntar på klassificering av {len(articles)} artiklar…"
        )
        raw = resp["choices"][0]["message"]["content"].strip()
        raw = _strip_think_blocks(raw)
        _lower = raw.lower()
        if any(phrase in _lower for phrase in ["i'm sorry", "i can't", "i cannot", "sorry,"]):
            _emit(f"    ⚠ AI vägrade svara ({raw[:80]}…) — försöker igen…")
            raw = ""
        if raw:
            break
        _emit("    ⚠ Tomt svar — försöker igen…")

    _emit(f"    [DEBUG] Steg 2 svar ({len(raw)} tecken):\n{raw[:2000]}")

    results: List[Tuple[int, str, str, str]] = []
    seq_map = {seq: (idx, art_num) for seq, (idx, art_num, _, _) in enumerate(articles, 1)}

    for line in raw.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue

        seq_num = None
        rest = ""

        if line_stripped.upper().startswith("ARTIKEL"):
            try:
                after_artikel = line_stripped.split(":", 1)
                seq_part = after_artikel[0].strip()
                seq_num = int("".join(c for c in seq_part if c.isdigit()))
                rest = after_artikel[1] if len(after_artikel) > 1 else ""
            except (ValueError, IndexError):
                pass

        if seq_num is None:
            m = _re.match(r'^(\d+)[.:\)]\s*(.*)', line_stripped)
            if m:
                seq_num = int(m.group(1))
                rest = m.group(2)

        if seq_num is None:
            continue

        category = "Övrigt"
        reason = ""

        if "KATEGORI:" in rest.upper():
            cat_text = rest[rest.upper().index("KATEGORI:") + 9:]
            if "|" in cat_text:
                cat_text, reason_part = cat_text.split("|", 1)
                if "ORSAK:" in reason_part.upper():
                    reason = reason_part[reason_part.upper().index("ORSAK:") + 6:].strip()
                else:
                    reason = reason_part.strip()
            cat_text = cat_text.strip()
            for name in all_names:
                if name.lower() == cat_text.lower() or name.lower() in cat_text.lower():
                    category = name
                    break
        else:
            rest_clean = rest.strip().rstrip(".")
            for name in all_names:
                if name.lower() in rest_clean.lower():
                    category = name
                    idx_cat = rest_clean.lower().index(name.lower()) + len(name)
                    tail = rest_clean[idx_cat:].strip(" -–:|,")
                    if tail:
                        reason = tail
                    break

        if seq_num in seq_map:
            idx, art_num = seq_map[seq_num]
            results.append((idx, art_num, category, reason))

    responded = {r[0] for r in results}
    for seq, (idx, art_num) in seq_map.items():
        if idx not in responded:
            results.append((idx, art_num, "Övrigt", "Inget svar från AI"))

    return results


# ---------------------------------------------------------------------------
# classify_article (single article)
# ---------------------------------------------------------------------------

def classify_article(
    img_path: str,
    meta: Dict,
    categories: List[Dict],
    cat_knowledge: Dict[str, str],
    syfte: str,
    model: str,
    call_api_fn: Callable,
    encode_fn: Callable,
    cat_example_images: Optional[Dict[str, List[str]]] = None,
    hint: str = "",
    old_category: str = "",
) -> Tuple[str, str]:
    """Classify a single article. Returns (category, reason)."""
    cat_example_images = cat_example_images or {}
    cat_names = [c["name"] for c in categories if c["name"] != "Övrigt"]
    all_names = cat_names + ["Övrigt"]

    cat_parts = []
    for name in cat_names:
        knowledge = cat_knowledge.get(name, "")
        if knowledge:
            cat_parts.append(f"KATEGORI: {name}\n{knowledge}")
        else:
            cat_parts.append(f"KATEGORI: {name}")
    cat_parts.append("KATEGORI: Övrigt\nKORT REGEL:\n- Artikel som inte tydligt tillhör någon annan kategori.")
    cat_block = "\n\n".join(cat_parts)

    art_lines = []
    if meta.get("beskrivning"):
        art_lines.append(f"  Beskrivning: {meta['beskrivning']}")
    dims = []
    if meta.get("langd"): dims.append(f"längd {meta['langd']} mm")
    if meta.get("bredd"): dims.append(f"bredd {meta['bredd']} mm")
    if meta.get("hojd"):  dims.append(f"höjd {meta['hojd']} mm")
    if dims:
        art_lines.append(f"  Mått: {', '.join(dims)}")
    if meta.get("volym"):
        art_lines.append(f"  Volym: {meta['volym']}")
    vikt = []
    if meta.get("vikt_brutto"): vikt.append(f"brutto {meta['vikt_brutto']} kg")
    if meta.get("vikt_netto"):  vikt.append(f"netto {meta['vikt_netto']} kg")
    if vikt:
        art_lines.append(f"  Vikt: {', '.join(vikt)}")

    hint_block = f"\nOBS: {hint}\n" if hint else ""
    old_cat_block = (
        f"Artikeln är för närvarande placerad i kategorin: \"{old_category}\".\n"
        "Utgå från den befintliga kategorin och ändra den bara om ny information tydligt motiverar det."
        if old_category else ""
    )
    names_str = ", ".join(all_names)

    example_img_desc = []
    for name in all_names:
        imgs = cat_example_images.get(name, [])
        if imgs:
            example_img_desc.append(
                f"Exempelbilder för '{name}' visas i början av meddelandet ({len(imgs)} st)."
            )

    prompt = "\n".join([
        f"Syfte: {syfte}", "",
        "Klassificera artikeln nedan i en av följande kategorier.",
        "Kategorinamnen beskriver direkt vad kategorin innehåller — låt dem vägleda ditt beslut.",
        "Välj 'Övrigt' om artikeln inte tydligt tillhör någon kategori.", "",
        "KATEGORIER:",
        cat_block, "",
        *example_img_desc,
        "",
        "VIKTIGT: Jämför artikelns mått, vikt och volym med kategoriernas beskrivna gränsvärden.",
        "Om artikeln inte uppfyller de kvantitativa kriterierna (t.ex. vikt, storlek),",
        "välj en annan kategori även om utseendet matchar.",
        "",
        *([old_cat_block, ""] if old_category else []),
        *([f"VIKTIGT SAMMANHANG:{hint_block}"] if hint else []),
        "ARTIKEL ATT KLASSIFICERA (sista bilden):",
        "\n".join(art_lines) if art_lines else "  (ingen metadata)",
        "",
        "Svara på exakt två rader:",
        f"KATEGORI: [ett av: {names_str}]",
        "ORSAK: [en mening som förklarar valet]",
    ])

    content: List[Dict] = []
    for name in all_names:
        for ep in cat_example_images.get(name, []):
            try:
                b64_ex, mime_ex = encode_fn(ep, False)
                content.append({"type": "text", "text": f"[Exempelbild — {name}]"})
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:{mime_ex};base64,{b64_ex}"}})
            except (IOError, OSError, ValueError) as _e:
                _logger.warning("Kunde inte koda exempelbild %s: %s", ep, _e)

    b64, mime = encode_fn(img_path, False)
    content.append({"type": "text", "text": "[Artikel att klassificera]"})
    content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    content.append({"type": "text", "text": prompt})

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 100,
        "temperature": 0.1,
    }
    raw = call_api_fn(
        payload, timeout=(5, 90),
        wait_msg="    ⏳ Väntar på klassificering…"
    )["choices"][0]["message"]["content"].strip()

    category = "Övrigt"
    raw_lower = raw.lower()
    for name in all_names:
        if name.lower() in raw_lower:
            category = name
            break

    reason = ""
    for line in raw.splitlines():
        if line.upper().startswith("ORSAK:"):
            reason = line[6:].strip()
            break

    return category, reason

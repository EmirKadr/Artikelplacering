"""Tests for core/classifier_core.py.

All LLM calls are mocked. No network, no Qt.
"""
import os
from pathlib import Path
from typing import Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from core.classifier_core import classify_batch, classify_article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CATEGORIES = [
    {"name": "Säck", "description": ""},
    {"name": "Hink", "description": ""},
]

CAT_KNOWLEDGE = {
    "Säck": "VISUELLA KRAV:\n- Säckform\nKORT REGEL:\n- Säck.",
    "Hink": "VISUELLA KRAV:\n- Rund hink\nKORT REGEL:\n- Hink.",
}

SYFTE = "Testa klassificering"
MODEL = "test-model"


def make_encode(b64="FAKEBASE64==", mime="image/jpeg"):
    return lambda path, compress=False: (b64, mime)


def make_image(tmp_path, name="img.jpg") -> str:
    p = tmp_path / name
    p.write_bytes(b"fake image data")
    return str(p)


def make_articles(n: int, tmp_path) -> List[Tuple[int, str, str, Dict]]:
    result = []
    for i in range(n):
        img = make_image(tmp_path, f"img{i}.jpg")
        result.append((i, str(10000 + i), img, {"beskrivning": f"Artikel {i}"}))
    return result


def batch_api(raw_response: str):
    """Return a call_api_fn that returns raw_response as LLM output."""
    def fn(payload, **kwargs):
        return {"choices": [{"message": {"content": raw_response}, "finish_reason": "stop"}]}
    return fn


# ---------------------------------------------------------------------------
# classify_batch — parsing
# ---------------------------------------------------------------------------

def test_classify_batch_parses_kategori_format(tmp_path):
    articles = make_articles(2, tmp_path)
    raw = (
        "ARTIKEL 1: KATEGORI: Säck | ORSAK: Bilden visar en säck.\n"
        "ARTIKEL 2: KATEGORI: Hink | ORSAK: Bilden visar en hink."
    )
    results = classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    assert len(results) == 2
    cats = {art_num: cat for _, art_num, cat, _ in results}
    assert cats["10000"] == "Säck"
    assert cats["10001"] == "Hink"


def test_classify_batch_parses_reason(tmp_path):
    articles = make_articles(1, tmp_path)
    raw = "ARTIKEL 1: KATEGORI: Säck | ORSAK: Bilden visar en säck."
    results = classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    assert results[0][3] == "Bilden visar en säck."


def test_classify_batch_defaults_to_ovrigt_when_no_match(tmp_path):
    articles = make_articles(1, tmp_path)
    raw = "ARTIKEL 1: KATEGORI: Okänd | ORSAK: Vet ej."
    results = classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    assert results[0][2] == "Övrigt"


def test_classify_batch_fills_missing_articles_with_ovrigt(tmp_path):
    """Articles not in response get Övrigt + 'Inget svar från AI'."""
    articles = make_articles(2, tmp_path)
    raw = "ARTIKEL 1: KATEGORI: Säck | ORSAK: Säck."
    results = classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    cats = {art_num: (cat, reason) for _, art_num, cat, reason in results}
    assert cats["10001"][0] == "Övrigt"
    assert "Inget svar" in cats["10001"][1]


def test_classify_batch_parses_numbered_format(tmp_path):
    """'1. KATEGORI: ...' format."""
    articles = make_articles(1, tmp_path)
    raw = "1. KATEGORI: Hink | ORSAK: Hink visas."
    results = classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    assert results[0][2] == "Hink"


def test_classify_batch_retries_on_empty_response(tmp_path):
    """Up to 3 retries if response is empty."""
    articles = make_articles(1, tmp_path)
    attempts = [0]

    def flaky_api(payload, **kwargs):
        attempts[0] += 1
        if attempts[0] < 3:
            return {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}
        return {"choices": [{"message": {"content": "ARTIKEL 1: KATEGORI: Säck | ORSAK: Säck."}, "finish_reason": "stop"}]}

    results = classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=flaky_api, encode_fn=make_encode(),
    )
    assert results[0][2] == "Säck"
    assert attempts[0] == 3


def test_classify_batch_handles_think_blocks(tmp_path):
    articles = make_articles(1, tmp_path)
    raw = "<think>Internal reasoning</think>ARTIKEL 1: KATEGORI: Hink | ORSAK: Hink."
    results = classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    assert results[0][2] == "Hink"


def test_classify_batch_missing_image_does_not_crash(tmp_path):
    """Article with missing image path should be handled gracefully."""
    articles = [(0, "99999", "/nonexistent/img.jpg", {})]
    raw = "ARTIKEL 1: KATEGORI: Övrigt | ORSAK: Ingen bild."
    results = classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    assert results[0][2] == "Övrigt"


def test_classify_batch_calls_progress_cb(tmp_path):
    articles = make_articles(1, tmp_path)
    messages = []
    raw = "ARTIKEL 1: KATEGORI: Säck | ORSAK: Säck."
    classify_batch(
        articles, CAT_KNOWLEDGE, CATEGORIES, SYFTE, MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
        progress_cb=messages.append,
    )
    assert any("Batch" in m or "artiklar" in m for m in messages)


# ---------------------------------------------------------------------------
# classify_article
# ---------------------------------------------------------------------------

def test_classify_article_returns_category_and_reason(tmp_path):
    img = make_image(tmp_path)
    raw = "KATEGORI: Säck\nORSAK: Bilden visar en säck."
    results = classify_article(
        img_path=img,
        meta={"beskrivning": "Foder 20kg"},
        categories=CATEGORIES,
        cat_knowledge=CAT_KNOWLEDGE,
        syfte=SYFTE,
        model=MODEL,
        call_api_fn=batch_api(raw),
        encode_fn=make_encode(),
    )
    category, reason = results
    assert category == "Säck"
    assert "säck" in reason.lower()


def test_classify_article_defaults_to_ovrigt_on_no_match(tmp_path):
    img = make_image(tmp_path)
    raw = "KATEGORI: Unknown\nORSAK: Vet ej."
    category, reason = classify_article(
        img_path=img, meta={},
        categories=CATEGORIES, cat_knowledge={},
        syfte=SYFTE, model=MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    assert category == "Övrigt"


def test_classify_article_uses_hint(tmp_path):
    img = make_image(tmp_path)
    sent_payloads = []

    def recording_api(payload, **kwargs):
        sent_payloads.append(payload)
        return {"choices": [{"message": {"content": "KATEGORI: Säck\nORSAK: Säck."}, "finish_reason": "stop"}]}

    classify_article(
        img_path=img, meta={},
        categories=CATEGORIES, cat_knowledge={},
        syfte=SYFTE, model=MODEL,
        call_api_fn=recording_api, encode_fn=make_encode(),
        hint="Troligen en säck",
    )
    # hint should appear in the prompt
    prompt_text = ""
    for msg in sent_payloads[0]["messages"]:
        c = msg.get("content", "")
        if isinstance(c, list):
            for part in c:
                if part.get("type") == "text":
                    prompt_text += part["text"]
    assert "Troligen en säck" in prompt_text


def test_classify_article_uses_old_category(tmp_path):
    img = make_image(tmp_path)
    sent_payloads = []

    def recording_api(payload, **kwargs):
        sent_payloads.append(payload)
        return {"choices": [{"message": {"content": "KATEGORI: Säck\nORSAK: Säck."}, "finish_reason": "stop"}]}

    classify_article(
        img_path=img, meta={},
        categories=CATEGORIES, cat_knowledge={},
        syfte=SYFTE, model=MODEL,
        call_api_fn=recording_api, encode_fn=make_encode(),
        old_category="Hink",
    )
    prompt_text = ""
    for msg in sent_payloads[0]["messages"]:
        c = msg.get("content", "")
        if isinstance(c, list):
            for part in c:
                if part.get("type") == "text":
                    prompt_text += part["text"]
    assert "Hink" in prompt_text


def test_classify_article_parses_orsak(tmp_path):
    img = make_image(tmp_path)
    raw = "KATEGORI: Hink\nORSAK: En rund hink syns tydligt."
    _, reason = classify_article(
        img_path=img, meta={},
        categories=CATEGORIES, cat_knowledge={},
        syfte=SYFTE, model=MODEL,
        call_api_fn=batch_api(raw), encode_fn=make_encode(),
    )
    assert reason == "En rund hink syns tydligt."

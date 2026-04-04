"""Tests for core/knowledge_gen.py.

All LLM calls are mocked — no network access, no Qt.
"""
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

import pytest

from core.knowledge_gen import (
    _strip_think_blocks,
    _article_meta_lines,
    generate_knowledge,
    generate_ovrigt_knowledge,
    generate_all_knowledge_external,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_data_mgr(meta: Dict = None):
    dm = MagicMock()
    dm.get_meta.return_value = meta or {}
    return dm


def make_call_api(response_text: str):
    """Return a call_api_fn that always returns *response_text*."""
    def fn(payload, **kwargs):
        return {"choices": [{"message": {"content": response_text},
                             "finish_reason": "stop"}]}
    return fn


def make_encode_fn():
    return lambda path, compress=False: ("FAKEBASE64==", "image/jpeg")


def make_items(n: int, with_image: bool = False, tmp_path: Path = None) -> List[Dict]:
    items = []
    for i in range(n):
        item: Dict = {"article_number": str(10000 + i)}
        if with_image and tmp_path:
            p = tmp_path / f"img{i}.jpg"
            p.write_bytes(b"fake")
            item["image_path"] = str(p)
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# _strip_think_blocks
# ---------------------------------------------------------------------------

def test_strip_think_blocks_removes_think_tag():
    text = "<think>Internal reasoning here.</think>Actual answer."
    assert _strip_think_blocks(text) == "Actual answer."


def test_strip_think_blocks_noop_without_tags():
    text = "No think tags here."
    assert _strip_think_blocks(text) == "No think tags here."


def test_strip_think_blocks_multiline():
    text = "<think>\nline1\nline2\n</think>Result"
    assert _strip_think_blocks(text) == "Result"


def test_strip_think_blocks_unclosed_tag():
    text = "<think>start without close"
    result = _strip_think_blocks(text)
    assert "start without close" not in result or result == ""


# ---------------------------------------------------------------------------
# _article_meta_lines
# ---------------------------------------------------------------------------

def test_article_meta_lines_includes_beskrivning():
    dm = make_mock_data_mgr({"beskrivning": "Testkorg"})
    result = _article_meta_lines({"article_number": "12345"}, 0, dm)
    assert "Testkorg" in result
    assert "Artikel 1:" in result


def test_article_meta_lines_includes_dimensions():
    dm = make_mock_data_mgr({"langd": "300", "bredd": "200", "hojd": "100"})
    result = _article_meta_lines({"article_number": "12345"}, 0, dm)
    assert "längd 300 mm" in result
    assert "bredd 200 mm" in result
    assert "höjd 100 mm" in result


def test_article_meta_lines_empty_meta():
    dm = make_mock_data_mgr({})
    result = _article_meta_lines({"article_number": "12345"}, 0, dm)
    assert "Artikel 1:" in result


def test_article_meta_lines_no_article_number():
    dm = make_mock_data_mgr({"beskrivning": "Something"})
    # Empty article_number → get_meta("", "") → should not crash
    result = _article_meta_lines({}, 0, dm)
    assert "Artikel 1:" in result


# ---------------------------------------------------------------------------
# generate_knowledge
# ---------------------------------------------------------------------------

def test_generate_knowledge_returns_stripped_response(tmp_path):
    items = make_items(2, with_image=True, tmp_path=tmp_path)
    dm = make_mock_data_mgr({"beskrivning": "Test"})
    api = make_call_api("VISUELLA KRAV:\n- Rund form\nKORT REGEL:\n- Rund.")

    result = generate_knowledge(
        cat_name="Rund", cat_desc="", items=items,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=make_encode_fn(),
    )
    assert "VISUELLA KRAV" in result
    assert "Rund form" in result


def test_generate_knowledge_strips_think_blocks(tmp_path):
    items = make_items(1, with_image=True, tmp_path=tmp_path)
    dm = make_mock_data_mgr({})
    api = make_call_api("<think>hidden</think>VISUELLA KRAV:\n- Kvadrat")

    result = generate_knowledge(
        cat_name="Kvadrat", cat_desc="", items=items,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=make_encode_fn(),
    )
    assert "hidden" not in result
    assert "VISUELLA KRAV" in result


def test_generate_knowledge_works_without_images():
    """Items without image_path should not crash."""
    items = [{"article_number": "11111"}]
    dm = make_mock_data_mgr({})
    api = make_call_api("KORT REGEL:\n- Ingen bild.")

    result = generate_knowledge(
        cat_name="NoBild", cat_desc="Test desc", items=items,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=make_encode_fn(),
    )
    assert "KORT REGEL" in result


def test_generate_knowledge_encode_error_skipped(tmp_path):
    """Encoding failures should not crash — images are just skipped."""
    p = tmp_path / "img.jpg"
    p.write_bytes(b"fake")
    items = [{"article_number": "22222", "image_path": str(p)}]
    dm = make_mock_data_mgr({})
    api = make_call_api("OK")

    def bad_encode(path, compress=False):
        raise OSError("encode failed")

    result = generate_knowledge(
        cat_name="Kat", cat_desc="", items=items,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=bad_encode,
    )
    assert "OK" in result


# ---------------------------------------------------------------------------
# generate_ovrigt_knowledge
# ---------------------------------------------------------------------------

def test_generate_ovrigt_knowledge_returns_response(tmp_path):
    items = make_items(3, with_image=True, tmp_path=tmp_path)
    dm = make_mock_data_mgr({})
    api = make_call_api("Övrigt-artiklar är diverse.")

    result = generate_ovrigt_knowledge(
        items=items, syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=make_encode_fn(),
    )
    assert "Övrigt-artiklar är diverse." in result


def test_generate_ovrigt_knowledge_limits_to_3_images(tmp_path):
    """Only up to 3 representative images used for Övrigt."""
    items = make_items(5, with_image=True, tmp_path=tmp_path)
    dm = make_mock_data_mgr({})
    encode_calls = []

    def counting_encode(path, compress=False):
        encode_calls.append(path)
        return ("b64", "image/jpeg")

    api = make_call_api("Text")
    generate_ovrigt_knowledge(
        items=items, syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=counting_encode,
    )
    assert len(encode_calls) <= 3


# ---------------------------------------------------------------------------
# generate_all_knowledge_external
# ---------------------------------------------------------------------------

def test_generate_all_external_returns_dict_per_category(tmp_path):
    items_a = make_items(2, with_image=True, tmp_path=tmp_path)
    items_b = make_items(2, with_image=True, tmp_path=tmp_path)
    by_cat = {"KatA": items_a, "KatB": items_b}
    categories = [
        {"name": "KatA", "description": ""},
        {"name": "KatB", "description": ""},
    ]
    dm = make_mock_data_mgr({})

    call_count = [0]
    def api(payload, **kwargs):
        call_count[0] += 1
        cat_in_prompt = "unknown"
        for m in payload.get("messages", []):
            c = m.get("content", "")
            if isinstance(c, list):
                for part in c:
                    if part.get("type") == "text" and "KatA" in part["text"]:
                        cat_in_prompt = "KatA"
                    elif part.get("type") == "text" and "KatB" in part["text"]:
                        cat_in_prompt = "KatB"
        return {"choices": [{"message": {"content": f"Kunskap för {cat_in_prompt}"},
                             "finish_reason": "stop"}]}

    result = generate_all_knowledge_external(
        by_cat=by_cat, categories=categories,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=make_encode_fn(),
    )
    assert "KatA" in result
    assert "KatB" in result
    assert call_count[0] == 2


def test_generate_all_external_skips_categories_without_images():
    by_cat = {"KatA": [{"article_number": "1"}]}  # no image_path
    categories = [{"name": "KatA", "description": ""}]
    dm = make_mock_data_mgr({})
    api = make_call_api("Should not be called")
    call_count = [0]

    def counting_api(payload, **kwargs):
        call_count[0] += 1
        return {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}

    result = generate_all_knowledge_external(
        by_cat=by_cat, categories=categories,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=counting_api, encode_fn=make_encode_fn(),
    )
    assert result == {}
    assert call_count[0] == 0


def test_generate_all_external_respects_stop_flag(tmp_path):
    items = make_items(2, with_image=True, tmp_path=tmp_path)
    by_cat = {"KatA": items, "KatB": items}
    categories = [
        {"name": "KatA", "description": ""},
        {"name": "KatB", "description": ""},
    ]
    dm = make_mock_data_mgr({})
    call_count = [0]

    def api(payload, **kwargs):
        call_count[0] += 1
        return {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}

    # stop_flag returns True immediately → zero calls
    result = generate_all_knowledge_external(
        by_cat=by_cat, categories=categories,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=make_encode_fn(),
        stop_flag=lambda: True,
    )
    assert call_count[0] == 0


def test_generate_all_external_continues_on_api_error(tmp_path):
    items = make_items(2, with_image=True, tmp_path=tmp_path)
    by_cat = {"KatA": items, "KatB": items}
    categories = [
        {"name": "KatA", "description": ""},
        {"name": "KatB", "description": ""},
    ]
    dm = make_mock_data_mgr({})
    call_count = [0]

    def api(payload, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("API error for KatA")
        return {"choices": [{"message": {"content": "KatB knowledge"},
                             "finish_reason": "stop"}]}

    result = generate_all_knowledge_external(
        by_cat=by_cat, categories=categories,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=make_encode_fn(),
    )
    # KatA failed but KatB should succeed
    assert "KatA" not in result
    assert result.get("KatB") == "KatB knowledge"


def test_generate_all_external_emits_progress(tmp_path):
    items = make_items(1, with_image=True, tmp_path=tmp_path)
    by_cat = {"KatA": items}
    categories = [{"name": "KatA", "description": ""}]
    dm = make_mock_data_mgr({})
    api = make_call_api("OK")
    messages = []

    generate_all_knowledge_external(
        by_cat=by_cat, categories=categories,
        syfte="Testa", model="test-model",
        data_mgr=dm, call_api_fn=api, encode_fn=make_encode_fn(),
        progress_cb=messages.append,
    )
    assert any("KatA" in m for m in messages)

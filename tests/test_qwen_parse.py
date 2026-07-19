"""The Qwen output-parsing boundary. Pure logic — no torch, no weights.

`_extract_json` is where an open model's free-form text becomes a strict object, so its
edge cases (fences, surrounding prose, nested braces) are worth pinning down directly.
"""

import pytest

from morrow.qwen import _extract_json


def test_bare_object():
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_object_with_surrounding_prose():
    assert _extract_json('Sure, here it is:\n{"a": 1}\nHope that helps.') == '{"a": 1}'


def test_fenced_json():
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_nested_braces():
    text = '{"a": {"b": [1, 2]}, "c": "}"}'
    assert _extract_json("prefix " + text) == text


def test_no_object_raises():
    with pytest.raises(ValueError):
        _extract_json("no json here")

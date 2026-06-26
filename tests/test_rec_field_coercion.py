from swing_lab.recommendation import _as_str_list


def test_list_passes_through():
    assert _as_str_list(["a", "b"]) == ["a", "b"]


def test_bare_string_is_not_exploded():
    # Regression: a model field returned as a string must become a single
    # item, never list("text") -> ['t','e','x','t'].
    assert _as_str_list("Quant score deterioration") == ["Quant score deterioration"]


def test_none_returns_empty():
    assert _as_str_list(None) == []


def test_empty_string_returns_empty():
    assert _as_str_list("   ") == []


def test_list_items_stringified_and_blanks_dropped():
    assert _as_str_list(["x", "", "  ", "y"]) == ["x", "y"]

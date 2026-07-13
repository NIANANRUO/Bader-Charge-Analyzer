import pytest

from core.selection import SelectionError, SelectionResolver


ELEMENTS = ["Li", "O", "O", "S"]


def test_empty_expression_selects_all_atoms():
    assert SelectionResolver.resolve("", ELEMENTS) == (1, 2, 3, 4)


def test_mixed_atom_ranges_and_elements_returns_unique_sorted_ids():
    assert SelectionResolver.resolve("4, 2-3, O", ELEMENTS) == (2, 3, 4)


def test_empty_match_raises_selection_error():
    with pytest.raises(SelectionError, match="未匹配任何原子"):
        SelectionResolver.resolve("", [])


@pytest.mark.parametrize("expression", ["0", "5", "3-1", "Xx"])
def test_invalid_selection_raises_selection_error(expression):
    with pytest.raises(SelectionError):
        SelectionResolver.resolve(expression, ELEMENTS)

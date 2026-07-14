import pandas as pd
import pytest

from core.calculator import ChargeCalculator, TargetSelectionError


@pytest.fixture
def charge_df():
    return pd.DataFrame(
        {
            "Atom": [1, 2, 3, 4],
            "Element": ["Li", "O", "O", "S"],
            "Bader_Charge": [0.2, -0.3, 0.5, -0.1],
        }
    )


def test_parse_target_atoms_supports_mixed_ranges_atoms_and_elements():
    indices = ChargeCalculator.parse_target_atoms("1-2, 4, O", 4, ["Li", "O", "O", "S"])
    assert indices == [1, 2, 3, 4]


def test_parse_target_atoms_empty_expression_uses_authoritative_total_atoms():
    indices = ChargeCalculator.parse_target_atoms("", 5, ["H", "H", "H"])
    assert indices == [1, 2, 3, 4, 5]


def test_parse_target_atoms_numeric_id_uses_authoritative_total_atoms():
    indices = ChargeCalculator.parse_target_atoms("5", 5, ["H", "H", "H"])
    assert indices == [5]


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("5", "超出"),
        ("3-1", "倒序"),
        ("Xx", "未知元素"),
    ],
)
def test_parse_target_atoms_rejects_invalid_selection(expression, message):
    with pytest.raises(TargetSelectionError, match=message):
        ChargeCalculator.parse_target_atoms(expression, 4, ["Li", "O", "O", "S"])


def test_aggregate_charge_returns_complete_statistics(charge_df):
    result = ChargeCalculator.aggregate_charge(charge_df, "2-3")

    assert result["atom_indices"] == [2, 3]
    assert result["count"] == 2
    assert result["sum"] == pytest.approx(0.2)
    assert result["mean"] == pytest.approx(0.1)
    assert result["std"] == pytest.approx(0.4 * 2 ** 0.5)
    assert result["max"] == pytest.approx(0.5)
    assert result["min"] == pytest.approx(-0.3)


def test_aggregate_by_element_supports_sum_and_mean(charge_df):
    summed = ChargeCalculator.aggregate_by_element(charge_df, "sum")
    averaged = ChargeCalculator.aggregate_by_element(charge_df, "mean")

    assert summed["O"] == pytest.approx(0.2)
    assert averaged["O"] == pytest.approx(0.1)


def test_prepare_plot_data_supports_element_and_fragment_levels(charge_df):
    data = {"ws1": {"df": charge_df, "struct": None}}

    elements = ChargeCalculator.prepare_plot_data(data, level="element", metric="sum")
    fragments = ChargeCalculator.prepare_plot_data(
        data,
        level="fragment",
        fragments={"ws1": {"吸附物": "2-3"}},
    )

    assert elements["ws1"]["df"].set_index("Atom").loc["O", "Bader_Charge"] == pytest.approx(0.2)
    assert fragments["ws1"]["df"].iloc[0]["Atom"] == "吸附物"
    assert fragments["ws1"]["df"].iloc[0]["Bader_Charge"] == pytest.approx(0.2)


def test_prepare_plot_data_filters_atoms_by_committed_workspace_scope(charge_df):
    struct = object()
    data = {"ws1": {"df": charge_df, "struct": struct}}

    prepared = ChargeCalculator.prepare_plot_data(
        data,
        level="atom",
        selected_by_workspace={"ws1": (2, 3)},
    )

    assert prepared["ws1"]["df"]["Atom"].tolist() == [2, 3]
    assert prepared["ws1"]["struct"] is struct
    assert charge_df["Atom"].tolist() == [1, 2, 3, 4]


@pytest.mark.parametrize(
    ("metric", "expected"),
    [("sum", 0.2), ("mean", 0.1)],
)
def test_prepare_plot_data_filters_before_element_aggregation(charge_df, metric, expected):
    prepared = ChargeCalculator.prepare_plot_data(
        {"ws1": {"df": charge_df, "struct": None}},
        level="element",
        metric=metric,
        selected_by_workspace={"ws1": (2, 3)},
    )

    result = prepared["ws1"]["df"].set_index("Atom")
    assert list(result.index) == ["O"]
    assert result.loc["O", "Bader_Charge"] == pytest.approx(expected)


def test_prepare_plot_data_fragments_always_use_full_workspace_data(charge_df):
    prepared = ChargeCalculator.prepare_plot_data(
        {"ws1": {"df": charge_df, "struct": None}},
        level="fragment",
        fragments={"ws1": {"outer": "1,4"}},
        selected_by_workspace={"ws1": (2, 3)},
    )

    result = prepared["ws1"]["df"].iloc[0]
    assert result["Atom"] == "outer"
    assert result["Bader_Charge"] == pytest.approx(0.1)


def test_prepare_plot_data_applies_distinct_scope_per_workspace(charge_df):
    prepared = ChargeCalculator.prepare_plot_data(
        {
            "left": {"df": charge_df, "struct": None},
            "right": {"df": charge_df, "struct": None},
            "unscoped": {"df": charge_df, "struct": None},
        },
        selected_by_workspace={"left": (1,), "right": (4,)},
    )

    assert prepared["left"]["df"]["Atom"].tolist() == [1]
    assert prepared["right"]["df"]["Atom"].tolist() == [4]
    assert prepared["unscoped"]["df"]["Atom"].tolist() == [1, 2, 3, 4]


def test_explicit_workspace_scope_wins_over_legacy_target(charge_df):
    prepared = ChargeCalculator.prepare_plot_data(
        {"ws1": {"df": charge_df, "struct": None}},
        target="1",
        selected_by_workspace={"ws1": (2, 3)},
    )

    assert prepared["ws1"]["df"]["Atom"].tolist() == [2, 3]

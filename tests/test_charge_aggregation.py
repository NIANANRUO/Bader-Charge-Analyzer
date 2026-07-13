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

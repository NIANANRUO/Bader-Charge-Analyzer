from types import SimpleNamespace

import pandas as pd

from gui.main_window import MainWindow


def test_multi_compare_aligns_workspaces_by_atom_id():
    first = pd.DataFrame({
        "Atom": [1, 2], "Element": ["Li", "O"], "ZVAL": [1, 6],
        "X": [0.0, 1.0], "Y": [0.0, 1.0], "Z": [0.0, 1.0],
        "Bader_Charge": [0.1, -0.2],
    })
    second = pd.DataFrame({
        "Atom": [2, 3], "Element": ["O", "S"], "ZVAL": [6, 6],
        "X": [1.0, 2.0], "Y": [1.0, 2.0], "Z": [1.0, 2.0],
        "Bader_Charge": [-0.4, 0.3],
    })
    owner = SimpleNamespace(_delta_mode=False, _baseline_ws="ws1")

    result = MainWindow._build_multi_compare_df(
        owner, {"ws1": {"df": first}, "ws2": {"df": second}}
    )
    atoms = result[result["Atom"].apply(lambda value: isinstance(value, (int, float)))]

    assert atoms["Atom"].tolist() == [1, 2, 3]
    row2 = atoms[atoms["Atom"] == 2].iloc[0]
    assert row2["ws1_Bader_Charge"] == -0.2
    assert row2["ws2_Bader_Charge"] == -0.4


def test_multi_compare_keeps_missing_scoped_atoms_as_nan():
    first = pd.DataFrame({
        "Atom": [1, 3], "Element": ["Li", "S"],
        "Bader_Charge": [0.1, 0.3],
    })
    second = pd.DataFrame({
        "Atom": [2, 3], "Element": ["O", "S"],
        "Bader_Charge": [-0.4, 0.5],
    })
    owner = SimpleNamespace(_delta_mode=False, _baseline_ws="ws1")

    result = MainWindow._build_multi_compare_df(
        owner, {"ws1": {"df": first}, "ws2": {"df": second}}
    )
    atoms = result[pd.to_numeric(result["Atom"], errors="coerce").notna()]

    assert atoms["Atom"].tolist() == [1, 2, 3]
    assert pd.isna(atoms.loc[atoms["Atom"] == 1, "ws2_Bader_Charge"].iloc[0])
    assert pd.isna(atoms.loc[atoms["Atom"] == 2, "ws1_Bader_Charge"].iloc[0])

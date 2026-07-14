import pandas as pd
import pytest
from pymatgen.core.structure import Structure

from core.structure_model import Atom3D, Bond3D, Structure3D


def make_structure():
    return Structure(
        lattice=[[5, 0, 0], [0, 5, 0], [0, 0, 5]],
        species=["Mo", "N"],
        coords=[[0, 0, 0], [0.5, 0, 0]],
    )


def make_df():
    return pd.DataFrame(
        {
            "Atom": [1, 2],
            "Element": ["Mo", "N"],
            "X": [0.0, 2.5],
            "Y": [0.0, 0.0],
            "Z": [0.0, 0.0],
            "CHARGE": [7.2, 5.4],
            "ZVAL": [6.0, 5.0],
            "Bader_Charge": [1.2, 0.4],
        }
    )


def test_structure3d_maps_atoms_by_one_based_id():
    model = Structure3D.from_pymatgen(make_structure(), make_df())

    assert len(model.atoms) == 2
    assert model.atoms[0].atom_id == 1
    assert model.atoms[0].element == "Mo"
    assert model.atoms[0].charge == pytest.approx(1.2)
    assert model.atoms[0].raw_charge == pytest.approx(7.2)
    assert model.atoms[0].zval == pytest.approx(6.0)
    assert model.atoms[0].cart_coords == pytest.approx((0.0, 0.0, 0.0))
    assert model.atom_by_id(2).element == "N"


def test_structure3d_defaults_missing_charge_data_to_zero():
    model = Structure3D.from_pymatgen(make_structure(), None)

    assert len(model.atoms) == 2
    assert model.atoms[1].atom_id == 2
    assert model.atoms[1].charge == 0.0
    assert model.atoms[1].raw_charge == 0.0
    assert model.atoms[1].zval == 0.0


def test_structure3d_uses_tuple_defaults_and_lattice_floats():
    model = Structure3D.from_pymatgen(make_structure(), make_df())

    assert model.bonds == ()
    assert isinstance(model.atoms, tuple)
    assert isinstance(model.lattice_matrix, tuple)
    assert len(model.lattice_matrix) == 3
    assert all(isinstance(row, tuple) for row in model.lattice_matrix)
    assert all(len(row) == 3 for row in model.lattice_matrix)
    assert model.lattice_matrix == (
        (5.0, 0.0, 0.0),
        (0.0, 5.0, 0.0),
        (0.0, 0.0, 5.0),
    )


def test_structure3d_rejects_non_3x3_lattice_matrix():
    atom = Atom3D(
        atom_id=1,
        element="Mo",
        cart_coords=(0.0, 0.0, 0.0),
        frac_coords=(0.0, 0.0, 0.0),
        charge=0.0,
        raw_charge=0.0,
        zval=0.0,
    )

    with pytest.raises(ValueError, match="3x3"):
        Structure3D(lattice_matrix=((1.0, 0.0), (0.0, 1.0)), atoms=(atom,))


def test_structure3d_converts_nan_charge_fields_to_zero():
    df = make_df()
    df.loc[0, "Bader_Charge"] = float("nan")
    df.loc[0, "CHARGE"] = pd.NA
    df.loc[0, "ZVAL"] = None

    model = Structure3D.from_pymatgen(make_structure(), df)

    assert model.atoms[0].charge == 0.0
    assert model.atoms[0].raw_charge == 0.0
    assert model.atoms[0].zval == 0.0


def test_with_charges_preserves_geometry_bonds_and_atom_identity_fields():
    model = Structure3D.from_pymatgen(make_structure(), make_df())
    bond = Bond3D(1, 2, model.atoms[0].cart_coords, model.atoms[1].cart_coords, 2.5)
    model.with_bonds((bond,))

    updated = model.with_charges(
        pd.DataFrame(
            {
                "Atom": [1, 2],
                "Bader_Charge": [-0.1, 0.8],
                "CHARGE": [5.9, 5.8],
                "ZVAL": [6.0, 5.0],
            }
        )
    )

    assert updated is not model
    assert updated.lattice_matrix == model.lattice_matrix
    assert updated.bonds == model.bonds
    assert [atom.atom_id for atom in updated.atoms] == [atom.atom_id for atom in model.atoms]
    assert [atom.element for atom in updated.atoms] == [atom.element for atom in model.atoms]
    assert [atom.cart_coords for atom in updated.atoms] == [atom.cart_coords for atom in model.atoms]
    assert [atom.frac_coords for atom in updated.atoms] == [atom.frac_coords for atom in model.atoms]
    assert [atom.charge for atom in updated.atoms] == [-0.1, 0.8]
    assert [atom.raw_charge for atom in updated.atoms] == [5.9, 5.8]
    assert [atom.zval for atom in updated.atoms] == [6.0, 5.0]


def test_with_charges_keeps_existing_values_for_missing_atoms_and_fields():
    model = Structure3D.from_pymatgen(make_structure(), make_df())

    updated = model.with_charges(pd.DataFrame({"Atom": [1], "Bader_Charge": [float("nan")]}))

    assert updated.atoms[0].charge == 0.0
    assert updated.atoms[0].raw_charge == model.atoms[0].raw_charge
    assert updated.atoms[0].zval == model.atoms[0].zval
    assert updated.atoms[1] == model.atoms[1]

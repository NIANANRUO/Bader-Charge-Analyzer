import pytest
from pymatgen.core.structure import Structure

from core.bond_detector import BondDetector
from core.structure_model import Structure3D


def make_structure(species, coords):
    return Structure(
        lattice=[[10, 0, 0], [0, 10, 0], [0, 0, 10]],
        species=species,
        coords=coords,
        coords_are_cartesian=True,
    )


def test_mo_n_pair_close_enough_produces_one_bond():
    struct = make_structure(["Mo", "N"], [[0, 0, 0], [1.5, 0, 0]])
    model = Structure3D.from_pymatgen(struct)

    bonds = BondDetector().detect(struct, model.atoms)

    assert len(bonds) == 1
    bond = bonds[0]
    assert bond.atom_i == 1
    assert bond.atom_j == 2
    assert bond.start == pytest.approx((0.0, 0.0, 0.0))
    assert bond.end == pytest.approx((1.5, 0.0, 0.0))
    assert bond.length == pytest.approx(1.5)


def test_mo_n_pair_above_default_search_radius_but_within_threshold_bonds():
    struct = make_structure(["Mo", "N"], [[0, 0, 0], [2.805, 0, 0]])
    model = Structure3D.from_pymatgen(struct)

    bonds = BondDetector().detect(struct, model.atoms)

    assert len(bonds) == 1
    assert bonds[0].atom_i == 1
    assert bonds[0].atom_j == 2
    assert bonds[0].length == pytest.approx(2.805)


def test_far_atoms_do_not_bond():
    struct = make_structure(["Mo", "N"], [[0, 0, 0], [4.0, 0, 0]])
    model = Structure3D.from_pymatgen(struct)

    bonds = BondDetector().detect(struct, model.atoms)

    assert bonds == []


def test_bond_threshold_uses_element_specific_covalent_radii():
    detector = BondDetector()

    assert detector._bond_threshold("Mo", "N") == pytest.approx(2.8125)
    assert detector._bond_threshold("N", "N") == pytest.approx(1.775)


def test_pbc_crossing_bond_uses_neighbor_image_for_endpoint():
    struct = make_structure(["N", "N"], [[0.2, 0, 0], [9.8, 0, 0]])
    model = Structure3D.from_pymatgen(struct)

    bonds = BondDetector().detect(struct, model.atoms)

    assert len(bonds) == 1
    bond = bonds[0]
    assert bond.length == pytest.approx(0.4)
    assert bond.end[0] < 0.0 or bond.end[0] > 10.0


def test_distinct_periodic_images_for_same_atom_pair_are_preserved():
    struct = Structure(
        lattice=[[1, 0, 0], [0, 10, 0], [0, 0, 10]],
        species=["H", "H"],
        coords=[[0, 0, 0], [0.5, 0, 0]],
        coords_are_cartesian=True,
    )
    model = Structure3D.from_pymatgen(struct)

    bonds = BondDetector().detect(struct, model.atoms)

    assert len(bonds) == 2
    assert {(bond.atom_i, bond.atom_j) for bond in bonds} == {(1, 2)}
    assert sorted(bond.end[0] for bond in bonds) == pytest.approx([-0.5, 0.5])


def test_structure3d_with_bonds_stores_tuple_without_mutating_atoms():
    struct = make_structure(["Mo", "N"], [[0, 0, 0], [1.5, 0, 0]])
    model = Structure3D.from_pymatgen(struct)
    original_atoms = model.atoms
    bonds = BondDetector().detect(struct, model.atoms)

    returned = model.with_bonds(bonds)

    assert returned is model
    assert model.atoms is original_atoms
    assert isinstance(model.bonds, tuple)
    assert model.bonds == tuple(bonds)

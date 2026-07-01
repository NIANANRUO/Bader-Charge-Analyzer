from dataclasses import dataclass, field
import math
from typing import Any, Iterable


@dataclass(frozen=True)
class Atom3D:
    atom_id: int
    element: str
    cart_coords: tuple[float, float, float]
    frac_coords: tuple[float, float, float]
    charge: float
    raw_charge: float
    zval: float


@dataclass(frozen=True)
class Bond3D:
    atom_i: int
    atom_j: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    length: float


@dataclass
class Structure3D:
    lattice_matrix: tuple[tuple[float, float, float], ...]
    atoms: tuple[Atom3D, ...]
    bonds: tuple[Bond3D, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        lattice_matrix = tuple(tuple(float(value) for value in row) for row in self.lattice_matrix)
        if len(lattice_matrix) != 3 or any(len(row) != 3 for row in lattice_matrix):
            raise ValueError("lattice_matrix must be a 3x3 matrix")

        self.lattice_matrix = lattice_matrix
        self.atoms = tuple(self.atoms)
        self.bonds = tuple(self.bonds)

    @classmethod
    def from_pymatgen(cls, struct: Any, df: Any = None) -> "Structure3D":
        charge_rows = cls._charge_rows_by_atom_id(df)
        atoms = []

        for atom_id, site in enumerate(struct, start=1):
            charge_row = charge_rows.get(atom_id, {})
            atoms.append(
                Atom3D(
                    atom_id=atom_id,
                    element=site.specie.symbol,
                    cart_coords=cls._coords_tuple(site.coords),
                    frac_coords=cls._coords_tuple(site.frac_coords),
                    charge=cls._float_field(charge_row, "Bader_Charge"),
                    raw_charge=cls._float_field(charge_row, "CHARGE"),
                    zval=cls._float_field(charge_row, "ZVAL"),
                )
            )

        return cls(
            lattice_matrix=tuple(cls._coords_tuple(row) for row in struct.lattice.matrix),
            atoms=tuple(atoms),
            bonds=(),
        )

    def atom_by_id(self, atom_id: int) -> Atom3D:
        for atom in self.atoms:
            if atom.atom_id == atom_id:
                return atom
        raise KeyError(atom_id)

    def atom_ids(self) -> Iterable[int]:
        return (atom.atom_id for atom in self.atoms)

    def with_bonds(self, bonds: Iterable[Bond3D]) -> "Structure3D":
        self.bonds = tuple(bonds)
        return self

    @staticmethod
    def _coords_tuple(coords: Any) -> tuple[float, float, float]:
        x, y, z = coords
        return (float(x), float(y), float(z))

    @staticmethod
    def _charge_rows_by_atom_id(df: Any) -> dict[int, dict[str, Any]]:
        if df is None or "Atom" not in df:
            return {}

        rows = {}
        for row in df.to_dict("records"):
            rows[int(row["Atom"])] = row
        return rows

    @staticmethod
    def _float_field(row: dict[str, Any], field_name: str) -> float:
        value = row.get(field_name, 0.0)
        if value is None:
            return 0.0

        try:
            numeric_value = float(value)
        except TypeError:
            return 0.0

        if math.isnan(numeric_value):
            return 0.0
        return numeric_value

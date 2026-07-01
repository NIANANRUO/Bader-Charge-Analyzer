from dataclasses import dataclass
from typing import Any

from pymatgen.core.periodic_table import Element

from core.structure_model import Atom3D, Bond3D


COVALENT_RADII: dict[str, float] = {
    "H": 0.31,
    "C": 0.76,
    "N": 0.71,
    "O": 0.66,
    "F": 0.57,
    "Si": 1.11,
    "P": 1.07,
    "S": 1.05,
    "Cl": 1.02,
    "Br": 1.20,
    "I": 1.39,
    "Li": 1.28,
    "Na": 1.66,
    "K": 2.03,
    "Mg": 1.41,
    "Ca": 1.76,
    "Al": 1.21,
    "Fe": 1.32,
    "Co": 1.26,
    "Ni": 1.24,
    "Cu": 1.32,
    "Zn": 1.22,
    "Mo": 1.54,
    "Mn": 1.39,
}


@dataclass
class BondDetector:
    scale_factor: float = 1.25
    max_bond_length: float = 2.8

    def detect(self, struct: Any, atoms: list[Atom3D] | tuple[Atom3D, ...]) -> list[Bond3D]:
        atom_list = list(atoms)
        bonds: list[Bond3D] = []
        seen_pairs: set[tuple[int, int, tuple[int, int, int]]] = set()
        center_indices, neighbor_indices, images, _distances = struct.get_neighbor_list(r=self._search_radius())
        neighbor_entries = sorted(
            (
                (int(center_index), int(neighbor_index), self._image_tuple(image))
                for center_index, neighbor_index, image in zip(center_indices, neighbor_indices, images)
            ),
            key=lambda entry: (*self._canonical_pair_key(*entry), 0 if entry[0] <= entry[1] else 1),
        )

        for i, j, image in neighbor_entries:
            if i == j:
                continue

            pair_key = self._canonical_pair_key(i, j, image)
            if pair_key in seen_pairs:
                continue

            atom_i = atom_list[i]
            atom_j = atom_list[j]
            distance, _nearest_image = struct.lattice.get_distance_and_image(
                struct[i].frac_coords,
                struct[j].frac_coords,
                jimage=image,
            )
            if float(distance) > self._bond_threshold(atom_i.element, atom_j.element):
                continue

            seen_pairs.add(pair_key)
            start = self._coords_tuple(struct[i].coords)
            end_frac = struct[j].frac_coords + image
            end = self._coords_tuple(struct.lattice.get_cartesian_coords(end_frac))
            bonds.append(
                Bond3D(
                    atom_i=atom_i.atom_id,
                    atom_j=atom_j.atom_id,
                    start=start,
                    end=end,
                    length=float(distance),
                )
            )

        return bonds

    def _bond_threshold(self, element_i: str, element_j: str) -> float:
        return self.scale_factor * (self._covalent_radius(element_i) + self._covalent_radius(element_j))

    def _search_radius(self) -> float:
        return max(self.max_bond_length, self._max_supported_threshold())

    def _max_supported_threshold(self) -> float:
        max_radius = max(COVALENT_RADII.values(), default=0.7)
        return self.scale_factor * (max_radius * 2)

    @staticmethod
    def _covalent_radius(element: str) -> float:
        if element in COVALENT_RADII:
            return COVALENT_RADII[element]

        try:
            pymatgen_element = Element(element)
        except ValueError:
            return 0.7

        try:
            radius = pymatgen_element.covalent_radius
        except AttributeError:
            radius = pymatgen_element.data.get("Covalent radius")
        if radius is None:
            return 0.7
        try:
            return float(radius)
        except TypeError:
            return 0.7

    @staticmethod
    def _canonical_pair_key(i: int, j: int, image: tuple[int, int, int]) -> tuple[int, int, tuple[int, int, int]]:
        if i <= j:
            return (i, j, image)
        return (j, i, tuple(-value for value in image))

    @staticmethod
    def _image_tuple(image: Any) -> tuple[int, int, int]:
        x, y, z = image
        return (int(x), int(y), int(z))

    @staticmethod
    def _coords_tuple(coords: Any) -> tuple[float, float, float]:
        x, y, z = coords
        return (float(x), float(y), float(z))

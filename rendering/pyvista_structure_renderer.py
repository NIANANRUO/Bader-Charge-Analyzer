# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyvista as pv

from core.bond_detector import COVALENT_RADII
from core.structure_model import Atom3D, Bond3D, Structure3D
from rendering.charge_color_mapper import ChargeColorMapper


@dataclass
class RenderSettings:
    show_bonds: bool = True
    show_cell: bool = True
    show_axes: bool = True
    show_labels: bool = False
    fade_background: bool = True
    background_opacity: float = 0.4
    sphere_scale: float = 1.0
    bond_radius: float = 0.06
    ambient_light: float = 0.65
    color_by: str = "Bader 电荷"
    cmap: str = "coolwarm"
    cmap_gamma: float = 1.0
    cmap_range: str = "极值"
    color_profile: str = "标准"
    representation: str = "ball_stick"
    selected_atom_id: int | None = None
    visible_atom_ids: set[int] | None = None
    label_atom_ids: set[int] | None = None
    custom_colors: dict[str, tuple[float, float, float]] | None = None


ELEMENT_COLORS: dict[str, tuple[float, float, float]] = {
    "H": (1.0, 1.0, 1.0),
    "C": (0.2, 0.2, 0.2),
    "N": (0.1, 0.2, 0.9),
    "O": (0.9, 0.05, 0.05),
    "F": (0.1, 0.8, 0.1),
    "P": (0.95, 0.5, 0.05),
    "S": (0.95, 0.85, 0.05),
    "Cl": (0.1, 0.75, 0.1),
    "Li": (0.55, 0.25, 0.8),
    "Mo": (0.45, 0.62, 0.72),
}
FALLBACK_ELEMENT_COLOR = (0.7, 0.7, 0.72)
CELL_COLOR = (0.55, 0.55, 0.58)
BOND_COLOR = (0.78, 0.78, 0.78)
SELECTED_HIGHLIGHT_COLOR = (1.0, 0.9, 0.05)


class PyVistaStructureRenderer:
    def __init__(self, plotter: Any) -> None:
        self.plotter = plotter
        self.atom_meshes: dict[int, pv.PolyData] = {}
        self.atom_actors: dict[int, Any] = {}
        self.bond_actors: list[Any] = []
        self.cell_actors: list[Any] = []
        self.export_meshes: list[pv.PolyData] = []
        self.last_charge_clim = (-1.0, 1.0)
        self._highlight_actor = None
        self._highlight_signature = None
        self._labels_actor = None
        self._labels_signature = None
        self._scalarbar_actor = None
        self._scalarbar_signature = None

    def clear(self) -> None:
        self.plotter.clear()
        self.atom_meshes.clear()
        self.atom_actors.clear()
        self.bond_actors.clear()
        self.cell_actors.clear()
        self.export_meshes.clear()
        self._highlight_actor = None
        self._highlight_signature = None
        self._labels_actor = None
        self._labels_signature = None
        self._scalarbar_actor = None
        self._scalarbar_signature = None

    def render(self, model: Structure3D, settings: RenderSettings) -> None:
        self.build_geometry(model, settings)
        self.update_appearance(model, settings)

    def build_geometry(self, model: Structure3D, settings: RenderSettings) -> None:
        self.clear()
        atoms = list(model.atoms)

        if settings.show_axes:
            self.plotter.add_axes()

        for atom in atoms:
            self._add_atom(atom, settings)

        if settings.show_bonds:
            for bond in model.bonds:
                self._add_bond(bond, settings)

        if settings.show_cell:
            for line in self._unit_cell_lines(model.lattice_matrix):
                self._add_cell_line(line, settings)

    def update_appearance(self, model: Structure3D, settings: RenderSettings) -> None:
        atoms = list(model.atoms)
        atom_by_id = {atom.atom_id: atom for atom in atoms}
        target_ids = (
            set(atom_by_id)
            if settings.visible_atom_ids is None
            else set(settings.visible_atom_ids) & set(atom_by_id)
        )
        charge_mapper = ChargeColorMapper(
            (atom_by_id[atom_id].charge for atom_id in target_ids),
            gamma=settings.cmap_gamma,
            range_mode=settings.cmap_range,
            profile=settings.color_profile,
        )
        self.last_charge_clim = charge_mapper.clim

        for atom_id, actor in self.atom_actors.items():
            atom = atom_by_id.get(atom_id)
            if atom is None:
                continue
            actor.prop.color = self._appearance_atom_color(
                atom, target_ids, settings, charge_mapper
            )
            actor.prop.opacity = self._atom_opacity(atom, settings)
            actor.prop.ambient = settings.ambient_light

        for bond, actor in zip(model.bonds, self.bond_actors):
            actor.prop.color = BOND_COLOR
            actor.prop.opacity = self._bond_opacity(bond, settings)
            actor.prop.ambient = settings.ambient_light

        for actor in self.cell_actors:
            actor.prop.color = CELL_COLOR
            actor.prop.ambient = settings.ambient_light

        self._update_highlight(atom_by_id, settings)
        self._update_labels(atoms, settings)
        self._update_charge_colorbar(charge_mapper, settings)

        self.plotter.update()

    def atom_id_for_picked_cell(self, picker: Any) -> int | None:
        """Resolve a vtkCellPicker pick to an atom_id by reading cell data
        from the picked dataset.

        This is the ROBUST approach: instead of comparing object identities
        (which fails because VTK Python creates new proxy objects on every
        access), we embed ``atom_id`` into each atom mesh's ``cell_data``
        and read it back directly from the picked cell.

        Parameters
        ----------
        picker : vtkCellPicker
            A picker that has already executed ``Pick()``.

        Returns
        -------
        int | None
            The atom_id if an atom mesh was hit, else None.
        """
        try:
            dataset = picker.GetDataSet()
        except Exception:
            return None
        if dataset is None:
            return None
        cell_id = picker.GetCellId()
        if cell_id < 0:
            return None
        try:
            import pyvista as _pv
            pv_dataset = _pv.wrap(dataset)
            if "atom_id" not in pv_dataset.cell_data:
                return None
            return int(pv_dataset.cell_data["atom_id"][cell_id])
        except Exception:
            return None

    def screenshot(self, path: str | Path) -> Any:
        return self.plotter.screenshot(path)

    def export_model(self, path: str | Path) -> None:
        export_path = Path(path)
        if not self.export_meshes:
            raise ValueError("No rendered meshes to export.")

        suffix = export_path.suffix.lower()
        if suffix in {".vtm", ".vtmb"}:
            pv.MultiBlock(self.export_meshes).save(export_path)
            return

        if suffix in {".ply", ".vtp"}:
            try:
                merged_mesh = pv.merge(self.export_meshes)
            except Exception as exc:
                raise ValueError(f"Unable to merge rendered meshes for {suffix} export.") from exc
            merged_mesh.save(export_path)
            return

        raise ValueError(f"Unsupported export format: {suffix or '<none>'}")

    def _add_atom(self, atom: Atom3D, settings: RenderSettings) -> None:
        radius = self._atom_radius(atom, settings)
        mesh = pv.Sphere(radius=radius, center=atom.cart_coords, theta_resolution=32, phi_resolution=32)
        # Embed atom_id into the mesh's cell data so that vtkCellPicker can
        # recover it directly from the picked dataset — no object-identity
        # comparison needed (which is unreliable due to VTK Python proxy
        # objects creating new wrappers on every access).
        mesh.cell_data["atom_id"] = [atom.atom_id] * mesh.n_cells
        actor = self.plotter.add_mesh(
            mesh,
            color=ELEMENT_COLORS.get(atom.element, FALLBACK_ELEMENT_COLOR),
            opacity=1.0,
            smooth_shading=True,
            ambient=settings.ambient_light,
        )
        self.atom_meshes[atom.atom_id] = mesh
        self.atom_actors[atom.atom_id] = actor
        self.export_meshes.append(mesh)

    def _add_selection_highlight(self, atom: Atom3D, radius: float, settings: RenderSettings):
        mesh = pv.Sphere(radius=radius * 1.12, center=atom.cart_coords, theta_resolution=32, phi_resolution=32)
        actor = self.plotter.add_mesh(
            mesh,
            color=SELECTED_HIGHLIGHT_COLOR,
            opacity=1.0,
            style="wireframe",
            line_width=3,
            ambient=settings.ambient_light,
            pickable=False,
        )
        return actor

    def _add_bond(self, bond: Bond3D, settings: RenderSettings) -> None:
        mesh = pv.Line(bond.start, bond.end).tube(radius=settings.bond_radius)
        actor = self.plotter.add_mesh(
            mesh,
            color=BOND_COLOR,
            opacity=self._bond_opacity(bond, settings),
            smooth_shading=True,
            ambient=settings.ambient_light,
        )
        self.bond_actors.append(actor)
        self.export_meshes.append(mesh)

    def _add_cell_line(
        self,
        line: tuple[tuple[float, float, float], tuple[float, float, float]],
        settings: RenderSettings,
    ) -> None:
        mesh = pv.Line(line[0], line[1])
        actor = self.plotter.add_mesh(
            mesh, color=CELL_COLOR, line_width=2, ambient=settings.ambient_light
        )
        self.cell_actors.append(actor)
        self.export_meshes.append(mesh)

    def _add_labels(self, atoms: list[Atom3D], settings: RenderSettings) -> Any:
        label_atoms = [
            atom
            for atom in atoms
            if settings.label_atom_ids is None or atom.atom_id in settings.label_atom_ids
        ]
        if not label_atoms:
            return
        return self.plotter.add_point_labels(
            [atom.cart_coords for atom in label_atoms],
            [f"{atom.atom_id} {atom.element}" for atom in label_atoms],
            point_size=0,
            font_size=12,
            shape_opacity=0.35,
        )

    def _add_charge_colorbar(self, charge_mapper: ChargeColorMapper, settings: RenderSettings) -> Any:
        dummy = pv.PolyData([(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
        dummy["Bader Charge"] = [charge_mapper.clim[0], charge_mapper.clim[1]]
        return self.plotter.add_mesh(
            dummy,
            scalars="Bader Charge",
            cmap=settings.cmap,
            clim=charge_mapper.clim,
            opacity=0.0,
            show_scalar_bar=True,
            scalar_bar_args={"title": "Bader Charge"},
            pickable=False,
        )

    @staticmethod
    def _atom_radius(atom: Atom3D, settings: RenderSettings) -> float:
        base_radius = COVALENT_RADII.get(atom.element, 0.7)
        scale = 0.35 if settings.representation == "ball_stick" else 0.7
        return max(base_radius * scale * settings.sphere_scale, 0.05)

    @staticmethod
    def _atom_color(
        atom: Atom3D,
        settings: RenderSettings,
        charge_mapper: ChargeColorMapper,
    ) -> tuple[float, float, float]:
        if settings.color_by in ("元素", "Element"):
            return ELEMENT_COLORS.get(atom.element, FALLBACK_ELEMENT_COLOR)
        if settings.color_by in ("自定义", "Custom") and settings.custom_colors:
            return settings.custom_colors.get(
                atom.element,
                ELEMENT_COLORS.get(atom.element, FALLBACK_ELEMENT_COLOR),
            )
        return charge_mapper.rgb_for_charge(atom.charge)

    @staticmethod
    def _appearance_atom_color(
        atom: Atom3D,
        target_ids: set[int],
        settings: RenderSettings,
        charge_mapper: ChargeColorMapper,
    ) -> tuple[float, float, float]:
        if settings.color_by in ("Bader 电荷", "Bader Charge"):
            if atom.atom_id in target_ids:
                return charge_mapper.rgb_for_charge(atom.charge)
            return ELEMENT_COLORS.get(atom.element, FALLBACK_ELEMENT_COLOR)
        return PyVistaStructureRenderer._atom_color(atom, settings, charge_mapper)

    def _update_highlight(
        self, atom_by_id: dict[int, Atom3D], settings: RenderSettings
    ) -> None:
        signature = (
            settings.selected_atom_id,
            settings.sphere_scale,
            settings.representation,
        )
        if signature == self._highlight_signature:
            if self._highlight_actor is not None:
                self._highlight_actor.prop.ambient = settings.ambient_light
            return
        if self._highlight_actor is not None:
            self.plotter.remove_actor(self._highlight_actor)
            self._highlight_actor = None
        atom = atom_by_id.get(settings.selected_atom_id)
        if atom is not None:
            self._highlight_actor = self._add_selection_highlight(
                atom, self._atom_radius(atom, settings), settings
            )
        self._highlight_signature = signature

    def _update_labels(self, atoms: list[Atom3D], settings: RenderSettings) -> None:
        signature = (
            settings.show_labels,
            None if settings.label_atom_ids is None else tuple(sorted(settings.label_atom_ids)),
        )
        if signature == self._labels_signature:
            return
        if self._labels_actor is not None:
            self.plotter.remove_actor(self._labels_actor)
            self._labels_actor = None
        if settings.show_labels:
            self._labels_actor = self._add_labels(atoms, settings)
        self._labels_signature = signature

    def _update_charge_colorbar(
        self, charge_mapper: ChargeColorMapper, settings: RenderSettings
    ) -> None:
        enabled = settings.color_by in ("Bader 电荷", "Bader Charge")
        signature = (enabled, settings.cmap, charge_mapper.clim)
        if signature == self._scalarbar_signature:
            return
        if self._scalarbar_actor is not None:
            self.plotter.remove_actor(self._scalarbar_actor)
            self._scalarbar_actor = None
        if enabled:
            self._scalarbar_actor = self._add_charge_colorbar(charge_mapper, settings)
        self._scalarbar_signature = signature

    @staticmethod
    def _atom_opacity(atom: Atom3D, settings: RenderSettings) -> float:
        if not settings.fade_background or settings.visible_atom_ids is None:
            return 1.0
        if atom.atom_id in settings.visible_atom_ids:
            return 1.0
        return settings.background_opacity

    @staticmethod
    def _bond_opacity(bond: Bond3D, settings: RenderSettings) -> float:
        if not settings.fade_background or settings.visible_atom_ids is None:
            return 1.0
        if bond.atom_i in settings.visible_atom_ids and bond.atom_j in settings.visible_atom_ids:
            return 1.0
        return settings.background_opacity

    @staticmethod
    def _unit_cell_lines(
        lattice_matrix: tuple[tuple[float, float, float], ...],
    ) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
        origin = (0.0, 0.0, 0.0)
        a, b, c = lattice_matrix
        corners = [
            origin,
            a,
            b,
            c,
            _add(a, b),
            _add(a, c),
            _add(b, c),
            _add(_add(a, b), c),
        ]
        index_pairs = [
            (0, 1),
            (0, 2),
            (0, 3),
            (1, 4),
            (1, 5),
            (2, 4),
            (2, 6),
            (3, 5),
            (3, 6),
            (4, 7),
            (5, 7),
            (6, 7),
        ]
        return [(corners[start], corners[end]) for start, end in index_pairs]


def _add(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])

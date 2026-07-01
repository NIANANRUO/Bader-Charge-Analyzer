# -*- coding: utf-8 -*-
import pytest
import tempfile
from pathlib import Path

from core.structure_model import Atom3D, Bond3D, Structure3D
import rendering.pyvista_structure_renderer as renderer_module
from rendering.pyvista_structure_renderer import PyVistaStructureRenderer, RenderSettings


class FakePlotter:
    def __init__(self):
        self.meshes = []
        self.axes_added = 0
        self.clears = 0
        self.updates = 0
        self.point_labels = []
        self.screenshots = []

    def add_mesh(self, mesh, **kwargs):
        self.meshes.append((mesh, kwargs))
        return {"mesh": mesh, "kwargs": kwargs}

    def add_axes(self):
        self.axes_added += 1

    def clear(self):
        self.clears += 1

    def update(self):
        self.updates += 1

    def add_point_labels(self, points, labels, **kwargs):
        self.point_labels.append((points, labels, kwargs))

    def screenshot(self, path):
        self.screenshots.append(path)
        return path


def make_model():
    atom_1 = Atom3D(
        atom_id=1,
        element="Mo",
        cart_coords=(0.0, 0.0, 0.0),
        frac_coords=(0.0, 0.0, 0.0),
        charge=0.6,
        raw_charge=6.0,
        zval=6.0,
    )
    atom_2 = Atom3D(
        atom_id=2,
        element="Xx",
        cart_coords=(1.5, 0.0, 0.0),
        frac_coords=(0.3, 0.0, 0.0),
        charge=-0.4,
        raw_charge=5.0,
        zval=5.0,
    )
    bond = Bond3D(
        atom_i=1,
        atom_j=2,
        start=atom_1.cart_coords,
        end=atom_2.cart_coords,
        length=1.5,
    )
    return Structure3D(
        lattice_matrix=((5.0, 0.0, 0.0), (0.0, 5.0, 0.0), (0.0, 0.0, 5.0)),
        atoms=(atom_1, atom_2),
        bonds=(bond,),
    )


def test_render_stores_atom_meshes_export_meshes_and_atom_lookup():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(make_model(), RenderSettings(show_labels=True))

    assert set(renderer.atom_meshes) == {1, 2}
    # atom_id is now embedded in cell_data on each atom mesh
    assert "atom_id" in renderer.atom_meshes[1].cell_data
    assert renderer.atom_meshes[1].cell_data["atom_id"][0] == 1
    assert renderer.atom_meshes[2].cell_data["atom_id"][0] == 2
    assert len(renderer.export_meshes) == 15
    assert plotter.axes_added == 1
    assert plotter.point_labels[0][1] == ["1 Mo", "2 Xx"]
    assert plotter.updates == 1


def test_label_atom_ids_filters_rendered_labels():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(make_model(), RenderSettings(show_labels=True, label_atom_ids={2}))

    assert plotter.point_labels[0][1] == ["2 Xx"]


def test_colorbar_uses_configured_colormap():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(make_model(), RenderSettings(show_bonds=False, show_cell=False, cmap="RdBu_r"))

    colorbar_kwargs = next(
        kwargs
        for _mesh, kwargs in plotter.meshes
        if kwargs.get("show_scalar_bar")
    )
    assert colorbar_kwargs["cmap"] == "RdBu_r"


def test_show_bonds_false_suppresses_bond_export_meshes():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(make_model(), RenderSettings(show_bonds=False))

    assert len(renderer.atom_meshes) == 2
    assert len(renderer.export_meshes) == 14


def test_element_coloring_uses_non_none_colors_for_unknown_elements():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(make_model(), RenderSettings(color_by="Element", show_bonds=False, show_cell=False))

    atom_colors = [
        kwargs.get("color")
        for mesh, kwargs in plotter.meshes
        if mesh in renderer.atom_meshes.values()
    ]
    assert atom_colors
    assert all(color is not None for color in atom_colors)


def test_visible_atom_ids_fades_non_target_atoms_without_filtering_them():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(
        make_model(),
        RenderSettings(visible_atom_ids={1}, background_opacity=0.25),
    )

    assert set(renderer.atom_meshes) == {1, 2}
    # Build atom_id → opacity map by matching mesh objects
    mesh_to_atom_id = {id(m): aid for aid, m in renderer.atom_meshes.items()}
    atom_opacities = {
        mesh_to_atom_id[id(mesh)]: kwargs.get("opacity")
        for mesh, kwargs in plotter.meshes
        if id(mesh) in mesh_to_atom_id
    }
    assert atom_opacities == {1: 1.0, 2: 0.25}


def test_visible_atom_ids_do_not_fade_when_fade_background_is_false():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(
        make_model(),
        RenderSettings(visible_atom_ids={1}, fade_background=False),
    )

    atom_opacities = [
        kwargs.get("opacity")
        for mesh, kwargs in plotter.meshes
        if mesh in renderer.atom_meshes.values()
    ]
    assert atom_opacities == [1.0, 1.0]


def test_bonds_fade_when_either_endpoint_is_outside_visible_atom_ids():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(
        make_model(),
        RenderSettings(visible_atom_ids={1}, background_opacity=0.25, show_cell=False),
    )

    bond_kwargs = next(
        kwargs
        for _mesh, kwargs in plotter.meshes
        if kwargs.get("color") == renderer_module.BOND_COLOR
    )
    assert bond_kwargs["opacity"] == 0.25


def test_bonds_stay_opaque_when_visible_filter_is_disabled_or_contains_both_endpoints():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(
        make_model(),
        RenderSettings(visible_atom_ids={1, 2}, background_opacity=0.25, show_cell=False),
    )
    bond_kwargs = next(
        kwargs
        for _mesh, kwargs in plotter.meshes
        if kwargs.get("color") == renderer_module.BOND_COLOR
    )
    assert bond_kwargs["opacity"] == 1.0

    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)
    renderer.render(
        make_model(),
        RenderSettings(visible_atom_ids={1}, fade_background=False, background_opacity=0.25, show_cell=False),
    )
    bond_kwargs = next(
        kwargs
        for _mesh, kwargs in plotter.meshes
        if kwargs.get("color") == renderer_module.BOND_COLOR
    )
    assert bond_kwargs["opacity"] == 1.0


def test_selected_atom_keeps_charge_color_and_adds_highlight_mesh():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(
        make_model(),
        RenderSettings(selected_atom_id=1, show_bonds=False, show_cell=False),
    )

    selected_atom_kwargs = next(
        kwargs
        for mesh, kwargs in plotter.meshes
        if mesh is renderer.atom_meshes[1]
    )
    red, _green, blue = selected_atom_kwargs["color"]
    assert red > blue
    assert selected_atom_kwargs["color"] != renderer_module.SELECTED_HIGHLIGHT_COLOR
    assert any(kwargs.get("style") == "wireframe" for _mesh, kwargs in plotter.meshes)


def test_atom_meshes_have_atom_id_in_cell_data():
    renderer = PyVistaStructureRenderer(FakePlotter())
    renderer.render(make_model(), RenderSettings(show_bonds=False, show_cell=False))

    # Each atom mesh carries its atom_id in cell_data for robust picking
    assert "atom_id" in renderer.atom_meshes[1].cell_data
    assert renderer.atom_meshes[1].cell_data["atom_id"][0] == 1
    assert "atom_id" in renderer.atom_meshes[2].cell_data
    assert renderer.atom_meshes[2].cell_data["atom_id"][0] == 2

    # A copied mesh still has the cell data (it's part of the dataset)
    copied_mesh = renderer.atom_meshes[1].copy()
    assert copied_mesh.cell_data["atom_id"][0] == 1


def test_colorbar_dummy_mesh_is_not_pickable():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)

    renderer.render(make_model(), RenderSettings(show_bonds=False, show_cell=False))

    colorbar_kwargs = next(
        kwargs
        for _mesh, kwargs in plotter.meshes
        if kwargs.get("show_scalar_bar")
    )
    assert colorbar_kwargs["pickable"] is False


def test_export_model_requires_rendered_meshes():
    renderer = PyVistaStructureRenderer(FakePlotter())

    with pytest.raises(ValueError, match="No rendered meshes to export"):
        renderer.export_model("empty.ply")


def test_export_model_saves_multiblock_for_vtm(monkeypatch):
    saved = []

    class FakeMultiBlock:
        def __init__(self, meshes):
            self.meshes = meshes

        def save(self, path):
            saved.append((self.meshes, path))

    monkeypatch.setattr(renderer_module.pv, "MultiBlock", FakeMultiBlock)
    renderer = PyVistaStructureRenderer(FakePlotter())
    renderer.export_meshes = [object(), object()]

    renderer.export_model("model.vtm")

    assert saved == [([renderer.export_meshes[0], renderer.export_meshes[1]], Path("model.vtm"))]


def test_export_model_saves_merged_mesh_for_ply_and_vtp(monkeypatch):
    saved = []

    class FakeMergedMesh:
        def save(self, path):
            saved.append(path)

    monkeypatch.setattr(renderer_module.pv, "merge", lambda meshes: FakeMergedMesh())
    renderer = PyVistaStructureRenderer(FakePlotter())
    renderer.export_meshes = [object()]

    renderer.export_model("model.ply")
    renderer.export_model("model.vtp")

    assert saved == [Path("model.ply"), Path("model.vtp")]


def test_export_model_writes_real_vtp_file_from_rendered_meshes():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)
    renderer.render(make_model(), RenderSettings())

    with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp_dir:
        export_path = Path(tmp_dir) / "structure.vtp"
        renderer.export_model(export_path)

        assert export_path.exists()
        assert export_path.stat().st_size > 0


def test_export_model_rejects_unsupported_suffixes():
    renderer = PyVistaStructureRenderer(FakePlotter())
    renderer.export_meshes = [object()]

    with pytest.raises(ValueError, match="Unsupported export format"):
        renderer.export_model("model.obj")

    with pytest.raises(ValueError, match="Unsupported export format"):
        renderer.export_model("model.stl")


def test_clear_resets_plotter_and_internal_state():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)
    renderer.render(make_model(), RenderSettings())

    renderer.clear()

    assert plotter.clears == 2
    assert renderer.atom_meshes == {}
    assert renderer.export_meshes == []

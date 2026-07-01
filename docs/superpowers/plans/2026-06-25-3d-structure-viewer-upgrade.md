# 3D Structure Viewer Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the 3D Structure View pipeline so real VASP/Bader data renders as a stable PyVista ball-and-stick structure before adding richer interaction and UI controls.

**Architecture:** Extract atom/bond/charge data into small core modules, move PyVista mesh creation into a dedicated renderer, then simplify `Visualizer3D` into a Qt wrapper that coordinates renderer state and selection signals. The right panel remains the control surface, but new UI controls are only added after the renderer is reliable.

**Tech Stack:** Python, PySide6, PyVista, PyVistaQt, pymatgen, pandas, numpy, pytest.

---

## File Structure

Create:

- `core/structure_model.py` - atom, bond, and structure dataclasses plus conversion from pymatgen/DataFrame.
- `core/bond_detector.py` - covalent-radius bond inference with periodic boundary support.
- `rendering/__init__.py` - package marker.
- `rendering/charge_color_mapper.py` - charge semantics, color mapping, scalar range.
- `rendering/pyvista_structure_renderer.py` - PyVista mesh creation, scene clearing, picking map, screenshots, model export.
- `tests/test_structure_model.py` - data model tests.
- `tests/test_bond_detector.py` - bond inference tests.
- `tests/test_charge_color_mapper.py` - charge color tests.
- `tests/test_3d_renderer_smoke.py` - optional offscreen render smoke test.

Modify:

- `gui/visualizer_3d.py` - delegate model/render/export/picking to extracted modules.
- `gui/analysis_panel.py` - keep current controls, align names with render settings.
- `gui/main_window.py` - fix max gain/loss semantics and route export through `Visualizer3D`.
- `requirements.txt` - add `pytest` if missing.

---

### Task 1: Add Structure3D Data Model

**Files:**
- Create: `core/structure_model.py`
- Test: `tests/test_structure_model.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytest to requirements if it is missing**

Add this line to `requirements.txt`:

```text
pytest
```

- [ ] **Step 2: Write the failing model test**

Create `tests/test_structure_model.py`:

```python
import pandas as pd
import pytest
from pymatgen.core.structure import Structure

from core.structure_model import Structure3D


def make_structure():
    return Structure(
        lattice=[[5, 0, 0], [0, 5, 0], [0, 0, 5]],
        species=["Mo", "N"],
        coords=[[0, 0, 0], [0.5, 0, 0]],
    )


def make_df():
    return pd.DataFrame({
        "Atom": [1, 2],
        "Element": ["Mo", "N"],
        "X": [0.0, 2.5],
        "Y": [0.0, 0.0],
        "Z": [0.0, 0.0],
        "CHARGE": [7.2, 5.4],
        "ZVAL": [6.0, 5.0],
        "Bader_Charge": [1.2, 0.4],
    })


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
```

- [ ] **Step 3: Run the failing test**

Run:

```powershell
python -m pytest tests/test_structure_model.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'core.structure_model'`.

- [ ] **Step 4: Implement the model**

Create `core/structure_model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class Atom3D:
    atom_id: int
    element: str
    cart_coords: tuple[float, float, float]
    frac_coords: tuple[float, float, float]
    charge: float = 0.0
    raw_charge: float = 0.0
    zval: float = 0.0


@dataclass(frozen=True)
class Bond3D:
    atom_i: int
    atom_j: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    length: float


@dataclass
class Structure3D:
    lattice_matrix: np.ndarray
    atoms: list[Atom3D]
    bonds: list[Bond3D] = field(default_factory=list)

    @classmethod
    def from_pymatgen(cls, struct, df=None) -> "Structure3D":
        charge_rows = {}
        if df is not None:
            for _, row in df.iterrows():
                charge_rows[int(row["Atom"])] = row

        atoms = []
        for idx, site in enumerate(struct, start=1):
            row = charge_rows.get(idx)
            atoms.append(
                Atom3D(
                    atom_id=idx,
                    element=site.specie.symbol,
                    cart_coords=tuple(float(v) for v in site.coords),
                    frac_coords=tuple(float(v) for v in site.frac_coords),
                    charge=float(row["Bader_Charge"]) if row is not None else 0.0,
                    raw_charge=float(row["CHARGE"]) if row is not None else 0.0,
                    zval=float(row["ZVAL"]) if row is not None else 0.0,
                )
            )

        return cls(lattice_matrix=np.array(struct.lattice.matrix, dtype=float), atoms=atoms)

    def atom_by_id(self, atom_id: int) -> Atom3D:
        for atom in self.atoms:
            if atom.atom_id == atom_id:
                return atom
        raise KeyError(f"Atom ID not found: {atom_id}")

    def atom_ids(self) -> Iterable[int]:
        return (atom.atom_id for atom in self.atoms)
```

- [ ] **Step 5: Run the model test**

Run:

```powershell
python -m pytest tests/test_structure_model.py -v
```

Expected: PASS.

---

### Task 2: Add BondDetector

**Files:**
- Create: `core/bond_detector.py`
- Test: `tests/test_bond_detector.py`
- Modify: `core/structure_model.py`

- [ ] **Step 1: Write the failing bond tests**

Create `tests/test_bond_detector.py`:

```python
import pandas as pd
from pymatgen.core.structure import Structure

from core.bond_detector import BondDetector
from core.structure_model import Structure3D


def empty_df(n):
    return pd.DataFrame({
        "Atom": list(range(1, n + 1)),
        "CHARGE": [0.0] * n,
        "ZVAL": [0.0] * n,
        "Bader_Charge": [0.0] * n,
    })


def test_detects_simple_mo_n_bond():
    struct = Structure(
        lattice=[[8, 0, 0], [0, 8, 0], [0, 0, 8]],
        species=["Mo", "N"],
        coords=[[0, 0, 0], [0.23, 0, 0]],
    )
    model = Structure3D.from_pymatgen(struct, empty_df(2))

    bonds = BondDetector().detect(struct, model.atoms)

    assert len(bonds) == 1
    assert bonds[0].atom_i == 1
    assert bonds[0].atom_j == 2


def test_ignores_far_atoms():
    struct = Structure(
        lattice=[[8, 0, 0], [0, 8, 0], [0, 0, 8]],
        species=["Mo", "N"],
        coords=[[0, 0, 0], [0.8, 0.8, 0.8]],
    )
    model = Structure3D.from_pymatgen(struct, empty_df(2))

    bonds = BondDetector(max_bond_length=2.8).detect(struct, model.atoms)

    assert bonds == []
```

- [ ] **Step 2: Run the failing bond tests**

Run:

```powershell
python -m pytest tests/test_bond_detector.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'core.bond_detector'`.

- [ ] **Step 3: Implement BondDetector**

Create `core/bond_detector.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from pymatgen.core.periodic_table import Element

from core.structure_model import Atom3D, Bond3D


@dataclass(frozen=True)
class BondDetector:
    scale_factor: float = 1.25
    max_bond_length: float = 2.8

    def detect(self, struct, atoms: list[Atom3D]) -> list[Bond3D]:
        bonds: list[Bond3D] = []
        drawn: set[tuple[int, int]] = set()
        i_list, j_list, _, _, _ = struct.get_neighbor_list(r=self.max_bond_length)

        for i, j in zip(i_list, j_list):
            if i == j:
                continue
            atom_i = atoms[int(i)]
            atom_j = atoms[int(j)]
            key = tuple(sorted((atom_i.atom_id, atom_j.atom_id)))
            if key in drawn:
                continue

            dist, image = struct.lattice.get_distance_and_image(
                struct.frac_coords[int(i)],
                struct.frac_coords[int(j)],
            )
            if dist > self.max_bond_length:
                continue
            if dist > self.scale_factor * (self._radius(atom_i.element) + self._radius(atom_j.element)):
                continue

            start = tuple(float(v) for v in struct.cart_coords[int(i)])
            end_coords = struct.cart_coords[int(j)] + struct.lattice.get_cartesian_coords(image)
            end = tuple(float(v) for v in end_coords)
            bonds.append(Bond3D(atom_i=atom_i.atom_id, atom_j=atom_j.atom_id, start=start, end=end, length=float(dist)))
            drawn.add(key)

        return bonds

    @staticmethod
    def _radius(element: str) -> float:
        try:
            radius = Element(element).covalent_radius
            return float(radius) if radius is not None else 0.7
        except Exception:
            return 0.7
```

- [ ] **Step 4: Run bond tests**

Run:

```powershell
python -m pytest tests/test_bond_detector.py -v
```

Expected: PASS.

- [ ] **Step 5: Add bonds to Structure3D**

Modify `core/structure_model.py` by adding this method inside `Structure3D`:

```python
    def with_bonds(self, bonds: list[Bond3D]) -> "Structure3D":
        self.bonds = bonds
        return self
```

- [ ] **Step 6: Run model and bond tests**

Run:

```powershell
python -m pytest tests/test_structure_model.py tests/test_bond_detector.py -v
```

Expected: PASS.

---

### Task 3: Add ChargeColorMapper

**Files:**
- Create: `rendering/__init__.py`
- Create: `rendering/charge_color_mapper.py`
- Test: `tests/test_charge_color_mapper.py`

- [ ] **Step 1: Write failing color mapper tests**

Create `tests/test_charge_color_mapper.py`:

```python
from rendering.charge_color_mapper import ChargeColorMapper


def test_positive_charge_maps_to_red_gain():
    mapper = ChargeColorMapper([-1.0, 0.0, 1.0])

    color = mapper.rgb_for_charge(1.0)

    assert color[0] > color[2]
    assert mapper.label_for_charge(1.0) == "electron gain"


def test_negative_charge_maps_to_blue_loss():
    mapper = ChargeColorMapper([-1.0, 0.0, 1.0])

    color = mapper.rgb_for_charge(-1.0)

    assert color[2] > color[0]
    assert mapper.label_for_charge(-1.0) == "electron loss"


def test_zero_charge_maps_to_neutral():
    mapper = ChargeColorMapper([-1.0, 0.0, 1.0])

    assert mapper.rgb_for_charge(0.0) == (0.85, 0.85, 0.85)
    assert mapper.clim == (-1.0, 1.0)
```

- [ ] **Step 2: Run failing color tests**

Run:

```powershell
python -m pytest tests/test_charge_color_mapper.py -v
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement package marker and mapper**

Create `rendering/__init__.py`:

```python
"""Rendering helpers for the 3D structure viewer."""
```

Create `rendering/charge_color_mapper.py`:

```python
from __future__ import annotations


class ChargeColorMapper:
    """Bader charge color semantics: positive gain is red, negative loss is blue."""

    def __init__(self, charges, neutral=(0.85, 0.85, 0.85)):
        values = [float(v) for v in charges]
        max_abs = max((abs(v) for v in values), default=1.0)
        if max_abs == 0:
            max_abs = 1.0
        self.clim = (-max_abs, max_abs)
        self.neutral = neutral

    def rgb_for_charge(self, charge: float) -> tuple[float, float, float]:
        value = float(charge)
        max_abs = self.clim[1]
        if abs(value) < 1e-12:
            return self.neutral
        intensity = min(1.0, abs(value) / max_abs)
        channel = max(0.05, 1.0 - intensity)
        if value > 0:
            return (1.0, channel, channel)
        return (channel, channel, 1.0)

    @staticmethod
    def label_for_charge(charge: float) -> str:
        if charge > 0:
            return "electron gain"
        if charge < 0:
            return "electron loss"
        return "neutral"
```

- [ ] **Step 4: Run color tests**

Run:

```powershell
python -m pytest tests/test_charge_color_mapper.py -v
```

Expected: PASS.

---

### Task 4: Fix Charge Gain/Loss Summary Semantics

**Files:**
- Modify: `gui/main_window.py`
- Test: manual plus existing import check

- [ ] **Step 1: Locate the summary block**

In `gui/main_window.py`, find:

```python
max_gain_idx = df['Bader_Charge'].idxmin()
max_loss_idx = df['Bader_Charge'].idxmax()
```

- [ ] **Step 2: Replace with positive-gain semantics**

Change it to:

```python
max_gain_idx = df['Bader_Charge'].idxmax()
max_loss_idx = df['Bader_Charge'].idxmin()
```

- [ ] **Step 3: Run a syntax check**

Run:

```powershell
python -m py_compile gui/main_window.py
```

Expected: no output and exit code 0.

---

### Task 5: Add PyVistaStructureRenderer Skeleton

**Files:**
- Create: `rendering/pyvista_structure_renderer.py`
- Test: import check first

- [ ] **Step 1: Create renderer skeleton**

Create `rendering/pyvista_structure_renderer.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyvista as pv
from pymatgen.core.periodic_table import Element

from core.structure_model import Atom3D, Structure3D
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
    color_by: str = "Bader Charge"
    representation: str = "ball_stick"
    selected_atom_id: int | None = None
    visible_atom_ids: set[int] | None = None


class PyVistaStructureRenderer:
    def __init__(self, plotter):
        self.plotter = plotter
        self.atom_actors: dict[int, object] = {}
        self.atom_meshes: dict[int, pv.PolyData] = {}
        self.actor_to_atom_id: dict[str, int] = {}
        self.export_meshes: list[pv.DataSet] = []

    def clear(self):
        self.plotter.clear()
        self.atom_actors.clear()
        self.atom_meshes.clear()
        self.actor_to_atom_id.clear()
        self.export_meshes.clear()

    def render(self, model: Structure3D, settings: RenderSettings):
        self.clear()
        if settings.show_axes:
            self.plotter.add_axes()

        mapper = ChargeColorMapper([atom.charge for atom in model.atoms])
        for atom in model.atoms:
            if settings.visible_atom_ids is not None and atom.atom_id not in settings.visible_atom_ids:
                continue
            self._add_atom(atom, mapper, settings)

        if settings.show_bonds:
            self._add_bonds(model, settings)
        if settings.show_cell:
            self._add_unit_cell(model)
        if settings.show_labels:
            self._add_labels(model, settings)
        if settings.color_by == "Bader Charge":
            self._add_colorbar(mapper)

        self.plotter.update()

    def atom_id_for_mesh(self, mesh) -> int | None:
        for atom_id, stored in self.atom_meshes.items():
            if stored == mesh:
                return atom_id
        return None

    def screenshot(self, path: str):
        self.plotter.screenshot(path)

    def export_model(self, path: str):
        if not self.export_meshes:
            raise ValueError("No rendered meshes to export.")
        combined = pv.MultiBlock({f"mesh_{i}": mesh for i, mesh in enumerate(self.export_meshes)})
        combined.save(path)

    def _add_atom(self, atom: Atom3D, mapper: ChargeColorMapper, settings: RenderSettings):
        radius = self._atom_radius(atom, settings)
        if atom.atom_id == settings.selected_atom_id:
            radius *= 1.18

        sphere = pv.Sphere(radius=radius, center=atom.cart_coords, theta_resolution=32, phi_resolution=32)
        color = self._atom_color(atom, mapper, settings)
        opacity = 1.0
        actor = self.plotter.add_mesh(
            sphere,
            color=color,
            opacity=opacity,
            smooth_shading=True,
            specular=0.6,
            specular_power=32,
            ambient=settings.ambient_light,
            diffuse=0.85,
            pickable=True,
        )
        self.atom_actors[atom.atom_id] = actor
        self.atom_meshes[atom.atom_id] = sphere
        self.export_meshes.append(sphere)

        if atom.atom_id == settings.selected_atom_id:
            self.plotter.add_mesh(sphere.extract_feature_edges(feature_angle=30), color="yellow", line_width=3)

    def _add_bonds(self, model: Structure3D, settings: RenderSettings):
        visible = settings.visible_atom_ids
        for bond in model.bonds:
            if visible is not None and (bond.atom_i not in visible or bond.atom_j not in visible):
                continue
            tube = pv.Line(bond.start, bond.end).tube(radius=settings.bond_radius)
            self.plotter.add_mesh(tube, color="#666666", opacity=0.85, smooth_shading=True)
            self.export_meshes.append(tube)

    def _add_unit_cell(self, model: Structure3D):
        import numpy as np

        origin = np.array([0.0, 0.0, 0.0])
        a, b, c = model.lattice_matrix
        corners = [origin, a, b, c, a + b, a + c, b + c, a + b + c]
        pairs = [(0, 1), (0, 2), (0, 3), (1, 4), (1, 5), (2, 4), (2, 6), (3, 5), (3, 6), (4, 7), (5, 7), (6, 7)]
        for i, j in pairs:
            line = pv.Line(corners[i], corners[j])
            self.plotter.add_mesh(line, color="#333333", line_width=2)
            self.export_meshes.append(line)

    def _add_labels(self, model: Structure3D, settings: RenderSettings):
        visible = settings.visible_atom_ids
        points = []
        labels = []
        for atom in model.atoms:
            if visible is not None and atom.atom_id not in visible:
                continue
            points.append(atom.cart_coords)
            labels.append(f"{atom.element}{atom.atom_id}")
        if points:
            self.plotter.add_point_labels(points, labels, point_size=0, font_size=11)

    def _add_colorbar(self, mapper: ChargeColorMapper):
        dummy = pv.Sphere(radius=0.001, center=(0, 0, 0))
        dummy.point_data["Bader Charge"] = [mapper.clim[1]] * dummy.n_points
        self.plotter.add_mesh(
            dummy,
            scalars="Bader Charge",
            cmap="bwr",
            clim=mapper.clim,
            opacity=0.0,
            scalar_bar_args={"title": "Bader Charge (e)", "n_labels": 5},
        )

    @staticmethod
    def _atom_radius(atom: Atom3D, settings: RenderSettings) -> float:
        try:
            covalent = Element(atom.element).covalent_radius or 0.7
        except Exception:
            covalent = 0.7
        multiplier = 1.0 if settings.representation == "space_filling" else 0.4
        return float(covalent) * multiplier * settings.sphere_scale

    @staticmethod
    def _atom_color(atom: Atom3D, mapper: ChargeColorMapper, settings: RenderSettings):
        if settings.color_by == "Element":
            return None
        return mapper.rgb_for_charge(atom.charge)
```

- [ ] **Step 2: Run import check**

Run:

```powershell
python - <<'PY'
from rendering.pyvista_structure_renderer import PyVistaStructureRenderer, RenderSettings
print(RenderSettings())
PY
```

Expected: prints a `RenderSettings(...)` instance.

---

### Task 6: Rewire Visualizer3D To Use The Pipeline

**Files:**
- Modify: `gui/visualizer_3d.py`

- [ ] **Step 1: Add imports**

Add these imports near the top of `gui/visualizer_3d.py`:

```python
from core.bond_detector import BondDetector
from core.structure_model import Structure3D
from rendering.pyvista_structure_renderer import PyVistaStructureRenderer, RenderSettings
```

- [ ] **Step 2: Add new fields in `__init__`**

Inside `Visualizer3D.__init__`, add:

```python
self.structure_model = None
self.renderer = None
self._pymatgen_struct = None
```

- [ ] **Step 3: Initialize renderer after plotter creation**

After:

```python
self.plotter = QtInteractor(self)
```

add:

```python
self.renderer = PyVistaStructureRenderer(self.plotter)
```

- [ ] **Step 4: Replace `load_data` internals**

Replace `load_data` with:

```python
def load_data(self, struct, df):
    self.struct = struct
    self.df = df
    self._pymatgen_struct = struct
    self._cached_bonds = None
    self.selected_atom_idx = -1

    if struct is None:
        self.structure_model = None
        if self.renderer:
            self.renderer.clear()
        return

    model = Structure3D.from_pymatgen(struct, df)
    model.with_bonds(BondDetector().detect(struct, model.atoms))
    self.structure_model = model

    if df is not None:
        self.chg_dict = dict(zip(df["Atom"].values, df["Bader_Charge"].values))
        self.charge_dict = dict(zip(df["Atom"].values, df["CHARGE"].values))
        self.zval_dict = dict(zip(df["Atom"].values, df["ZVAL"].values))
    else:
        self.chg_dict = {}
        self.charge_dict = {}
        self.zval_dict = {}

    self.render_scene()
    self.reset_camera()
```

- [ ] **Step 5: Replace `render_scene` with delegation**

Replace the body of `render_scene` with:

```python
def render_scene(self):
    if not self.structure_model:
        if self.renderer:
            self.renderer.clear()
        return

    rs = self.render_settings
    target_set = self._parse_target_str(rs.get("target_str", ""))
    selected_atom_id = self.selected_atom_idx + 1 if self.selected_atom_idx >= 0 else None
    settings = RenderSettings(
        show_bonds=rs.get("show_bonds", True),
        show_cell=rs.get("show_cell", True),
        show_axes=rs.get("show_axes_flag", True),
        show_labels=rs.get("show_labels", False),
        fade_background=rs.get("hide_bg", True),
        background_opacity=max(0.0, min(1.0, 1.0 - rs.get("transparency", 10) / 100.0)),
        sphere_scale=rs.get("sphere_scale", 100) / 100.0,
        bond_radius=rs.get("bond_radius", 8) / 100.0,
        ambient_light=rs.get("ambient_light", 65) / 100.0,
        color_by=rs.get("color_by", "Bader Charge"),
        representation=rs.get("representation", "ball_stick"),
        selected_atom_id=selected_atom_id,
        visible_atom_ids=target_set,
    )
    self.renderer.render(self.structure_model, settings)
```

- [ ] **Step 6: Replace `on_pick` atom lookup**

In `on_pick`, replace the loop over `self.meshes.items()` with:

```python
atom_id = self.renderer.atom_id_for_mesh(mesh) if self.renderer else None
if atom_id is not None and self.structure_model:
    atom = self.structure_model.atom_by_id(atom_id)
    self.selected_atom_idx = atom_id - 1
    coord_num = self._compute_coordination(self.selected_atom_idx)
    self.atom_selected.emit({
        "id": atom.atom_id,
        "element": atom.element,
        "charge": atom.charge,
        "bader_raw": atom.raw_charge,
        "zval": atom.zval,
        "coord": coord_num,
        "pos": atom.cart_coords,
    })
    self.render_scene()
    return
```

- [ ] **Step 7: Replace `export_model`**

Replace `export_model` with:

```python
def export_model(self, filepath):
    if not self.renderer:
        raise ValueError("3D renderer is not initialized.")
    self.renderer.export_model(filepath)
```

- [ ] **Step 8: Run syntax checks**

Run:

```powershell
python -m py_compile core/structure_model.py core/bond_detector.py rendering/charge_color_mapper.py rendering/pyvista_structure_renderer.py gui/visualizer_3d.py
```

Expected: no output and exit code 0.

---

### Task 7: Add Renderer Smoke Test

**Files:**
- Create: `tests/test_3d_renderer_smoke.py`

- [ ] **Step 1: Write smoke test**

Create `tests/test_3d_renderer_smoke.py`:

```python
from pathlib import Path

import pandas as pd
import pyvista as pv
from PIL import Image
from pymatgen.core.structure import Structure

from core.bond_detector import BondDetector
from core.structure_model import Structure3D
from rendering.pyvista_structure_renderer import PyVistaStructureRenderer, RenderSettings


def test_renderer_creates_nonblank_screenshot(tmp_path):
    pv.OFF_SCREEN = True
    plotter = pv.Plotter(off_screen=True, window_size=(400, 300))
    struct = Structure(
        lattice=[[5, 0, 0], [0, 5, 0], [0, 0, 5]],
        species=["Mo", "N"],
        coords=[[0, 0, 0], [0.4, 0, 0]],
    )
    df = pd.DataFrame({
        "Atom": [1, 2],
        "CHARGE": [7.0, 4.5],
        "ZVAL": [6.0, 5.0],
        "Bader_Charge": [1.0, -0.5],
    })
    model = Structure3D.from_pymatgen(struct, df)
    model.with_bonds(BondDetector().detect(struct, model.atoms))

    renderer = PyVistaStructureRenderer(plotter)
    renderer.render(model, RenderSettings())
    output = tmp_path / "render.png"
    renderer.screenshot(str(output))

    image = Image.open(output).convert("RGB")
    colors = image.getcolors(maxcolors=1_000_000)
    assert output.stat().st_size > 1000
    assert colors is not None
    assert len(colors) > 1
```

- [ ] **Step 2: Add Pillow if needed**

If `PIL` is missing, add this line to `requirements.txt`:

```text
Pillow
```

- [ ] **Step 3: Run smoke test**

Run:

```powershell
python -m pytest tests/test_3d_renderer_smoke.py -v
```

Expected: PASS on environments with working offscreen VTK. If local VTK offscreen rendering is unavailable, mark the test with `pytest.skip` only after confirming the failure is environmental, not a renderer exception.

---

### Task 8: Manual App Validation

**Files:**
- No code unless validation exposes defects.

- [ ] **Step 1: Run all focused tests**

Run:

```powershell
python -m pytest tests/test_structure_model.py tests/test_bond_detector.py tests/test_charge_color_mapper.py -v
```

Expected: PASS.

- [ ] **Step 2: Launch the app**

Run:

```powershell
python main.py
```

Expected: app opens.

- [ ] **Step 3: Validate real workspace rendering**

In the app:

```text
1. Select workspaces/Mo-N4-Li2S.
2. Run analysis if the workspace is not already calculated.
3. Open 3D Structure View.
4. Confirm atoms render as shaded spheres.
5. Confirm chemical bonds render as cylinders.
6. Confirm unit cell and axes are visible.
7. Toggle Show chemical bonds.
8. Toggle Show unit cell.
9. Click one atom and confirm the right panel updates.
10. Export PNG and verify it is not blank.
```

Expected: all listed checks pass.

---

### Task 9: Commit Or Record Non-Git Completion

**Files:**
- No code.

- [ ] **Step 1: Check repository state**

Run:

```powershell
git status --short
```

Expected in this workspace today: `fatal: not a git repository`.

- [ ] **Step 2: If it is a Git repo, commit**

Only if `git status` succeeds, run:

```powershell
git add core/structure_model.py core/bond_detector.py rendering tests gui/visualizer_3d.py gui/main_window.py requirements.txt docs/superpowers
git commit -m "refactor: rebuild 3d structure rendering pipeline"
```

- [ ] **Step 3: If it is not a Git repo, report changed files**

Report the created and modified file list in the final response instead of claiming a commit.

---

## Self-Review

- Spec coverage: model, bond detection, charge semantics, renderer split, selection, screenshot, model export, and manual validation are all covered.
- Placeholder scan: no `TBD`, `TODO`, or vague implementation-only steps remain.
- Type consistency: `Atom3D`, `Bond3D`, `Structure3D`, `RenderSettings`, and `PyVistaStructureRenderer` names are consistent across tasks.
- Scope: this plan intentionally stops at the stable pipeline and first interaction loop. Advanced UI controls, clipping, volumetric rendering, and measurement tools remain out of scope.

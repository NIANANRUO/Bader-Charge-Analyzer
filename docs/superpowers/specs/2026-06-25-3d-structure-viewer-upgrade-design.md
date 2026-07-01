# 3D Structure Viewer Upgrade Design

## Purpose

Upgrade the 3D Structure View from a fragile PyVista prototype into a reliable atomistic structure viewer for VASP Bader charge analysis.

The goal is not visual polish first. The first goal is a correct rendering pipeline:

- Load real `CONTCAR` or `POSCAR` structure data.
- Map `ACF.dat` and `POTCAR` values onto the correct atom IDs.
- Render atoms as true 3D spheres.
- Render inferred chemical bonds as true 3D cylinders.
- Render unit cell edges, orientation axes, and a charge colorbar.
- Support interactive picking, focus, isolate, view reset, screenshots, and model export.

## Current Assessment

The project already uses `PyVistaQt + VTK` in `gui/visualizer_3d.py`, so the fix is not to switch away from the engine. The problem is that the current implementation mixes data mapping, bond detection, rendering, UI state, picking, and export inside one widget.

Observed risks:

- `Visualizer3D` owns too many responsibilities.
- Bader charge colors are manually computed per atom instead of driven by one scalar mapping path.
- The colorbar is created from a dummy mesh, which can drift from the actual atom colors.
- Model export attempts to save actors instead of persistent mesh objects.
- Charge semantics are inconsistent: `core/calculator.py` defines positive as electron gain, while some summary logic treats the minimum value as max gain.
- Bond detection is embedded in the widget and has no focused tests.
- Screenshot evidence shows the current render can become effectively blank.

## Design Direction

Keep `PyVistaQt + VTK` as the rendering backend, but split the 3D feature into a small pipeline:

```text
VASP files / calculated DataFrame
        |
        v
Structure3D model
        |
        +--> BondDetector
        +--> ChargeColorMapper
        |
        v
PyVistaStructureRenderer
        |
        v
Visualizer3D QWidget
        |
        v
AnalysisPanel3D controls
```

The widget should coordinate the UI. It should not be the place where chemistry, charge semantics, mesh assembly, and export rules live.

## Proposed Files

Create:

- `core/structure_model.py`
  - Defines `Atom3D`, `Bond3D`, and `Structure3D`.
  - Converts a pymatgen `Structure` plus analysis DataFrame into a stable atom-indexed model.
  - Stores atom ID, element, Cartesian position, fractional position, Bader charge, raw `CHARGE`, `ZVAL`, and selection/display metadata.

- `core/bond_detector.py`
  - Infers bonds using covalent radii and periodic boundary conditions.
  - Exposes tunable `scale_factor` and `max_bond_length`.
  - Returns `Bond3D` records with atom IDs, length, and start/end Cartesian points.

- `rendering/charge_color_mapper.py`
  - Owns Bader charge semantics.
  - Positive `Bader_Charge` means electron gain and maps to red.
  - Zero maps to neutral light gray or white.
  - Negative `Bader_Charge` means electron loss and maps to blue.
  - Supports symmetric automatic range and manual range.

- `rendering/pyvista_structure_renderer.py`
  - Owns PyVista mesh creation and scene updates.
  - Creates and stores atom sphere meshes, bond tube meshes, unit cell line meshes, labels, scalar bar, and selection highlight.
  - Provides methods such as `render(structure_model, settings)`, `pick_atom(mesh)`, `screenshot(path)`, and `export_model(path)`.

Modify:

- `gui/visualizer_3d.py`
  - Keep as the Qt widget wrapper around `QtInteractor`.
  - Delegate chemistry/model/render work to the new modules.
  - Emit atom selection data from the stable `Atom3D` model.

- `gui/analysis_panel.py`
  - Keep the right-side panel, but align emitted settings with the new render settings model.
  - Add charge range controls only after the first stable rendering milestone is complete.

- `gui/main_window.py`
  - Keep current signal wiring.
  - Fix max gain/loss summary semantics to match the project definition.

## Charge Semantics

Use one definition everywhere:

```text
Bader_Charge = CHARGE - ZVAL
Bader_Charge > 0: electron gain, red
Bader_Charge = 0: neutral, light gray / white
Bader_Charge < 0: electron loss, blue
```

This definition already matches the comment in `core/calculator.py`. All table labels, plot summaries, 3D color mapping, colorbar title, and right-panel selection labels must follow it.

## Rendering Requirements

First stable milestone:

- Atoms are PyVista sphere meshes, not 2D points.
- Bonds are PyVista tube/cylinder meshes, not lines painted in screen space.
- Unit cell is rendered as twelve 3D edge segments.
- Orientation axes are visible.
- Default camera is isometric and fitted to the structure.
- Empty state is explicit when no structure is loaded.
- Rendering a real workspace must not produce a black or blank screenshot.

Default visual settings:

```text
Representation: Ball & Stick
Atom sphere scale: covalent radius * 0.35 to 0.45
Bond radius: 0.04 to 0.08 Angstrom
Background atom opacity: 0.35 to 0.45 when fading is enabled
Selected atom scale: 1.15x to 1.20x
Neutral charge color: light gray
Electron gain: red
Electron loss: blue
```

## Interaction Requirements

First interactive milestone:

- Clicking an atom selects it.
- The right panel displays atom ID, element, Bader charge, raw `CHARGE`, `ZVAL`, coordination number, and Cartesian position.
- `Focus` moves the camera target to the selected atom.
- `Isolate` displays the selected atom and its bonded neighbors.
- `Clear` removes selection and restores the full structure.
- `Show atom labels` displays element plus atom ID.

Hover tooltip and context menu are useful but should come after stable click selection.

## Export Requirements

Screenshot export:

- Uses the current camera and current visual settings.
- Produces a non-empty PNG.

Model export:

- Exports actual stored PyVista mesh data, not renderer actors.
- Supports `PLY` and `VTP` first.
- `OBJ` can be added after `PLY/VTP` are verified.

## Testing Strategy

Add focused tests before broad GUI work:

- `tests/test_structure_model.py`
  - Builds a `Structure3D` from a small pymatgen structure and DataFrame.
  - Verifies atom IDs, elements, positions, `CHARGE`, `ZVAL`, and `Bader_Charge`.

- `tests/test_bond_detector.py`
  - Uses a simple known geometry.
  - Verifies expected bond count and periodic image handling.

- `tests/test_charge_color_mapper.py`
  - Verifies positive charge maps toward red, zero to neutral, and negative toward blue.
  - Verifies symmetric charge range.

- `tests/test_3d_renderer_smoke.py`
  - Runs a minimal offscreen render if supported by the local environment.
  - Saves a screenshot and verifies it is not blank.

Manual validation:

- Load `workspaces/Mo-N4-Li2S`.
- Run analysis if needed.
- Open `3D Structure View`.
- Verify atoms, bonds, unit cell, axes, colorbar, and camera controls.
- Export PNG.
- Export PLY or VTP.

## Milestones

### Milestone 1: Correct Data And Geometry

- Create `Structure3D` and atom records.
- Create `BondDetector`.
- Fix charge gain/loss summary semantics.
- Add tests for model and bond detection.

Acceptance:

- Model tests pass.
- Bond detector tests pass.
- Real workspace atom count matches structure atom count.

### Milestone 2: Stable PyVista Render

- Move mesh creation into `PyVistaStructureRenderer`.
- Render atoms, bonds, unit cell, axes, and colorbar.
- Store actual mesh objects for export.
- Add nonblank render smoke test where the environment permits.

Acceptance:

- Real workspace renders a visible ball-and-stick structure.
- Screenshot is not blank.
- `Show chemical bonds` visibly toggles bonds.
- `Show unit cell` visibly toggles the unit cell.

### Milestone 3: Selection And Inspection

- Map picked meshes to atom IDs.
- Update right panel from `Atom3D`.
- Implement focus, isolate, clear, labels.

Acceptance:

- Clicking an atom updates the right panel.
- Focus and isolate affect the current 3D view.
- Clear restores the full structure.

### Milestone 4: Export And UI Completion

- Implement reliable PNG export.
- Implement verified PLY/VTP export.
- Add charge range controls.
- Add projection mode control if not already stable.

Acceptance:

- Exported PNG reflects the current camera.
- Exported model can be opened by a standard VTK/PyVista reader.
- Charge colorbar range matches atom colors.

## Out Of Scope For The First Upgrade

- Volumetric CHGCAR charge density rendering.
- Surface isosurfaces.
- Full measurement tools.
- Clipping planes.
- Animated camera paths.
- Periodic supercell replication UI.

These are valid later features, but they should not block a correct ball-and-stick Bader charge viewer.

## Implementation Gate

Do not start by adding more right-panel controls. Start by extracting the data model and renderer boundaries, then make the simplest visible real structure work.

The minimum acceptable result is a true 3D ball-and-stick view loaded from real VASP data, with bonds, unit cell, axes, Bader charge colors, colorbar, and click selection.

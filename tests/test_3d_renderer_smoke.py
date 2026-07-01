"""Task 7: offscreen renderer smoke test.

Renders a small Mo-N structure through the full pipeline (Structure3D +
BondDetector + PyVistaStructureRenderer), screenshots to PNG, and asserts the
image is non-blank. Skips automatically when the local VTK build cannot
produce a valid offscreen OpenGL context (the documented Task 7 caveat).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
import pyvista as pv

pv.OFF_SCREEN = True

try:
    from PIL import Image
except ImportError:  # pragma: no cover - environment guard
    Image = None

from pymatgen.core.structure import Structure

from core.bond_detector import BondDetector
from core.structure_model import Structure3D
from rendering.pyvista_structure_renderer import PyVistaStructureRenderer, RenderSettings


def _offscreen_rendering_available() -> bool:
    """Probe whether VTK can actually render offscreen on this machine.

    `pv.Plotter(off_screen=True)` constructs without error even when the GL
    backend is missing; the failure only surfaces on `update()`/`screenshot()`.
    We initialise the interactor, render a throwaway single-sphere scene, and
    check the byte size of the output. Mirrors what `PyVistaStructureRenderer`
    does internally (`plotter.update()` -> `iren.process_events()`).
    """
    try:
        probe = pv.Plotter(off_screen=True, window_size=(64, 48))
        probe.iren.initialize()
        probe.add_mesh(pv.Sphere())
        probe.update()
        tmp = Path(os.environ.get("TEMP", "/tmp")) / "_pv_probe.png"
        probe.screenshot(str(tmp))
        ok = tmp.exists() and tmp.stat().st_size > 0
        probe.close()
        if tmp.exists():
            tmp.unlink()
        return ok
    except Exception:
        return False


_OFFSCREEN_OK = _offscreen_rendering_available()


pytestmark = pytest.mark.skipif(
    not _OFFSCREEN_OK or Image is None,
    reason="Offscreen VTK rendering unavailable in this environment (Task 7 documented caveat).",
)


def test_renderer_creates_nonblank_screenshot(tmp_path):
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

    plotter = pv.Plotter(off_screen=True, window_size=(400, 300))
    try:
        # Offscreen plotters do not auto-init the interactor; PyVistaStructureRenderer
        # calls plotter.update() which routes through iren.process_events().
        plotter.iren.initialize()
        renderer = PyVistaStructureRenderer(plotter)
        renderer.render(model, RenderSettings())
        output = tmp_path / "render.png"
        renderer.screenshot(str(output))

        assert output.exists()
        assert output.stat().st_size > 1000, "screenshot file too small to be a real render"

        image = Image.open(output).convert("RGB")
        colors = image.getcolors(maxcolors=1_000_000)
        assert colors is not None, "image has more than 1M colors (unexpected for a 400x300 scene)"
        assert len(colors) > 1, "screenshot is blank (single color only)"
    finally:
        plotter.close()

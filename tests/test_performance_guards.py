import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from gui.main_window import MainWindow
from gui.analysis_panel import AnalysisPanel3D
from gui.visualizer_3d import MultiVisualizer3DPanel


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


class Dummy3DPanel:
    def __init__(self):
        self.calls = []

    def set_workspaces_data(self, data_by_workspace, names):
        self.calls.append((dict(data_by_workspace), list(names)))


class DummyVisualizer:
    def __init__(self):
        self.loads = []
        self.appearance_updates = []
        self.cleaned = False

    def load_data(self, struct, df):
        self.loads.append((struct, df))

    def update_appearance(self, df, selected_atom_ids):
        self.appearance_updates.append((df, tuple(selected_atom_ids)))

    def cleanup(self):
        self.cleaned = True


def test_3d_sync_is_deferred_when_3d_tab_is_not_active():
    app()
    window = MainWindow()
    dummy = Dummy3DPanel()
    window._has_3d = True
    window._3d_loaded = True
    window.visualizer_3d = dummy
    window.selected_workspaces = ["ws1"]
    window.all_calculated_data = {"ws1": {"struct": object(), "df": object()}}
    window.nav_tabs.setCurrentIndex(1)

    window._request_3d_sync()

    assert dummy.calls == []
    assert window._3d_dirty is True

    window.close()


def test_multi_visualizer_skips_reloading_unchanged_workspace_data(monkeypatch):
    app()
    panel = MultiVisualizer3DPanel()
    visualizer = DummyVisualizer()

    def fake_create_tile(workspace):
        return {
            "frame": QFrame(),
            "visualizer": visualizer,
            "button": QPushButton(),
            "data_key": None,
        }

    monkeypatch.setattr(panel, "_create_tile", fake_create_tile)
    data = {"ws1": {"struct": object(), "df": object()}}

    panel.set_workspaces_data(data, ["ws1"])
    panel.set_workspaces_data(data, ["ws1"])

    assert len(visualizer.loads) == 1

    panel.close()


def semantic_data(structure_revision="structure-1", analysis_revision=1, selected=(1,)):
    return {
        "struct": object(),
        "df": object(),
        "structure_fingerprint": structure_revision,
        "atom_count": 2,
        "element_sequence": ("Li", "S"),
        "analysis_revision": analysis_revision,
        "selected_atom_ids": selected,
        "source_revision": "source-1",
        "charge_revision": "charge-1",
    }


def test_multi_visualizer_scope_change_is_appearance_only(monkeypatch):
    app()
    panel = MultiVisualizer3DPanel()
    visualizer = DummyVisualizer()
    monkeypatch.setattr(
        panel,
        "_create_tile",
        lambda _workspace: {
            "frame": QFrame(),
            "visualizer": visualizer,
            "button": QPushButton(),
            "geometry_key": None,
            "appearance_key": None,
        },
    )
    first = {"ws": semantic_data()}
    panel.set_workspaces_data(first, ["ws"])
    panel.active_workspace = "ws"
    panel.maximized_workspace = "ws"
    visualizer.selected_atom_idx = 0
    changed = {
        "ws": dict(first["ws"], analysis_revision=2, selected_atom_ids=(2,))
    }

    panel.set_workspaces_data(changed, ["ws"])

    assert len(visualizer.loads) == 1
    assert visualizer.appearance_updates == [(changed["ws"]["df"], (2,))]
    assert visualizer.selected_atom_idx == 0
    assert panel.active_workspace == "ws"
    assert panel.maximized_workspace == "ws"
    panel.close()


def test_multi_visualizer_identical_semantic_payload_does_zero_work(monkeypatch):
    app()
    panel = MultiVisualizer3DPanel()
    visualizer = DummyVisualizer()
    monkeypatch.setattr(
        panel,
        "_create_tile",
        lambda _workspace: {
            "frame": QFrame(),
            "visualizer": visualizer,
            "button": QPushButton(),
            "geometry_key": None,
            "appearance_key": None,
        },
    )
    data = {"ws": semantic_data()}
    panel.set_workspaces_data(data, ["ws"])
    visualizer.appearance_updates.clear()

    panel.set_workspaces_data({"ws": dict(data["ws"])}, ["ws"])

    assert len(visualizer.loads) == 1
    assert visualizer.appearance_updates == []
    panel.close()


def test_multi_visualizer_structure_change_rebuilds_geometry(monkeypatch):
    app()
    panel = MultiVisualizer3DPanel()
    visualizer = DummyVisualizer()
    monkeypatch.setattr(
        panel,
        "_create_tile",
        lambda _workspace: {
            "frame": QFrame(),
            "visualizer": visualizer,
            "button": QPushButton(),
            "geometry_key": None,
            "appearance_key": None,
        },
    )
    data = {"ws": semantic_data()}
    panel.set_workspaces_data(data, ["ws"])

    panel.set_workspaces_data(
        {"ws": semantic_data(structure_revision="structure-2")}, ["ws"]
    )

    assert len(visualizer.loads) == 2
    panel.close()


def test_reentering_3d_tab_does_not_sync_when_clean(monkeypatch):
    app()
    window = MainWindow()
    window._3d_loaded = True
    window._has_3d = True
    calls = []
    monkeypatch.setattr(
        window,
        "_request_3d_sync",
        lambda force=False: calls.append(("sync", force)),
    )
    window._3d_dirty = False

    window.on_tab_changed(2)
    window.on_tab_changed(0)
    window.on_tab_changed(2)

    assert calls == []
    window.close()


def test_main_window_scope_refresh_uses_appearance_entrypoint(monkeypatch):
    app()
    window = MainWindow()

    class Panel:
        def __init__(self):
            self.appearance_calls = []

        def update_workspace_appearances(self, payloads, names):
            self.appearance_calls.append((payloads, list(names)))

    panel = Panel()
    payload = semantic_data()
    window._3d_loaded = True
    window._has_3d = True
    window.visualizer_3d = panel
    window._3d_dirty = False
    window.nav_tabs.setCurrentIndex(2)
    monkeypatch.setattr(window, "_workspace_3d_payload", lambda _name: payload)

    window._request_3d_appearance_update(["ws"])

    assert panel.appearance_calls == [({"ws": payload}, ["ws"])]
    assert window._3d_dirty is False
    window.visualizer_3d = None
    window.close()


def test_analysis_panel_3d_does_not_emit_an_independent_empty_target():
    app()
    panel = AnalysisPanel3D()
    emitted = []
    panel.request_render_update.connect(emitted.append)

    panel.emit_render_update()

    assert "target_str" not in emitted[-1]
    panel.close()


def test_multi_visualizer_loads_many_workspaces_progressively(monkeypatch):
    app()
    panel = MultiVisualizer3DPanel()
    visualizers = {}

    def fake_create_tile(workspace):
        visualizer = DummyVisualizer()
        visualizers[workspace] = visualizer
        return {
            "frame": QFrame(),
            "visualizer": visualizer,
            "button": QPushButton(),
            "data_key": None,
        }

    monkeypatch.setattr(panel, "_create_tile", fake_create_tile)
    data = {
        "ws1": {"struct": object(), "df": object()},
        "ws2": {"struct": object(), "df": object()},
        "ws3": {"struct": object(), "df": object()},
    }

    panel.set_workspaces_data(data, ["ws1", "ws2", "ws3"])

    assert len(visualizers["ws1"].loads) == 1
    assert len(visualizers["ws2"].loads) == 0
    assert len(visualizers["ws3"].loads) == 0
    assert len(panel._pending_workspace_loads) == 2

    panel._load_next_pending_workspace()

    assert len(visualizers["ws2"].loads) == 1
    assert len(visualizers["ws3"].loads) == 0

    panel.close()


def test_multi_visualizer_cleanup_cancels_pending_loads_and_closes_tiles(monkeypatch):
    app()
    panel = MultiVisualizer3DPanel()
    visualizers = {}

    def fake_create_tile(workspace):
        visualizer = DummyVisualizer()
        visualizers[workspace] = visualizer
        return {
            "frame": QFrame(),
            "visualizer": visualizer,
            "button": QPushButton(),
            "data_key": None,
        }

    monkeypatch.setattr(panel, "_create_tile", fake_create_tile)
    data = {
        "ws1": {"struct": object(), "df": object()},
        "ws2": {"struct": object(), "df": object()},
        "ws3": {"struct": object(), "df": object()},
    }

    panel.set_workspaces_data(data, ["ws1", "ws2", "ws3"])
    assert panel._pending_workspace_loads

    panel.cleanup()

    assert panel._pending_workspace_loads == []
    assert panel.tiles == {}
    assert all(visualizer.cleaned for visualizer in visualizers.values())

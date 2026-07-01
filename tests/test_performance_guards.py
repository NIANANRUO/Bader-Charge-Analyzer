import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from gui.main_window import MainWindow
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
        self.cleaned = False

    def load_data(self, struct, df):
        self.loads.append((struct, df))

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

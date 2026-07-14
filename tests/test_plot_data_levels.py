import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication

from gui.plot_panel import PlotPanel

_APP = None

def app():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_plot_panel_never_reintroduces_workspace_missing_from_new_payload(monkeypatch):
    app()
    panel = PlotPanel()
    monkeypatch.setattr(panel, "apply_styles", lambda: None)
    data = {
        "selected": {
            "df": pd.DataFrame({
                "Atom": [1], "Element": ["O"], "Bader_Charge": [0.2]
            }),
            "struct": None,
        }
    }

    panel.plot_data(data)

    assert panel._ws_all == ["selected"]
    assert list(panel.current_data) == ["selected"]
    assert "stale" not in panel._original_data
    panel.close()


def test_plot_panel_element_level_switches_sum_and_mean(monkeypatch):
    app()
    panel = PlotPanel()
    monkeypatch.setattr(panel, "apply_styles", lambda: None)
    panel.cb_data_level.setCurrentText("元素")
    data = {
        "ws": {
            "df": pd.DataFrame({
                "Atom": [1, 2],
                "Element": ["O", "O"],
                "Bader_Charge": [0.2, 0.4],
            }),
            "struct": None,
        }
    }

    panel.plot_data(data)
    assert panel.current_data["ws"]["df"].iloc[0]["Bader_Charge"] == pytest.approx(0.6)

    panel.cb_element_metric.setCurrentText("平均值")
    assert panel.current_data["ws"]["df"].iloc[0]["Bader_Charge"] == pytest.approx(0.3)
    panel.close()


def test_plot_panel_retains_committed_scope_across_level_rebuilds(monkeypatch):
    app()
    panel = PlotPanel()
    monkeypatch.setattr(panel, "apply_styles", lambda: None)
    data = {
        "ws": {
            "df": pd.DataFrame({
                "Atom": [1, 2, 3, 4],
                "Element": ["Li", "O", "O", "S"],
                "Bader_Charge": [0.2, -0.3, 0.5, -0.1],
            }),
            "struct": None,
        }
    }

    panel.plot_data(data, selected_by_workspace={"ws": (2, 3)})
    assert panel._selected_by_workspace == {"ws": (2, 3)}
    assert panel.current_data["ws"]["df"]["Atom"].tolist() == [2, 3]

    panel.cb_data_level.setCurrentText("元素")
    assert panel.current_data["ws"]["df"]["Atom"].tolist() == ["O"]

    panel.cb_data_level.setCurrentText("原子")
    assert panel.current_data["ws"]["df"]["Atom"].tolist() == [2, 3]
    panel.close()


def test_plot_panel_explicit_scope_ignores_legacy_target(monkeypatch):
    app()
    panel = PlotPanel()
    monkeypatch.setattr(panel, "apply_styles", lambda: None)
    data = {
        "ws": {
            "df": pd.DataFrame({
                "Atom": [1, 2, 3],
                "Element": ["Li", "O", "O"],
                "Bader_Charge": [0.2, -0.3, 0.5],
            }),
            "struct": None,
        }
    }

    panel.plot_data(
        data,
        target="1",
        selected_by_workspace={"ws": (2, 3)},
    )

    assert panel.current_data["ws"]["df"]["Atom"].tolist() == [2, 3]
    panel.close()


def test_set_analysis_context_replaces_committed_workspace_scope(monkeypatch):
    app()
    panel = PlotPanel()
    monkeypatch.setattr(panel, "apply_styles", lambda: None)
    data = {
        "ws": {
            "df": pd.DataFrame({
                "Atom": [1, 2, 3],
                "Element": ["Li", "O", "O"],
                "Bader_Charge": [0.2, -0.3, 0.5],
            }),
            "struct": None,
        }
    }
    panel.plot_data(data, selected_by_workspace={"ws": (1,)})

    panel.set_analysis_context(selected_by_workspace={"ws": (2, 3)})

    assert panel._selected_by_workspace == {"ws": (2, 3)}
    assert panel.current_data["ws"]["df"]["Atom"].tolist() == [2, 3]
    panel.close()

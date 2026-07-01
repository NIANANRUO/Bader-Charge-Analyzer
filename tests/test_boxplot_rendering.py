# -*- coding: utf-8 -*-
import os
import sys
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from matplotlib.container import BarContainer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

qtawesome_stub = types.SimpleNamespace(icon=lambda *args, **kwargs: QIcon())
sys.modules.setdefault("qtawesome", qtawesome_stub)

from gui.plot_panel import PlotPanel


def boxplot_data():
    return {
        "A": {
            "df": pd.DataFrame(
                {
                    "Atom": [1, 2, 3],
                    "Element": ["N", "Mo", "Li"],
                    "Bader_Charge": [0.9, -1.2, -0.4],
                }
            )
        },
        "B": {
            "df": pd.DataFrame(
                {
                    "Atom": [1, 2, 3],
                    "Element": ["N", "Mo", "Li"],
                    "Bader_Charge": [1.0, -1.1, -0.3],
                }
            )
        },
    }


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_single_workspace_boxplot_renders_charge_bars():
    app()
    plot_panel = PlotPanel()
    plot_panel.current_data = {"A": boxplot_data()["A"]}

    plot_panel._draw_boxplot(
        x_labels=["A"],
        all_atoms=[1, 2, 3],
        element_map={1: "N", 2: "Mo", 3: "Li"},
        workspaces=["A"],
        cfg=plot_panel.config,
    )

    bar_containers = [
        container
        for container in plot_panel.ax.containers
        if isinstance(container, BarContainer)
    ]

    plot_panel.close()
    assert len(bar_containers) == 1
    assert [bar.get_height() for bar in bar_containers[0]] == [0.9, -1.2, -0.4]
    assert [
        plot_panel._bar_to_atom_id[bar]
        for bar in bar_containers[0]
    ] == [1, 2, 3]


def test_boxplot_workspace_dropdown_includes_multi_workspace_option():
    app()
    plot_panel = PlotPanel()
    plot_panel.current_data = boxplot_data()
    plot_panel.config.plot_type = "箱线图"

    plot_panel._update_chart_ws_dropdown()
    items = [
        plot_panel._chart_ws_combo.itemText(i)
        for i in range(plot_panel._chart_ws_combo.count())
    ]
    plot_panel._on_chart_ws_changed("全部（多体系）")

    plot_panel.close()
    assert items == ["全部（多体系）", "A", "B"]
    assert plot_panel._chart_ws_single is None

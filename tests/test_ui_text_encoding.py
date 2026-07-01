# -*- coding: utf-8 -*-
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpacerItem,
    QTabBar,
)
from PySide6.QtCore import Qt

from gui.main_window import MainWindow
from gui.plot_panel import PlotPanel
from gui.app_icon import app_icon_path, load_app_icon


BAD_TEXT_MARKERS = tuple(
    chr(code)
    for code in (
        0xFFFD,
        0x951B,
        0x9286,
        0x9358,
        0x93C1,
        0x93C2,
        0x6D63,
        0x9422,
        0x4F43,
        0x93B5,
        0x6DC7,
        0x7481,
        0x7F01,
        0x93C3,
        0x9983,
        0x9225,
        0x922B,
        0x9239,
        0x923A,
    )
) + ("δ" + chr(0xFFFD) * 4,)

SOURCE_BAD_MARKERS = (
    "\ufffd",
    "???",
    "Ã",
    "Â",
    "鈥",
    "鈮",
)


def iter_project_python_files():
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        if path == Path(__file__).resolve():
            continue
        if any(
            part == "__pycache__"
            or part == ".pytest_cache"
            or part.startswith(".pytest_tmp")
            for part in path.parts
        ):
            continue
        yield path


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def sample_plot_data():
    return {
        "A": {
            "df": pd.DataFrame(
                {
                    "Atom": [1, 2, 3, 4],
                    "Element": ["N", "P", "Mo", "Li"],
                    "Bader_Charge": [0.35, -0.45, 0.8, -0.2],
                }
            )
        },
        "B": {
            "df": pd.DataFrame(
                {
                    "Atom": [1, 2, 3, 4],
                    "Element": ["N", "P", "Mo", "Li"],
                    "Bader_Charge": [0.25, -0.3, 0.65, -0.1],
                }
            )
        },
    }


def test_python_sources_are_utf8_without_mojibake_markers():
    bad = []
    for path in iter_project_python_files():
        text = path.read_text(encoding="utf-8")
        markers = [marker for marker in SOURCE_BAD_MARKERS if marker in text]
        if markers:
            bad.append((str(path), markers))

    assert bad == []


def widget_texts(widget):
    texts = []
    for cls in (QLabel, QPushButton, QLineEdit, QCheckBox, QRadioButton):
        for obj in widget.findChildren(cls):
            for attr in ("text", "placeholderText", "toolTip", "windowTitle"):
                if hasattr(obj, attr):
                    value = getattr(obj, attr)()
                    if value:
                        texts.append(value)
    for tab_bar in widget.findChildren(QTabBar):
        for index in range(tab_bar.count()):
            texts.append(tab_bar.tabText(index))
    return texts


def test_main_window_visible_text_has_no_mojibake_markers():
    app()
    window = MainWindow()

    bad = [
        text for text in widget_texts(window)
        if any(marker in text for marker in BAD_TEXT_MARKERS)
    ]

    window.close()
    assert bad == []


def test_workspace_header_does_not_use_text_button_for_group_action():
    app()
    window = MainWindow()

    group_text_buttons = [
        button for button in window.findChildren(QPushButton)
        if button.text().strip() == "分组"
    ]

    window.close()
    assert group_text_buttons == []


def test_header_branding_block_is_removed():
    app()
    window = MainWindow()

    header_labels = [
        label.text()
        for label in window.header_bar.findChildren(QLabel)
        if label.text()
    ]
    assert window.header_bar.findChild(QLabel, "HeaderLogo") is None
    assert "Bader Charge Analyzer Pro" not in header_labels

    window.close()


def test_project_actions_move_to_workspace_sidebar_and_theme_button_is_explicit():
    app()
    window = MainWindow()

    header_buttons = [
        button.text().strip()
        for button in window.header_bar.findChildren(QPushButton)
        if button.text().strip()
    ]
    sidebar_buttons = [
        button.text().strip()
        for button in window.left_sidebar.findChildren(QPushButton)
        if button.text().strip()
    ]

    assert "打开" not in header_buttons
    assert "保存项目" not in header_buttons
    assert "设置" not in header_buttons
    assert "打开" in sidebar_buttons
    assert "保存项目" in sidebar_buttons
    assert window.btn_theme.text().strip() == "夜间模式"

    window.close()


def test_dark_mode_restylizes_workspace_sidebar_buttons():
    app()
    window = MainWindow()

    window.toggle_theme()

    assert window.is_dark_theme is True
    assert window.btn_theme.text().strip() == "日间模式"
    assert "#2a2a2a" in window.btn_import.styleSheet().lower()
    assert "#2a2a2a" in window.btn_new_ws.styleSheet().lower()
    assert "#2a2a2a" in window.btn_open_project.styleSheet().lower()
    assert "#2a2a2a" in window.btn_save_project.styleSheet().lower()

    window.close()


def test_application_icon_is_loaded_from_project_icon_file():
    app()
    icon = load_app_icon()
    window = MainWindow()

    assert app_icon_path().name == "图标.png"
    assert app_icon_path().exists()
    assert icon.isNull() is False
    assert window.windowIcon().isNull() is False

    window.close()


def test_clicking_group_keeps_children_visible():
    app()
    window = MainWindow()
    group = window.ws_tree.topLevelItem(0)

    assert group is not None
    assert group.childCount() > 0
    first_child_name = group.child(0).data(0, Qt.UserRole)
    group.setExpanded(True)
    group.setSelected(True)
    group.setCheckState(0, Qt.Checked)

    window.on_ws_selected(group, 0)

    assert group.isExpanded() is True
    assert window.current_ws == first_child_name
    assert window.lbl_files.text().startswith(first_child_name)
    assert window.list_files.count() > 0

    window.close()


def test_selecting_any_workspace_or_group_loads_files_and_compute_state():
    app()
    window = MainWindow()

    def is_ready(ws_name):
        imported = window.ws_mgr.load_state(ws_name).get("imported_files", [])
        return (
            "ACF.dat" in imported
            and ("CONTCAR" in imported or "POSCAR" in imported)
        )

    seen_workspaces = []
    for group_index in range(window.ws_tree.topLevelItemCount()):
        group = window.ws_tree.topLevelItem(group_index)
        if group.childCount() == 0:
            continue

        window.ws_tree.clearSelection()
        group.setExpanded(True)
        group.setSelected(True)
        group.setCheckState(0, Qt.Checked)
        window.on_ws_selected(group, 0)

        child_names = [
            group.child(child_index).data(0, Qt.UserRole)
            for child_index in range(group.childCount())
        ]
        first_child = child_names[0]
        assert group.isExpanded() is True
        assert window.current_ws == first_child
        assert set(child_names).issubset(set(window.get_selected_workspace_names()))
        assert window.lbl_files.text().startswith(first_child)
        assert window.list_files.count() > 0
        assert window.analysis_panel_plot.btn_calc.isEnabled() is is_ready(first_child)

        for child_index in range(group.childCount()):
            child = group.child(child_index)
            ws_name = child.data(0, Qt.UserRole)
            seen_workspaces.append(ws_name)

            window.ws_tree.clearSelection()
            child.setSelected(True)
            window.on_ws_selected(child, 0)

            assert window.current_ws == ws_name
            assert window.lbl_files.text().startswith(ws_name)
            assert window.list_files.count() > 0
            assert window.analysis_panel_plot.btn_calc.isEnabled() is is_ready(ws_name)

    assert seen_workspaces
    window.close()


def test_checked_groups_accumulate_for_batch_analysis_while_latest_group_controls_focus():
    app()
    window = MainWindow()

    groups = [
        window.ws_tree.topLevelItem(index)
        for index in range(window.ws_tree.topLevelItemCount())
        if window.ws_tree.topLevelItem(index).childCount() > 0
    ]
    assert len(groups) >= 2

    first_group, second_group = groups[0], groups[1]
    first_names = [
        first_group.child(index).data(0, Qt.UserRole)
        for index in range(first_group.childCount())
    ]
    second_names = [
        second_group.child(index).data(0, Qt.UserRole)
        for index in range(second_group.childCount())
    ]

    first_group.setCheckState(0, Qt.Checked)
    first_group.setSelected(True)
    window.on_ws_selected(first_group, 0)

    window.ws_tree.clearSelection()
    second_group.setCheckState(0, Qt.Checked)
    second_group.setSelected(True)
    window.on_ws_selected(second_group, 0)

    selected = set(window.get_selected_workspace_names())
    assert set(first_names).issubset(selected)
    assert set(second_names).issubset(selected)
    assert window.current_ws == second_names[0]
    assert window.lbl_files.text().startswith(second_names[0])

    window.close()


def test_plot_refresh_uses_only_currently_selected_workspace_data(monkeypatch):
    app()
    window = MainWindow()
    group = window.ws_tree.topLevelItem(0)
    assert group is not None
    assert group.childCount() >= 2

    stale_ws = group.child(0).data(0, Qt.UserRole)
    selected_ws = group.child(1).data(0, Qt.UserRole)

    class FakeDf:
        empty = False

    captured = {}
    window.selected_workspaces = [selected_ws]
    window.all_calculated_data = {
        stale_ws: {"df": FakeDf(), "struct": object()},
        selected_ws: {"df": FakeDf(), "struct": object()},
    }
    window._batch_errors = []
    window.analysis_panel_plot.line_fragment.setText("")

    monkeypatch.setattr(window, "update_table_view", lambda df: None)
    monkeypatch.setattr(window, "_update_element_summary", lambda: None)
    monkeypatch.setattr(window, "_rebuild_multi_compare", lambda: None)
    monkeypatch.setattr(window, "_request_3d_sync", lambda *args, **kwargs: None)
    monkeypatch.setattr(window.plot_panel, "plot_data", lambda data: captured.setdefault("data", dict(data)))

    window._finish_batch_analysis()

    assert set(captured["data"].keys()) == {selected_ws}

    window.close()


def test_plot_and_main_tabs_are_not_overly_compact():
    app()
    window = MainWindow()
    plot_panel = PlotPanel()

    assert plot_panel.ribbon_tabs.tabBar().expanding() is True
    assert "font-size: 12px" in plot_panel.ribbon_tabs.styleSheet()
    assert "min-width: 72px" in plot_panel.ribbon_tabs.styleSheet()
    assert "font-size: 14px" in window.nav_tabs.styleSheet()
    assert isinstance(window.header_left_balance, QSpacerItem)
    assert window.header_left_balance.sizeHint().width() == window.btn_theme.minimumWidth()

    plot_panel.close()
    window.close()


def test_all_legend_controls_are_in_legend_tab():
    app()
    plot_panel = PlotPanel()
    legend_tab = plot_panel.ribbon_tabs.widget(6)

    def is_descendant(parent, child):
        node = child
        while node is not None:
            if node is parent:
                return True
            node = node.parentWidget()
        return False

    legend_controls = [
        plot_panel.cb_leg_pos,
        plot_panel.chk_leg_frame,
        plot_panel.cb_leg_font,
        plot_panel.spin_leg_size,
        plot_panel.le_custom_leg,
        plot_panel.cb_radar_legend_pos,
        plot_panel.spin_radar_legend_size,
        plot_panel.cb_pie_legend_pos,
    ]

    assert plot_panel.ribbon_tabs.tabText(6) == "图例"
    assert all(is_descendant(legend_tab, control) for control in legend_controls)

    plot_panel.close()


def test_plot_tabs_use_compact_origin_property_layout():
    app()
    plot_panel = PlotPanel()

    assert getattr(plot_panel, "_compact_property_columns", None) == 3
    assert getattr(plot_panel, "_compact_property_max_width", 0) >= 1180

    for index in range(plot_panel.ribbon_tabs.count()):
        tab = plot_panel.ribbon_tabs.widget(index)
        scrolls = tab.findChildren(QScrollArea)
        assert scrolls, f"tab {index} should use a compact scroll area"
        assert all(scroll.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff for scroll in scrolls)

    assert getattr(plot_panel, "_compact_sections", {})
    assert "axis_ticks" in plot_panel._compact_sections
    assert "legend_box" in plot_panel._compact_sections
    assert "heatmap_colorbar" in plot_panel._compact_sections
    assert "radar_grid" in plot_panel._compact_sections

    plot_panel.close()


def test_origin_style_plot_controls_are_added_without_removing_existing_controls():
    app()
    plot_panel = PlotPanel()
    original_control_names = [
        "cb_plot_type",
        "spin_y_min",
        "chk_hm_colorbar",
        "cb_radar_grid_shape",
        "chk_bp_violin",
        "btn_ws_select",
        "chk_realtime",
    ]
    new_control_names = [
        "spin_fig_margin_left",
        "spin_axes_pad",
        "cb_title_position",
        "spin_major_tick_length",
        "spin_minor_tick_length",
        "cb_tick_sides",
        "spin_legend_columns",
        "spin_legend_alpha",
        "le_legend_title",
        "cb_data_label_format",
        "spin_data_label_decimals",
        "chk_data_label_avoid_overlap",
    ]

    assert all(hasattr(plot_panel, name) for name in original_control_names)
    assert all(hasattr(plot_panel, name) for name in new_control_names)

    plot_panel.update_config_and_plot()
    cfg = plot_panel.config
    for field in [
        "figure_margin_left",
        "axes_label_pad",
        "title_position",
        "major_tick_length",
        "minor_tick_length",
        "tick_sides",
        "legend_columns",
        "legend_alpha",
        "legend_title",
        "data_label_format",
        "data_label_decimals",
        "data_label_avoid_overlap",
    ]:
        assert hasattr(cfg, field)

    plot_panel.close()


def test_deprecated_plot_types_are_hidden_but_old_config_falls_back():
    app()
    plot_panel = PlotPanel()

    visible_types = [
        plot_panel.cb_plot_type.itemText(i)
        for i in range(plot_panel.cb_plot_type.count())
    ]

    assert visible_types == [
        "分组柱状图",
        "水平柱状图",
        "折线图",
        "散点图",
        "箱线图",
        "热力图",
        "雷达图",
        "饼图",
    ]
    assert all(t not in visible_types for t in ("堆叠柱状图", "面积图", "瀑布图"))

    for old_type in ("堆叠柱状图", "面积图", "瀑布图"):
        plot_panel.config.from_dict({"plot_type": old_type})
        plot_panel.sync_ui_from_config()
        assert plot_panel.cb_plot_type.currentText() == "分组柱状图"
        assert plot_panel.config.plot_type == "分组柱状图"

    plot_panel.close()


def test_advanced_chart_panels_and_external_legend_anchor_controls_exist():
    app()
    plot_panel = PlotPanel()

    assert hasattr(plot_panel, "cb_leg_external_anchor")
    assert [
        plot_panel.cb_leg_external_anchor.itemText(i)
        for i in range(plot_panel.cb_leg_external_anchor.count())
    ] == ["右侧上", "右侧中", "右侧下", "底部左", "底部中", "底部右"]

    for chart_type, group_attr in [
        ("箱线图", "_grp_boxplot"),
        ("热力图", "_grp_heatmap"),
        ("雷达图", "_grp_radar"),
        ("饼图", "_grp_pie"),
    ]:
        plot_panel.cb_plot_type.setCurrentText(chart_type)
        plot_panel._on_plot_type_changed(plot_panel.cb_plot_type.currentIndex())
        assert getattr(plot_panel, group_attr).isHidden() is False

    plot_panel.cb_leg_external_anchor.setCurrentText("右侧下")
    plot_panel.update_config_and_plot()
    assert plot_panel.config.legend_external_anchor == "右侧下"

    plot_panel.config.legend_external_anchor = "底部左"
    plot_panel.sync_ui_from_config()
    assert plot_panel.cb_leg_external_anchor.currentText() == "底部左"

    plot_panel.close()


def test_new_advanced_chart_controls_round_trip_to_config():
    app()
    plot_panel = PlotPanel()

    expected_controls = [
        "cb_bp_orientation",
        "spin_bp_category_gap",
        "chk_radar_legend_outside",
        "chk_pie_leader_lines",
        "chk_pie_legend_outside",
    ]
    assert all(hasattr(plot_panel, name) for name in expected_controls)

    plot_panel.cb_bp_orientation.setCurrentText("水平")
    plot_panel.spin_bp_category_gap.setValue(1.4)
    plot_panel.chk_radar_legend_outside.setChecked(False)
    plot_panel.chk_pie_leader_lines.setChecked(True)
    plot_panel.chk_pie_legend_outside.setChecked(False)
    plot_panel.update_config_and_plot()

    assert plot_panel.config.boxplot_orientation == "水平"
    assert plot_panel.config.boxplot_category_gap == 1.4
    assert plot_panel.config.radar_legend_outside is False
    assert plot_panel.config.pie_show_leader_lines is True
    assert plot_panel.config.pie_legend_outside is False

    plot_panel.config.boxplot_orientation = "垂直"
    plot_panel.config.boxplot_category_gap = 1.2
    plot_panel.config.radar_legend_outside = True
    plot_panel.config.pie_show_leader_lines = False
    plot_panel.config.pie_legend_outside = True
    plot_panel.sync_ui_from_config()

    assert plot_panel.cb_bp_orientation.currentText() == "垂直"
    assert plot_panel.spin_bp_category_gap.value() == 1.2
    assert plot_panel.chk_radar_legend_outside.isChecked() is True
    assert plot_panel.chk_pie_leader_lines.isChecked() is False
    assert plot_panel.chk_pie_legend_outside.isChecked() is True

    plot_panel.close()


def test_radar_circular_grid_settings_apply_without_matplotlib_text_pad_error():
    app()
    plot_panel = PlotPanel()
    plot_panel.plot_data(sample_plot_data())

    plot_panel.cb_plot_type.setCurrentText("雷达图")
    plot_panel.cb_radar_grid_shape.setCurrentText("圆形")
    plot_panel.spin_radar_spoke_dist.setValue(1.4)
    plot_panel.update_config_and_plot()

    assert plot_panel.config.plot_type == "雷达图"
    assert plot_panel.config.radar_grid_shape == "圆形"
    assert plot_panel.ax.name == "polar"

    plot_panel.close()


def test_advanced_chart_settings_apply_for_all_specialized_charts():
    app()
    plot_panel = PlotPanel()
    plot_panel.plot_data(sample_plot_data())

    cases = [
        (
            "箱线图",
            lambda p: (
                p.cb_bp_orientation.setCurrentText("水平"),
                p.spin_bp_category_gap.setValue(1.3),
                p.chk_boxplot_show_mean.setChecked(True),
            ),
        ),
        (
            "热力图",
            lambda p: (
                p.cb_heatmap_normalize.setCurrentText("手动"),
                p.spin_heatmap_vmin.setValue(-1.0),
                p.spin_heatmap_vmax.setValue(1.0),
                p.chk_heatmap_show_values.setChecked(True),
            ),
        ),
        (
            "雷达图",
            lambda p: (
                p.cb_radar_grid_shape.setCurrentText("圆形"),
                p.spin_radar_spoke_dist.setValue(1.35),
                p.chk_radar_show_values.setChecked(True),
            ),
        ),
        (
            "饼图",
            lambda p: (
                p.cb_pie_mode.setCurrentText("环形图"),
                p.spin_pie_inner_radius.setValue(0.35),
                p.cb_pie_label_pos.setCurrentText("图例"),
                p.chk_pie_legend_outside.setChecked(True),
            ),
        ),
    ]

    for chart_type, configure in cases:
        plot_panel.cb_plot_type.setCurrentText(chart_type)
        configure(plot_panel)
        plot_panel.update_config_and_plot()
        assert plot_panel.config.plot_type == chart_type

    plot_panel.close()

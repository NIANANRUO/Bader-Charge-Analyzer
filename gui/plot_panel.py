# -*- coding: utf-8 -*-
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import json
import math

from PySide6.QtWidgets import (QWidget, QMessageBox, QVBoxLayout, QHBoxLayout, QComboBox,
                               QLineEdit, QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
                               QPushButton, QGridLayout, QFrame, QTabWidget, QScrollArea,
                               QFileDialog, QGroupBox, QColorDialog, QApplication, QSizePolicy,
                               QLayout)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor
import qtawesome as qta

from gui.plot_config import PlotConfig
from gui.components.collapsible import CollapsiblePanel
from core.calculator import ChargeCalculator, TargetSelectionError

# ── CJK font support for matplotlib ──
# Must be configured BEFORE any Figure/Canvas creation so the initial
# "未选择数据源" placeholder and all subsequent renders display Chinese.
# Prepending CJK fonts before the default list enables per-glyph fallback:
# matplotlib tries the CJK font first, falls back to sans-serif for Latin.
_CJK_FONTS = ['Microsoft YaHei', 'SimHei', 'SimSun']
_existing = plt.rcParams.get('font.sans-serif', [])
plt.rcParams['font.sans-serif'] = _CJK_FONTS + [f for f in _existing if f not in _CJK_FONTS]
plt.rcParams['axes.unicode_minus'] = False

ELEMENT_COLORS = {
    "Fe": "#FF5722", "O": "#2196F3", "C": "#4CAF50", "H": "#9C27B0",
    "N": "#00BCD4", "S": "#FFEB3B", "Li": "#795548", "Na": "#607D8B",
    "K": "#E91E63", "Co": "#3F51B5", "Ni": "#009688", "Cu": "#FFC107",
    "Mo": "#4DBBD5", "P": "#E64B35", "Cl": "#00A087", "F": "#3C5488",
    "Si": "#F39B7F", "Ti": "#8491B4", "Mn": "#91D1C2", "Zn": "#DC0000",
    "Ca": "#B09F80", "Mg": "#8CB5C5", "Al": "#C0C0C0", "B": "#FFB5B5",
}
DEFAULT_COLOR = "#808080"

PALETTES = {
    "Origin Classic": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"],
    "Scientific Muted": ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860"],
    "Nature Style": ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F", "#8491B4"],
    "Pastel": ["#fbb4ae", "#b3cde3", "#ccebc5", "#decbe4", "#fed9a6", "#ffffcc"],
    "Set1": ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#ffff33"],
    "Dark2": ["#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02"],
}

MARKER_MAP = {
    "圆形": "o", "方形": "s", "上三角": "^", "下三角": "v",
    "菱形": "D", "五边形": "p", "六边形": "h", "星形": "*",
    "十字": "+", "X 形": "x", "无": "None",
}
LINE_STYLE_MAP = {
    "实线": "-", "虚线": "--", "点线": ":", "点划线": "-.", "无": "None",
}
TICK_DIR_MAP = {"向内": "in", "向外": "out", "双向": "inout"}
HEATMAP_ASPECT_MAP = {"自动": "auto", "等比": "equal"}

# Golden ratio conjugate for maximally uniform hue distribution
_GOLDEN_CONJ = 0.618033988749895

def generate_distinct_colors(n, base_colors=None):
    """Generate n perceptually distinct colors.

    Keeps *base_colors* (if provided) at the front, then fills the rest
    using golden-ratio-conjugate based hue spacing in HSV space so that
    no two colours are ever the same.
    """
    import colorsys
    result = list(base_colors) if base_colors else []
    start = len(result)
    if start >= n:
        return result[:n]
    h = 0.0
    for i in range(n):
        hue = (h * _GOLDEN_CONJ) % 1.0
        h += 1.0
        if i < start:
            continue
        sat = 0.70 if (i // 20) % 2 == 0 else 0.50
        val = 0.85 if (i // 20) % 3 != 2 else 0.65
        rgb = colorsys.hsv_to_rgb(hue, sat, val)
        result.append(matplotlib.colors.to_hex(rgb))
    return result


class PlotPanel(QWidget):
    data_point_selected = Signal(int)  # emits atom index (1-based) when user clicks a bar/point

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark_mode = False
        self.current_data = {}
        self._raw_data = {}
        self._target_expression = ""
        self._fragments_by_workspace = {}
        self._fragment_text = ""
        self.config = PlotConfig()
        self._draggable_annotations = []
        self.init_ui()

    # ==================================================================
    #  UI Construction — 6 reorganised tabs
    # ==================================================================

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.ribbon_tabs = QTabWidget()
        self.ribbon_tabs.setMaximumHeight(225)
        self.ribbon_tabs.tabBar().setExpanding(True)
        self.ribbon_tabs.tabBar().setUsesScrollButtons(True)
        self.ribbon_tabs.tabBar().setElideMode(Qt.ElideRight)
        self.ribbon_tabs.setStyleSheet("""
            QTabWidget::pane {
                border-top: 1px solid #d7d7d7;
            }
            QTabBar::tab {
                font-size: 12px;
                padding: 5px 10px;
                margin: 0;
                min-width: 72px;
                max-width: 118px;
            }
            QTabBar::tab:selected {
                font-weight: 600;
            }
        """)

        # ---- Tab 1: Data & Chart ----
        tab_chart_type = QWidget()
        lay_ct = QGridLayout(tab_chart_type)
        lay_ct.addWidget(QLabel("图表类型:"), 0, 0)
        self.cb_plot_type = QComboBox()
        self.cb_plot_type.addItems([
            "分组柱状图", "水平柱状图", "折线图", "散点图",
            "箱线图", "热力图", "雷达图", "饼图",
        ])
        self.cb_plot_type.currentIndexChanged.connect(self._on_plot_type_changed)
        lay_ct.addWidget(self.cb_plot_type, 0, 1)
        lay_ct.addWidget(QLabel("分组逻辑:"), 1, 0)
        self.cb_group_logic = QComboBox()
        self.cb_group_logic.addItems(["X=体系, 柱=原子", "X=原子, 柱=体系"])
        lay_ct.addWidget(self.cb_group_logic, 1, 1)
        lay_ct.addWidget(QLabel("过滤 |q| < :"), 0, 2)
        self.spin_filter = QDoubleSpinBox()
        self.spin_filter.setRange(0.0, 10.0)
        self.spin_filter.setSingleStep(0.05)
        self.spin_filter.setToolTip("过滤掉 |电荷| 小于此阈值的原子（不参与绘图）")
        lay_ct.addWidget(self.spin_filter, 0, 3)
        lay_ct.addWidget(QLabel("显示前 N 个:"), 1, 2)
        self.spin_top_n = QSpinBox()
        self.spin_top_n.setRange(0, 1000)
        self.spin_top_n.setToolTip("仅显示 Top N 个电荷变化最大的原子（0 = 显示全部）")
        lay_ct.addWidget(self.spin_top_n, 1, 3)
        lay_ct.addWidget(QLabel("图表标题:"), 2, 0)
        self.le_title = QLineEdit()
        self.le_title.setPlaceholderText("可选图表标题")
        lay_ct.addWidget(self.le_title, 2, 1, 1, 3)
        lay_ct.addWidget(QLabel("面板布局:"), 3, 0)
        self.cb_panel_layout = QComboBox()
        self.cb_panel_layout.addItems(["单面板", "1x2", "2x1", "2x2"])
        lay_ct.addWidget(self.cb_panel_layout, 3, 1)
        lay_ct.addWidget(QLabel("面板视图:"), 3, 2)
        self.cb_panel_views = QComboBox()
        self.cb_panel_views.addItems(["相同", "按工作区", "按原子组"])
        self.cb_panel_views.setToolTip("数据在各面板中的分布方式")
        lay_ct.addWidget(self.cb_panel_views, 3, 3)

        # Row 4: workspace selection for plotting
        lay_ct.addWidget(QLabel("绘图体系:"), 4, 0)
        self.btn_ws_select = QPushButton("全部")
        self.btn_ws_select.setToolTip("选择哪些体系参与绘图（点击弹出选择框）")
        self.btn_ws_select.clicked.connect(self._pick_plot_workspaces)
        lay_ct.addWidget(self.btn_ws_select, 4, 1)
        lay_ct.addWidget(QLabel("数据层级:"), 4, 2)
        self.cb_data_level = QComboBox()
        self.cb_data_level.addItems(["原子", "片段", "元素"])
        lay_ct.addWidget(self.cb_data_level, 4, 3)
        lay_ct.addWidget(QLabel("元素统计:"), 5, 2)
        self.cb_element_metric = QComboBox()
        self.cb_element_metric.addItems(["总和", "平均值"])
        lay_ct.addWidget(self.cb_element_metric, 5, 3)
        self.cb_data_level.currentTextChanged.connect(self._rebuild_level_data)
        self.cb_element_metric.currentTextChanged.connect(self._rebuild_level_data)
        self._ws_all = []          # all workspace names from data
        self._ws_selected = None   # None = all selected; set of names otherwise
        self._chart_ws_single = None  # single workspace selected from toolbar dropdown

        lay_ct.setRowStretch(5, 1)
        lay_ct.setColumnStretch(4, 1)

        # ---- Tab 2: Chart Style ----
        tab_chart_style = QWidget()
        lay_cs_outer = QVBoxLayout(tab_chart_style)
        scroll_style = QScrollArea()
        scroll_style.setWidgetResizable(True)
        scroll_style.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        lay_cs = QVBoxLayout(scroll_content)
        lay_cs.setSpacing(6)

        # Color Theme row (from old Tab 4)
        theme_row = QWidget()
        theme_lay = QHBoxLayout(theme_row)
        theme_lay.setContentsMargins(0, 0, 0, 0)
        theme_lay.addWidget(QLabel("配色方案:"))
        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["红白蓝电荷图", "按元素",
                                "Scientific Muted", "Origin Classic", "Nature Style",
                                "Pastel", "Set1", "Dark2"])
        theme_lay.addWidget(self.cb_theme)
        theme_lay.addStretch()
        lay_cs.addWidget(theme_row)

        # ---- Tab 3: Chart-specific Settings ----
        tab_chart_specific = QWidget()
        lay_specific_outer = QVBoxLayout(tab_chart_specific)
        scroll_specific = QScrollArea()
        scroll_specific.setWidgetResizable(True)
        scroll_specific.setFrameShape(QFrame.NoFrame)
        scroll_specific.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        specific_content = QWidget()
        lay_specific = QVBoxLayout(specific_content)
        lay_specific.setSpacing(6)

        # -- CollapsiblePanel: Bar Settings --
        self._grp_bar = CollapsiblePanel("柱状图设置", is_expanded=True)
        bar_grid = QGridLayout()
        bar_grid.addWidget(QLabel("柱宽 (%):"), 0, 0)
        self.spin_bw = QSpinBox()
        self.spin_bw.setRange(10, 100)
        self.spin_bw.setValue(80)
        bar_grid.addWidget(self.spin_bw, 0, 1)
        bar_grid.addWidget(QLabel("边框颜色:"), 0, 2)
        self.cb_edge = QComboBox()
        self.cb_edge.addItems(["none", "black", "white"])
        bar_grid.addWidget(self.cb_edge, 0, 3)
        bar_grid.addWidget(QLabel("填充图案:"), 1, 0)
        self.cb_hatch = QComboBox()
        self.cb_hatch.addItems(["无", "///", "\\\\", "xxx", "---", "+++", "..."])
        bar_grid.addWidget(self.cb_hatch, 1, 1)
        bar_grid.addWidget(QLabel("误差棒:"), 1, 2)
        self.chk_err_bars = QCheckBox("启用")
        bar_grid.addWidget(self.chk_err_bars, 1, 3)
        bar_grid.addWidget(QLabel("误差类型:"), 2, 0)
        self.cb_err_type = QComboBox()
        self.cb_err_type.addItems(["固定 5%", "标准差"])
        bar_grid.addWidget(self.cb_err_type, 2, 1)
        bar_grid.setColumnStretch(4, 1)
        self._grp_bar.addLayout(bar_grid)
        lay_specific.addWidget(self._grp_bar)

        # -- CollapsiblePanel: Line/Scatter Settings --
        self._grp_line = CollapsiblePanel("折线/散点设置", is_expanded=False)
        line_grid = QGridLayout()
        line_grid.addWidget(QLabel("线型:"), 0, 0)
        self.cb_line_style = QComboBox()
        self.cb_line_style.addItems(list(LINE_STYLE_MAP.keys()))
        line_grid.addWidget(self.cb_line_style, 0, 1)
        line_grid.addWidget(QLabel("线宽:"), 0, 2)
        self.spin_line_width = QDoubleSpinBox()
        self.spin_line_width.setRange(0.5, 6.0)
        self.spin_line_width.setValue(1.5)
        self.spin_line_width.setSingleStep(0.1)
        line_grid.addWidget(self.spin_line_width, 0, 3)
        line_grid.addWidget(QLabel("标记样式:"), 1, 0)
        self.cb_marker = QComboBox()
        self.cb_marker.addItems(list(MARKER_MAP.keys()))
        line_grid.addWidget(self.cb_marker, 1, 1)
        line_grid.addWidget(QLabel("标记大小:"), 1, 2)
        self.spin_marker_size = QDoubleSpinBox()
        self.spin_marker_size.setRange(1.0, 20.0)
        self.spin_marker_size.setValue(6.0)
        self.spin_marker_size.setSingleStep(0.5)
        line_grid.addWidget(self.spin_marker_size, 1, 3)
        line_grid.addWidget(QLabel("趋势线:"), 2, 0)
        self.cb_trend = QComboBox()
        self.cb_trend.addItems(["无", "线性拟合", "多项式", "均值", "移动平均 (3)"])
        line_grid.addWidget(self.cb_trend, 2, 1)
        line_grid.addWidget(QLabel("多项式阶数:"), 2, 2)
        self.spin_trend_degree = QSpinBox()
        self.spin_trend_degree.setRange(1, 6)
        self.spin_trend_degree.setValue(1)
        self.spin_trend_degree.setToolTip("多项式阶数（仅用于多项式趋势线）")
        line_grid.addWidget(self.spin_trend_degree, 2, 3)
        line_grid.setColumnStretch(4, 1)
        self._grp_line.addLayout(line_grid)
        lay_specific.addWidget(self._grp_line)

        # -- CollapsiblePanel: Area Settings --
        self._grp_area = CollapsiblePanel("面积图设置", is_expanded=False)
        area_grid = QGridLayout()
        area_grid.addWidget(QLabel("填充透明度:"), 0, 0)
        self.spin_area_alpha = QDoubleSpinBox()
        self.spin_area_alpha.setRange(0.05, 1.0)
        self.spin_area_alpha.setValue(0.3)
        self.spin_area_alpha.setSingleStep(0.05)
        area_grid.addWidget(self.spin_area_alpha, 0, 1)
        area_grid.addWidget(QLabel("堆叠模式:"), 1, 0)
        self.cb_area_mode = QComboBox()
        self.cb_area_mode.addItems(["堆叠", "重叠", "100% 归一化"])
        area_grid.addWidget(self.cb_area_mode, 1, 1)
        area_grid.addWidget(QLabel("插值方式:"), 2, 0)
        self.cb_area_interpolation = QComboBox()
        self.cb_area_interpolation.addItems(["线性", "阶梯"])
        area_grid.addWidget(self.cb_area_interpolation, 2, 1)
        self.chk_area_edge = QCheckBox("显示边线")
        self.chk_area_edge.setChecked(True)
        area_grid.addWidget(self.chk_area_edge, 3, 0)
        area_grid.addWidget(QLabel("边线宽度:"), 3, 1)
        self.spin_area_edge_width = QDoubleSpinBox()
        self.spin_area_edge_width.setRange(0.5, 3.0)
        self.spin_area_edge_width.setValue(1.0)
        self.spin_area_edge_width.setSingleStep(0.1)
        area_grid.addWidget(self.spin_area_edge_width, 3, 2)
        area_grid.addWidget(QLabel("边线型:"), 3, 3)
        self.cb_area_edge_style = QComboBox()
        self.cb_area_edge_style.addItems(["实线", "虚线", "点线"])
        area_grid.addWidget(self.cb_area_edge_style, 3, 4)
        area_grid.addWidget(QLabel("堆叠顺序:"), 4, 0)
        self.cb_area_order = QComboBox()
        self.cb_area_order.addItems(["默认", "按总量升序", "按总量降序"])
        area_grid.addWidget(self.cb_area_order, 4, 1)
        self.chk_area_gradient = QCheckBox("渐变填充")
        area_grid.addWidget(self.chk_area_gradient, 4, 2)
        self.chk_area_negative = QCheckBox("负值向下")
        self.chk_area_negative.setChecked(True)
        area_grid.addWidget(self.chk_area_negative, 4, 3)
        area_grid.setColumnStretch(5, 1)
        self._grp_area.addLayout(area_grid)
        lay_specific.addWidget(self._grp_area)

        # -- CollapsiblePanel: Waterfall Settings --
        self._grp_waterfall = CollapsiblePanel("瀑布图设置", is_expanded=False)
        wf_grid = QGridLayout()
        wf_grid.addWidget(QLabel("正值颜色:"), 0, 0)
        self.btn_waterfall_pos_color = QPushButton("  #2ecc71")
        self.btn_waterfall_pos_color.setStyleSheet("background: #2ecc71; color: white; border: 1px solid #999;")
        self._waterfall_pos_color = "#2ecc71"
        self.btn_waterfall_pos_color.clicked.connect(lambda: self._pick_chart_color("waterfall_pos"))
        wf_grid.addWidget(self.btn_waterfall_pos_color, 0, 1)
        wf_grid.addWidget(QLabel("负值颜色:"), 0, 2)
        self.btn_waterfall_neg_color = QPushButton("  #e74c3c")
        self.btn_waterfall_neg_color.setStyleSheet("background: #e74c3c; color: white; border: 1px solid #999;")
        self._waterfall_neg_color = "#e74c3c"
        self.btn_waterfall_neg_color.clicked.connect(lambda: self._pick_chart_color("waterfall_neg"))
        wf_grid.addWidget(self.btn_waterfall_neg_color, 0, 3)
        self.chk_waterfall_connectors = QCheckBox("连接线")
        self.chk_waterfall_connectors.setChecked(True)
        wf_grid.addWidget(self.chk_waterfall_connectors, 1, 0, 1, 2)
        wf_grid.addWidget(QLabel("原子编号:"), 1, 2)
        self.spin_waterfall_atom_id = QSpinBox()
        self.spin_waterfall_atom_id.setRange(0, 9999)
        self.spin_waterfall_atom_id.setToolTip("0 = 自动选择第一个原子")
        wf_grid.addWidget(self.spin_waterfall_atom_id, 1, 3)
        wf_grid.addWidget(QLabel("柱宽:"), 2, 0)
        self.spin_waterfall_bar_width = QDoubleSpinBox()
        self.spin_waterfall_bar_width.setRange(0.2, 1.0)
        self.spin_waterfall_bar_width.setSingleStep(0.05)
        self.spin_waterfall_bar_width.setValue(0.6)
        wf_grid.addWidget(self.spin_waterfall_bar_width, 2, 1)
        wf_grid.addWidget(QLabel("边框颜色:"), 2, 2)
        self.btn_waterfall_edge_color = QPushButton("  black")
        self.btn_waterfall_edge_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._waterfall_edge_color = "black"
        self.btn_waterfall_edge_color.clicked.connect(lambda: self._pick_chart_color("waterfall_edge"))
        wf_grid.addWidget(self.btn_waterfall_edge_color, 2, 3)
        wf_grid.addWidget(QLabel("边框宽度:"), 3, 0)
        self.spin_waterfall_edge_width = QDoubleSpinBox()
        self.spin_waterfall_edge_width.setRange(0.0, 3.0)
        self.spin_waterfall_edge_width.setSingleStep(0.1)
        self.spin_waterfall_edge_width.setValue(0.5)
        wf_grid.addWidget(self.spin_waterfall_edge_width, 3, 1)
        wf_grid.addWidget(QLabel("排序:"), 3, 2)
        self.cb_waterfall_sort = QComboBox()
        self.cb_waterfall_sort.addItems(["默认", "按电荷", "按元素"])
        wf_grid.addWidget(self.cb_waterfall_sort, 3, 3)
        self.chk_waterfall_total = QCheckBox("总计栏")
        self.chk_waterfall_total.setChecked(True)
        wf_grid.addWidget(self.chk_waterfall_total, 4, 0, 1, 2)
        wf_grid.addWidget(QLabel("连接线型:"), 5, 0)
        self.cb_wf_conn_style = QComboBox()
        self.cb_wf_conn_style.addItems(["实线", "虚线", "点线"])
        wf_grid.addWidget(self.cb_wf_conn_style, 5, 1)
        wf_grid.addWidget(QLabel("连接线颜色:"), 5, 2)
        self.btn_wf_conn_color = QPushButton("  black")
        self.btn_wf_conn_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._wf_conn_color = "black"
        self.btn_wf_conn_color.clicked.connect(lambda: self._pick_chart_color("wf_conn"))
        wf_grid.addWidget(self.btn_wf_conn_color, 5, 3)
        wf_grid.addWidget(QLabel("连接线宽:"), 6, 0)
        self.spin_wf_conn_width = QDoubleSpinBox()
        self.spin_wf_conn_width.setRange(0.1, 3.0)
        self.spin_wf_conn_width.setSingleStep(0.1)
        self.spin_wf_conn_width.setValue(0.5)
        wf_grid.addWidget(self.spin_wf_conn_width, 6, 1)
        wf_grid.addWidget(QLabel("连接线透明度:"), 6, 2)
        self.spin_wf_conn_alpha = QDoubleSpinBox()
        self.spin_wf_conn_alpha.setRange(0.0, 1.0)
        self.spin_wf_conn_alpha.setSingleStep(0.05)
        self.spin_wf_conn_alpha.setValue(0.3)
        wf_grid.addWidget(self.spin_wf_conn_alpha, 6, 3)
        self.chk_wf_labels = QCheckBox("数值标签")
        wf_grid.addWidget(self.chk_wf_labels, 7, 0)
        wf_grid.addWidget(QLabel("总计栏颜色:"), 7, 1)
        self.btn_wf_total_color = QPushButton("  #3498db")
        self.btn_wf_total_color.setStyleSheet("background: #3498db; color: white; border: 1px solid #999;")
        self._wf_total_color = "#3498db"
        self.btn_wf_total_color.clicked.connect(lambda: self._pick_chart_color("wf_total"))
        wf_grid.addWidget(self.btn_wf_total_color, 7, 2)
        # Row 8: zero line color, zero line width, label format
        self._wf_zero_line_color = "black"
        self.btn_wf_zero_color = QPushButton()
        self.btn_wf_zero_color.setFixedSize(60, 24)
        self.btn_wf_zero_color.setStyleSheet("background-color: black; border: 1px solid gray;")
        self.btn_wf_zero_color.setText("  black")
        wf_grid.addWidget(QLabel("零线颜色:"), 8, 0)
        wf_grid.addWidget(self.btn_wf_zero_color, 8, 1)
        wf_grid.addWidget(QLabel("零线宽度:"), 8, 2)
        self.spin_wf_zero_width = QDoubleSpinBox()
        self.spin_wf_zero_width.setRange(0.1, 5.0)
        self.spin_wf_zero_width.setSingleStep(0.1)
        self.spin_wf_zero_width.setValue(1.0)
        wf_grid.addWidget(self.spin_wf_zero_width, 8, 3)
        self.btn_wf_zero_color.clicked.connect(lambda: self._pick_chart_color("wf_zero"))
        wf_grid.addWidget(QLabel("标签格式:"), 9, 0)
        self.cb_wf_label_fmt = QComboBox()
        self.cb_wf_label_fmt.addItems([".2f", ".3f", ".1f", ".0f"])
        wf_grid.addWidget(self.cb_wf_label_fmt, 9, 1)
        wf_grid.addWidget(QLabel("标签字体:"), 10, 0)
        self.cb_wf_label_font = QComboBox()
        self.cb_wf_label_font.addItems(["Arial", "Times New Roman", "Helvetica", "Microsoft YaHei", "SimHei"])
        wf_grid.addWidget(self.cb_wf_label_font, 10, 1)
        wf_grid.addWidget(QLabel("标签粗细:"), 10, 2)
        self.cb_wf_label_weight = QComboBox()
        self.cb_wf_label_weight.addItems(["normal", "bold"])
        wf_grid.addWidget(self.cb_wf_label_weight, 10, 3)
        wf_grid.addWidget(QLabel("填充图案:"), 11, 0)
        self.cb_wf_hatch = QComboBox()
        self.cb_wf_hatch.addItems(["无", "///", "\\\\", "xxx", "---", "+++", "..."])
        wf_grid.addWidget(self.cb_wf_hatch, 11, 1)
        wf_grid.addWidget(QLabel("柱体圆角:"), 11, 2)
        self.spin_wf_bar_round = QDoubleSpinBox()
        self.spin_wf_bar_round.setRange(0.0, 0.5)
        self.spin_wf_bar_round.setSingleStep(0.05)
        self.spin_wf_bar_round.setValue(0.0)
        wf_grid.addWidget(self.spin_wf_bar_round, 11, 3)
        self.chk_wf_cumulative = QCheckBox("累积折线")
        wf_grid.addWidget(self.chk_wf_cumulative, 12, 0)
        wf_grid.addWidget(QLabel("累积线颜色:"), 12, 1)
        self.btn_wf_cum_color = QPushButton("  black")
        self.btn_wf_cum_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._wf_cum_color = "black"
        self.btn_wf_cum_color.clicked.connect(lambda: self._pick_chart_color("wf_cum"))
        wf_grid.addWidget(self.btn_wf_cum_color, 12, 2)
        wf_grid.addWidget(QLabel("累积线宽:"), 12, 3)
        self.spin_wf_cum_width = QDoubleSpinBox()
        self.spin_wf_cum_width.setRange(0.5, 5.0)
        self.spin_wf_cum_width.setSingleStep(0.1)
        self.spin_wf_cum_width.setValue(1.5)
        wf_grid.addWidget(self.spin_wf_cum_width, 12, 4)
        self.chk_wf_pct_mode = QCheckBox("百分比标签")
        wf_grid.addWidget(self.chk_wf_pct_mode, 13, 0)
        wf_grid.setColumnStretch(5, 1)
        self._grp_waterfall.addLayout(wf_grid)
        lay_specific.addWidget(self._grp_waterfall)

        # -- CollapsiblePanel: Box Plot Settings --
        self._grp_boxplot = CollapsiblePanel("箱线图设置", is_expanded=False)
        bp_grid = QGridLayout()
        bp_grid.addWidget(QLabel("箱体颜色:"), 0, 0)
        self.btn_boxplot_color = QPushButton("  #3498db")
        self.btn_boxplot_color.setStyleSheet("background: #3498db; color: white; border: 1px solid #999;")
        self._boxplot_color = "#3498db"
        self.btn_boxplot_color.clicked.connect(lambda: self._pick_chart_color("boxplot"))
        bp_grid.addWidget(self.btn_boxplot_color, 0, 1)
        self.chk_boxplot_show_mean = QCheckBox("显示均值")
        self.chk_boxplot_show_mean.setChecked(True)
        bp_grid.addWidget(self.chk_boxplot_show_mean, 0, 2)
        bp_grid.addWidget(QLabel("透明度:"), 1, 0)
        self.spin_boxplot_alpha = QDoubleSpinBox()
        self.spin_boxplot_alpha.setRange(0.1, 1.0)
        self.spin_boxplot_alpha.setValue(0.6)
        self.spin_boxplot_alpha.setSingleStep(0.1)
        bp_grid.addWidget(self.spin_boxplot_alpha, 1, 1)
        bp_grid.addWidget(QLabel("最大原子数:"), 1, 2)
        self.spin_boxplot_max_atoms = QSpinBox()
        self.spin_boxplot_max_atoms.setRange(1, 100)
        self.spin_boxplot_max_atoms.setValue(20)
        bp_grid.addWidget(self.spin_boxplot_max_atoms, 1, 3)
        bp_grid.addWidget(QLabel("胡须倍数:"), 2, 0)
        self.spin_boxplot_whisker = QDoubleSpinBox()
        self.spin_boxplot_whisker.setRange(0.5, 3.0)
        self.spin_boxplot_whisker.setSingleStep(0.25)
        self.spin_boxplot_whisker.setValue(1.5)
        bp_grid.addWidget(self.spin_boxplot_whisker, 2, 1)
        self.chk_boxplot_notch = QCheckBox("缺口")
        bp_grid.addWidget(self.chk_boxplot_notch, 2, 2)
        bp_grid.addWidget(QLabel("中位线颜色:"), 2, 3)
        self.btn_boxplot_median_color = QPushButton("  black")
        self.btn_boxplot_median_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._boxplot_median_color = "black"
        self.btn_boxplot_median_color.clicked.connect(lambda: self._pick_chart_color("boxplot_median"))
        bp_grid.addWidget(self.btn_boxplot_median_color, 2, 4)
        bp_grid.addWidget(QLabel("中位线宽度:"), 3, 0)
        self.spin_boxplot_median_width = QDoubleSpinBox()
        self.spin_boxplot_median_width.setRange(0.5, 4.0)
        self.spin_boxplot_median_width.setSingleStep(0.5)
        self.spin_boxplot_median_width.setValue(2.0)
        bp_grid.addWidget(self.spin_boxplot_median_width, 3, 1)
        bp_grid.addWidget(QLabel("异常值标记:"), 3, 2)
        self.cb_boxplot_outlier_marker = QComboBox()
        self.cb_boxplot_outlier_marker.addItems([k for k in MARKER_MAP.keys() if k != "无"])
        bp_grid.addWidget(self.cb_boxplot_outlier_marker, 3, 3)
        bp_grid.addWidget(QLabel("异常值颜色:"), 4, 0)
        self.btn_boxplot_outlier_color = QPushButton("  red")
        self.btn_boxplot_outlier_color.setStyleSheet("background: red; color: white; border: 1px solid #999;")
        self._boxplot_outlier_color = "red"
        self.btn_boxplot_outlier_color.clicked.connect(lambda: self._pick_chart_color("boxplot_outlier"))
        bp_grid.addWidget(self.btn_boxplot_outlier_color, 4, 1)
        self.chk_boxplot_outliers = QCheckBox("显示异常值")
        self.chk_boxplot_outliers.setChecked(True)
        bp_grid.addWidget(self.chk_boxplot_outliers, 4, 2)
        bp_grid.addWidget(QLabel("数据点:"), 5, 0)
        self.cb_bp_points = QComboBox()
        self.cb_bp_points.addItems(["无", "抖动", "蜂群"])
        bp_grid.addWidget(self.cb_bp_points, 5, 1)
        self.chk_bp_violin = QCheckBox("小提琴")
        bp_grid.addWidget(self.chk_bp_violin, 5, 2)
        bp_grid.addWidget(QLabel("端帽宽度:"), 5, 3)
        self.spin_bp_cap_width = QDoubleSpinBox()
        self.spin_bp_cap_width.setRange(0.1, 1.0)
        self.spin_bp_cap_width.setSingleStep(0.1)
        self.spin_bp_cap_width.setValue(0.5)
        bp_grid.addWidget(self.spin_bp_cap_width, 5, 4)
        self.chk_bp_caps = QCheckBox("显示端帽")
        self.chk_bp_caps.setChecked(True)
        bp_grid.addWidget(self.chk_bp_caps, 6, 0)
        bp_grid.addWidget(QLabel("箱体宽度:"), 6, 1)
        self.spin_bp_width = QDoubleSpinBox()
        self.spin_bp_width.setRange(0.1, 1.0)
        self.spin_bp_width.setSingleStep(0.1)
        self.spin_bp_width.setValue(0.5)
        bp_grid.addWidget(self.spin_bp_width, 6, 2)
        bp_grid.addWidget(QLabel("方向:"), 6, 5)
        self.cb_bp_orientation = QComboBox()
        self.cb_bp_orientation.addItems(["垂直", "水平"])
        bp_grid.addWidget(self.cb_bp_orientation, 6, 6)
        bp_grid.addWidget(QLabel("分类间距:"), 7, 5)
        self.spin_bp_category_gap = QDoubleSpinBox()
        self.spin_bp_category_gap.setRange(0.5, 2.5)
        self.spin_bp_category_gap.setSingleStep(0.1)
        self.spin_bp_category_gap.setValue(1.0)
        bp_grid.addWidget(self.spin_bp_category_gap, 7, 6)
        bp_grid.addWidget(QLabel("胡须颜色:"), 6, 3)
        self.btn_bp_whisker_color = QPushButton("  black")
        self.btn_bp_whisker_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._bp_whisker_color = "black"
        self.btn_bp_whisker_color.clicked.connect(lambda: self._pick_chart_color("bp_whisker"))
        bp_grid.addWidget(self.btn_bp_whisker_color, 6, 4)
        # Row 7-9: jitter/scatter settings + violin alpha
        bp_grid.addWidget(QLabel("散点宽度:"), 7, 0)
        self.spin_bp_jitter_w = QDoubleSpinBox()
        self.spin_bp_jitter_w.setRange(0.01, 1.0)
        self.spin_bp_jitter_w.setSingleStep(0.01)
        self.spin_bp_jitter_w.setValue(0.2)
        bp_grid.addWidget(self.spin_bp_jitter_w, 7, 1)
        bp_grid.addWidget(QLabel("散点透明度:"), 7, 2)
        self.spin_bp_jitter_alpha = QDoubleSpinBox()
        self.spin_bp_jitter_alpha.setRange(0.0, 1.0)
        self.spin_bp_jitter_alpha.setSingleStep(0.1)
        self.spin_bp_jitter_alpha.setValue(0.6)
        bp_grid.addWidget(self.spin_bp_jitter_alpha, 7, 3)
        bp_grid.addWidget(QLabel("散点大小:"), 8, 0)
        self.spin_bp_jitter_size = QDoubleSpinBox()
        self.spin_bp_jitter_size.setRange(1.0, 20.0)
        self.spin_bp_jitter_size.setSingleStep(0.5)
        self.spin_bp_jitter_size.setValue(3.0)
        bp_grid.addWidget(self.spin_bp_jitter_size, 8, 1)
        bp_grid.addWidget(QLabel("小提琴透明度:"), 8, 2)
        self.spin_bp_violin_alpha = QDoubleSpinBox()
        self.spin_bp_violin_alpha.setRange(0.0, 1.0)
        self.spin_bp_violin_alpha.setSingleStep(0.05)
        self.spin_bp_violin_alpha.setValue(0.2)
        bp_grid.addWidget(self.spin_bp_violin_alpha, 8, 3)
        self.chk_bp_show_individual = QCheckBox("显示散点")
        self.chk_bp_show_individual.setChecked(True)
        bp_grid.addWidget(self.chk_bp_show_individual, 9, 0, 1, 2)
        bp_grid.addWidget(QLabel("散点颜色:"), 10, 0)
        self.btn_bp_point_color = QPushButton("  black")
        self.btn_bp_point_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._bp_point_color = "black"
        self.btn_bp_point_color.clicked.connect(lambda: self._pick_chart_color("bp_point"))
        bp_grid.addWidget(self.btn_bp_point_color, 10, 1)
        bp_grid.addWidget(QLabel("小提琴宽度比:"), 10, 2)
        self.spin_bp_violin_w_ratio = QDoubleSpinBox()
        self.spin_bp_violin_w_ratio.setRange(0.1, 2.0)
        self.spin_bp_violin_w_ratio.setSingleStep(0.1)
        self.spin_bp_violin_w_ratio.setValue(0.8)
        bp_grid.addWidget(self.spin_bp_violin_w_ratio, 10, 3)
        bp_grid.addWidget(QLabel("须线宽度:"), 11, 0)
        self.spin_bp_whisker_w = QDoubleSpinBox()
        self.spin_bp_whisker_w.setRange(0.1, 5.0)
        self.spin_bp_whisker_w.setSingleStep(0.1)
        self.spin_bp_whisker_w.setValue(1.0)
        bp_grid.addWidget(self.spin_bp_whisker_w, 11, 1)
        bp_grid.addWidget(QLabel("离群点大小:"), 11, 2)
        self.spin_bp_outlier_size = QDoubleSpinBox()
        self.spin_bp_outlier_size.setRange(1.0, 20.0)
        self.spin_bp_outlier_size.setSingleStep(0.5)
        self.spin_bp_outlier_size.setValue(6.0)
        bp_grid.addWidget(self.spin_bp_outlier_size, 11, 3)
        bp_grid.addWidget(QLabel("均值标记:"), 12, 0)
        self.cb_bp_mean_marker = QComboBox()
        self.cb_bp_mean_marker.addItems(["圆形", "方形", "上三角", "下三角", "菱形", "五边形", "六边形", "星形", "十字", "X 形"])
        bp_grid.addWidget(self.cb_bp_mean_marker, 12, 1)
        bp_grid.addWidget(QLabel("均值颜色:"), 12, 2)
        self.btn_bp_mean_color = QPushButton("  red")
        self.btn_bp_mean_color.setStyleSheet("background: red; color: white; border: 1px solid #999;")
        self._bp_mean_color = "red"
        self.btn_bp_mean_color.clicked.connect(lambda: self._pick_chart_color("bp_mean"))
        bp_grid.addWidget(self.btn_bp_mean_color, 12, 3)
        bp_grid.addWidget(QLabel("均值大小:"), 13, 0)
        self.spin_bp_mean_size = QDoubleSpinBox()
        self.spin_bp_mean_size.setRange(1.0, 20.0)
        self.spin_bp_mean_size.setSingleStep(0.5)
        self.spin_bp_mean_size.setValue(5.0)
        bp_grid.addWidget(self.spin_bp_mean_size, 13, 1)
        bp_grid.addWidget(QLabel("箱体边框色:"), 13, 2)
        self.btn_bp_edge_color = QPushButton("  black")
        self.btn_bp_edge_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._bp_edge_color = "black"
        self.btn_bp_edge_color.clicked.connect(lambda: self._pick_chart_color("bp_edge"))
        bp_grid.addWidget(self.btn_bp_edge_color, 13, 3)
        bp_grid.addWidget(QLabel("箱体边框宽:"), 14, 0)
        self.spin_bp_edge_w = QDoubleSpinBox()
        self.spin_bp_edge_w.setRange(0.0, 5.0)
        self.spin_bp_edge_w.setSingleStep(0.1)
        self.spin_bp_edge_w.setValue(1.0)
        bp_grid.addWidget(self.spin_bp_edge_w, 14, 1)
        bp_grid.addWidget(QLabel("箱体填充图案:"), 14, 2)
        self.cb_bp_hatch = QComboBox()
        self.cb_bp_hatch.addItems(["无", "///", "\\\\", "xxx", "---", "+++", "..."])
        bp_grid.addWidget(self.cb_bp_hatch, 14, 3)
        self.chk_bp_ws_indicator = QCheckBox("工作区指示器")
        self.chk_bp_ws_indicator.setChecked(True)
        bp_grid.addWidget(self.chk_bp_ws_indicator, 15, 0, 1, 2)
        bp_grid.addWidget(QLabel("指示器字号:"), 15, 2)
        self.spin_bp_ws_size = QSpinBox()
        self.spin_bp_ws_size.setRange(6, 16)
        self.spin_bp_ws_size.setValue(9)
        bp_grid.addWidget(self.spin_bp_ws_size, 15, 3)
        self.chk_bp_show_legend = QCheckBox("显示图例")
        self.chk_bp_show_legend.setChecked(True)
        bp_grid.addWidget(self.chk_bp_show_legend, 16, 0, 1, 2)
        bp_grid.addWidget(QLabel("图例位置:"), 16, 2)
        self.cb_bp_legend_pos = QComboBox()
        self.cb_bp_legend_pos.addItems(["最佳", "右上角", "左上角", "右下角", "左下角"])
        bp_grid.addWidget(self.cb_bp_legend_pos, 16, 3)
        bp_grid.setColumnStretch(5, 1)
        self._grp_boxplot.addLayout(bp_grid)
        lay_specific.addWidget(self._grp_boxplot)

        # -- CollapsiblePanel: Heatmap Settings --
        self._grp_heatmap = CollapsiblePanel("热力图设置", is_expanded=False)
        hm_grid = QGridLayout()
        hm_grid.addWidget(QLabel("配色方案:"), 0, 0)
        self.cb_heatmap_colormap = QComboBox()
        self.cb_heatmap_colormap.addItems(["RdBu_r", "viridis", "coolwarm", "Blues", "Reds", "YlOrRd", "plasma"])
        hm_grid.addWidget(self.cb_heatmap_colormap, 0, 1)
        self.chk_heatmap_show_values = QCheckBox("显示数值")
        hm_grid.addWidget(self.chk_heatmap_show_values, 0, 2)
        hm_grid.addWidget(QLabel("数值格式:"), 1, 0)
        self.cb_heatmap_value_format = QComboBox()
        self.cb_heatmap_value_format.addItems([".2f", ".3f", ".1f", ".0f"])
        hm_grid.addWidget(self.cb_heatmap_value_format, 1, 1)
        hm_grid.addWidget(QLabel("数值字号:"), 1, 2)
        self.spin_heatmap_value_size = QSpinBox()
        self.spin_heatmap_value_size.setRange(6, 16)
        self.spin_heatmap_value_size.setValue(8)
        hm_grid.addWidget(self.spin_heatmap_value_size, 1, 3)
        hm_grid.addWidget(QLabel("宽高比:"), 2, 0)
        self.cb_heatmap_aspect = QComboBox()
        self.cb_heatmap_aspect.addItems(["自动", "等比"])
        hm_grid.addWidget(self.cb_heatmap_aspect, 2, 1)
        hm_grid.addWidget(QLabel("归一化:"), 3, 0)
        self.cb_heatmap_normalize = QComboBox()
        self.cb_heatmap_normalize.addItems(["自动", "对称发散", "手动"])
        hm_grid.addWidget(self.cb_heatmap_normalize, 3, 1)
        hm_grid.addWidget(QLabel("vmin:"), 3, 2)
        self.spin_heatmap_vmin = QDoubleSpinBox()
        self.spin_heatmap_vmin.setRange(-100, 100)
        self.spin_heatmap_vmin.setSingleStep(0.1)
        self.spin_heatmap_vmin.setValue(0.0)
        self.spin_heatmap_vmin.setEnabled(False)
        hm_grid.addWidget(self.spin_heatmap_vmin, 3, 3)
        hm_grid.addWidget(QLabel("vmax:"), 3, 4)
        self.spin_heatmap_vmax = QDoubleSpinBox()
        self.spin_heatmap_vmax.setRange(-100, 100)
        self.spin_heatmap_vmax.setSingleStep(0.1)
        self.spin_heatmap_vmax.setValue(0.0)
        self.spin_heatmap_vmax.setEnabled(False)
        hm_grid.addWidget(self.spin_heatmap_vmax, 3, 5)

        def _on_heatmap_normalize_change(text):
            is_manual = (text == "手动")
            self.spin_heatmap_vmin.setEnabled(is_manual)
            self.spin_heatmap_vmax.setEnabled(is_manual)

        self.cb_heatmap_normalize.currentTextChanged.connect(_on_heatmap_normalize_change)
        self.chk_heatmap_border = QCheckBox("单元格边框")
        hm_grid.addWidget(self.chk_heatmap_border, 4, 0)
        hm_grid.addWidget(QLabel("边框颜色:"), 4, 1)
        self.btn_heatmap_border_color = QPushButton("  white")
        self.btn_heatmap_border_color.setStyleSheet("background: white; color: #333; border: 1px solid #999;")
        self._heatmap_border_color = "white"
        self.btn_heatmap_border_color.clicked.connect(lambda: self._pick_chart_color("heatmap_border"))
        hm_grid.addWidget(self.btn_heatmap_border_color, 4, 2)
        self.chk_hm_colorbar = QCheckBox("色标")
        self.chk_hm_colorbar.setChecked(True)
        hm_grid.addWidget(self.chk_hm_colorbar, 5, 0)
        hm_grid.addWidget(QLabel("色标标签:"), 5, 1)
        self.le_hm_cb_label = QLineEdit("Bader 电荷")
        self.le_hm_cb_label.setPlaceholderText("色标标签文字")
        hm_grid.addWidget(self.le_hm_cb_label, 5, 2)
        hm_grid.addWidget(QLabel("插值:"), 5, 3)
        self.cb_hm_interp = QComboBox()
        self.cb_hm_interp.addItems(["最近邻", "双线性", "双三次"])
        hm_grid.addWidget(self.cb_hm_interp, 5, 4)
        hm_grid.addWidget(QLabel("NaN 颜色:"), 6, 0)
        self.btn_hm_nan_color = QPushButton("  #E0E0E0")
        self.btn_hm_nan_color.setStyleSheet("background: #E0E0E0; color: #333; border: 1px solid #999;")
        self._hm_nan_color = "#E0E0E0"
        self.btn_hm_nan_color.clicked.connect(lambda: self._pick_chart_color("hm_nan"))
        hm_grid.addWidget(self.btn_hm_nan_color, 6, 1)
        hm_grid.addWidget(QLabel("行排序:"), 6, 2)
        self.cb_hm_sort = QComboBox()
        self.cb_hm_sort.addItems(["默认", "按总量", "按字母"])
        hm_grid.addWidget(self.cb_hm_sort, 6, 3)
        # Row 7-8: new heatmap settings
        hm_grid.addWidget(QLabel("边框宽度:"), 7, 0)
        self.spin_hm_border_w = QDoubleSpinBox()
        self.spin_hm_border_w.setRange(0.1, 5.0)
        self.spin_hm_border_w.setSingleStep(0.1)
        self.spin_hm_border_w.setValue(0.5)
        hm_grid.addWidget(self.spin_hm_border_w, 7, 1)
        hm_grid.addWidget(QLabel("数值文字色:"), 7, 2)
        self.cb_hm_txt_color = QComboBox()
        self.cb_hm_txt_color.addItems(["auto", "black", "white"])
        hm_grid.addWidget(self.cb_hm_txt_color, 7, 3)
        hm_grid.addWidget(QLabel("文字背景:"), 8, 0)
        self.spin_hm_txt_bg = QDoubleSpinBox()
        self.spin_hm_txt_bg.setRange(0.0, 1.0)
        self.spin_hm_txt_bg.setSingleStep(0.1)
        self.spin_hm_txt_bg.setValue(0.0)
        hm_grid.addWidget(self.spin_hm_txt_bg, 8, 1)
        hm_grid.addWidget(QLabel("色标位置:"), 8, 2)
        self.cb_hm_cb_pos = QComboBox()
        self.cb_hm_cb_pos.addItems(["右侧", "底部"])
        hm_grid.addWidget(self.cb_hm_cb_pos, 8, 3)
        hm_grid.addWidget(QLabel("发散中心:"), 9, 0)
        self.spin_hm_vcenter = QDoubleSpinBox()
        self.spin_hm_vcenter.setRange(-10.0, 10.0)
        self.spin_hm_vcenter.setSingleStep(0.1)
        self.spin_hm_vcenter.setValue(0.0)
        hm_grid.addWidget(self.spin_hm_vcenter, 9, 1)
        hm_grid.addWidget(QLabel("色标缩放:"), 9, 2)
        self.spin_hm_cb_shrink = QDoubleSpinBox()
        self.spin_hm_cb_shrink.setRange(0.1, 2.0)
        self.spin_hm_cb_shrink.setSingleStep(0.05)
        self.spin_hm_cb_shrink.setValue(1.0)
        hm_grid.addWidget(self.spin_hm_cb_shrink, 9, 3)
        hm_grid.addWidget(QLabel("色标间距:"), 10, 0)
        self.spin_hm_cb_pad = QDoubleSpinBox()
        self.spin_hm_cb_pad.setRange(0.0, 0.5)
        self.spin_hm_cb_pad.setSingleStep(0.01)
        self.spin_hm_cb_pad.setValue(0.05)
        hm_grid.addWidget(self.spin_hm_cb_pad, 10, 1)
        hm_grid.addWidget(QLabel("色标字号:"), 10, 2)
        self.spin_hm_cb_fs = QSpinBox()
        self.spin_hm_cb_fs.setRange(6, 20)
        self.spin_hm_cb_fs.setValue(10)
        hm_grid.addWidget(self.spin_hm_cb_fs, 10, 3)
        hm_grid.addWidget(QLabel("色标刻度数:"), 11, 0)
        self.spin_hm_cb_ticks = QSpinBox()
        self.spin_hm_cb_ticks.setRange(0, 20)
        self.spin_hm_cb_ticks.setValue(0)
        self.spin_hm_cb_ticks.setToolTip("0 = 自动")
        hm_grid.addWidget(self.spin_hm_cb_ticks, 11, 1)
        hm_grid.addWidget(QLabel("数值粗细:"), 11, 2)
        self.cb_hm_val_weight = QComboBox()
        self.cb_hm_val_weight.addItems(["normal", "bold"])
        hm_grid.addWidget(self.cb_hm_val_weight, 11, 3)
        hm_grid.addWidget(QLabel("数值旋转:"), 12, 0)
        self.spin_hm_val_rot = QSpinBox()
        self.spin_hm_val_rot.setRange(0, 90)
        self.spin_hm_val_rot.setValue(0)
        hm_grid.addWidget(self.spin_hm_val_rot, 12, 1)
        hm_grid.addWidget(QLabel("X 轴标签:"), 12, 2)
        self.le_hm_x_label = QLineEdit("工作区")
        hm_grid.addWidget(self.le_hm_x_label, 12, 3)
        hm_grid.addWidget(QLabel("Y 轴标签:"), 12, 4)
        self.le_hm_y_label = QLineEdit("原子")
        hm_grid.addWidget(self.le_hm_y_label, 12, 5)
        self.chk_hm_show_x = QCheckBox("显示X标签")
        self.chk_hm_show_x.setChecked(True)
        hm_grid.addWidget(self.chk_hm_show_x, 13, 0, 1, 2)
        self.chk_hm_show_y = QCheckBox("显示Y标签")
        self.chk_hm_show_y.setChecked(True)
        hm_grid.addWidget(self.chk_hm_show_y, 13, 2, 1, 2)
        hm_grid.addWidget(QLabel("色标标签字号:"), 13, 4)
        self.spin_hm_cb_label_size = QSpinBox()
        self.spin_hm_cb_label_size.setRange(6, 20)
        self.spin_hm_cb_label_size.setValue(10)
        hm_grid.addWidget(self.spin_hm_cb_label_size, 13, 5)
        hm_grid.setColumnStretch(6, 1)
        self._grp_heatmap.addLayout(hm_grid)
        lay_specific.addWidget(self._grp_heatmap)

        # -- CollapsiblePanel: Radar Settings --
        self._grp_radar = CollapsiblePanel("雷达图设置", is_expanded=False)
        rd_grid = QGridLayout()
        rd_grid.addWidget(QLabel("线条颜色:"), 0, 0)
        self.btn_radar_line_color = QPushButton("  #1f77b4")
        self.btn_radar_line_color.setStyleSheet("background: #1f77b4; color: white; border: 1px solid #999;")
        self._radar_line_color = "#1f77b4"
        self.btn_radar_line_color.clicked.connect(lambda: self._pick_chart_color("radar_line"))
        rd_grid.addWidget(self.btn_radar_line_color, 0, 1)
        rd_grid.addWidget(QLabel("线宽:"), 0, 2)
        self.spin_radar_line_width = QDoubleSpinBox()
        self.spin_radar_line_width.setRange(0.5, 5.0)
        self.spin_radar_line_width.setValue(2.0)
        self.spin_radar_line_width.setSingleStep(0.5)
        rd_grid.addWidget(self.spin_radar_line_width, 0, 3)
        rd_grid.addWidget(QLabel("填充透明度:"), 1, 0)
        self.spin_radar_fill_alpha = QDoubleSpinBox()
        self.spin_radar_fill_alpha.setRange(0.0, 0.8)
        self.spin_radar_fill_alpha.setValue(0.25)
        self.spin_radar_fill_alpha.setSingleStep(0.05)
        rd_grid.addWidget(self.spin_radar_fill_alpha, 1, 1)
        rd_grid.addWidget(QLabel("标记大小:"), 1, 2)
        self.spin_radar_marker_size = QDoubleSpinBox()
        self.spin_radar_marker_size.setRange(2.0, 15.0)
        self.spin_radar_marker_size.setValue(6.0)
        self.spin_radar_marker_size.setSingleStep(1.0)
        rd_grid.addWidget(self.spin_radar_marker_size, 1, 3)
        rd_grid.addWidget(QLabel("最大原子数:"), 2, 0)
        self.spin_radar_max_atoms = QSpinBox()
        self.spin_radar_max_atoms.setRange(3, 24)
        self.spin_radar_max_atoms.setValue(12)
        rd_grid.addWidget(self.spin_radar_max_atoms, 2, 1)
        rd_grid.addWidget(QLabel("网格形状:"), 3, 0)
        self.cb_radar_grid_shape = QComboBox()
        self.cb_radar_grid_shape.addItems(["多边形", "圆形"])
        rd_grid.addWidget(self.cb_radar_grid_shape, 3, 1)
        rd_grid.addWidget(QLabel("网格圈数:"), 3, 2)
        self.spin_radar_grid_rings = QSpinBox()
        self.spin_radar_grid_rings.setRange(0, 8)
        self.spin_radar_grid_rings.setValue(4)
        rd_grid.addWidget(self.spin_radar_grid_rings, 3, 3)
        rd_grid.addWidget(QLabel("标记样式:"), 4, 0)
        self.cb_radar_marker_style = QComboBox()
        self.cb_radar_marker_style.addItems([k for k in MARKER_MAP.keys() if k != "无"])
        rd_grid.addWidget(self.cb_radar_marker_style, 4, 1)
        rd_grid.addWidget(QLabel("起始角度:"), 4, 2)
        self.spin_radar_start_angle = QSpinBox()
        self.spin_radar_start_angle.setRange(0, 360)
        self.spin_radar_start_angle.setValue(90)
        rd_grid.addWidget(self.spin_radar_start_angle, 4, 3)
        self.chk_radar_show_values = QCheckBox("显示数值")
        rd_grid.addWidget(self.chk_radar_show_values, 5, 0, 1, 2)
        rd_grid.addWidget(QLabel("填充颜色:"), 6, 0)
        self.btn_radar_fill_color = QPushButton("  同线条")
        self.btn_radar_fill_color.setStyleSheet("background: #cccccc; color: #333; border: 1px solid #999;")
        self._radar_fill_color = ""
        self.btn_radar_fill_color.clicked.connect(lambda: self._pick_chart_color("radar_fill"))
        rd_grid.addWidget(self.btn_radar_fill_color, 6, 1)
        self.chk_radar_rings_labels = QCheckBox("径向刻度")
        self.chk_radar_rings_labels.setChecked(True)
        rd_grid.addWidget(self.chk_radar_rings_labels, 6, 2)
        self.chk_radar_clockwise = QCheckBox("顺时针")
        rd_grid.addWidget(self.chk_radar_clockwise, 6, 3)
        rd_grid.addWidget(QLabel("辐条字号:"), 7, 0)
        self.spin_radar_spoke_size = QSpinBox()
        self.spin_radar_spoke_size.setRange(6, 16)
        self.spin_radar_spoke_size.setValue(10)
        rd_grid.addWidget(self.spin_radar_spoke_size, 7, 1)
        rd_grid.addWidget(QLabel("线型:"), 7, 2)
        self.cb_radar_line_style = QComboBox()
        self.cb_radar_line_style.addItems(["实线", "虚线", "点线"])
        rd_grid.addWidget(self.cb_radar_line_style, 7, 3)
        # Row 8-9: new radar settings
        rd_grid.addWidget(QLabel("数值字号:"), 8, 0)
        self.spin_radar_val_fs = QSpinBox()
        self.spin_radar_val_fs.setRange(5, 16)
        self.spin_radar_val_fs.setValue(8)
        rd_grid.addWidget(self.spin_radar_val_fs, 8, 1)
        rd_grid.addWidget(QLabel("径向最大值:"), 8, 2)
        self.spin_radar_scale_max = QDoubleSpinBox()
        self.spin_radar_scale_max.setRange(0.0, 100.0)
        self.spin_radar_scale_max.setSingleStep(0.1)
        self.spin_radar_scale_max.setValue(0.0)
        self.spin_radar_scale_max.setSpecialValueText("自动")
        rd_grid.addWidget(self.spin_radar_scale_max, 8, 3)
        rd_grid.addWidget(QLabel("数值格式:"), 9, 0)
        self.cb_radar_val_fmt = QComboBox()
        self.cb_radar_val_fmt.addItems([".2f", ".3f", ".1f", ".0f"])
        rd_grid.addWidget(self.cb_radar_val_fmt, 9, 1)
        rd_grid.addWidget(QLabel("网格颜色:"), 10, 0)
        self.btn_radar_grid_color = QPushButton("  gray")
        self.btn_radar_grid_color.setStyleSheet("background: gray; color: white; border: 1px solid #999;")
        self._radar_grid_color = "gray"
        self.btn_radar_grid_color.clicked.connect(lambda: self._pick_chart_color("radar_grid"))
        rd_grid.addWidget(self.btn_radar_grid_color, 10, 1)
        rd_grid.addWidget(QLabel("网格线宽:"), 10, 2)
        self.spin_radar_grid_width = QDoubleSpinBox()
        self.spin_radar_grid_width.setRange(0.1, 3.0)
        self.spin_radar_grid_width.setSingleStep(0.1)
        self.spin_radar_grid_width.setValue(0.5)
        rd_grid.addWidget(self.spin_radar_grid_width, 10, 3)
        rd_grid.addWidget(QLabel("网格透明度:"), 11, 0)
        self.spin_radar_grid_alpha = QDoubleSpinBox()
        self.spin_radar_grid_alpha.setRange(0.0, 1.0)
        self.spin_radar_grid_alpha.setSingleStep(0.05)
        self.spin_radar_grid_alpha.setValue(0.4)
        rd_grid.addWidget(self.spin_radar_grid_alpha, 11, 1)
        rd_grid.addWidget(QLabel("网格线型:"), 11, 2)
        self.cb_radar_grid_style = QComboBox()
        self.cb_radar_grid_style.addItems(list(LINE_STYLE_MAP.keys()))
        rd_grid.addWidget(self.cb_radar_grid_style, 11, 3)
        self.cb_radar_legend_pos = QComboBox()
        self.cb_radar_legend_pos.addItems(["最佳", "右上角", "左上角", "右下角", "左下角", "中央偏上"])
        self.spin_radar_legend_size = QSpinBox()
        self.spin_radar_legend_size.setRange(6, 20)
        self.spin_radar_legend_size.setValue(8)
        self.chk_radar_legend_outside = QCheckBox("图例外置")
        self.chk_radar_legend_outside.setChecked(True)
        rd_grid.addWidget(self.chk_radar_legend_outside, 12, 0, 1, 2)
        rd_grid.addWidget(QLabel("图例位置:"), 12, 2)
        rd_grid.addWidget(self.cb_radar_legend_pos, 12, 3)
        rd_grid.addWidget(QLabel("图例字号:"), 12, 4)
        rd_grid.addWidget(self.spin_radar_legend_size, 12, 5)
        rd_grid.addWidget(QLabel("缩放系数:"), 13, 0)
        self.spin_radar_scale_pad = QDoubleSpinBox()
        self.spin_radar_scale_pad.setRange(1.0, 2.0)
        self.spin_radar_scale_pad.setSingleStep(0.05)
        self.spin_radar_scale_pad.setValue(1.2)
        rd_grid.addWidget(self.spin_radar_scale_pad, 13, 1)
        rd_grid.addWidget(QLabel("标签距中心:"), 13, 2)
        self.spin_radar_spoke_dist = QDoubleSpinBox()
        self.spin_radar_spoke_dist.setRange(1.0, 2.0)
        self.spin_radar_spoke_dist.setSingleStep(0.05)
        self.spin_radar_spoke_dist.setValue(1.15)
        rd_grid.addWidget(self.spin_radar_spoke_dist, 13, 3)
        rd_grid.addWidget(QLabel("填充边框宽:"), 14, 0)
        self.spin_radar_fill_edge_w = QDoubleSpinBox()
        self.spin_radar_fill_edge_w.setRange(0.0, 3.0)
        self.spin_radar_fill_edge_w.setSingleStep(0.1)
        self.spin_radar_fill_edge_w.setValue(0.0)
        rd_grid.addWidget(self.spin_radar_fill_edge_w, 14, 1)
        rd_grid.addWidget(QLabel("填充边框色:"), 14, 2)
        self.btn_radar_fill_edge_color = QPushButton("  (同线条)")
        self.btn_radar_fill_edge_color.setStyleSheet("background: gray; color: white; border: 1px solid #999;")
        self._radar_fill_edge_color = ""
        self.btn_radar_fill_edge_color.clicked.connect(lambda: self._pick_chart_color("radar_fill_edge"))
        rd_grid.addWidget(self.btn_radar_fill_edge_color, 14, 3)
        rd_grid.addWidget(QLabel("标题:"), 15, 0)
        self.le_radar_title = QLineEdit("电荷分布")
        rd_grid.addWidget(self.le_radar_title, 15, 1)
        self.chk_radar_show_title = QCheckBox("显示标题")
        self.chk_radar_show_title.setChecked(True)
        rd_grid.addWidget(self.chk_radar_show_title, 15, 2)
        rd_grid.addWidget(QLabel("标题字号:"), 15, 3)
        self.spin_radar_title_size = QSpinBox()
        self.spin_radar_title_size.setRange(8, 24)
        self.spin_radar_title_size.setValue(14)
        rd_grid.addWidget(self.spin_radar_title_size, 15, 4)
        self.chk_radar_show_spokes = QCheckBox("显示辐条标签")
        self.chk_radar_show_spokes.setChecked(True)
        rd_grid.addWidget(self.chk_radar_show_spokes, 16, 0, 1, 2)
        rd_grid.addWidget(QLabel("环刻度格式:"), 16, 2)
        self.cb_radar_ring_fmt = QComboBox()
        self.cb_radar_ring_fmt.addItems([".2f", ".3f", ".1f", ".0f"])
        rd_grid.addWidget(self.cb_radar_ring_fmt, 16, 3)
        rd_grid.setColumnStretch(5, 1)
        self._grp_radar.addLayout(rd_grid)
        lay_specific.addWidget(self._grp_radar)

        # -- CollapsiblePanel: Pie Chart Settings --
        self._grp_pie = CollapsiblePanel("饼图设置", is_expanded=False)
        pie_grid = QGridLayout()
        pie_grid.addWidget(QLabel("模式:"), 0, 0)
        self.cb_pie_mode = QComboBox()
        self.cb_pie_mode.addItems(["饼图", "环形图"])
        pie_grid.addWidget(self.cb_pie_mode, 0, 1)
        pie_grid.addWidget(QLabel("内环半径:"), 0, 2)
        self.spin_pie_inner_radius = QDoubleSpinBox()
        self.spin_pie_inner_radius.setRange(0.0, 0.8)
        self.spin_pie_inner_radius.setSingleStep(0.05)
        self.spin_pie_inner_radius.setValue(0.0)
        self.spin_pie_inner_radius.setEnabled(False)
        pie_grid.addWidget(self.spin_pie_inner_radius, 0, 3)

        def _on_pie_mode_change(text):
            self.spin_pie_inner_radius.setEnabled(text == "环形图")

        self.cb_pie_mode.currentTextChanged.connect(_on_pie_mode_change)
        pie_grid.addWidget(QLabel("起始角度:"), 1, 0)
        self.spin_pie_start_angle = QSpinBox()
        self.spin_pie_start_angle.setRange(0, 360)
        self.spin_pie_start_angle.setValue(90)
        pie_grid.addWidget(self.spin_pie_start_angle, 1, 1)
        pie_grid.addWidget(QLabel("标签位置:"), 1, 2)
        self.cb_pie_label_pos = QComboBox()
        self.cb_pie_label_pos.addItems(["外部", "内部", "图例"])
        pie_grid.addWidget(self.cb_pie_label_pos, 1, 3)
        pie_grid.addWidget(QLabel("标签格式:"), 2, 0)
        self.cb_pie_label_fmt = QComboBox()
        self.cb_pie_label_fmt.addItems(["百分比", "数值", "两者"])
        pie_grid.addWidget(self.cb_pie_label_fmt, 2, 1)
        pie_grid.addWidget(QLabel("最小切片 %:"), 2, 2)
        self.spin_pie_min_slice = QDoubleSpinBox()
        self.spin_pie_min_slice.setRange(0.0, 20.0)
        self.spin_pie_min_slice.setSingleStep(0.5)
        self.spin_pie_min_slice.setValue(2.0)
        pie_grid.addWidget(self.spin_pie_min_slice, 2, 3)
        self.chk_pie_explode = QCheckBox("突出最大")
        pie_grid.addWidget(self.chk_pie_explode, 3, 0)
        pie_grid.addWidget(QLabel("边框颜色:"), 3, 1)
        self.btn_pie_edge_color = QPushButton("  white")
        self.btn_pie_edge_color.setStyleSheet("background: white; color: #333; border: 1px solid #999;")
        self._pie_edge_color = "white"
        self.btn_pie_edge_color.clicked.connect(lambda: self._pick_chart_color("pie_edge"))
        pie_grid.addWidget(self.btn_pie_edge_color, 3, 2)
        pie_grid.addWidget(QLabel("中心标签:"), 4, 0)
        self.le_pie_center = QLineEdit()
        self.le_pie_center.setPlaceholderText("环形图中心文字")
        pie_grid.addWidget(self.le_pie_center, 4, 1)
        pie_grid.addWidget(QLabel("突出偏移:"), 4, 2)
        self.spin_pie_explode_offset = QDoubleSpinBox()
        self.spin_pie_explode_offset.setRange(0.0, 0.5)
        self.spin_pie_explode_offset.setSingleStep(0.02)
        self.spin_pie_explode_offset.setValue(0.1)
        pie_grid.addWidget(self.spin_pie_explode_offset, 4, 3)
        pie_grid.addWidget(QLabel("切片间距:"), 5, 0)
        self.spin_pie_gap = QDoubleSpinBox()
        self.spin_pie_gap.setRange(0.0, 0.1)
        self.spin_pie_gap.setSingleStep(0.005)
        self.spin_pie_gap.setValue(0.0)
        pie_grid.addWidget(self.spin_pie_gap, 5, 1)
        self.chk_pie_shadow = QCheckBox("阴影")
        pie_grid.addWidget(self.chk_pie_shadow, 5, 2)
        pie_grid.addWidget(QLabel("排序:"), 6, 0)
        self.cb_pie_sort = QComboBox()
        self.cb_pie_sort.addItems(["默认", "按大小升序", "按大小降序"])
        pie_grid.addWidget(self.cb_pie_sort, 6, 1)
        pie_grid.addWidget(QLabel("标签字号:"), 6, 2)
        self.spin_pie_label_size = QSpinBox()
        self.spin_pie_label_size.setRange(6, 16)
        self.spin_pie_label_size.setValue(10)
        pie_grid.addWidget(self.spin_pie_label_size, 6, 3)
        # Row 7: new pie settings
        pie_grid.addWidget(QLabel("中心字号:"), 7, 0)
        self.spin_pie_center_fs = QSpinBox()
        self.spin_pie_center_fs.setRange(8, 24)
        self.spin_pie_center_fs.setValue(14)
        pie_grid.addWidget(self.spin_pie_center_fs, 7, 1)
        self.chk_pie_pct_symbol = QCheckBox("显示 % 符号")
        self.chk_pie_pct_symbol.setChecked(True)
        pie_grid.addWidget(self.chk_pie_pct_symbol, 7, 2, 1, 2)
        pie_grid.addWidget(QLabel("百分比精度:"), 8, 0)
        self.spin_pie_pct_precision = QSpinBox()
        self.spin_pie_pct_precision.setRange(0, 4)
        self.spin_pie_pct_precision.setValue(1)
        pie_grid.addWidget(self.spin_pie_pct_precision, 8, 1)
        self.cb_pie_legend_pos = QComboBox()
        self.cb_pie_legend_pos.addItems(["最佳", "右上角", "左上角", "右下角", "左下角", "中央偏上"])
        self.chk_pie_leader_lines = QCheckBox("外部标签引导线")
        pie_grid.addWidget(self.chk_pie_leader_lines, 8, 2, 1, 2)
        self.chk_pie_legend_outside = QCheckBox("图例外置")
        self.chk_pie_legend_outside.setChecked(True)
        pie_grid.addWidget(self.chk_pie_legend_outside, 8, 4, 1, 2)
        pie_grid.addWidget(QLabel("图例位置:"), 8, 6)
        pie_grid.addWidget(self.cb_pie_legend_pos, 8, 7)
        pie_grid.addWidget(QLabel("标签距离:"), 9, 0)
        self.spin_pie_label_dist = QDoubleSpinBox()
        self.spin_pie_label_dist.setRange(0.5, 2.0)
        self.spin_pie_label_dist.setSingleStep(0.05)
        self.spin_pie_label_dist.setValue(1.1)
        pie_grid.addWidget(self.spin_pie_label_dist, 9, 1)
        pie_grid.addWidget(QLabel("百分比距离:"), 9, 2)
        self.spin_pie_pct_dist = QDoubleSpinBox()
        self.spin_pie_pct_dist.setRange(0.0, 1.0)
        self.spin_pie_pct_dist.setSingleStep(0.05)
        self.spin_pie_pct_dist.setValue(0.6)
        pie_grid.addWidget(self.spin_pie_pct_dist, 9, 3)
        pie_grid.addWidget(QLabel("边框宽度:"), 10, 0)
        self.spin_pie_edge_width = QDoubleSpinBox()
        self.spin_pie_edge_width.setRange(0.0, 5.0)
        self.spin_pie_edge_width.setSingleStep(0.1)
        self.spin_pie_edge_width.setValue(1.0)
        pie_grid.addWidget(self.spin_pie_edge_width, 10, 1)
        self.chk_pie_counterclockwise = QCheckBox("逆时针排列")
        self.chk_pie_counterclockwise.setChecked(True)
        pie_grid.addWidget(self.chk_pie_counterclockwise, 10, 2, 1, 2)
        pie_grid.addWidget(QLabel("百分比颜色:"), 11, 0)
        self.cb_pie_pct_color = QComboBox()
        self.cb_pie_pct_color.addItems(["auto", "black", "white"])
        pie_grid.addWidget(self.cb_pie_pct_color, 11, 1)
        pie_grid.addWidget(QLabel("中心标签色:"), 11, 2)
        self.btn_pie_center_lbl_color = QPushButton("  black")
        self.btn_pie_center_lbl_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._pie_center_label_color = "black"
        self.btn_pie_center_lbl_color.clicked.connect(lambda: self._pick_chart_color("pie_center_lbl"))
        pie_grid.addWidget(self.btn_pie_center_lbl_color, 11, 3)
        pie_grid.addWidget(QLabel("标题:"), 12, 0)
        self.le_pie_title = QLineEdit("Bader 电荷分布")
        pie_grid.addWidget(self.le_pie_title, 12, 1)
        self.chk_pie_show_title = QCheckBox("显示标题")
        self.chk_pie_show_title.setChecked(True)
        pie_grid.addWidget(self.chk_pie_show_title, 12, 2)
        pie_grid.addWidget(QLabel("标题字号:"), 12, 3)
        self.spin_pie_title_size = QSpinBox()
        self.spin_pie_title_size.setRange(8, 24)
        self.spin_pie_title_size.setValue(14)
        pie_grid.addWidget(self.spin_pie_title_size, 12, 4)
        pie_grid.addWidget(QLabel("标题粗细:"), 13, 0)
        self.cb_pie_title_weight = QComboBox()
        self.cb_pie_title_weight.addItems(["normal", "bold"])
        pie_grid.addWidget(self.cb_pie_title_weight, 13, 1)
        self.chk_pie_ws_indicator = QCheckBox("工作区指示器")
        self.chk_pie_ws_indicator.setChecked(True)
        pie_grid.addWidget(self.chk_pie_ws_indicator, 13, 2)
        pie_grid.addWidget(QLabel("指示器字号:"), 13, 3)
        self.spin_pie_ws_size = QSpinBox()
        self.spin_pie_ws_size.setRange(6, 16)
        self.spin_pie_ws_size.setValue(9)
        pie_grid.addWidget(self.spin_pie_ws_size, 13, 4)
        pie_grid.setColumnStretch(5, 1)
        self._grp_pie.addLayout(pie_grid)
        lay_specific.addWidget(self._grp_pie)

        # -- CollapsiblePanel: Legend Settings (always visible) --
        _grp_legend = CollapsiblePanel("图例设置", is_expanded=True)
        leg_grid = QGridLayout()
        leg_grid.addWidget(QLabel("图例位置:"), 0, 0)
        self.cb_leg_pos = QComboBox()
        self.cb_leg_pos.addItems(["右侧外部", "最佳", "右上", "左上", "底部外部", "隐藏"])
        leg_grid.addWidget(self.cb_leg_pos, 0, 1)
        leg_grid.addWidget(QLabel("外置锚点:"), 0, 2)
        self.cb_leg_external_anchor = QComboBox()
        self.cb_leg_external_anchor.addItems(["右侧上", "右侧中", "右侧下", "底部左", "底部中", "底部右"])
        leg_grid.addWidget(self.cb_leg_external_anchor, 0, 3)
        self.chk_leg_frame = QCheckBox("图例边框")
        self.chk_leg_frame.setChecked(True)
        leg_grid.addWidget(self.chk_leg_frame, 0, 4)
        leg_grid.addWidget(QLabel("图例字体:"), 1, 0)
        self.cb_leg_font = QComboBox()
        self.cb_leg_font.addItems(["Arial", "Times New Roman", "Microsoft YaHei", "Inter"])
        leg_grid.addWidget(self.cb_leg_font, 1, 1)
        leg_grid.addWidget(QLabel("图例字号:"), 1, 2)
        self.spin_leg_size = QSpinBox()
        self.spin_leg_size.setValue(10)
        leg_grid.addWidget(self.spin_leg_size, 1, 3)
        leg_grid.addWidget(QLabel("自定义图例:"), 2, 0)
        self.le_custom_leg = QLineEdit()
        self.le_custom_leg.setPlaceholderText("A, B, C...")
        leg_grid.addWidget(self.le_custom_leg, 2, 1, 1, 3)
        leg_grid.setColumnStretch(4, 1)
        _grp_legend.addLayout(leg_grid)
        lay_cs.addWidget(_grp_legend)

        # Per-series color override belongs with common chart styling.
        btn_series_color = QPushButton(" 覆盖系列颜色...")
        btn_series_color.setIcon(qta.icon("fa5s.paint-brush"))
        btn_series_color.clicked.connect(self._override_series_colors)
        lay_cs.addWidget(btn_series_color)

        # Chart-type groups dict for show/hide
        self._chart_type_groups = {
            "bar": self._grp_bar,
            "line": self._grp_line,
            "area": self._grp_area,
            "waterfall": self._grp_waterfall,
            "boxplot": self._grp_boxplot,
            "heatmap": self._grp_heatmap,
            "radar": self._grp_radar,
            "pie": self._grp_pie,
        }

        lay_specific.addStretch()
        scroll_specific.setWidget(specific_content)
        lay_specific_outer.addWidget(scroll_specific)

        lay_cs.addStretch()
        scroll_style.setWidget(scroll_content)
        lay_cs_outer.addWidget(scroll_style)

        # Set initial visibility based on plot type
        self._on_plot_type_changed(self.cb_plot_type.currentIndex())

        # ---- Tab 4: Axes (minus font controls) ----
        tab_axes = QWidget()
        lay_axes = QGridLayout(tab_axes)
        lay_axes.addWidget(QLabel("X 轴标签:"), 0, 0)
        self.le_xlabel = QLineEdit("工作区 (体系)")
        lay_axes.addWidget(self.le_xlabel, 0, 1)
        self.chk_show_xlabel = QCheckBox("显示 X 标签")
        self.chk_show_xlabel.setChecked(True)
        lay_axes.addWidget(self.chk_show_xlabel, 0, 6)
        lay_axes.addWidget(QLabel("Y 轴标签:"), 1, 0)
        self.le_ylabel = QLineEdit("Bader 电荷 (e)")
        lay_axes.addWidget(self.le_ylabel, 1, 1)
        self.chk_show_ylabel = QCheckBox("显示 Y 标签")
        self.chk_show_ylabel.setChecked(True)
        lay_axes.addWidget(self.chk_show_ylabel, 1, 6)
        lay_axes.addWidget(QLabel("X 轴缩放:"), 0, 2)
        self.cb_x_scale = QComboBox()
        self.cb_x_scale.addItems(["线性", "对称对数"])
        lay_axes.addWidget(self.cb_x_scale, 0, 3)
        lay_axes.addWidget(QLabel("Y 轴缩放:"), 1, 2)
        self.cb_y_scale = QComboBox()
        self.cb_y_scale.addItems(["线性", "对称对数"])
        lay_axes.addWidget(self.cb_y_scale, 1, 3)
        lay_axes.addWidget(QLabel("刻度方向:"), 0, 4)
        self.cb_tick_dir = QComboBox()
        self.cb_tick_dir.addItems(["向内", "向外", "双向"])
        self.cb_tick_dir.setCurrentText("向外")
        lay_axes.addWidget(self.cb_tick_dir, 0, 5)
        lay_axes.addWidget(QLabel("X 刻度旋转 (度):"), 1, 4)
        self.spin_rot = QSpinBox()
        self.spin_rot.setRange(-90, 90)
        lay_axes.addWidget(self.spin_rot, 1, 5)
        self.chk_symmetric = QCheckBox("Y 轴对称 (以零为中心)")
        self.chk_symmetric.setChecked(True)
        self.chk_symmetric.setToolTip("Y 轴关于 0 对称显示（正负范围相等）")
        lay_axes.addWidget(self.chk_symmetric, 2, 0, 1, 2)
        self.chk_spines = QCheckBox("显示上/右边框")
        self.chk_spines.setChecked(True)
        lay_axes.addWidget(self.chk_spines, 2, 2)
        lay_axes.addWidget(QLabel("Y 最小值:"), 3, 0)
        self.spin_y_min = QDoubleSpinBox()
        self.spin_y_min.setRange(-1000, 1000)
        lay_axes.addWidget(self.spin_y_min, 3, 1)
        lay_axes.addWidget(QLabel("Y 最大值:"), 3, 2)
        self.spin_y_max = QDoubleSpinBox()
        self.spin_y_max.setRange(-1000, 1000)
        lay_axes.addWidget(self.spin_y_max, 3, 3)
        lay_axes.addWidget(QLabel("Y 步长:"), 3, 4)
        self.spin_y_step = QDoubleSpinBox()
        self.spin_y_step.setRange(0, 1000)
        lay_axes.addWidget(self.spin_y_step, 3, 5)
        lay_axes.addWidget(QLabel("刻度格式:"), 4, 0)
        self.cb_tick_fmt = QComboBox()
        self.cb_tick_fmt.addItems(["自动", "定点小数"])
        lay_axes.addWidget(self.cb_tick_fmt, 4, 1)
        lay_axes.addWidget(QLabel("小数位数:"), 4, 2)
        self.spin_tick_dec = QSpinBox()
        self.spin_tick_dec.setRange(0, 8)
        self.spin_tick_dec.setValue(2)
        lay_axes.addWidget(self.spin_tick_dec, 4, 3)
        self.chk_sci_notation = QCheckBox("科学计数法")
        self.chk_sci_notation.setToolTip("以科学计数法显示刻度值")
        lay_axes.addWidget(self.chk_sci_notation, 4, 4)
        lay_axes.addWidget(QLabel("次刻度数量:"), 5, 0)
        self.spin_minor_ticks = QSpinBox()
        self.spin_minor_ticks.setRange(0, 10)
        self.spin_minor_ticks.setToolTip("0 = 自动, >0 = 每个主刻度区间的次刻度数")
        lay_axes.addWidget(self.spin_minor_ticks, 5, 1)
        self.chk_spine_style = QCheckBox("自定义边框")
        lay_axes.addWidget(self.chk_spine_style, 6, 0)
        lay_axes.addWidget(QLabel("边框宽度:"), 6, 1)
        self.spin_spine_width = QDoubleSpinBox()
        self.spin_spine_width.setRange(0.1, 5.0)
        self.spin_spine_width.setValue(1.0)
        self.spin_spine_width.setSingleStep(0.1)
        lay_axes.addWidget(self.spin_spine_width, 6, 2)
        lay_axes.addWidget(QLabel("边框颜色:"), 6, 3)
        self.btn_spine_color = QPushButton(" black")
        self.btn_spine_color.setStyleSheet("background: black; color: white; border: 1px solid #999;")
        self._spine_color = "black"
        self.btn_spine_color.clicked.connect(self._pick_spine_color)
        lay_axes.addWidget(self.btn_spine_color, 6, 4)
        # Axis break controls
        self.chk_axis_break = QCheckBox("Y 轴断裂")
        self.chk_axis_break.setToolTip("在 Y 轴添加断裂标记，适用于数据范围跨越较大的情况")
        lay_axes.addWidget(self.chk_axis_break, 7, 0)
        lay_axes.addWidget(QLabel("断裂下限:"), 7, 1)
        self.spin_break_low = QDoubleSpinBox()
        self.spin_break_low.setRange(-1000, 1000)
        self.spin_break_low.setValue(-0.5)
        lay_axes.addWidget(self.spin_break_low, 7, 2)
        lay_axes.addWidget(QLabel("断裂上限:"), 7, 3)
        self.spin_break_high = QDoubleSpinBox()
        self.spin_break_high.setRange(-1000, 1000)
        self.spin_break_high.setValue(0.5)
        lay_axes.addWidget(self.spin_break_high, 7, 4)
        lay_axes.setRowStretch(8, 1)
        lay_axes.setColumnStretch(7, 1)

        # ---- Tab 4: Annotation & Reference Lines ----
        tab_annotation = QWidget()
        lay_annot = QGridLayout(tab_annotation)
        # Grid controls (from old Tab 3)
        self.chk_y_maj = QCheckBox("Y 主网格")
        self.chk_y_maj.setChecked(True)
        lay_annot.addWidget(self.chk_y_maj, 0, 0)
        self.chk_y_min = QCheckBox("Y 次网格")
        lay_annot.addWidget(self.chk_y_min, 1, 0)
        self.chk_x_maj = QCheckBox("X 主网格")
        lay_annot.addWidget(self.chk_x_maj, 0, 1)
        lay_annot.addWidget(QLabel("网格样式:"), 1, 1)
        self.cb_grid_style = QComboBox()
        self.cb_grid_style.addItems(["--", "-", ":", "-."])
        lay_annot.addWidget(self.cb_grid_style, 1, 2)
        lay_annot.addWidget(QLabel("网格颜色:"), 0, 2)
        self.btn_grid_color = QPushButton("  #CCCCCC")
        self.btn_grid_color.setStyleSheet("background: #CCCCCC; color: #333; border: 1px solid #999;")
        self._grid_color = "#CCCCCC"
        self.btn_grid_color.clicked.connect(self._pick_grid_color)
        lay_annot.addWidget(self.btn_grid_color, 0, 3)
        lay_annot.addWidget(QLabel("网格宽度:"), 1, 3)
        self.spin_grid_width = QDoubleSpinBox()
        self.spin_grid_width.setRange(0.1, 3.0)
        self.spin_grid_width.setValue(0.5)
        self.spin_grid_width.setSingleStep(0.1)
        lay_annot.addWidget(self.spin_grid_width, 1, 4)
        lay_annot.addWidget(QLabel("网格透明度:"), 0, 4)
        self.spin_grid_alpha = QDoubleSpinBox()
        self.spin_grid_alpha.setRange(0.05, 1.0)
        self.spin_grid_alpha.setValue(0.5)
        self.spin_grid_alpha.setSingleStep(0.05)
        lay_annot.addWidget(self.spin_grid_alpha, 0, 5)
        # Reference lines (from old Tab 3)
        self.chk_zero = QCheckBox("显示 Y=0 线")
        self.chk_zero.setChecked(True)
        lay_annot.addWidget(self.chk_zero, 2, 0)
        self._zero_line_color = "black"
        self.btn_zero_line_color = QPushButton("■")
        self.btn_zero_line_color.setFixedSize(28, 22)
        self.btn_zero_line_color.setToolTip("零线颜色")
        self.btn_zero_line_color.setStyleSheet(
            f"background: {self._zero_line_color}; color: white; border: 1px solid #999;")
        self.btn_zero_line_color.clicked.connect(lambda: self._pick_chart_color("zero_line"))
        lay_annot.addWidget(self.btn_zero_line_color, 2, 1)
        self.chk_ref05 = QCheckBox("显示 Y=+/-0.5")
        lay_annot.addWidget(self.chk_ref05, 2, 2)
        self.chk_ref10 = QCheckBox("显示 Y=+/-1.0")
        lay_annot.addWidget(self.chk_ref10, 2, 3)
        self.chk_span = QCheckBox("高亮 -0.2 到 0.2")
        lay_annot.addWidget(self.chk_span, 2, 4)
        # Data labels (from old Tab 5)
        lay_annot.addWidget(QLabel("数据标签:"), 3, 0)
        self.cb_labels = QComboBox()
        self.cb_labels.addItems(["仅极值", "无", "全部", "> 阈值"])
        lay_annot.addWidget(self.cb_labels, 3, 1)
        lay_annot.addWidget(QLabel("标签阈值:"), 3, 2)
        self.spin_lbl_thresh = QDoubleSpinBox()
        self.spin_lbl_thresh.setValue(0.5)
        lay_annot.addWidget(self.spin_lbl_thresh, 3, 3)
        lay_annot.addWidget(QLabel("数据标签字体:"), 4, 0)
        self.cb_data_font = QComboBox()
        self.cb_data_font.addItems(["Arial", "Times New Roman", "Microsoft YaHei", "Inter"])
        lay_annot.addWidget(self.cb_data_font, 4, 1)
        lay_annot.addWidget(QLabel("数据标签字号:"), 4, 2)
        self.spin_data_size = QSpinBox()
        self.spin_data_size.setValue(10)
        lay_annot.addWidget(self.spin_data_size, 4, 3)
        lay_annot.addWidget(QLabel("标签偏移:"), 4, 4)
        self.spin_data_offset = QDoubleSpinBox()
        self.spin_data_offset.setRange(-100, 100)
        self.spin_data_offset.setValue(5.0)
        lay_annot.addWidget(self.spin_data_offset, 4, 5)
        lay_annot.addWidget(QLabel("标签旋转 (度):"), 5, 0)
        self.spin_data_rot = QSpinBox()
        self.spin_data_rot.setRange(0, 360)
        lay_annot.addWidget(self.spin_data_rot, 5, 1)
        self.chk_bold_data = QCheckBox("加粗数据标签")
        lay_annot.addWidget(self.chk_bold_data, 5, 2)
        # Annotation (from old Tab 5)
        lay_annot.addWidget(QLabel("注释:"), 6, 0)
        self.le_annot = QLineEdit()
        self.le_annot.setPlaceholderText("自由文本注释")
        lay_annot.addWidget(self.le_annot, 6, 1, 1, 2)
        lay_annot.addWidget(QLabel("X 位置:"), 6, 3)
        self.spin_annot_x = QDoubleSpinBox()
        self.spin_annot_x.setRange(0.0, 1.0)
        self.spin_annot_x.setValue(0.05)
        self.spin_annot_x.setSingleStep(0.01)
        lay_annot.addWidget(self.spin_annot_x, 6, 4)
        lay_annot.addWidget(QLabel("Y 位置:"), 6, 5)
        self.spin_annot_y = QDoubleSpinBox()
        self.spin_annot_y.setRange(0.0, 1.0)
        self.spin_annot_y.setValue(0.95)
        self.spin_annot_y.setSingleStep(0.01)
        lay_annot.addWidget(self.spin_annot_y, 6, 6)
        lay_annot.setRowStretch(7, 1)
        lay_annot.setColumnStretch(7, 1)

        # ---- Tab 5: Font & Export ----
        tab_font_export = QWidget()
        lay_fe = QGridLayout(tab_font_export)
        # Font controls (moved from old Tab 2)
        lay_fe.addWidget(QLabel("轴标签字体:"), 0, 0)
        self.cb_ax_font = QComboBox()
        self.cb_ax_font.addItems(["Arial", "Times New Roman", "Microsoft YaHei", "Inter"])
        lay_fe.addWidget(self.cb_ax_font, 0, 1)
        lay_fe.addWidget(QLabel("轴标签字号:"), 0, 2)
        self.spin_ax_size = QSpinBox()
        self.spin_ax_size.setValue(12)
        lay_fe.addWidget(self.spin_ax_size, 0, 3)
        lay_fe.addWidget(QLabel("刻度标签字体:"), 0, 4)
        self.cb_tick_font = QComboBox()
        self.cb_tick_font.addItems(["Arial", "Times New Roman", "Microsoft YaHei", "Inter"])
        lay_fe.addWidget(self.cb_tick_font, 0, 5)
        lay_fe.addWidget(QLabel("刻度标签字号:"), 0, 6)
        self.spin_tick_size = QSpinBox()
        self.spin_tick_size.setValue(10)
        lay_fe.addWidget(self.spin_tick_size, 0, 7)
        self.chk_bold_ax = QCheckBox("加粗轴标签")
        lay_fe.addWidget(self.chk_bold_ax, 1, 0)
        self.chk_bold_ticks = QCheckBox("加粗刻度标签")
        lay_fe.addWidget(self.chk_bold_ticks, 1, 1)
        # Global font (from old Tab 5)
        lay_fe.addWidget(QLabel("全局字体:"), 1, 2)
        self.cb_font = QComboBox()
        self.cb_font.addItems(["Arial", "Times New Roman", "Microsoft YaHei", "Inter"])
        lay_fe.addWidget(self.cb_font, 1, 3)
        lay_fe.addWidget(QLabel("字号:"), 1, 4)
        self.spin_fsize = QSpinBox()
        self.spin_fsize.setValue(12)
        lay_fe.addWidget(self.spin_fsize, 1, 5)
        self.chk_latex = QCheckBox("LaTeX 数学公式渲染")
        self.chk_latex.setToolTip("使用 LaTeX 引擎渲染数学公式（需要安装 MiKTeX 或 TeX Live）")
        lay_fe.addWidget(self.chk_latex, 1, 6, 1, 2)
        # Export controls (from old Tab 6)
        lay_fe.addWidget(QLabel("导出 DPI:"), 2, 0)
        self.cb_dpi = QComboBox()
        self.cb_dpi.addItems(["150", "300", "600", "1200"])
        self.cb_dpi.setCurrentText("300")
        lay_fe.addWidget(self.cb_dpi, 2, 1)
        lay_fe.addWidget(QLabel("宽度 (英寸):"), 2, 2)
        self.spin_width = QDoubleSpinBox()
        self.spin_width.setValue(8.0)
        lay_fe.addWidget(self.spin_width, 2, 3)
        lay_fe.addWidget(QLabel("高度 (英寸):"), 2, 4)
        self.spin_height = QDoubleSpinBox()
        self.spin_height.setValue(6.0)
        lay_fe.addWidget(self.spin_height, 2, 5)
        self.chk_transparent = QCheckBox("透明背景")
        lay_fe.addWidget(self.chk_transparent, 2, 6, 1, 2)
        btn_export_img = QPushButton(" 导出高分辨率图像")
        btn_export_img.setIcon(qta.icon("fa5s.file-image"))
        btn_export_img.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold;")
        btn_export_img.clicked.connect(self.export_high_res_image)
        lay_fe.addWidget(btn_export_img, 3, 0, 1, 3)
        btn_clipboard = QPushButton(" 复制到剪贴板")
        btn_clipboard.setIcon(qta.icon("fa5s.clipboard"))
        btn_clipboard.setStyleSheet("background-color: #6c757d; color: white; font-weight: bold;")
        btn_clipboard.clicked.connect(self.export_to_clipboard)
        lay_fe.addWidget(btn_clipboard, 3, 3, 1, 3)
        btn_save_cfg = QPushButton(" 保存设置 (JSON)")
        btn_save_cfg.setIcon(qta.icon("fa5s.save"))
        btn_save_cfg.clicked.connect(self.save_template)
        lay_fe.addWidget(btn_save_cfg, 4, 0, 1, 3)
        btn_load_cfg = QPushButton(" 加载设置 (JSON)")
        btn_load_cfg.setIcon(qta.icon("fa5s.folder-open"))
        btn_load_cfg.clicked.connect(self.load_template)
        lay_fe.addWidget(btn_load_cfg, 4, 3, 1, 3)
        # Journal presets
        lay_fe.addWidget(QLabel("期刊预设:"), 5, 0)
        self.cb_journal = QComboBox()
        self.cb_journal.addItems(["自定义", "Nature", "Science", "ACS", "RSC", "Elsevier"])
        lay_fe.addWidget(self.cb_journal, 5, 1, 1, 2)
        btn_apply_preset = QPushButton("应用预设")
        btn_apply_preset.clicked.connect(self._apply_journal_preset)
        lay_fe.addWidget(btn_apply_preset, 5, 3, 1, 2)
        # Real-time preview & batch export
        self.chk_realtime = QCheckBox("实时预览 (修改设置时自动渲染)")
        self.chk_realtime.setToolTip("启用后修改设置时自动刷新图表（可能影响性能）")
        lay_fe.addWidget(self.chk_realtime, 6, 0, 1, 3)
        btn_batch = QPushButton(" 批量导出 (所有工作区)")
        btn_batch.setIcon(qta.icon("fa5s.images"))
        btn_batch.setStyleSheet("background-color: #6f42c1; color: white; font-weight: bold;")
        btn_batch.clicked.connect(self.batch_export)
        lay_fe.addWidget(btn_batch, 6, 3, 1, 3)
        lay_fe.setRowStretch(8, 1)
        lay_fe.setColumnStretch(8, 1)

        # ---- Re-home controls into refined tabs ----
        # The original widgets keep their object attributes so config sync and
        # plotting logic remain untouched; only their visible parent tab changes.
        def make_double_spin(value, minimum=0.0, maximum=100.0, step=0.1,
                             decimals=2):
            spin = QDoubleSpinBox()
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setValue(value)
            return spin

        self.spin_fig_margin_left = make_double_spin(0.0, 0.0, 0.45, 0.01)
        self.spin_fig_margin_right = make_double_spin(0.0, 0.0, 0.45, 0.01)
        self.spin_fig_margin_top = make_double_spin(0.0, 0.0, 0.45, 0.01)
        self.spin_fig_margin_bottom = make_double_spin(0.0, 0.0, 0.45, 0.01)
        for spin in (self.spin_fig_margin_left, self.spin_fig_margin_right,
                     self.spin_fig_margin_top, self.spin_fig_margin_bottom):
            spin.setToolTip("0 表示沿用当前自动布局")
        self.spin_axes_pad = make_double_spin(4.0, 0.0, 40.0, 1.0)
        self.spin_title_pad = make_double_spin(12.0, 0.0, 60.0, 1.0)
        self.cb_title_position = QComboBox()
        self.cb_title_position.addItems(["顶部居中", "顶部左侧", "图内左上", "图内右上"])

        self.spin_major_tick_length = make_double_spin(3.5, 0.0, 20.0, 0.5)
        self.spin_minor_tick_length = make_double_spin(2.0, 0.0, 20.0, 0.5)
        self.spin_tick_width = make_double_spin(0.8, 0.1, 5.0, 0.1)
        self.cb_tick_sides = QComboBox()
        self.cb_tick_sides.addItems(["默认", "上下左右", "仅左下"])

        self.spin_legend_columns = QSpinBox()
        self.spin_legend_columns.setRange(1, 6)
        self.spin_legend_columns.setValue(1)
        self.spin_legend_alpha = make_double_spin(1.0, 0.0, 1.0, 0.05)
        self.le_legend_title = QLineEdit()
        self.le_legend_title.setPlaceholderText("可选图例标题")
        self.spin_legend_handle_length = make_double_spin(2.0, 0.2, 8.0, 0.2)
        self.spin_legend_border_pad = make_double_spin(0.4, 0.0, 4.0, 0.1)

        self.cb_data_label_format = QComboBox()
        self.cb_data_label_format.addItems(["固定小数", "科学计数", "带符号"])
        self.spin_data_label_decimals = QSpinBox()
        self.spin_data_label_decimals.setRange(0, 8)
        self.spin_data_label_decimals.setValue(3)
        self.cb_data_label_pos_color = QComboBox()
        self.cb_data_label_pos_color.addItems(["auto", "black", "red", "blue", "#198754", "#dc3545"])
        self.cb_data_label_neg_color = QComboBox()
        self.cb_data_label_neg_color.addItems(["auto", "black", "red", "blue", "#198754", "#dc3545"])
        self.chk_data_label_avoid_overlap = QCheckBox("标签避让")

        self._compact_property_columns = 3
        self._compact_property_max_width = 1320
        self._compact_sections = {}
        self._compact_sections.update({
            "heatmap_colorbar": self._grp_heatmap,
            "radar_grid": self._grp_radar,
            "boxplot_violin": self._grp_boxplot,
        })

        def make_grid_tab():
            tab = QWidget()
            outer = QVBoxLayout(tab)
            outer.setContentsMargins(0, 0, 0, 0)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            page = QWidget()
            page_layout = QHBoxLayout(page)
            page_layout.setContentsMargins(8, 6, 8, 6)
            page_layout.setSpacing(0)
            content = QWidget()
            content.setMaximumWidth(self._compact_property_max_width)
            content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            grid = QGridLayout(content)
            grid.setContentsMargins(10, 6, 10, 6)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(5)
            grid.setSizeConstraint(QLayout.SetMinAndMaxSize)
            for label_col in (0, 2, 4):
                grid.setColumnMinimumWidth(label_col, 86)
            for field_col in (1, 3, 5):
                grid.setColumnMinimumWidth(field_col, 160)
                grid.setColumnStretch(field_col, 1)
            page_layout.addWidget(content, 1)
            scroll.setWidget(page)
            outer.addWidget(scroll)
            return tab, grid

        def add_row(grid, row, label, widget, col=0, span=1):
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl, row, col)
            grid.addWidget(widget, row, col + 1, 1, span)

        def add_section(grid, key, title, row):
            lbl = QLabel(title)
            lbl.setStyleSheet(
                "font-weight: 700; color: #495057; padding-top: 4px;"
                "border-bottom: 1px solid #e5e7eb;"
            )
            grid.addWidget(lbl, row, 0, 1, 6)
            self._compact_sections[key] = lbl
            return row + 1

        tab_data_filter, lay_data_filter = make_grid_tab()
        add_row(lay_data_filter, 0, "图表类型:", self.cb_plot_type)
        add_row(lay_data_filter, 1, "分组逻辑:", self.cb_group_logic)
        add_row(lay_data_filter, 0, "过滤 |q| < :", self.spin_filter, 2)
        add_row(lay_data_filter, 1, "显示前 N 个:", self.spin_top_n, 2)
        add_row(lay_data_filter, 2, "绘图体系:", self.btn_ws_select)
        add_row(lay_data_filter, 2, "数据层级:", self.cb_data_level, 2)
        add_row(lay_data_filter, 3, "元素统计:", self.cb_element_metric, 2)
        lay_data_filter.setColumnStretch(4, 1)

        tab_layout_title, lay_layout_title = make_grid_tab()
        add_row(lay_layout_title, 0, "图表标题:", self.le_title, span=3)
        add_row(lay_layout_title, 1, "面板布局:", self.cb_panel_layout)
        add_row(lay_layout_title, 1, "面板视图:", self.cb_panel_views, 2)
        row = add_section(lay_layout_title, "layout_canvas", "图层 / 画布", 3)
        add_row(lay_layout_title, row, "左边距:", self.spin_fig_margin_left)
        add_row(lay_layout_title, row, "右边距:", self.spin_fig_margin_right, 2)
        add_row(lay_layout_title, row, "上边距:", self.spin_fig_margin_top, 4)
        row += 1
        add_row(lay_layout_title, row, "下边距:", self.spin_fig_margin_bottom)
        add_row(lay_layout_title, row, "轴标题距:", self.spin_axes_pad, 2)
        add_row(lay_layout_title, row, "标题距离:", self.spin_title_pad, 4)
        row += 1
        add_row(lay_layout_title, row, "标题位置:", self.cb_title_position)
        lay_layout_title.setColumnStretch(4, 1)

        tab_global_theme, lay_global_theme = make_grid_tab()
        add_row(lay_global_theme, 0, "配色方案:", self.cb_theme)
        add_row(lay_global_theme, 1, "期刊预设:", self.cb_journal)
        lay_global_theme.addWidget(btn_apply_preset, 1, 2, 1, 2)
        lay_global_theme.addWidget(btn_series_color, 2, 0, 1, 2)
        lay_global_theme.setColumnStretch(4, 1)

        tab_global_font, lay_global_font = make_grid_tab()
        add_row(lay_global_font, 0, "全局字体:", self.cb_font)
        add_row(lay_global_font, 0, "字号:", self.spin_fsize, 2)
        add_row(lay_global_font, 1, "轴标签字体:", self.cb_ax_font)
        add_row(lay_global_font, 1, "轴标签字号:", self.spin_ax_size, 2)
        add_row(lay_global_font, 2, "刻度字体:", self.cb_tick_font)
        add_row(lay_global_font, 2, "刻度字号:", self.spin_tick_size, 2)
        add_row(lay_global_font, 3, "数据标签字体:", self.cb_data_font)
        add_row(lay_global_font, 3, "数据标签字号:", self.spin_data_size, 2)
        lay_global_font.addWidget(self.chk_bold_ax, 4, 0)
        lay_global_font.addWidget(self.chk_bold_ticks, 4, 1)
        lay_global_font.addWidget(self.chk_bold_data, 4, 2)
        lay_global_font.addWidget(self.chk_latex, 4, 3, 1, 2)
        lay_global_font.setColumnStretch(5, 1)

        tab_axis, lay_axis = make_grid_tab()
        add_row(lay_axis, 0, "X 轴标签:", self.le_xlabel)
        lay_axis.addWidget(self.chk_show_xlabel, 0, 2)
        add_row(lay_axis, 1, "Y 轴标签:", self.le_ylabel)
        lay_axis.addWidget(self.chk_show_ylabel, 1, 2)
        add_row(lay_axis, 0, "X 轴缩放:", self.cb_x_scale, 3)
        add_row(lay_axis, 1, "Y 轴缩放:", self.cb_y_scale, 3)
        add_row(lay_axis, 2, "刻度方向:", self.cb_tick_dir)
        add_row(lay_axis, 2, "X 刻度旋转:", self.spin_rot, 2)
        add_row(lay_axis, 3, "Y 最小值:", self.spin_y_min)
        add_row(lay_axis, 3, "Y 最大值:", self.spin_y_max, 2)
        add_row(lay_axis, 4, "Y 步长:", self.spin_y_step)
        add_row(lay_axis, 4, "刻度格式:", self.cb_tick_fmt, 2)
        add_row(lay_axis, 5, "小数位数:", self.spin_tick_dec)
        add_row(lay_axis, 5, "次刻度数:", self.spin_minor_ticks, 2)
        lay_axis.addWidget(self.chk_symmetric, 6, 0, 1, 2)
        lay_axis.addWidget(self.chk_sci_notation, 6, 2)
        lay_axis.addWidget(self.chk_axis_break, 7, 0)
        add_row(lay_axis, 7, "断裂下限:", self.spin_break_low, 1)
        add_row(lay_axis, 7, "断裂上限:", self.spin_break_high, 3)
        row = add_section(lay_axis, "axis_ticks", "刻度线", 8)
        add_row(lay_axis, row, "主刻度长:", self.spin_major_tick_length)
        add_row(lay_axis, row, "次刻度长:", self.spin_minor_tick_length, 2)
        add_row(lay_axis, row, "刻度宽:", self.spin_tick_width, 4)
        row += 1
        add_row(lay_axis, row, "显示边:", self.cb_tick_sides)
        lay_axis.setColumnStretch(5, 1)

        tab_grid_frame, lay_grid_frame = make_grid_tab()
        lay_grid_frame.addWidget(self.chk_y_maj, 0, 0)
        lay_grid_frame.addWidget(self.chk_y_min, 0, 1)
        lay_grid_frame.addWidget(self.chk_x_maj, 0, 2)
        add_row(lay_grid_frame, 1, "网格样式:", self.cb_grid_style)
        add_row(lay_grid_frame, 1, "网格颜色:", self.btn_grid_color, 2)
        add_row(lay_grid_frame, 2, "网格宽度:", self.spin_grid_width)
        add_row(lay_grid_frame, 2, "网格透明度:", self.spin_grid_alpha, 2)
        lay_grid_frame.addWidget(self.chk_spines, 3, 0)
        lay_grid_frame.addWidget(self.chk_spine_style, 3, 1)
        add_row(lay_grid_frame, 4, "边框宽度:", self.spin_spine_width)
        add_row(lay_grid_frame, 4, "边框颜色:", self.btn_spine_color, 2)
        lay_grid_frame.setColumnStretch(4, 1)

        tab_legend, lay_legend = make_grid_tab()
        add_row(lay_legend, 0, "图例位置:", self.cb_leg_pos)
        lay_legend.addWidget(self.chk_leg_frame, 0, 2)
        add_row(lay_legend, 0, "外置锚点:", self.cb_leg_external_anchor, 4)
        add_row(lay_legend, 1, "图例字体:", self.cb_leg_font)
        add_row(lay_legend, 1, "图例字号:", self.spin_leg_size, 2)
        add_row(lay_legend, 2, "自定义图例:", self.le_custom_leg, span=3)
        row = add_section(lay_legend, "legend_box", "图例框", 3)
        add_row(lay_legend, row, "图例列数:", self.spin_legend_columns)
        add_row(lay_legend, row, "透明度:", self.spin_legend_alpha, 2)
        add_row(lay_legend, row, "句柄长度:", self.spin_legend_handle_length, 4)
        row += 1
        add_row(lay_legend, row, "内边距:", self.spin_legend_border_pad)
        add_row(lay_legend, row, "图例标题:", self.le_legend_title, 2, 3)
        lay_legend.setColumnStretch(4, 1)

        tab_annotation_assist, lay_annotation_assist = make_grid_tab()
        lay_annotation_assist.addWidget(self.chk_zero, 0, 0)
        lay_annotation_assist.addWidget(self.btn_zero_line_color, 0, 1)
        lay_annotation_assist.addWidget(self.chk_ref05, 0, 2)
        lay_annotation_assist.addWidget(self.chk_ref10, 0, 3)
        lay_annotation_assist.addWidget(self.chk_span, 0, 4)
        add_row(lay_annotation_assist, 1, "数据标签:", self.cb_labels)
        add_row(lay_annotation_assist, 1, "标签阈值:", self.spin_lbl_thresh, 2)
        add_row(lay_annotation_assist, 2, "标签偏移:", self.spin_data_offset)
        add_row(lay_annotation_assist, 2, "标签旋转:", self.spin_data_rot, 2)
        add_row(lay_annotation_assist, 3, "注释:", self.le_annot, span=3)
        add_row(lay_annotation_assist, 4, "X 位置:", self.spin_annot_x)
        add_row(lay_annotation_assist, 4, "Y 位置:", self.spin_annot_y, 2)
        row = add_section(lay_annotation_assist, "annotation_labels", "数据标签格式", 5)
        add_row(lay_annotation_assist, row, "数字格式:", self.cb_data_label_format)
        add_row(lay_annotation_assist, row, "小数位:", self.spin_data_label_decimals, 2)
        lay_annotation_assist.addWidget(self.chk_data_label_avoid_overlap, row, 4, 1, 2)
        row += 1
        add_row(lay_annotation_assist, row, "正值颜色:", self.cb_data_label_pos_color)
        add_row(lay_annotation_assist, row, "负值颜色:", self.cb_data_label_neg_color, 2)
        lay_annotation_assist.setColumnStretch(4, 1)

        tab_export, lay_export = make_grid_tab()
        add_row(lay_export, 0, "导出 DPI:", self.cb_dpi)
        add_row(lay_export, 0, "宽度:", self.spin_width, 2)
        add_row(lay_export, 1, "高度:", self.spin_height)
        lay_export.addWidget(self.chk_transparent, 1, 2, 1, 2)
        lay_export.addWidget(btn_export_img, 2, 0, 1, 2)
        lay_export.addWidget(btn_clipboard, 2, 2, 1, 2)
        lay_export.addWidget(btn_save_cfg, 3, 0, 1, 2)
        lay_export.addWidget(btn_load_cfg, 3, 2, 1, 2)
        lay_export.addWidget(self.chk_realtime, 4, 0, 1, 2)
        lay_export.addWidget(btn_batch, 4, 2, 1, 2)
        lay_export.setColumnStretch(4, 1)

        # ---- Assemble tabs ----
        self.ribbon_tabs.addTab(tab_data_filter, qta.icon("fa5s.filter"), "数据筛选")
        self.ribbon_tabs.addTab(tab_layout_title, qta.icon("fa5s.th-large"), "布局标题")
        self.ribbon_tabs.addTab(tab_global_theme, qta.icon("fa5s.palette"), "全局主题")
        self.ribbon_tabs.addTab(tab_global_font, qta.icon("fa5s.font"), "全局字体")
        self.ribbon_tabs.addTab(tab_axis, qta.icon("fa5s.arrows-alt"), "坐标轴")
        self.ribbon_tabs.addTab(tab_grid_frame, qta.icon("fa5s.border-all"), "网格边框")
        self.ribbon_tabs.addTab(tab_legend, qta.icon("fa5s.list"), "图例")
        self.ribbon_tabs.addTab(tab_annotation_assist, qta.icon("fa5s.highlighter"), "标注辅助")
        self.ribbon_tabs.addTab(tab_chart_specific, qta.icon("fa5s.sliders-h"), "图表局部")
        self.ribbon_tabs.addTab(tab_export, qta.icon("fa5s.file-export"), "导出设置")

        # ---- Apply button ----
        lay_apply = QVBoxLayout()
        lay_apply.setContentsMargins(10, 10, 10, 10)
        btn_apply = QPushButton(" 应用样式")
        btn_apply.setIcon(qta.icon("fa5s.check", color="white"))
        btn_apply.setObjectName("PrimaryButton")
        btn_apply.setStyleSheet(
            "QPushButton#PrimaryButton {"
            "  background-color: #198754; color: white; font-weight: bold;"
            "  border-radius: 4px; padding: 12px 20px; font-size: 14px;"
            "}"
            "QPushButton#PrimaryButton:hover { background-color: #157347; }"
        )
        btn_apply.clicked.connect(self.update_config_and_plot)
        lay_apply.addWidget(btn_apply)

        btn_clear = QPushButton(" 清空画布")
        btn_clear.setIcon(qta.icon("fa5s.eraser", color="#666"))
        btn_clear.setStyleSheet(
            "QPushButton { background-color: #f0f0f0; color: #333; font-weight: bold;"
            "  border: 1px solid #ccc; border-radius: 4px; padding: 8px 16px; font-size: 12px; }"
            "QPushButton:hover { background-color: #e0e0e0; }"
        )
        btn_clear.setToolTip("清空当前画布（不影响数据和设置）")
        btn_clear.clicked.connect(self._clear_canvas)
        lay_apply.addWidget(btn_clear)
        lay_apply.addStretch()

        ribbon_container = QWidget()
        ribbon_layout = QHBoxLayout(ribbon_container)
        ribbon_layout.setContentsMargins(5, 5, 5, 5)
        ribbon_layout.addWidget(self.ribbon_tabs, 1)
        ribbon_layout.addLayout(lay_apply)
        main_layout.addWidget(ribbon_container)

        # ---- Figure & canvas ----
        self.figure = Figure(figsize=(5, 3.5), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumSize(200, 150)
        self.canvas.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.ax = self.figure.add_subplot(111)

        self._mpl_toolbar = NavigationToolbar2QT(self.canvas, self)
        self._mpl_toolbar.hide()

        custom_tb = QWidget()
        custom_tb.setStyleSheet("background: transparent; padding: 5px;")
        tb_lay = QHBoxLayout(custom_tb)
        tb_lay.setContentsMargins(15, 0, 15, 0)
        for name, icon, func in [
            ("Home", "fa5s.home", self._mpl_toolbar.home),
            ("Pan", "fa5s.arrows-alt", self._mpl_toolbar.pan),
            ("Zoom", "fa5s.search-plus", self._mpl_toolbar.zoom),
            ("Save", "fa5s.save", self._mpl_toolbar.save_figure),
        ]:
            btn = QPushButton()
            btn.setIcon(qta.icon(icon, color="#555"))
            btn.setFlat(True)
            if name in ["Pan", "Zoom"]:
                btn.setCheckable(True)
            btn.clicked.connect(func)
            tb_lay.addWidget(btn)
        # Workspace dropdown for boxplot/pie (single workspace selector)
        self._chart_ws_label = QLabel("  绘图体系:")
        self._chart_ws_label.setStyleSheet("font-size: 12px; color: #555;")
        self._chart_ws_combo = QComboBox()
        self._chart_ws_combo.setMinimumWidth(160)
        self._chart_ws_combo.setStyleSheet("QComboBox { font-size: 12px; padding: 3px 6px; }")
        self._chart_ws_combo.currentTextChanged.connect(self._on_chart_ws_changed)
        self._chart_ws_label.setVisible(False)
        self._chart_ws_combo.setVisible(False)
        tb_lay.addWidget(self._chart_ws_label)
        tb_lay.addWidget(self._chart_ws_combo)
        tb_lay.addStretch()
        main_layout.addWidget(custom_tb)
        main_layout.addWidget(self.canvas, 1)

        # ---- Hover annotation ----
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.annot = self.ax.annotate(
            "", xy=(0, 0), xytext=(10, 10), textcoords="offset points",
            bbox=dict(boxstyle="round", fc="w"), arrowprops=dict(arrowstyle="->"),
        )
        self.annot.set_visible(False)

        # ---- Cursor coordinate readout ----
        self.lbl_cursor_coords = QLabel("光标: (-, -)")
        self.lbl_cursor_coords.setStyleSheet("color: #666; font-size: 11px; padding: 2px 15px;")
        main_layout.addWidget(self.lbl_cursor_coords)
        self.canvas.mpl_connect("motion_notify_event", self._update_cursor_coords)

        # ---- Click handler for Plot-Table linkage ----
        self.canvas.mpl_connect("button_press_event", self._on_chart_click)
        self.canvas.mpl_connect("pick_event", self._on_annotation_pick)
        self._bar_to_atom_id = {}  # maps bar patch -> atom_id for linkage
        self._draggable_annotations = []  # list of draggable annotation artists

        # Real-time preview: connect key controls to auto-render
        self._realtime_signals = [
            self.cb_plot_type.currentTextChanged,
            self.cb_theme.currentTextChanged,
            self.cb_trend.currentTextChanged,
            self.chk_y_maj.toggled,
            self.chk_zero.toggled,
        ]
        for sig in self._realtime_signals:
            sig.connect(self._maybe_auto_render)

        # Hidden dark-mode toggle (driven by main window)
        self.chk_dark_mode = QCheckBox("深色模式")
        self.chk_dark_mode.hide()

    # ==================================================================
    #  Color pickers
    # ==================================================================

    def _pick_grid_color(self):
        color = QColorDialog.getColor(QColor(self._grid_color), self, "网格颜色")
        if color.isValid():
            self._grid_color = color.name()
            self.btn_grid_color.setStyleSheet(
                f"background: {self._grid_color}; color: #333; border: 1px solid #999;"
            )
            self.btn_grid_color.setText(f"  {self._grid_color}")

    def _pick_spine_color(self):
        color = QColorDialog.getColor(QColor(self._spine_color), self, "边框颜色")
        if color.isValid():
            self._spine_color = color.name()
            self.btn_spine_color.setStyleSheet(
                f"background: {self._spine_color}; color: white; border: 1px solid #999;"
            )
            self.btn_spine_color.setText(f"  {self._spine_color}")

    def _pick_chart_color(self, target):
        color = QColorDialog.getColor()
        if color.isValid():
            hex_color = color.name()
            style = f"background: {hex_color}; color: white; border: 1px solid #999;"
            if target == "waterfall_pos":
                self._waterfall_pos_color = hex_color
                self.btn_waterfall_pos_color.setStyleSheet(style)
                self.btn_waterfall_pos_color.setText(f"  {hex_color}")
            elif target == "waterfall_neg":
                self._waterfall_neg_color = hex_color
                self.btn_waterfall_neg_color.setStyleSheet(style)
                self.btn_waterfall_neg_color.setText(f"  {hex_color}")
            elif target == "boxplot":
                self._boxplot_color = hex_color
                self.btn_boxplot_color.setStyleSheet(style)
                self.btn_boxplot_color.setText(f"  {hex_color}")
            elif target == "radar_line":
                self._radar_line_color = hex_color
                self.btn_radar_line_color.setStyleSheet(style)
                self.btn_radar_line_color.setText(f"  {hex_color}")
            elif target == "waterfall_edge":
                self._waterfall_edge_color = hex_color
                self.btn_waterfall_edge_color.setStyleSheet(style)
                self.btn_waterfall_edge_color.setText(f"  {hex_color}")
            elif target == "boxplot_median":
                self._boxplot_median_color = hex_color
                self.btn_boxplot_median_color.setStyleSheet(style)
                self.btn_boxplot_median_color.setText(f"  {hex_color}")
            elif target == "boxplot_outlier":
                self._boxplot_outlier_color = hex_color
                self.btn_boxplot_outlier_color.setStyleSheet(style)
                self.btn_boxplot_outlier_color.setText(f"  {hex_color}")
            elif target == "heatmap_border":
                self._heatmap_border_color = hex_color
                text_color = "#333" if hex_color.lower() in ("#ffffff", "white") else "white"
                self.btn_heatmap_border_color.setStyleSheet(f"background: {hex_color}; color: {text_color}; border: 1px solid #999;")
                self.btn_heatmap_border_color.setText(f"  {hex_color}")
            elif target == "pie_edge":
                self._pie_edge_color = hex_color
                text_color = "#333" if hex_color.lower() in ("#ffffff", "white") else "white"
                self.btn_pie_edge_color.setStyleSheet(f"background: {hex_color}; color: {text_color}; border: 1px solid #999;")
                self.btn_pie_edge_color.setText(f"  {hex_color}")
            elif target == "wf_conn":
                self._wf_conn_color = hex_color
                self.btn_wf_conn_color.setStyleSheet(style)
                self.btn_wf_conn_color.setText(f"  {hex_color}")
            elif target == "wf_total":
                self._wf_total_color = hex_color
                self.btn_wf_total_color.setStyleSheet(style)
                self.btn_wf_total_color.setText(f"  {hex_color}")
            elif target == "bp_whisker":
                self._bp_whisker_color = hex_color
                self.btn_bp_whisker_color.setStyleSheet(style)
                self.btn_bp_whisker_color.setText(f"  {hex_color}")
            elif target == "hm_nan":
                self._hm_nan_color = hex_color
                text_color = "#333" if hex_color.lower() in ("#e0e0e0", "#ffffff", "white") else "white"
                self.btn_hm_nan_color.setStyleSheet(f"background: {hex_color}; color: {text_color}; border: 1px solid #999;")
                self.btn_hm_nan_color.setText(f"  {hex_color}")
            elif target == "radar_fill":
                self._radar_fill_color = hex_color
                self.btn_radar_fill_color.setStyleSheet(style)
                self.btn_radar_fill_color.setText(f"  {hex_color}")
            elif target == "wf_zero":
                self._wf_zero_line_color = hex_color
                text_color = "#333" if hex_color.lower() in ("#ffffff", "#000000", "white", "black") else "white"
                self.btn_wf_zero_color.setStyleSheet(f"background: {hex_color}; color: {text_color}; border: 1px solid #999;")
                self.btn_wf_zero_color.setText(f"  {hex_color}")
            elif target == "wf_cum":
                self._wf_cum_color = hex_color
                self.btn_wf_cum_color.setStyleSheet(style)
                self.btn_wf_cum_color.setText(f"  {hex_color}")
            elif target == "bp_point":
                self._bp_point_color = hex_color
                self.btn_bp_point_color.setStyleSheet(style)
                self.btn_bp_point_color.setText(f"  {hex_color}")
            elif target == "bp_edge":
                self._bp_edge_color = hex_color
                self.btn_bp_edge_color.setStyleSheet(style)
                self.btn_bp_edge_color.setText(f"  {hex_color}")
            elif target == "bp_mean":
                self._bp_mean_color = hex_color
                self.btn_bp_mean_color.setStyleSheet(style)
                self.btn_bp_mean_color.setText(f"  {hex_color}")
            elif target == "pie_pct":
                self._pie_pct_color = hex_color
                self.btn_pie_pct_color.setStyleSheet(style)
                self.btn_pie_pct_color.setText(f"  {hex_color}")
            elif target == "pie_center_lbl":
                self._pie_center_label_color = hex_color
                self.btn_pie_center_lbl_color.setStyleSheet(style)
                self.btn_pie_center_lbl_color.setText(f"  {hex_color}")
            elif target == "radar_grid":
                self._radar_grid_color = hex_color
                self.btn_radar_grid_color.setStyleSheet(style)
                self.btn_radar_grid_color.setText(f"  {hex_color}")
            elif target == "radar_fill_edge":
                self._radar_fill_edge_color = hex_color
                self.btn_radar_fill_edge_color.setStyleSheet(style)
                self.btn_radar_fill_edge_color.setText(f"  {hex_color}")
            elif target == "zero_line":
                self._zero_line_color = hex_color
                text_color = "#333" if hex_color.lower() in ("#ffffff", "white") else "white"
                self.btn_zero_line_color.setStyleSheet(
                    f"background: {hex_color}; color: {text_color}; border: 1px solid #999;")

    def _on_plot_type_changed(self, idx):
        """Show/hide collapsible chart-type groups based on selected plot type."""
        chart_type = self.cb_plot_type.itemText(idx) if idx >= 0 else self.cb_plot_type.currentText()
        type_groups = {
            "分组柱状图": "bar",
            "水平柱状图": "bar",
            "折线图": "line",
            "散点图": "line",
            "箱线图": "boxplot",
            "热力图": "heatmap",
            "雷达图": "radar",
            "饼图": "pie",
        }
        active = type_groups.get(chart_type, "bar")
        for name, group in self._chart_type_groups.items():
            is_active = (name == active)
            group.setVisible(is_active)
            if is_active:
                group.set_expanded(True)

        # Auto-render on chart type change so the user sees immediate feedback.
        # Skip if realtime preview is already on — _maybe_auto_render handles it.
        if self.current_data and not self.chk_realtime.isChecked():
            self.update_config_and_plot()

    # ==================================================================
    #  Real-time preview
    # ==================================================================

    def _maybe_auto_render(self, *_args):
        if self.chk_realtime.isChecked():
            self.update_config_and_plot()

    # ==================================================================
    #  Journal presets
    # ==================================================================

    def _apply_journal_preset(self):
        preset = self.cb_journal.currentText()
        presets = {
            "Nature": {"width": 7.2, "height": 5.0, "font": "Arial", "size": 8, "dpi": 300},
            "Science": {"width": 7.0, "height": 5.0, "font": "Arial", "size": 8, "dpi": 300},
            "ACS": {"width": 6.5, "height": 4.5, "font": "Arial", "size": 9, "dpi": 300},
            "RSC": {"width": 6.8, "height": 4.8, "font": "Arial", "size": 8, "dpi": 300},
            "Elsevier": {"width": 7.0, "height": 5.0, "font": "Times New Roman", "size": 10, "dpi": 300},
        }
        if preset not in presets:
            QMessageBox.information(self, "提示", "请先选择一个期刊预设。")
            return
        p = presets[preset]
        self.spin_width.setValue(p["width"])
        self.spin_height.setValue(p["height"])
        self.cb_font.setCurrentText(p["font"])
        self.cb_ax_font.setCurrentText(p["font"])
        self.cb_tick_font.setCurrentText(p["font"])
        self.cb_data_font.setCurrentText(p["font"])
        self.cb_leg_font.setCurrentText(p["font"])
        self.spin_fsize.setValue(p["size"])
        self.spin_ax_size.setValue(p["size"])
        self.spin_tick_size.setValue(p["size"] - 1)
        self.spin_data_size.setValue(p["size"] - 1)
        self.spin_leg_size.setValue(p["size"] - 1)
        self.cb_dpi.setCurrentText(str(p["dpi"]))
        self.config.journal_preset = preset
        QMessageBox.information(self, "已应用预设", f"已应用 {preset} 期刊预设。")

    # ==================================================================
    #  Batch export
    # ==================================================================

    def batch_export(self):
        if not self.current_data:
            QMessageBox.warning(self, "警告", "未加载数据。")
            return
        folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
        if not folder:
            return
        import os
        c = self.config
        orig_w, orig_h = self.figure.get_size_inches()
        try:
            for ws_name in list(self.current_data.keys()):
                single_data = {ws_name: self.current_data[ws_name]}
                old_data = self.current_data
                self.current_data = single_data
                self._no_data_restore = True
                self.apply_styles()
                path = os.path.join(folder, f"{ws_name}_plot.png")
                try:
                    self.figure.set_size_inches(c.export_width, c.export_height)
                    self.figure.savefig(path, dpi=c.export_dpi,
                                        bbox_inches='tight', transparent=c.export_transparent)
                except Exception:
                    pass
                self.current_data = old_data
        finally:
            self.figure.set_size_inches(orig_w, orig_h)
            self._no_data_restore = False
            self.apply_styles()
            self.figure.canvas.draw_idle()
        QMessageBox.information(self, "成功", f"批量导出完成至:\n{folder}")

    # ==================================================================
    #  Per-series color override
    # ==================================================================

    def _override_series_colors(self):
        if not self.current_data:
            QMessageBox.warning(self, "警告", "未加载数据。")
            return
        from PySide6.QtWidgets import QInputDialog
        atoms = []
        for ws in self.current_data.values():
            df = ws['df']
            if not df.empty:
                for _, row in df.iterrows():
                    lbl = f"{row.get('Element', 'X')}{row['Atom']}"
                    if lbl not in atoms:
                        atoms.append(lbl)
        if not atoms:
            return
        atom_str, ok = QInputDialog.getText(self, "覆盖系列颜色",
                                            f"可用: {', '.join(atoms[:20])}\n输入原子标签 (例如 O1):")
        if not ok or not atom_str.strip():
            return
        atom_str = atom_str.strip()
        color = QColorDialog.getColor(QColor("#FF0000"), self, f"{atom_str} 的颜色")
        if color.isValid():
            self.config.series_colors[atom_str] = color.name()
            self.apply_styles()
            QMessageBox.information(self, "完成", f"{atom_str} 的颜色已设置为 {color.name()}")

    # ==================================================================
    #  Cursor coordinate readout
    # ==================================================================

    def _update_cursor_coords(self, event):
        if event.inaxes == self.ax:
            self.lbl_cursor_coords.setText(
                f"光标: ({event.xdata:.4f}, {event.ydata:.4f})"
            )
        else:
            self.lbl_cursor_coords.setText("光标: (-, -)")

    # ==================================================================
    #  Plot-Table linkage: click chart to highlight table row
    # ==================================================================

    def _on_chart_click(self, event):
        if event.button != 1 or event.inaxes is None:
            return
        # Check if click is on any axes in the figure (supports multi-panel)
        if event.inaxes not in self.figure.get_axes():
            return
        for patch, atom_id in self._bar_to_atom_id.items():
            cont, _ = patch.contains(event)
            if cont:
                self.data_point_selected.emit(atom_id)
                return

    # ==================================================================
    #  Axis break rendering
    # ==================================================================

    def _apply_axis_break(self, cfg, all_atoms, element_map, workspaces):
        """Apply Y-axis break using two stacked subplots with recursive rendering."""
        break_low = getattr(cfg, 'axis_break_range_low', -0.5)
        break_high = getattr(cfg, 'axis_break_range_high', 0.5)
        if break_low >= break_high:
            # Invalid range — fall through to normal rendering
            cfg.axis_break = False
            return

        self.figure.clear()
        saved_bar_map = {}
        gs = self.figure.add_gridspec(2, 1, height_ratios=[1, 1], hspace=0.05)

        for idx, (ymin, ymax) in enumerate([(break_high, None), (None, break_low)]):
            ax = self.figure.add_subplot(gs[idx])
            self.ax = ax
            saved_break = cfg.axis_break
            saved_ymin = cfg.y_min
            saved_ymax = cfg.y_max
            cfg.axis_break = False
            cfg.y_min = ymin if ymin is not None else 0.0
            cfg.y_max = ymax if ymax is not None else 0.0
            self._clear_figure = False
            self.apply_styles()
            self._clear_figure = True
            cfg.axis_break = saved_break
            cfg.y_min = saved_ymin
            cfg.y_max = saved_ymax
            saved_bar_map.update(self._bar_to_atom_id)

        self._bar_to_atom_id = saved_bar_map

        # Hide connecting spines
        ax_upper = self.figure.axes[0]
        ax_lower = self.figure.axes[1]
        ax_upper.spines['bottom'].set_visible(False)
        ax_lower.spines['top'].set_visible(False)
        ax_upper.xaxis.set_ticks([])
        ax_upper.xaxis.set_ticklabels([])

        # Add diagonal break marks
        d = 0.015
        kwargs = dict(transform=ax_upper.transAxes, color='k', clip_on=False, linewidth=1.0)
        ax_upper.plot((-d, +d), (-d, +d), **kwargs)
        ax_upper.plot((1 - d, 1 + d), (-d, +d), **kwargs)
        kwargs.update(transform=ax_lower.transAxes)
        ax_lower.plot((-d, +d), (1 - d, 1 + d), **kwargs)
        ax_lower.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)

        self.ax = ax_lower
        self._apply_dark_mode()
        self.figure.canvas.draw_idle()

    # ==================================================================
    #  Draggable annotation system
    # ==================================================================

    def _add_draggable_annotation(self, text, x, y):
        """Add a draggable annotation with leader line to the plot."""
        annot = self.ax.annotate(
            text, xy=(x, y), xytext=(x + 0.5, y + 0.5),
            textcoords="data",
            arrowprops=dict(arrowstyle="->", color="gray", lw=1.0),
            bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.8, edgecolor="gray"),
            fontsize=9,
        )
        annot.set_picker(True)
        self._draggable_annotations.append(annot)
        return annot

    def _on_annotation_pick(self, event):
        """Handle annotation drag events."""
        if event.artist in self._draggable_annotations:
            annot = event.artist
            annot.xy = (event.mouseevent.xdata, event.mouseevent.ydata)
            self.canvas.draw_idle()

    # ==================================================================
    #  Config <-> UI synchronisation
    # ==================================================================

    def update_config_and_plot(self):
        c = self.config
        c.plot_type = self.cb_plot_type.currentText()
        c.group_logic = self.cb_group_logic.currentText()
        c.filter_threshold = self.spin_filter.value()
        c.show_top_n = self.spin_top_n.value()
        c.fig_title = self.le_title.text()

        c.x_label = self.le_xlabel.text()
        c.y_label = self.le_ylabel.text()
        c.show_x_label = self.chk_show_xlabel.isChecked()
        c.show_y_label = self.chk_show_ylabel.isChecked()
        c.x_scale = self.cb_x_scale.currentText()
        c.y_scale = self.cb_y_scale.currentText()
        c.tick_direction = self.cb_tick_dir.currentText()
        c.x_tick_rotation = self.spin_rot.value()
        c.y_symmetric = self.chk_symmetric.isChecked()
        c.show_top_right_spines = self.chk_spines.isChecked()
        c.y_min = self.spin_y_min.value()
        c.y_max = self.spin_y_max.value()
        c.y_step = self.spin_y_step.value()
        c.tick_format = self.cb_tick_fmt.currentText()
        c.tick_decimals = self.spin_tick_dec.value()
        c.scientific_notation = self.chk_sci_notation.isChecked()
        c.minor_ticks_count = self.spin_minor_ticks.value()
        c.axis_break = self.chk_axis_break.isChecked()
        c.axis_break_range_low = self.spin_break_low.value()
        c.axis_break_range_high = self.spin_break_high.value()
        c.panel_layout = self.cb_panel_layout.currentText()
        c.panel_views = self.cb_panel_views.currentText()
        c.figure_margin_left = self.spin_fig_margin_left.value()
        c.figure_margin_right = self.spin_fig_margin_right.value()
        c.figure_margin_top = self.spin_fig_margin_top.value()
        c.figure_margin_bottom = self.spin_fig_margin_bottom.value()
        c.axes_label_pad = self.spin_axes_pad.value()
        c.title_position = self.cb_title_position.currentText()
        c.title_pad = self.spin_title_pad.value()
        c.major_tick_length = self.spin_major_tick_length.value()
        c.minor_tick_length = self.spin_minor_tick_length.value()
        c.tick_width = self.spin_tick_width.value()
        c.tick_sides = self.cb_tick_sides.currentText()
        c.spine_width = self.spin_spine_width.value()
        c.spine_color = self._spine_color

        c.show_y_major_grid = self.chk_y_maj.isChecked()
        c.show_y_minor_grid = self.chk_y_min.isChecked()
        c.show_x_major_grid = self.chk_x_maj.isChecked()
        c.grid_style = self.cb_grid_style.currentText()
        c.grid_color = self._grid_color
        c.grid_width = self.spin_grid_width.value()
        c.grid_alpha = self.spin_grid_alpha.value()
        c.show_zero_line = self.chk_zero.isChecked()
        c.zero_line_color = self._zero_line_color
        c.show_ref_05 = self.chk_ref05.isChecked()
        c.show_ref_10 = self.chk_ref10.isChecked()
        c.show_highlight_span = self.chk_span.isChecked()

        c.theme = self.cb_theme.currentText()
        c.hatch_style = self.cb_hatch.currentText() if self.cb_hatch.currentText() != "无" else None
        c.bar_width = self.spin_bw.value()
        c.edge_color = self.cb_edge.currentText()
        c.edge_width = 1.0 if c.edge_color != "none" else 0.0
        c.line_style = LINE_STYLE_MAP.get(self.cb_line_style.currentText(), "-")
        c.line_width = self.spin_line_width.value()
        c.marker_style = MARKER_MAP.get(self.cb_marker.currentText(), "o")
        c.marker_size = self.spin_marker_size.value()
        c.trend_line = self.cb_trend.currentText()
        c.trend_line_degree = self.spin_trend_degree.value()

        c.legend_position = self.cb_leg_pos.currentText()
        c.legend_frame = self.chk_leg_frame.isChecked()
        c.legend_font = self.cb_leg_font.currentText()
        c.legend_size = self.spin_leg_size.value()
        c.custom_legend = self.le_custom_leg.text()
        c.legend_external_anchor = self.cb_leg_external_anchor.currentText()
        c.legend_columns = self.spin_legend_columns.value()
        c.legend_alpha = self.spin_legend_alpha.value()
        c.legend_title = self.le_legend_title.text()
        c.legend_handle_length = self.spin_legend_handle_length.value()
        c.legend_border_pad = self.spin_legend_border_pad.value()

        c.show_data_labels = self.cb_labels.currentText()
        c.label_threshold = self.spin_lbl_thresh.value()
        c.font_family = self.cb_font.currentText()
        c.font_size = self.spin_fsize.value()
        c.data_label_font = self.cb_data_font.currentText()
        c.data_label_size = self.spin_data_size.value()
        c.data_label_offset = self.spin_data_offset.value()
        c.data_label_rotation = self.spin_data_rot.value()
        c.data_label_format = self.cb_data_label_format.currentText()
        c.data_label_decimals = self.spin_data_label_decimals.value()
        c.data_label_positive_color = self.cb_data_label_pos_color.currentText()
        c.data_label_negative_color = self.cb_data_label_neg_color.currentText()
        c.data_label_avoid_overlap = self.chk_data_label_avoid_overlap.isChecked()
        c.bold_data = self.chk_bold_data.isChecked()
        c.axis_label_font = self.cb_ax_font.currentText()
        c.axis_label_size = self.spin_ax_size.value()
        c.tick_label_font = self.cb_tick_font.currentText()
        c.tick_label_size = self.spin_tick_size.value()
        c.bold_ax_lbl = self.chk_bold_ax.isChecked()
        c.bold_ticks = self.chk_bold_ticks.isChecked()

        c.show_error_bars = self.chk_err_bars.isChecked()
        c.error_bar_type = self.cb_err_type.currentText()
        c.annotation_text = self.le_annot.text()
        c.annotation_pos_x = self.spin_annot_x.value()
        c.annotation_pos_y = self.spin_annot_y.value()
        c.latex_rendering = self.chk_latex.isChecked()
        c.realtime_preview = self.chk_realtime.isChecked()
        c.journal_preset = self.cb_journal.currentText()

        c.export_dpi = int(self.cb_dpi.currentText())
        c.export_width = self.spin_width.value()
        c.export_height = self.spin_height.value()
        c.export_transparent = self.chk_transparent.isChecked()

        # Chart-type-specific settings
        c.waterfall_pos_color = self._waterfall_pos_color
        c.waterfall_neg_color = self._waterfall_neg_color
        c.waterfall_connectors = self.chk_waterfall_connectors.isChecked()
        c.waterfall_atom_id = self.spin_waterfall_atom_id.value()

        c.boxplot_color = self._boxplot_color
        c.boxplot_show_mean = self.chk_boxplot_show_mean.isChecked()
        c.boxplot_alpha = self.spin_boxplot_alpha.value()
        c.boxplot_max_atoms = self.spin_boxplot_max_atoms.value()

        c.heatmap_colormap = self.cb_heatmap_colormap.currentText()
        c.heatmap_show_values = self.chk_heatmap_show_values.isChecked()
        c.heatmap_value_format = self.cb_heatmap_value_format.currentText()
        c.heatmap_value_size = self.spin_heatmap_value_size.value()
        c.heatmap_aspect = self.cb_heatmap_aspect.currentText()

        c.radar_line_color = self._radar_line_color
        c.radar_line_width = self.spin_radar_line_width.value()
        c.radar_fill_alpha = self.spin_radar_fill_alpha.value()
        c.radar_marker_size = self.spin_radar_marker_size.value()
        c.radar_max_atoms = self.spin_radar_max_atoms.value()

        c.area_alpha = self.spin_area_alpha.value()
        c.area_mode = self.cb_area_mode.currentText()
        c.area_interpolation = self.cb_area_interpolation.currentText()
        c.area_edge_line = self.chk_area_edge.isChecked()
        c.area_edge_width = self.spin_area_edge_width.value()
        c.area_edge_style = LINE_STYLE_MAP.get(self.cb_area_edge_style.currentText(), "-")
        c.area_order = self.cb_area_order.currentText()
        c.area_gradient = self.chk_area_gradient.isChecked()
        c.area_negative = self.chk_area_negative.isChecked()

        c.waterfall_bar_width = self.spin_waterfall_bar_width.value()
        c.waterfall_edge_color = self._waterfall_edge_color
        c.waterfall_edge_width = self.spin_waterfall_edge_width.value()
        c.waterfall_sort = self.cb_waterfall_sort.currentText()
        c.waterfall_show_total = self.chk_waterfall_total.isChecked()
        c.waterfall_connector_style = LINE_STYLE_MAP.get(self.cb_wf_conn_style.currentText(), "-")
        c.waterfall_connector_color = self._wf_conn_color
        c.waterfall_connector_width = self.spin_wf_conn_width.value()
        c.waterfall_connector_alpha = self.spin_wf_conn_alpha.value()
        c.waterfall_show_labels = self.chk_wf_labels.isChecked()
        c.waterfall_total_color = self._wf_total_color
        c.waterfall_zero_line_color = self._wf_zero_line_color
        c.waterfall_zero_line_width = self.spin_wf_zero_width.value()
        c.waterfall_label_format = self.cb_wf_label_fmt.currentText()
        c.waterfall_label_font = self.cb_wf_label_font.currentText()
        c.waterfall_label_weight = self.cb_wf_label_weight.currentText()
        c.waterfall_hatch = self.cb_wf_hatch.currentText() if self.cb_wf_hatch.currentText() != "无" else None
        c.waterfall_bar_round = self.spin_wf_bar_round.value()
        c.waterfall_cumulative_line = self.chk_wf_cumulative.isChecked()
        c.waterfall_cumulative_color = self._wf_cum_color
        c.waterfall_cumulative_width = self.spin_wf_cum_width.value()
        c.waterfall_pct_mode = self.chk_wf_pct_mode.isChecked()

        c.boxplot_whisker = self.spin_boxplot_whisker.value()
        c.boxplot_notch = self.chk_boxplot_notch.isChecked()
        c.boxplot_median_color = self._boxplot_median_color
        c.boxplot_median_width = self.spin_boxplot_median_width.value()
        c.boxplot_outlier_marker = MARKER_MAP.get(self.cb_boxplot_outlier_marker.currentText(), "o")
        c.boxplot_outlier_color = self._boxplot_outlier_color
        c.boxplot_show_outliers = self.chk_boxplot_outliers.isChecked()
        c.boxplot_show_points = self.cb_bp_points.currentText()
        c.boxplot_violin = self.chk_bp_violin.isChecked()
        c.boxplot_cap_width = self.spin_bp_cap_width.value()
        c.boxplot_show_caps = self.chk_bp_caps.isChecked()
        c.boxplot_width = self.spin_bp_width.value()
        c.boxplot_whisker_color = self._bp_whisker_color
        c.boxplot_jitter_width = self.spin_bp_jitter_w.value()
        c.boxplot_jitter_alpha = self.spin_bp_jitter_alpha.value()
        c.boxplot_jitter_size = self.spin_bp_jitter_size.value()
        c.boxplot_violin_alpha = self.spin_bp_violin_alpha.value()
        c.boxplot_show_individual = self.chk_bp_show_individual.isChecked()
        c.boxplot_point_color = self._bp_point_color
        c.boxplot_violin_width_ratio = self.spin_bp_violin_w_ratio.value()
        c.boxplot_whisker_width = self.spin_bp_whisker_w.value()
        c.boxplot_outlier_size = self.spin_bp_outlier_size.value()
        c.boxplot_mean_marker = MARKER_MAP.get(self.cb_bp_mean_marker.currentText(), "D")
        c.boxplot_mean_color = self._bp_mean_color
        c.boxplot_mean_size = self.spin_bp_mean_size.value()
        c.boxplot_edge_color = self._bp_edge_color
        c.boxplot_edge_width = self.spin_bp_edge_w.value()
        c.boxplot_hatch = self.cb_bp_hatch.currentText() if self.cb_bp_hatch.currentText() != "无" else None
        c.boxplot_orientation = self.cb_bp_orientation.currentText()
        c.boxplot_category_gap = self.spin_bp_category_gap.value()
        c.boxplot_show_workspace_indicator = self.chk_bp_ws_indicator.isChecked()
        c.boxplot_workspace_indicator_size = self.spin_bp_ws_size.value()
        c.boxplot_show_legend = self.chk_bp_show_legend.isChecked()
        c.boxplot_legend_position = self.cb_bp_legend_pos.currentText()

        c.heatmap_normalize = self.cb_heatmap_normalize.currentText()
        c.heatmap_vmin = self.spin_heatmap_vmin.value()
        c.heatmap_vmax = self.spin_heatmap_vmax.value()
        c.heatmap_cell_border = self.chk_heatmap_border.isChecked()
        c.heatmap_cell_border_color = self._heatmap_border_color
        c.heatmap_colorbar = self.chk_hm_colorbar.isChecked()
        c.heatmap_colorbar_label = self.le_hm_cb_label.text()
        c.heatmap_interpolation = self.cb_hm_interp.currentText()
        c.heatmap_nan_color = self._hm_nan_color
        c.heatmap_sort_rows = self.cb_hm_sort.currentText()
        c.heatmap_cell_border_width = self.spin_hm_border_w.value()
        c.heatmap_value_text_color = self.cb_hm_txt_color.currentText()
        c.heatmap_value_bg_alpha = self.spin_hm_txt_bg.value()
        c.heatmap_colorbar_position = self.cb_hm_cb_pos.currentText()
        c.heatmap_vcenter = self.spin_hm_vcenter.value()
        c.heatmap_colorbar_shrink = self.spin_hm_cb_shrink.value()
        c.heatmap_colorbar_pad = self.spin_hm_cb_pad.value()
        c.heatmap_colorbar_fontsize = self.spin_hm_cb_fs.value()
        c.heatmap_colorbar_ticks = self.spin_hm_cb_ticks.value()
        c.heatmap_value_font_weight = self.cb_hm_val_weight.currentText()
        c.heatmap_value_rotation = self.spin_hm_val_rot.value()
        c.heatmap_x_label = self.le_hm_x_label.text()
        c.heatmap_y_label = self.le_hm_y_label.text()
        c.heatmap_show_x_label = self.chk_hm_show_x.isChecked()
        c.heatmap_show_y_label = self.chk_hm_show_y.isChecked()
        c.heatmap_colorbar_label_size = self.spin_hm_cb_label_size.value()

        c.radar_grid_shape = self.cb_radar_grid_shape.currentText()
        c.radar_grid_rings = self.spin_radar_grid_rings.value()
        c.radar_marker_style = MARKER_MAP.get(self.cb_radar_marker_style.currentText(), "o")
        c.radar_start_angle = self.spin_radar_start_angle.value()
        c.radar_show_values = self.chk_radar_show_values.isChecked()
        c.radar_fill_color = self._radar_fill_color
        c.radar_show_rings_labels = self.chk_radar_rings_labels.isChecked()
        c.radar_clockwise = self.chk_radar_clockwise.isChecked()
        c.radar_spoke_label_size = self.spin_radar_spoke_size.value()
        c.radar_line_style = LINE_STYLE_MAP.get(self.cb_radar_line_style.currentText(), "-")
        c.radar_value_font_size = self.spin_radar_val_fs.value()
        c.radar_scale_max = self.spin_radar_scale_max.value()
        c.radar_value_format = self.cb_radar_val_fmt.currentText()
        c.radar_grid_color = self._radar_grid_color
        c.radar_grid_width = self.spin_radar_grid_width.value()
        c.radar_grid_alpha = self.spin_radar_grid_alpha.value()
        c.radar_grid_style = LINE_STYLE_MAP.get(self.cb_radar_grid_style.currentText(), "--")
        c.radar_legend_position = self.cb_radar_legend_pos.currentText()
        c.radar_legend_size = self.spin_radar_legend_size.value()
        c.radar_scale_padding = self.spin_radar_scale_pad.value()
        c.radar_spoke_label_distance = self.spin_radar_spoke_dist.value()
        c.radar_fill_edge_width = self.spin_radar_fill_edge_w.value()
        c.radar_fill_edge_color = self._radar_fill_edge_color
        c.radar_legend_outside = self.chk_radar_legend_outside.isChecked()
        c.radar_title = self.le_radar_title.text()
        c.radar_show_title = self.chk_radar_show_title.isChecked()
        c.radar_title_size = self.spin_radar_title_size.value()
        c.radar_show_spoke_labels = self.chk_radar_show_spokes.isChecked()
        c.radar_ring_label_format = self.cb_radar_ring_fmt.currentText()

        c.pie_mode = self.cb_pie_mode.currentText()
        c.pie_inner_radius = self.spin_pie_inner_radius.value()
        c.pie_start_angle = self.spin_pie_start_angle.value()
        c.pie_label_position = self.cb_pie_label_pos.currentText()
        c.pie_label_format = self.cb_pie_label_fmt.currentText()
        c.pie_min_slice = self.spin_pie_min_slice.value()
        c.pie_explode_largest = self.chk_pie_explode.isChecked()
        c.pie_edge_color = self._pie_edge_color
        c.pie_center_label = self.le_pie_center.text()
        c.pie_explode_offset = self.spin_pie_explode_offset.value()
        c.pie_gap = self.spin_pie_gap.value()
        c.pie_shadow = self.chk_pie_shadow.isChecked()
        c.pie_sort = self.cb_pie_sort.currentText()
        c.pie_label_size = self.spin_pie_label_size.value()
        c.pie_center_label_size = self.spin_pie_center_fs.value()
        c.pie_show_percentage_symbol = self.chk_pie_pct_symbol.isChecked()
        c.pie_pct_precision = self.spin_pie_pct_precision.value()
        c.pie_legend_position = self.cb_pie_legend_pos.currentText()
        c.pie_label_distance = self.spin_pie_label_dist.value()
        c.pie_pct_distance = self.spin_pie_pct_dist.value()
        c.pie_edge_width = self.spin_pie_edge_width.value()
        c.pie_counterclockwise = self.chk_pie_counterclockwise.isChecked()
        c.pie_pct_color = self.cb_pie_pct_color.currentText()
        c.pie_center_label_color = self._pie_center_label_color
        c.pie_show_leader_lines = self.chk_pie_leader_lines.isChecked()
        c.pie_legend_outside = self.chk_pie_legend_outside.isChecked()
        c.pie_title = self.le_pie_title.text()
        c.pie_show_title = self.chk_pie_show_title.isChecked()
        c.pie_title_size = self.spin_pie_title_size.value()
        c.pie_title_weight = self.cb_pie_title_weight.currentText()
        c.pie_show_workspace_indicator = self.chk_pie_ws_indicator.isChecked()
        c.pie_workspace_indicator_size = self.spin_pie_ws_size.value()

        self.apply_styles()

    def sync_ui_from_config(self):
        c = self.config
        c._normalize()
        self.cb_plot_type.setCurrentText(c.plot_type)
        self.cb_group_logic.setCurrentText(c.group_logic)
        self.spin_filter.setValue(c.filter_threshold)
        self.spin_top_n.setValue(c.show_top_n)
        self.le_title.setText(c.fig_title)

        self.le_xlabel.setText(c.x_label)
        self.le_ylabel.setText(c.y_label)
        self.chk_show_xlabel.setChecked(getattr(c, 'show_x_label', True))
        self.chk_show_ylabel.setChecked(getattr(c, 'show_y_label', True))
        self.cb_x_scale.setCurrentText(c.x_scale)
        self.cb_y_scale.setCurrentText(c.y_scale)
        self.cb_tick_dir.setCurrentText(c.tick_direction)
        self.spin_rot.setValue(c.x_tick_rotation)
        self.chk_symmetric.setChecked(c.y_symmetric)
        self.chk_spines.setChecked(c.show_top_right_spines)
        self.spin_y_min.setValue(c.y_min)
        self.spin_y_max.setValue(c.y_max)
        self.spin_y_step.setValue(c.y_step)
        self.cb_tick_fmt.setCurrentText(c.tick_format)
        self.spin_tick_dec.setValue(c.tick_decimals)
        self.chk_sci_notation.setChecked(c.scientific_notation)
        self.spin_minor_ticks.setValue(c.minor_ticks_count)
        self.chk_axis_break.setChecked(getattr(c, 'axis_break', False))
        self.spin_break_low.setValue(getattr(c, 'axis_break_range_low', -0.5))
        self.spin_break_high.setValue(getattr(c, 'axis_break_range_high', 0.5))
        self.cb_panel_layout.setCurrentText(getattr(c, 'panel_layout', '单面板'))
        self.cb_panel_views.setCurrentText(getattr(c, 'panel_views', '相同'))
        self.spin_fig_margin_left.setValue(getattr(c, 'figure_margin_left', 0.0))
        self.spin_fig_margin_right.setValue(getattr(c, 'figure_margin_right', 0.0))
        self.spin_fig_margin_top.setValue(getattr(c, 'figure_margin_top', 0.0))
        self.spin_fig_margin_bottom.setValue(getattr(c, 'figure_margin_bottom', 0.0))
        self.spin_axes_pad.setValue(getattr(c, 'axes_label_pad', 4.0))
        self.cb_title_position.setCurrentText(getattr(c, 'title_position', '顶部居中'))
        self.spin_title_pad.setValue(getattr(c, 'title_pad', 12.0))
        self.spin_major_tick_length.setValue(getattr(c, 'major_tick_length', 3.5))
        self.spin_minor_tick_length.setValue(getattr(c, 'minor_tick_length', 2.0))
        self.spin_tick_width.setValue(getattr(c, 'tick_width', 0.8))
        self.cb_tick_sides.setCurrentText(getattr(c, 'tick_sides', '默认'))
        self.spin_spine_width.setValue(c.spine_width)
        self._spine_color = c.spine_color
        self.btn_spine_color.setStyleSheet(
            f"background: {c.spine_color}; color: white; border: 1px solid #999;"
        )

        self.chk_y_maj.setChecked(c.show_y_major_grid)
        self.chk_y_min.setChecked(c.show_y_minor_grid)
        self.chk_x_maj.setChecked(c.show_x_major_grid)
        self.cb_grid_style.setCurrentText(c.grid_style)
        self._grid_color = c.grid_color
        self.btn_grid_color.setStyleSheet(
            f"background: {c.grid_color}; color: #333; border: 1px solid #999;"
        )
        self.btn_grid_color.setText(f"  {c.grid_color}")
        self.spin_grid_width.setValue(c.grid_width)
        self.spin_grid_alpha.setValue(c.grid_alpha)
        self.chk_zero.setChecked(c.show_zero_line)
        self._zero_line_color = getattr(c, 'zero_line_color', 'black')
        _zlc = self._zero_line_color
        _zlc_text = "#333" if _zlc.lower() in ("#ffffff", "white") else "white"
        self.btn_zero_line_color.setStyleSheet(
            f"background: {_zlc}; color: {_zlc_text}; border: 1px solid #999;")
        self.chk_ref05.setChecked(c.show_ref_05)
        self.chk_ref10.setChecked(c.show_ref_10)
        self.chk_span.setChecked(c.show_highlight_span)

        self.cb_theme.setCurrentText(c.theme)
        self.cb_hatch.setCurrentText(c.hatch_style if c.hatch_style else "无")
        self.spin_bw.setValue(c.bar_width)
        self.cb_edge.setCurrentText(c.edge_color)
        # Reverse-lookup line_style / marker_style
        for name, val in LINE_STYLE_MAP.items():
            if val == c.line_style:
                self.cb_line_style.setCurrentText(name)
                break
        self.spin_line_width.setValue(c.line_width)
        for name, val in MARKER_MAP.items():
            if val == c.marker_style:
                self.cb_marker.setCurrentText(name)
                break
        self.spin_marker_size.setValue(c.marker_size)
        self.cb_trend.setCurrentText(c.trend_line)
        self.spin_trend_degree.setValue(c.trend_line_degree)

        self.cb_leg_pos.setCurrentText(c.legend_position)
        self.chk_leg_frame.setChecked(c.legend_frame)
        self.cb_leg_font.setCurrentText(c.legend_font)
        self.spin_leg_size.setValue(c.legend_size)
        self.le_custom_leg.setText(c.custom_legend)
        self.cb_leg_external_anchor.setCurrentText(getattr(c, 'legend_external_anchor', '右侧中'))
        self.spin_legend_columns.setValue(getattr(c, 'legend_columns', 1))
        self.spin_legend_alpha.setValue(getattr(c, 'legend_alpha', 1.0))
        self.le_legend_title.setText(getattr(c, 'legend_title', ''))
        self.spin_legend_handle_length.setValue(getattr(c, 'legend_handle_length', 2.0))
        self.spin_legend_border_pad.setValue(getattr(c, 'legend_border_pad', 0.4))

        self.cb_labels.setCurrentText(c.show_data_labels)
        self.spin_lbl_thresh.setValue(c.label_threshold)
        self.cb_font.setCurrentText(c.font_family)
        self.spin_fsize.setValue(c.font_size)
        self.cb_data_font.setCurrentText(c.data_label_font)
        self.spin_data_size.setValue(c.data_label_size)
        self.spin_data_offset.setValue(c.data_label_offset)
        self.spin_data_rot.setValue(c.data_label_rotation)
        self.cb_data_label_format.setCurrentText(getattr(c, 'data_label_format', '固定小数'))
        self.spin_data_label_decimals.setValue(getattr(c, 'data_label_decimals', 3))
        self.cb_data_label_pos_color.setCurrentText(getattr(c, 'data_label_positive_color', 'auto'))
        self.cb_data_label_neg_color.setCurrentText(getattr(c, 'data_label_negative_color', 'auto'))
        self.chk_data_label_avoid_overlap.setChecked(getattr(c, 'data_label_avoid_overlap', False))
        self.chk_bold_data.setChecked(c.bold_data)
        self.cb_ax_font.setCurrentText(c.axis_label_font)
        self.spin_ax_size.setValue(c.axis_label_size)
        self.cb_tick_font.setCurrentText(c.tick_label_font)
        self.spin_tick_size.setValue(c.tick_label_size)
        self.chk_bold_ax.setChecked(c.bold_ax_lbl)
        self.chk_bold_ticks.setChecked(c.bold_ticks)

        self.chk_err_bars.setChecked(c.show_error_bars)
        self.cb_err_type.setCurrentText(c.error_bar_type)
        self.le_annot.setText(c.annotation_text)
        self.spin_annot_x.setValue(c.annotation_pos_x)
        self.spin_annot_y.setValue(c.annotation_pos_y)
        self.chk_latex.setChecked(c.latex_rendering)
        self.chk_realtime.setChecked(c.realtime_preview)
        self.cb_journal.setCurrentText(c.journal_preset)

        self.cb_dpi.setCurrentText(str(c.export_dpi))
        self.spin_width.setValue(c.export_width)
        self.spin_height.setValue(c.export_height)
        self.chk_transparent.setChecked(c.export_transparent)

        # Chart-type-specific settings
        self._waterfall_pos_color = getattr(c, 'waterfall_pos_color', '#2ecc71')
        self.btn_waterfall_pos_color.setStyleSheet(f"background: {self._waterfall_pos_color}; color: white; border: 1px solid #999;")
        self.btn_waterfall_pos_color.setText(f"  {self._waterfall_pos_color}")
        self._waterfall_neg_color = getattr(c, 'waterfall_neg_color', '#e74c3c')
        self.btn_waterfall_neg_color.setStyleSheet(f"background: {self._waterfall_neg_color}; color: white; border: 1px solid #999;")
        self.btn_waterfall_neg_color.setText(f"  {self._waterfall_neg_color}")
        self.chk_waterfall_connectors.setChecked(getattr(c, 'waterfall_connectors', True))
        self.spin_waterfall_atom_id.setValue(getattr(c, 'waterfall_atom_id', 0))

        self._boxplot_color = getattr(c, 'boxplot_color', '#3498db')
        self.btn_boxplot_color.setStyleSheet(f"background: {self._boxplot_color}; color: white; border: 1px solid #999;")
        self.btn_boxplot_color.setText(f"  {self._boxplot_color}")
        self.chk_boxplot_show_mean.setChecked(getattr(c, 'boxplot_show_mean', True))
        self.spin_boxplot_alpha.setValue(getattr(c, 'boxplot_alpha', 0.6))
        self.spin_boxplot_max_atoms.setValue(getattr(c, 'boxplot_max_atoms', 20))

        idx = self.cb_heatmap_colormap.findText(getattr(c, 'heatmap_colormap', 'RdBu_r'))
        if idx >= 0:
            self.cb_heatmap_colormap.setCurrentIndex(idx)
        self.chk_heatmap_show_values.setChecked(getattr(c, 'heatmap_show_values', False))
        idx = self.cb_heatmap_value_format.findText(getattr(c, 'heatmap_value_format', '.2f'))
        if idx >= 0:
            self.cb_heatmap_value_format.setCurrentIndex(idx)
        self.spin_heatmap_value_size.setValue(getattr(c, 'heatmap_value_size', 8))
        idx = self.cb_heatmap_aspect.findText(getattr(c, 'heatmap_aspect', '自动'))
        if idx >= 0:
            self.cb_heatmap_aspect.setCurrentIndex(idx)

        self._radar_line_color = getattr(c, 'radar_line_color', '#1f77b4')
        self.btn_radar_line_color.setStyleSheet(f"background: {self._radar_line_color}; color: white; border: 1px solid #999;")
        self.btn_radar_line_color.setText(f"  {self._radar_line_color}")
        self.spin_radar_line_width.setValue(getattr(c, 'radar_line_width', 2.0))
        self.spin_radar_fill_alpha.setValue(getattr(c, 'radar_fill_alpha', 0.25))
        self.spin_radar_marker_size.setValue(getattr(c, 'radar_marker_size', 6.0))
        self.spin_radar_max_atoms.setValue(getattr(c, 'radar_max_atoms', 12))

        self.spin_area_alpha.setValue(getattr(c, 'area_alpha', 0.3))

        # Area
        self.cb_area_mode.setCurrentText(getattr(c, 'area_mode', '堆叠'))
        self.cb_area_interpolation.setCurrentText(getattr(c, 'area_interpolation', '线性'))
        self.chk_area_edge.setChecked(getattr(c, 'area_edge_line', True))
        self.spin_area_edge_width.setValue(getattr(c, 'area_edge_width', 1.0))
        # Reverse-lookup area edge style
        for name, val in LINE_STYLE_MAP.items():
            if val == getattr(c, 'area_edge_style', '-') and name != "无":
                self.cb_area_edge_style.setCurrentText(name)
                break
        self.cb_area_order.setCurrentText(getattr(c, 'area_order', '默认'))
        self.chk_area_gradient.setChecked(getattr(c, 'area_gradient', False))
        self.chk_area_negative.setChecked(getattr(c, 'area_negative', True))

        # Waterfall
        self.spin_waterfall_bar_width.setValue(getattr(c, 'waterfall_bar_width', 0.6))
        self._waterfall_edge_color = getattr(c, 'waterfall_edge_color', 'black')
        self.btn_waterfall_edge_color.setStyleSheet(f"background: {self._waterfall_edge_color}; color: white; border: 1px solid #999;")
        self.btn_waterfall_edge_color.setText(f"  {self._waterfall_edge_color}")
        self.spin_waterfall_edge_width.setValue(getattr(c, 'waterfall_edge_width', 0.5))
        self.cb_waterfall_sort.setCurrentText(getattr(c, 'waterfall_sort', '默认'))
        self.chk_waterfall_total.setChecked(getattr(c, 'waterfall_show_total', True))
        for name, val in LINE_STYLE_MAP.items():
            if val == getattr(c, 'waterfall_connector_style', '-'):
                self.cb_wf_conn_style.setCurrentText(name)
                break
        self._wf_conn_color = getattr(c, 'waterfall_connector_color', 'black')
        self.btn_wf_conn_color.setStyleSheet(f"background: {self._wf_conn_color}; color: white; border: 1px solid #999;")
        self.btn_wf_conn_color.setText(f"  {self._wf_conn_color}")
        self.spin_wf_conn_width.setValue(getattr(c, 'waterfall_connector_width', 0.5))
        self.spin_wf_conn_alpha.setValue(getattr(c, 'waterfall_connector_alpha', 0.3))
        self.chk_wf_labels.setChecked(getattr(c, 'waterfall_show_labels', False))
        self._wf_total_color = getattr(c, 'waterfall_total_color', '#3498db')
        self.btn_wf_total_color.setStyleSheet(f"background: {self._wf_total_color}; color: white; border: 1px solid #999;")
        self.btn_wf_total_color.setText(f"  {self._wf_total_color}")
        self._wf_zero_line_color = getattr(c, 'waterfall_zero_line_color', 'black')
        _zc = self._wf_zero_line_color
        self.btn_wf_zero_color.setStyleSheet(f"background: {_zc}; color: white; border: 1px solid #999;")
        self.btn_wf_zero_color.setText(f"  {_zc}")
        self.spin_wf_zero_width.setValue(getattr(c, 'waterfall_zero_line_width', 1.0))
        self.cb_wf_label_fmt.setCurrentText(getattr(c, 'waterfall_label_format', '.2f'))
        self.cb_wf_label_font.setCurrentText(getattr(c, 'waterfall_label_font', 'Arial'))
        self.cb_wf_label_weight.setCurrentText(getattr(c, 'waterfall_label_weight', 'normal'))
        self.cb_wf_hatch.setCurrentText(getattr(c, 'waterfall_hatch', None) or "无")
        self.spin_wf_bar_round.setValue(getattr(c, 'waterfall_bar_round', 0.0))
        self.chk_wf_cumulative.setChecked(getattr(c, 'waterfall_cumulative_line', False))
        self._wf_cum_color = getattr(c, 'waterfall_cumulative_color', 'black')
        self.btn_wf_cum_color.setStyleSheet(f"background: {self._wf_cum_color}; color: white; border: 1px solid #999;")
        self.btn_wf_cum_color.setText(f"  {self._wf_cum_color}")
        self.spin_wf_cum_width.setValue(getattr(c, 'waterfall_cumulative_width', 1.5))
        self.chk_wf_pct_mode.setChecked(getattr(c, 'waterfall_pct_mode', False))

        # Box Plot
        self.spin_boxplot_whisker.setValue(getattr(c, 'boxplot_whisker', 1.5))
        self.chk_boxplot_notch.setChecked(getattr(c, 'boxplot_notch', False))
        self._boxplot_median_color = getattr(c, 'boxplot_median_color', 'black')
        self.btn_boxplot_median_color.setStyleSheet(f"background: {self._boxplot_median_color}; color: white; border: 1px solid #999;")
        self.btn_boxplot_median_color.setText(f"  {self._boxplot_median_color}")
        self.spin_boxplot_median_width.setValue(getattr(c, 'boxplot_median_width', 2.0))
        for name, val in MARKER_MAP.items():
            if val == getattr(c, 'boxplot_outlier_marker', 'o'):
                self.cb_boxplot_outlier_marker.setCurrentText(name)
                break
        self._boxplot_outlier_color = getattr(c, 'boxplot_outlier_color', 'red')
        self.btn_boxplot_outlier_color.setStyleSheet(f"background: {self._boxplot_outlier_color}; color: white; border: 1px solid #999;")
        self.btn_boxplot_outlier_color.setText(f"  {self._boxplot_outlier_color}")
        self.chk_boxplot_outliers.setChecked(getattr(c, 'boxplot_show_outliers', True))
        self.cb_bp_points.setCurrentText(getattr(c, 'boxplot_show_points', '无'))
        self.chk_bp_violin.setChecked(getattr(c, 'boxplot_violin', False))
        self.spin_bp_cap_width.setValue(getattr(c, 'boxplot_cap_width', 0.5))
        self.chk_bp_caps.setChecked(getattr(c, 'boxplot_show_caps', True))
        self.spin_bp_width.setValue(getattr(c, 'boxplot_width', 0.5))
        self._bp_whisker_color = getattr(c, 'boxplot_whisker_color', 'black')
        self.btn_bp_whisker_color.setStyleSheet(f"background: {self._bp_whisker_color}; color: white; border: 1px solid #999;")
        self.btn_bp_whisker_color.setText(f"  {self._bp_whisker_color}")
        self.spin_bp_jitter_w.setValue(getattr(c, 'boxplot_jitter_width', 0.2))
        self.spin_bp_jitter_alpha.setValue(getattr(c, 'boxplot_jitter_alpha', 0.6))
        self.spin_bp_jitter_size.setValue(getattr(c, 'boxplot_jitter_size', 3.0))
        self.spin_bp_violin_alpha.setValue(getattr(c, 'boxplot_violin_alpha', 0.2))
        self.chk_bp_show_individual.setChecked(getattr(c, 'boxplot_show_individual', True))
        self._bp_point_color = getattr(c, 'boxplot_point_color', 'black')
        self.btn_bp_point_color.setStyleSheet(f"background: {self._bp_point_color}; color: white; border: 1px solid #999;")
        self.btn_bp_point_color.setText(f"  {self._bp_point_color}")
        self.spin_bp_violin_w_ratio.setValue(getattr(c, 'boxplot_violin_width_ratio', 0.8))
        self.spin_bp_whisker_w.setValue(getattr(c, 'boxplot_whisker_width', 1.0))
        self.spin_bp_outlier_size.setValue(getattr(c, 'boxplot_outlier_size', 6.0))
        for name, val in MARKER_MAP.items():
            if val == getattr(c, 'boxplot_mean_marker', 'D'):
                self.cb_bp_mean_marker.setCurrentText(name)
                break
        self._bp_mean_color = getattr(c, 'boxplot_mean_color', 'red')
        self.btn_bp_mean_color.setStyleSheet(f"background: {self._bp_mean_color}; color: white; border: 1px solid #999;")
        self.btn_bp_mean_color.setText(f"  {self._bp_mean_color}")
        self.spin_bp_mean_size.setValue(getattr(c, 'boxplot_mean_size', 5.0))
        self._bp_edge_color = getattr(c, 'boxplot_edge_color', 'black')
        self.btn_bp_edge_color.setStyleSheet(f"background: {self._bp_edge_color}; color: white; border: 1px solid #999;")
        self.btn_bp_edge_color.setText(f"  {self._bp_edge_color}")
        self.spin_bp_edge_w.setValue(getattr(c, 'boxplot_edge_width', 1.0))
        self.cb_bp_hatch.setCurrentText(getattr(c, 'boxplot_hatch', None) or "无")
        self.cb_bp_orientation.setCurrentText(getattr(c, 'boxplot_orientation', '垂直'))
        self.spin_bp_category_gap.setValue(getattr(c, 'boxplot_category_gap', 1.0))
        self.chk_bp_ws_indicator.setChecked(getattr(c, 'boxplot_show_workspace_indicator', True))
        self.spin_bp_ws_size.setValue(getattr(c, 'boxplot_workspace_indicator_size', 9))
        self.chk_bp_show_legend.setChecked(getattr(c, 'boxplot_show_legend', True))
        self.cb_bp_legend_pos.setCurrentText(getattr(c, 'boxplot_legend_position', '最佳'))

        # Heatmap
        self.cb_heatmap_normalize.setCurrentText(getattr(c, 'heatmap_normalize', '自动'))
        self.spin_heatmap_vmin.setValue(getattr(c, 'heatmap_vmin', 0.0))
        self.spin_heatmap_vmax.setValue(getattr(c, 'heatmap_vmax', 0.0))
        self.chk_heatmap_border.setChecked(getattr(c, 'heatmap_cell_border', False))
        self._heatmap_border_color = getattr(c, 'heatmap_cell_border_color', 'white')
        self.btn_heatmap_border_color.setStyleSheet(f"background: {self._heatmap_border_color}; color: {'#333' if self._heatmap_border_color in ('white', '#FFFFFF', '#ffffff') else 'white'}; border: 1px solid #999;")
        self.btn_heatmap_border_color.setText(f"  {self._heatmap_border_color}")
        self.chk_hm_colorbar.setChecked(getattr(c, 'heatmap_colorbar', True))
        self.le_hm_cb_label.setText(getattr(c, 'heatmap_colorbar_label', 'Bader 电荷'))
        self.cb_hm_interp.setCurrentText(getattr(c, 'heatmap_interpolation', '最近邻'))
        self._hm_nan_color = getattr(c, 'heatmap_nan_color', '#E0E0E0')
        self.btn_hm_nan_color.setStyleSheet(f"background: {self._hm_nan_color}; color: #333; border: 1px solid #999;")
        self.btn_hm_nan_color.setText(f"  {self._hm_nan_color}")
        self.cb_hm_sort.setCurrentText(getattr(c, 'heatmap_sort_rows', '默认'))
        self.spin_hm_border_w.setValue(getattr(c, 'heatmap_cell_border_width', 0.5))
        self.cb_hm_txt_color.setCurrentText(getattr(c, 'heatmap_value_text_color', 'auto'))
        self.spin_hm_txt_bg.setValue(getattr(c, 'heatmap_value_bg_alpha', 0.0))
        self.cb_hm_cb_pos.setCurrentText(getattr(c, 'heatmap_colorbar_position', '右侧'))
        self.spin_hm_vcenter.setValue(getattr(c, 'heatmap_vcenter', 0.0))
        self.spin_hm_cb_shrink.setValue(getattr(c, 'heatmap_colorbar_shrink', 1.0))
        self.spin_hm_cb_pad.setValue(getattr(c, 'heatmap_colorbar_pad', 0.05))
        self.spin_hm_cb_fs.setValue(getattr(c, 'heatmap_colorbar_fontsize', 10))
        self.spin_hm_cb_ticks.setValue(getattr(c, 'heatmap_colorbar_ticks', 0))
        self.cb_hm_val_weight.setCurrentText(getattr(c, 'heatmap_value_font_weight', 'normal'))
        self.spin_hm_val_rot.setValue(getattr(c, 'heatmap_value_rotation', 0))
        self.le_hm_x_label.setText(getattr(c, 'heatmap_x_label', '工作区'))
        self.le_hm_y_label.setText(getattr(c, 'heatmap_y_label', '原子'))
        self.chk_hm_show_x.setChecked(getattr(c, 'heatmap_show_x_label', True))
        self.chk_hm_show_y.setChecked(getattr(c, 'heatmap_show_y_label', True))
        self.spin_hm_cb_label_size.setValue(getattr(c, 'heatmap_colorbar_label_size', 10))

        # Radar
        self.cb_radar_grid_shape.setCurrentText(getattr(c, 'radar_grid_shape', '多边形'))
        self.spin_radar_grid_rings.setValue(getattr(c, 'radar_grid_rings', 4))
        for name, val in MARKER_MAP.items():
            if val == getattr(c, 'radar_marker_style', 'o'):
                self.cb_radar_marker_style.setCurrentText(name)
                break
        self.spin_radar_start_angle.setValue(getattr(c, 'radar_start_angle', 90))
        self.chk_radar_show_values.setChecked(getattr(c, 'radar_show_values', False))
        self._radar_fill_color = getattr(c, 'radar_fill_color', '')
        if self._radar_fill_color:
            self.btn_radar_fill_color.setStyleSheet(f"background: {self._radar_fill_color}; color: white; border: 1px solid #999;")
            self.btn_radar_fill_color.setText(f"  {self._radar_fill_color}")
        self.chk_radar_rings_labels.setChecked(getattr(c, 'radar_show_rings_labels', True))
        self.chk_radar_clockwise.setChecked(getattr(c, 'radar_clockwise', False))
        self.spin_radar_spoke_size.setValue(getattr(c, 'radar_spoke_label_size', 10))
        for name, val in LINE_STYLE_MAP.items():
            if val == getattr(c, 'radar_line_style', '-'):
                self.cb_radar_line_style.setCurrentText(name)
                break
        self.spin_radar_val_fs.setValue(getattr(c, 'radar_value_font_size', 8))
        self.spin_radar_scale_max.setValue(getattr(c, 'radar_scale_max', 0.0))
        self.cb_radar_val_fmt.setCurrentText(getattr(c, 'radar_value_format', '.2f'))
        self._radar_grid_color = getattr(c, 'radar_grid_color', 'gray')
        self.btn_radar_grid_color.setStyleSheet(f"background: {self._radar_grid_color}; color: white; border: 1px solid #999;")
        self.btn_radar_grid_color.setText(f"  {self._radar_grid_color}")
        self.spin_radar_grid_width.setValue(getattr(c, 'radar_grid_width', 0.5))
        self.spin_radar_grid_alpha.setValue(getattr(c, 'radar_grid_alpha', 0.4))
        for name, val in LINE_STYLE_MAP.items():
            if val == getattr(c, 'radar_grid_style', '--'):
                self.cb_radar_grid_style.setCurrentText(name)
                break
        self.cb_radar_legend_pos.setCurrentText(getattr(c, 'radar_legend_position', '最佳'))
        self.spin_radar_legend_size.setValue(getattr(c, 'radar_legend_size', 8))
        self.chk_radar_legend_outside.setChecked(getattr(c, 'radar_legend_outside', True))
        self.spin_radar_scale_pad.setValue(getattr(c, 'radar_scale_padding', 1.2))
        self.spin_radar_spoke_dist.setValue(getattr(c, 'radar_spoke_label_distance', 1.15))
        self.spin_radar_fill_edge_w.setValue(getattr(c, 'radar_fill_edge_width', 0.0))
        self._radar_fill_edge_color = getattr(c, 'radar_fill_edge_color', '')
        if self._radar_fill_edge_color:
            self.btn_radar_fill_edge_color.setStyleSheet(f"background: {self._radar_fill_edge_color}; color: white; border: 1px solid #999;")
            self.btn_radar_fill_edge_color.setText(f"  {self._radar_fill_edge_color}")
        self.le_radar_title.setText(getattr(c, 'radar_title', '电荷分布'))
        self.chk_radar_show_title.setChecked(getattr(c, 'radar_show_title', True))
        self.spin_radar_title_size.setValue(getattr(c, 'radar_title_size', 14))
        self.chk_radar_show_spokes.setChecked(getattr(c, 'radar_show_spoke_labels', True))
        self.cb_radar_ring_fmt.setCurrentText(getattr(c, 'radar_ring_label_format', '.2f'))

        # Pie
        self.cb_pie_mode.setCurrentText(getattr(c, 'pie_mode', '饼图'))
        self.spin_pie_inner_radius.setValue(getattr(c, 'pie_inner_radius', 0.0))
        self.spin_pie_start_angle.setValue(getattr(c, 'pie_start_angle', 90))
        self.cb_pie_label_pos.setCurrentText(getattr(c, 'pie_label_position', '外部'))
        self.cb_pie_label_fmt.setCurrentText(getattr(c, 'pie_label_format', '百分比'))
        self.spin_pie_min_slice.setValue(getattr(c, 'pie_min_slice', 2.0))
        self.chk_pie_explode.setChecked(getattr(c, 'pie_explode_largest', False))
        self._pie_edge_color = getattr(c, 'pie_edge_color', 'white')
        self.btn_pie_edge_color.setStyleSheet(f"background: {self._pie_edge_color}; color: {'#333' if self._pie_edge_color in ('white', '#FFFFFF', '#ffffff') else 'white'}; border: 1px solid #999;")
        self.btn_pie_edge_color.setText(f"  {self._pie_edge_color}")
        self.le_pie_center.setText(getattr(c, 'pie_center_label', ''))
        self.spin_pie_explode_offset.setValue(getattr(c, 'pie_explode_offset', 0.1))
        self.spin_pie_gap.setValue(getattr(c, 'pie_gap', 0.0))
        self.chk_pie_shadow.setChecked(getattr(c, 'pie_shadow', False))
        self.cb_pie_sort.setCurrentText(getattr(c, 'pie_sort', '默认'))
        self.spin_pie_label_size.setValue(getattr(c, 'pie_label_size', 10))
        self.spin_pie_center_fs.setValue(getattr(c, 'pie_center_label_size', 14))
        self.chk_pie_pct_symbol.setChecked(getattr(c, 'pie_show_percentage_symbol', True))
        self.spin_pie_pct_precision.setValue(getattr(c, 'pie_pct_precision', 1))
        self.cb_pie_legend_pos.setCurrentText(getattr(c, 'pie_legend_position', '最佳'))
        self.chk_pie_leader_lines.setChecked(getattr(c, 'pie_show_leader_lines', False))
        self.chk_pie_legend_outside.setChecked(getattr(c, 'pie_legend_outside', True))
        self.spin_pie_label_dist.setValue(getattr(c, 'pie_label_distance', 1.1))
        self.spin_pie_pct_dist.setValue(getattr(c, 'pie_pct_distance', 0.6))
        self.spin_pie_edge_width.setValue(getattr(c, 'pie_edge_width', 1.0))
        self.chk_pie_counterclockwise.setChecked(getattr(c, 'pie_counterclockwise', True))
        self.cb_pie_pct_color.setCurrentText(getattr(c, 'pie_pct_color', 'auto'))
        self._pie_center_label_color = getattr(c, 'pie_center_label_color', 'black')
        self.btn_pie_center_lbl_color.setStyleSheet(f"background: {self._pie_center_label_color}; color: white; border: 1px solid #999;")
        self.btn_pie_center_lbl_color.setText(f"  {self._pie_center_label_color}")
        self.le_pie_title.setText(getattr(c, 'pie_title', 'Bader 电荷分布'))
        self.chk_pie_show_title.setChecked(getattr(c, 'pie_show_title', True))
        self.spin_pie_title_size.setValue(getattr(c, 'pie_title_size', 14))
        self.cb_pie_title_weight.setCurrentText(getattr(c, 'pie_title_weight', 'bold'))
        self.chk_pie_ws_indicator.setChecked(getattr(c, 'pie_show_workspace_indicator', True))
        self.spin_pie_ws_size.setValue(getattr(c, 'pie_workspace_indicator_size', 9))

    # ==================================================================
    #  Data entry point
    # ==================================================================

    def plot_data(self, data_dict, target=None, fragments=None):
        if target is not None:
            self._target_expression = (target or "").strip()
        if fragments is not None:
            self._fragments_by_workspace = fragments or {}
        self._raw_data = dict(data_dict)
        self._set_prepared_plot_data()

    def set_analysis_context(self, target="", fragments=None):
        self._target_expression = (target or "").strip()
        self._fragments_by_workspace = fragments or {}
        if self._raw_data:
            self._rebuild_level_data()

    def _rebuild_level_data(self, *_args):
        if self._raw_data:
            self._set_prepared_plot_data()

    def _set_prepared_plot_data(self):
        level_map = {"原子": "atom", "片段": "fragment", "元素": "element"}
        level = level_map.get(self.cb_data_level.currentText(), "atom")
        metric = "mean" if self.cb_element_metric.currentText() == "平均值" else "sum"
        try:
            prepared = ChargeCalculator.prepare_plot_data(
                self._raw_data,
                level=level,
                metric=metric,
                fragments=self._fragments_by_workspace,
                target=self._target_expression,
            )
        except TargetSelectionError as exc:
            QMessageBox.warning(self, "绘图筛选错误", str(exc))
            prepared = {}
        self._original_data = dict(prepared)
        self.current_data = dict(prepared)
        # Update workspace selection list
        self._ws_all = list(prepared.keys())
        # Reset selection if previously selected workspaces no longer exist
        if self._ws_selected is not None:
            self._ws_selected = self._ws_selected & set(self._ws_all)
            if not self._ws_selected:
                self._ws_selected = None
        self._update_ws_button_text()
        self.apply_styles()

    def set_fragment_text(self, text):
        """Set fragment summation text (e.g. '72-74') to display fragment sums in chart."""
        self._fragment_text = text.strip() if text else ""

    @staticmethod
    def _cjk_font_list(user_font=None):
        """Return a font list with CJK fallbacks for per-glyph Chinese glyph support."""
        cjk = ['Microsoft YaHei', 'SimHei', 'SimSun']
        result = []
        if user_font and user_font not in cjk:
            result.append(user_font)
        result.extend(cjk)
        result.extend([f for f in ['Arial', 'DejaVu Sans'] if f not in result])
        return result

    # ==================================================================
    #  Canvas & workspace helpers
    # ==================================================================

    def _clear_canvas(self):
        """Clear the matplotlib canvas without affecting data or settings."""
        self.figure.clear()
        self.ax = self.figure.add_subplot(111)
        self._apply_dark_mode()
        self.canvas.draw_idle()

    def _pick_plot_workspaces(self):
        """Show a dialog to select which workspaces to include in the chart."""
        if not self._ws_all:
            return
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem
        from PySide6.QtWidgets import QDialogButtonBox, QLabel, QAbstractItemView
        from PySide6.QtCore import Qt

        dlg = QDialog(self)
        dlg.setWindowTitle("选择绘图体系")
        dlg.setMinimumWidth(350)
        dlg.setMinimumHeight(300)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("勾选要参与绘图的体系（未勾选的将从图表中排除）："))

        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.NoSelection)
        currently_selected = self._ws_selected if self._ws_selected is not None else set(self._ws_all)
        for ws in self._ws_all:
            item = QListWidgetItem(ws)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if ws in currently_selected else Qt.Unchecked)
            lst.addItem(item)
        lay.addWidget(lst)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # Add "Select All" / "Deselect All" buttons
        btn_all = btn_box.addButton("全选", QDialogButtonBox.ActionRole)
        btn_none = btn_box.addButton("全不选", QDialogButtonBox.ActionRole)
        btn_all.clicked.connect(lambda: [lst.item(i).setCheckState(Qt.Checked) for i in range(lst.count())])
        btn_none.clicked.connect(lambda: [lst.item(i).setCheckState(Qt.Unchecked) for i in range(lst.count())])
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        lay.addWidget(btn_box)

        if dlg.exec() == QDialog.Accepted:
            selected = set()
            for i in range(lst.count()):
                if lst.item(i).checkState() == Qt.Checked:
                    selected.add(lst.item(i).text())
            if not selected:
                self._ws_selected = None  # If nothing selected, treat as all
            elif len(selected) == len(self._ws_all):
                self._ws_selected = None  # All selected = no filter
            else:
                self._ws_selected = selected
            self._update_ws_button_text()
            # Auto re-render if we have data
            if self.current_data:
                self.apply_styles()

    def _update_ws_button_text(self):
        """Update the workspace selection button text."""
        if self._ws_selected is None or not self._ws_all:
            self.btn_ws_select.setText("全部")
        else:
            n = len(self._ws_selected)
            total = len(self._ws_all)
            self.btn_ws_select.setText(f"{n}/{total} 已选")

    def _on_chart_ws_changed(self, text):
        """Handle workspace selection change from canvas toolbar dropdown."""
        if text and text not in ("全部", "全部（多体系）"):
            self._chart_ws_single = text
        else:
            self._chart_ws_single = None
        cfg = self.config
        if cfg.plot_type in ("箱线图", "饼图"):
            self.apply_styles()

    def _update_chart_ws_dropdown(self):
        """Populate the chart workspace dropdown and manage its visibility."""
        cfg = self.config
        is_boxpie = cfg.plot_type in ("箱线图", "饼图")
        self._chart_ws_label.setVisible(is_boxpie)
        self._chart_ws_combo.setVisible(is_boxpie)
        if not is_boxpie:
            return
        # Populate with available workspaces
        self._chart_ws_combo.blockSignals(True)
        base_ws_list = list(self.current_data.keys()) if self.current_data else self._ws_all
        ws_list = list(base_ws_list)
        if cfg.plot_type == "箱线图" and len(base_ws_list) > 1:
            ws_list = ["全部（多体系）"] + ws_list
        self._chart_ws_combo.clear()
        self._chart_ws_combo.addItems(ws_list)
        # Restore previous selection if still valid
        prev = getattr(self, '_chart_ws_single', None)
        if prev and prev in ws_list:
            self._chart_ws_combo.setCurrentText(prev)
        elif ws_list:
            self._chart_ws_combo.setCurrentText(ws_list[0])
            self._chart_ws_single = None if ws_list[0] == "全部（多体系）" else ws_list[0]
        self._chart_ws_combo.blockSignals(False)

    # ==================================================================
    #  Export helpers
    # ==================================================================

    def export_high_res_image(self):
        self.update_config_and_plot()
        filters = "PNG (*.png);;SVG 矢量图 (*.svg);;PDF 文档 (*.pdf);;EPS 矢量图 (*.eps);;JPEG (*.jpg)"
        path, sel_filter = QFileDialog.getSaveFileName(self, "导出高分辨率图像", "plot.png", filters)
        if path:
            orig_w, orig_h = self.figure.get_size_inches()
            try:
                self.figure.set_size_inches(self.config.export_width, self.config.export_height)
                self.figure.savefig(path, dpi=self.config.export_dpi,
                                    bbox_inches='tight', transparent=self.config.export_transparent)
                QMessageBox.information(self, "成功", f"图像已成功导出至:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"导出图像失败:\n{e}")
            finally:
                self.figure.set_size_inches(orig_w, orig_h)
                self.figure.canvas.draw_idle()

    def export_to_clipboard(self):
        self.update_config_and_plot()
        orig_w, orig_h = self.figure.get_size_inches()
        try:
            import io
            buf = io.BytesIO()
            self.figure.set_size_inches(self.config.export_width, self.config.export_height)
            self.figure.savefig(buf, dpi=self.config.export_dpi, format='png',
                                bbox_inches='tight', transparent=self.config.export_transparent)
            buf.seek(0)
            from PySide6.QtGui import QImage, QPixmap
            img = QImage()
            img.loadFromData(buf.read())
            QApplication.clipboard().setPixmap(QPixmap.fromImage(img))
            QMessageBox.information(self, "成功", "图表已复制到剪贴板。")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"复制到剪贴板失败:\n{e}")
        finally:
            self.figure.set_size_inches(orig_w, orig_h)
            self.figure.canvas.draw_idle()

    def save_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存设置 (JSON)", "plot_settings.json", "JSON (*.json)")
        if path:
            self.update_config_and_plot()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, indent=4)
            QMessageBox.information(self, "成功", "模板已保存成功。")

    def load_template(self):
        path, _ = QFileDialog.getOpenFileName(self, "加载设置 (JSON)", "", "JSON (*.json)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.config.from_dict(data)
                self.sync_ui_from_config()
                self.apply_styles()
                QMessageBox.information(self, "成功", "模板已加载成功。")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"加载模板失败:\n{e}")

    # ==================================================================
    #  Dark mode
    # ==================================================================

    def _apply_dark_mode(self):
        bg = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
        fg = "#E0E0E0" if self._is_dark_mode else "black"
        self.figure.patch.set_facecolor(bg)
        for ax in self.figure.get_axes():
            ax.set_facecolor(bg)
            ax.tick_params(colors=fg, which='both')
            for spine in ax.spines.values():
                spine.set_color(fg)
            ax.xaxis.label.set_color(fg)
            ax.yaxis.label.set_color(fg)
            ax.title.set_color(fg)
        if hasattr(self, 'annot'):
            self.annot.get_bbox_patch().set_facecolor(bg)
            self.annot.get_bbox_patch().set_edgecolor(fg)
            self.annot.set_color(fg)

    # ==================================================================
    #  Hover tooltip
    # ==================================================================

    def on_hover(self, event):
        vis = self.annot.get_visible()
        if event.inaxes == self.ax:
            for patch in self.ax.patches:
                cont, ind = patch.contains(event)
                if cont:
                    if isinstance(patch, patches.Rectangle):
                        if self.config.plot_type == "水平柱状图":
                            val = patch.get_width()
                            self.annot.xy = (patch.get_x() + patch.get_width(),
                                             patch.get_y() + patch.get_height() / 2)
                        else:
                            val = patch.get_height()
                            self.annot.xy = (patch.get_x() + patch.get_width() / 2,
                                             patch.get_y() + patch.get_height())
                        self.annot.set_text(f"{val:.3f}")
                        self.annot.set_visible(True)
                        self.canvas.draw_idle()
                        return
        if vis:
            self.annot.set_visible(False)
            self.canvas.draw_idle()

    # ==================================================================
    #  Main rendering
    # ==================================================================

    def _restore_rc(self):
        """Restore plt.rcParams to pre-render state."""
        if hasattr(self, '_saved_rc'):
            for k, v in self._saved_rc.items():
                plt.rcParams[k] = v

    def _safe_draw_idle(self):
        """Render canvas, catching LaTeX subsystem errors gracefully."""
        try:
            self.figure.canvas.draw_idle()
        except Exception as e:
            self._restore_rc()
            plt.rcParams['text.usetex'] = False
            self.figure.canvas.draw_idle()
            QTimer.singleShot(100, lambda err=str(e): QMessageBox.warning(
                self, "渲染错误",
                f"无法渲染图表:\n{err}\n\n"
                "如果启用了 LaTeX，可能未正确安装。"))

    def apply_styles(self):
        # ── Clean-slate rendering ──
        # figure.clear() removes ALL axes from the figure (including stale
        # polar axes from Radar, colorbar axes from Heatmap, and subplot
        # axes from multi-panel layouts).  The old ax.clear() only wiped
        # one axes' content, leaving orphaned axes that accumulated across
        # redraws — the root cause of chart stacking.
        _do_clear = getattr(self, '_clear_figure', True)
        if _do_clear:
            self.figure.clear()
            self.ax = self.figure.add_subplot(111)
        # When _clear_figure is False (recursive call from multi-panel or
        # axis-break), the parent has already set self.ax to the correct
        # gridspec subplot.  Creating add_subplot(111) here would add a
        # full-figure axes that overlaps the gridspec — a subtle stacking bug.
        self._bar_to_atom_id = {}
        self._is_dark_mode = self.chk_dark_mode.isChecked()
        cfg = self.config

        # -- rcParams: save originals, apply locally, restore on exit --
        self._saved_rc = {
            'text.usetex': plt.rcParams.get('text.usetex', False),
            'font.sans-serif': list(plt.rcParams.get('font.sans-serif', [])),
            'font.family': plt.rcParams.get('font.family', 'sans-serif'),
            'font.size': plt.rcParams.get('font.size', 10),
            'axes.unicode_minus': plt.rcParams.get('axes.unicode_minus', True),
        }
        use_tex = getattr(cfg, 'latex_rendering', False)
        # ── LaTeX safety check: prevent UI freeze when TeX is not installed ──
        if use_tex:
            import shutil as _shutil
            if not _shutil.which('latex') or not _shutil.which('dvipng'):
                use_tex = False
                cfg.latex_rendering = False
                self.chk_latex.setChecked(False)
                self.chk_latex.setToolTip(
                    "未找到 LaTeX — 请先安装 MiKTeX 或 TeX Live")
                QTimer.singleShot(100, lambda: QMessageBox.warning(
                    self, "LaTeX 不可用",
                    "LaTeX 数学公式渲染需要 TeX 发行版\n"
                    "(MiKTeX 或 TeX Live) 和 dvipng。\n\n"
                    "请安装后重启应用程序。"))
        plt.rcParams['text.usetex'] = use_tex
        # CJK fonts first for Chinese glyph support, then user's preferred font
        _font_list = ['Microsoft YaHei', 'SimHei']
        if cfg.font_family not in _font_list:
            _font_list.append(cfg.font_family)
        _font_list.extend([f for f in ['Arial', 'DejaVu Sans'] if f not in _font_list])
        plt.rcParams['font.sans-serif'] = _font_list
        plt.rcParams['font.family'] = 'serif' if use_tex else 'sans-serif'
        plt.rcParams['font.size'] = cfg.font_size
        plt.rcParams['axes.unicode_minus'] = False

        # -- Collect atoms --
        # Restore from original data so fragment mode and workspace filter work on repeated calls.
        # Skip restore for multi-panel recursion (flag set by the caller before recursive call).
        _was_recursive = getattr(self, '_no_data_restore', False)
        self._no_data_restore = False  # Reset for next top-level call
        if not _was_recursive and hasattr(self, '_original_data') and self._original_data:
            self.current_data = self._original_data
            # Apply workspace filter after restore
            _ws_sel = getattr(self, '_ws_selected', None)
            if _ws_sel is not None and len(self.current_data) > 1:
                self.current_data = {ws: d for ws, d in self.current_data.items() if ws in _ws_sel}
        workspaces = list(self.current_data.keys())

        # -- Chart workspace dropdown (boxplot/pie single-workspace selector) --
        self._update_chart_ws_dropdown()
        if cfg.plot_type in ("箱线图", "饼图"):
            _single_ws = getattr(self, '_chart_ws_single', None)
            if _single_ws and _single_ws in self.current_data and len(self.current_data) > 1:
                self.current_data = {_single_ws: self.current_data[_single_ws]}
                workspaces = [_single_ws]

        if not workspaces:
            self.ax.set_title("未选择数据源", color="gray")
            self._apply_dark_mode()
            self.canvas.draw()
            self._restore_rc()
            return

        # -- Fragment mode: replace individual atoms with fragment sum entries --
        _frag_text = getattr(self, '_fragment_text', '')
        if _frag_text:
            import re as _re
            _frag_groups = []
            _all_frag_atoms = set()
            _parts = [_p.strip() for _p in _re.split(r'[,\s]+', _frag_text) if _p.strip()]
            for _part in _parts:
                _m = _re.match(r'^(\d+)-(\d+)$', _part)
                if _m:
                    _s, _e = int(_m.group(1)), int(_m.group(2))
                    _atoms = list(range(_s, _e + 1))
                elif _part.isdigit():
                    _atoms = [int(_part)]
                else:
                    continue
                if _atoms:
                    _frag_groups.append((_part, _atoms))
                    _all_frag_atoms.update(_atoms)

            if _frag_groups:
                _new_data = {}
                for _ws in workspaces:
                    _df = self.current_data[_ws]['df']
                    _new_rows = []
                    for _label, _fatoms in _frag_groups:
                        _fdf = _df[_df['Atom'].isin(_fatoms)]
                        _fsum = _fdf['Bader_Charge'].sum() if not _fdf.empty else 0.0
                        if not _fdf.empty:
                            _elem_counts = _fdf['Element'].value_counts()
                            _lbl_parts = []
                            for _el in _elem_counts.index:
                                _cnt = _elem_counts[_el]
                                _lbl_parts.append(f"{_el}{_cnt}" if _cnt > 1 else _el)
                            _frag_label = ''.join(_lbl_parts)
                        else:
                            _frag_label = f"片段{_label}"
                        _new_rows.append({
                            'Atom': _frag_label,
                            'Element': 'Frag',
                            'Bader_Charge': _fsum,
                            'CHARGE': 0.0,
                            'ZVAL': 0.0,
                        })
                    import pandas as pd
                    _new_df = pd.DataFrame(_new_rows)
                    _new_data[_ws] = {
                        'df': _new_df,
                        'struct': self.current_data[_ws].get('struct'),
                    }
                self.current_data = _new_data

        all_atoms = []
        element_map = {}
        for ws in workspaces:
            df = self.current_data[ws]['df']
            if df.empty:
                continue
            for _, row in df.iterrows():
                a_id = row['Atom']
                if a_id not in all_atoms:
                    all_atoms.append(a_id)
                    element_map[a_id] = row.get('Element', 'X')
        all_atoms.sort()
        if not all_atoms:
            self.ax.set_title("无可用原子数据", color="gray")
            self._apply_dark_mode()
            self._safe_draw_idle()
            self._restore_rc()
            return

        # -- Override atoms for multi-panel Per Atom Group rendering --
        if hasattr(self, '_force_atoms') and self._force_atoms is not None:
            all_atoms = list(self._force_atoms)

        # -- Top N filter: keep atoms with largest |charge| --
        if cfg.show_top_n > 0:
            atom_max_abs = {}
            for a_id in all_atoms:
                max_abs = 0.0
                for ws in workspaces:
                    df = self.current_data[ws]['df']
                    if not df.empty:
                        m = df[df['Atom'] == a_id]
                        if not m.empty:
                            v = m.iloc[0]['Bader_Charge']
                            if not np.isnan(v):
                                max_abs = max(max_abs, abs(v))
                atom_max_abs[a_id] = max_abs
            all_atoms = sorted(all_atoms, key=lambda a: atom_max_abs.get(a, 0), reverse=True)[:cfg.show_top_n]
            all_atoms.sort()

        # -- Pre-compute per-atom std dev across workspaces (for "Std Dev" error bars) --
        atom_std = {}
        if cfg.show_error_bars and cfg.error_bar_type == "标准差":
            for a_id in all_atoms:
                charges = []
                for ws in workspaces:
                    df = self.current_data[ws]['df']
                    if not df.empty:
                        m = df[df['Atom'] == a_id]
                        if not m.empty:
                            v = m.iloc[0]['Bader_Charge']
                            if not np.isnan(v):
                                charges.append(v)
                atom_std[a_id] = float(np.std(charges)) if len(charges) > 1 else abs(charges[0]) * 0.05 if charges else 0.0

        # -- Early polar-axes creation for Radar (must happen before multi-panel) --
        if cfg.plot_type == "雷达图" and getattr(cfg, 'panel_layout', '单面板') == "单面板":
            self.figure.clear()
            self.ax = self.figure.add_subplot(111, polar=True)

        # -- Multi-panel subplot rendering --
        panel_layout = getattr(cfg, 'panel_layout', '单面板')
        if panel_layout != "单面板":
            nrows, ncols = {"1x2": (1, 2), "2x1": (2, 1), "2x2": (2, 2)}.get(panel_layout, (1, 1))
            n_panels = nrows * ncols
            # figure.clear() already called at top of apply_styles()
            saved_bar_map = {}
            gs = self.figure.add_gridspec(nrows, ncols, hspace=0.35, wspace=0.3)

            panel_views = getattr(cfg, 'panel_views', '相同')
            if panel_views == "按工作区" and len(workspaces) > 0:
                for idx in range(n_panels):
                    ax = self.figure.add_subplot(gs[idx // ncols, idx % ncols])
                    if idx >= len(workspaces):
                        ax.set_visible(False)
                        continue
                    ws = workspaces[idx]
                    self.ax = ax
                    saved_data = self.current_data
                    self.current_data = {ws: saved_data[ws]}
                    orig_layout = cfg.panel_layout
                    cfg.panel_layout = "单面板"
                    self._clear_figure = False
                    self._no_data_restore = True
                    self.apply_styles()
                    self._clear_figure = True
                    cfg.panel_layout = orig_layout
                    saved_bar_map.update(self._bar_to_atom_id)
                    self.current_data = saved_data
                    ax.set_title(ws, fontsize=cfg.font_size, weight="bold")

            elif panel_views == "按原子组" and len(all_atoms) > 0:
                chunk = math.ceil(len(all_atoms) / n_panels)
                for idx in range(n_panels):
                    ax = self.figure.add_subplot(gs[idx // ncols, idx % ncols])
                    group = all_atoms[idx * chunk:(idx + 1) * chunk]
                    if not group:
                        ax.set_visible(False)
                        continue
                    self.ax = ax
                    orig_layout = cfg.panel_layout
                    orig_force = getattr(self, '_force_atoms', None)
                    cfg.panel_layout = "单面板"
                    self._force_atoms = group
                    self._clear_figure = False
                    self._no_data_restore = True
                    self.apply_styles()
                    self._clear_figure = True
                    cfg.panel_layout = orig_layout
                    self._force_atoms = orig_force
                    saved_bar_map.update(self._bar_to_atom_id)
                    ax.set_title(f"原子 {group[0]}–{group[-1]}", fontsize=cfg.font_size)

            else:
                # "Same" view: identical chart in each panel (layout preview)
                for idx in range(n_panels):
                    ax = self.figure.add_subplot(gs[idx // ncols, idx % ncols])
                    self.ax = ax
                    orig_layout = cfg.panel_layout
                    cfg.panel_layout = "单面板"
                    self._clear_figure = False
                    self._no_data_restore = True
                    self.apply_styles()
                    self._clear_figure = True
                    cfg.panel_layout = orig_layout
                    saved_bar_map.update(self._bar_to_atom_id)

            self._bar_to_atom_id = saved_bar_map
            self._apply_dark_mode()
            self._safe_draw_idle()
            self._restore_rc()
            return

        # -- Axis break (Y-axis) rendering --
        if getattr(cfg, 'axis_break', False) and cfg.plot_type not in (
                "水平柱状图", "瀑布图", "箱线图", "热力图", "雷达图", "饼图"):
            self._apply_axis_break(cfg, all_atoms, element_map, workspaces)
            self._restore_rc()
            return

        colors = PALETTES.get(cfg.theme, PALETTES.get("Origin Classic"))
        # Generate enough distinct colors for all series (golden ratio hue spacing)
        _needed = max(len(all_atoms), len(workspaces), 50)
        if cfg.theme in ("红白蓝电荷图", "按元素"):
            _expanded_colors = colors  # These themes use their own color logic
        else:
            _expanded_colors = generate_distinct_colors(_needed, colors)
        self._expanded_colors = _expanded_colors  # accessible by _draw_* methods
        plot_type = cfg.plot_type
        group_logic = cfg.group_logic
        b_width = cfg.bar_width / 100.0
        line_style = getattr(cfg, 'line_style', '-')
        line_width = getattr(cfg, 'line_width', 1.5)
        marker_style = getattr(cfg, 'marker_style', 'o')
        marker_size = getattr(cfg, 'marker_size', 6.0)

        # -- Dispatch special chart types (complete rendering, skip standard loop) --
        if plot_type in ("瀑布图", "箱线图", "热力图", "雷达图", "饼图"):
            x_labels = workspaces
            if plot_type == "瀑布图":
                self._draw_waterfall(x_labels, all_atoms, element_map, workspaces, cfg)
            elif plot_type == "箱线图":
                self._draw_boxplot(x_labels, all_atoms, element_map, workspaces, cfg)
            elif plot_type == "热力图":
                self._draw_heatmap(x_labels, all_atoms, element_map, workspaces, cfg)
            elif plot_type == "雷达图":
                self._draw_radar(x_labels, all_atoms, element_map, workspaces, cfg)
            elif plot_type == "饼图":
                self._draw_pie(cfg, all_atoms, element_map, workspaces)
            # Store workspaces for post-render (e.g., pie workspace indicator)
            self._workspaces = workspaces
            # All special types: apply full post-render, dark mode and return
            self._apply_full_post_render(cfg, plot_type)
            self._apply_dark_mode()
            self._safe_draw_idle()
            self._restore_rc()
            return

        extremes_pts = []

        def is_valid(val):
            if np.isnan(val):
                return False
            if cfg.filter_threshold > 0 and abs(val) < cfg.filter_threshold:
                return False
            return True

        def get_color(a_id, j, items_count, y_vals):
            """Resolve bar/line colour for the j-th series."""
            # Check per-series override first
            series_overrides = getattr(cfg, 'series_colors', {})
            if a_id is not None:
                el = element_map.get(a_id, "X")
                lbl = f"{el}{a_id}"
                if lbl in series_overrides:
                    return [series_overrides[lbl]] * len(y_vals)
            if cfg.theme == "红白蓝电荷图":
                return ["#D62728" if not np.isnan(v) and v < 0 else "#1F77B4" for v in y_vals]
            if cfg.theme == "按元素":
                el = element_map.get(a_id, "X")
                c = ELEMENT_COLORS.get(el, DEFAULT_COLOR)
                return [c] * len(y_vals)
            return [_expanded_colors[j % len(_expanded_colors)]] * len(y_vals)

        def get_err_vals(a_id, y_vals):
            if not cfg.show_error_bars:
                return None
            if cfg.error_bar_type == "固定 5%":
                return np.abs(y_vals) * 0.05
            # "Std Dev" — real std dev across systems
            s = atom_std.get(a_id, 0.0)
            return np.full(len(y_vals), s)

        if group_logic == "X=体系, 柱=原子" or plot_type not in ["分组柱状图", "堆叠柱状图", "水平柱状图"]:
            x_labels = workspaces
            x = np.arange(len(workspaces))
            items = all_atoms
            # Area chart: sort atoms by total |charge| if area_order is not "默认"
            if plot_type == "面积图":
                _area_order = getattr(cfg, 'area_order', '默认')
                if _area_order in ("按总量升序", "按总量降序"):
                    _atom_totals = {}
                    for _aid in items:
                        _total = 0.0
                        for _ws in workspaces:
                            _df = self.current_data[_ws]['df']
                            if not _df.empty:
                                _m = _df[_df['Atom'] == _aid]
                                if not _m.empty:
                                    _v = _m.iloc[0]['Bader_Charge']
                                    if not np.isnan(_v):
                                        _total += abs(_v)
                        _atom_totals[_aid] = _total
                    items = sorted(items, key=lambda a: _atom_totals.get(a, 0),
                                   reverse=(_area_order == "按总量降序"))
            num_bars = len(items)
            w = b_width / num_bars if num_bars > 0 else 0.5
            bottoms = np.zeros(len(workspaces))

            for j, a_id in enumerate(items):
                y_vals = np.full(len(workspaces), np.nan)
                for i, ws_name in enumerate(workspaces):
                    df = self.current_data[ws_name]['df']
                    if not df.empty:
                        matches = df[df['Atom'] == a_id]
                        if not matches.empty:
                            v = matches.iloc[0]['Bader_Charge']
                            if is_valid(v):
                                y_vals[i] = v

                el = element_map.get(a_id, "X")
                lbl = f"{el}{a_id}"
                bar_colors = get_color(a_id, j, num_bars, y_vals)
                err_vals = get_err_vals(a_id, y_vals)

                if plot_type == "分组柱状图":
                    off_x = x - b_width / 2.0 + w / 2.0 + j * w
                    bars = self.ax.bar(off_x, y_vals, w, label=lbl, color=bar_colors,
                                edgecolor=cfg.edge_color, linewidth=cfg.edge_width, hatch=cfg.hatch_style)
                    for patch, aid in zip(bars, [a_id] * len(workspaces)):
                        self._bar_to_atom_id[patch] = aid
                    if err_vals is not None:
                        self.ax.errorbar(off_x, y_vals, yerr=err_vals, fmt='none', ecolor='black', capsize=3)
                    for ox, oy in zip(off_x, y_vals):
                        if not np.isnan(oy):
                            extremes_pts.append((ox, oy, oy))
                elif plot_type == "堆叠柱状图":
                    bars = self.ax.bar(x, y_vals, b_width, bottom=bottoms, label=lbl, color=bar_colors,
                                edgecolor=cfg.edge_color, linewidth=cfg.edge_width, hatch=cfg.hatch_style)
                    for patch, aid in zip(bars, [a_id] * len(workspaces)):
                        self._bar_to_atom_id[patch] = aid
                    for ox, oy, ob in zip(x, y_vals, bottoms):
                        if not np.isnan(oy):
                            extremes_pts.append((ox, ob + oy, oy))
                    valid_idx = ~np.isnan(y_vals)
                    bottoms[valid_idx] += y_vals[valid_idx]
                elif plot_type == "水平柱状图":
                    off_y = x - b_width / 2.0 + w / 2.0 + j * w
                    bars = self.ax.barh(off_y, y_vals, w, label=lbl, color=bar_colors,
                                 edgecolor=cfg.edge_color, linewidth=cfg.edge_width, hatch=cfg.hatch_style)
                    for patch, aid in zip(bars, [a_id] * len(workspaces)):
                        self._bar_to_atom_id[patch] = aid
                    for oy, ox in zip(off_y, y_vals):
                        if not np.isnan(ox):
                            extremes_pts.append((ox, oy, ox))
                elif plot_type == "折线图":
                    self.ax.plot(x, y_vals, label=lbl, color=bar_colors[0],
                                 linestyle=line_style, linewidth=line_width,
                                 marker=marker_style, markersize=marker_size)
                    for ox, oy in zip(x, y_vals):
                        if not np.isnan(oy):
                            extremes_pts.append((ox, oy, oy))
                elif plot_type == "散点图":
                    self.ax.scatter(x, y_vals, label=lbl, color=bar_colors[0],
                                    marker=marker_style, s=marker_size ** 2)
                    for ox, oy in zip(x, y_vals):
                        if not np.isnan(oy):
                            extremes_pts.append((ox, oy, oy))
                elif plot_type == "面积图":
                    area_alpha = getattr(cfg, 'area_alpha', 0.3)
                    area_mode = getattr(cfg, 'area_mode', '堆叠')
                    area_interp = getattr(cfg, 'area_interpolation', '线性')
                    step_kw = {'step': 'mid'} if area_interp == "阶梯" else {}
                    use_gradient = getattr(cfg, 'area_gradient', False)

                    if area_mode == "100% 归一化":
                        # Two-pass: collect all y, normalize, then draw
                        _norm_all = []
                        _norm_meta = []
                        for _ni, _na in enumerate(items):
                            _ndf = self.current_data[ws]['df']
                            _nm = _ndf[_ndf['Atom'] == _na]
                            _ny = _nm.iloc[0]['Bader_Charge'] if not _nm.empty else np.nan
                            _ny_clean = np.nan_to_num(np.array([_ny] * len(x), dtype=float))
                            if not getattr(cfg, 'area_negative', True):
                                _ny_clean = np.abs(_ny_clean)
                            _el = element_map.get(_na, "X")
                            _nlbl = f"{_el}{_na}"
                            _ec = getattr(self, '_expanded_colors', None) or PALETTES.get(cfg.theme, PALETTES.get("Origin Classic"))
                            _ncolors = [_ec[_ni % len(_ec)]]
                            _norm_all.append(_ny_clean)
                            _norm_meta.append((_nlbl, _ncolors))
                        _col_totals = np.nansum(np.array(_norm_all), axis=0)
                        _col_totals[_col_totals == 0] = 1.0
                        _nbase = np.zeros(len(x))
                        for _yi, (_nlbl, _ncolors) in enumerate(_norm_meta):
                            _yn = _norm_all[_yi] / _col_totals
                            self.ax.fill_between(x, _nbase, _nbase + _yn,
                                                 label=_nlbl, color=_ncolors[0],
                                                 alpha=area_alpha, **step_kw)
                            if getattr(cfg, 'area_edge_line', True):
                                _es = getattr(cfg, 'area_edge_style', '-')
                                _ew = getattr(cfg, 'area_edge_width', 1.0)
                                self.ax.plot(x, _nbase + _yn, linestyle=_es,
                                             linewidth=_ew, color=_ncolors[0])
                            _nbase += _yn
                        bottoms[:] = _nbase
                    else:
                        if area_mode == "重叠":
                            base = np.zeros(len(x))
                        else:
                            base = bottoms.copy()
                        y_clean = np.nan_to_num(y_vals)
                        if not getattr(cfg, 'area_negative', True):
                            y_clean = np.abs(y_clean)
                        if area_mode == "重叠":
                            pc = self.ax.fill_between(x, np.zeros(len(x)), y_clean,
                                                 label=lbl, color=bar_colors[0], alpha=area_alpha, **step_kw)
                        else:
                            pc = self.ax.fill_between(x, base, base + y_clean,
                                                 label=lbl, color=bar_colors[0], alpha=area_alpha, **step_kw)
                        # Gradient fill overlay
                        if use_gradient and pc is not None:
                            from matplotlib.patches import PathPatch
                            from matplotlib.path import Path
                            _paths = pc.get_paths()
                            if _paths:
                                _ylim = self.ax.get_ylim()
                                _xlim = self.ax.get_xlim()
                                _grad_img = np.linspace(0, 1, 256).reshape(-1, 1)
                                for _p in _paths:
                                    _patch = PathPatch(_p, transform=self.ax.transData,
                                                       facecolor='none', edgecolor='none')
                                    _img = self.ax.imshow(_grad_img, aspect='auto',
                                                          extent=[_xlim[0], _xlim[1], _ylim[0], _ylim[1]],
                                                          cmap='Blues', alpha=0.3,
                                                          origin='lower')
                                    _img.set_clip_path(_patch)
                        # Draw edge line on top
                        if getattr(cfg, 'area_edge_line', True):
                            edge_style = getattr(cfg, 'area_edge_style', '-')
                            edge_w = getattr(cfg, 'area_edge_width', 1.0)
                            if area_mode == "重叠":
                                self.ax.plot(x, y_clean, linestyle=edge_style, linewidth=edge_w, color=bar_colors[0])
                            else:
                                self.ax.plot(x, base + y_clean, linestyle=edge_style, linewidth=edge_w, color=bar_colors[0])
                        if area_mode != "重叠":
                            valid_idx = ~np.isnan(y_vals)
                            bottoms[valid_idx] += y_vals[valid_idx]

        else:  # X=Atom, Bar=System
            x_labels = [f"{element_map.get(a, 'X')}{a}" for a in all_atoms]
            x = np.arange(len(all_atoms))
            items = workspaces
            num_bars = len(items)
            w = b_width / num_bars if num_bars > 0 else 0.5
            bottoms = np.zeros(len(all_atoms))

            for j, ws_name in enumerate(items):
                y_vals = np.full(len(all_atoms), np.nan)
                df = self.current_data[ws_name]['df']
                if not df.empty:
                    for i, a_id in enumerate(all_atoms):
                        matches = df[df['Atom'] == a_id]
                        if not matches.empty:
                            v = matches.iloc[0]['Bader_Charge']
                            if is_valid(v):
                                y_vals[i] = v

                lbl = ws_name
                bar_colors = get_color(None, j, num_bars, y_vals)
                err_vals = None
                if cfg.show_error_bars:
                    if cfg.error_bar_type == "固定 5%":
                        err_vals = np.abs(y_vals) * 0.05
                    else:
                        err_vals = np.array([atom_std.get(a, 0.0) for a in all_atoms])

                if plot_type == "分组柱状图":
                    off_x = x - b_width / 2.0 + w / 2.0 + j * w
                    bars = self.ax.bar(off_x, y_vals, w, label=lbl, color=bar_colors,
                                edgecolor=cfg.edge_color, linewidth=cfg.edge_width, hatch=cfg.hatch_style)
                    for patch, aid in zip(bars, all_atoms):
                        self._bar_to_atom_id[patch] = aid
                    if err_vals is not None:
                        self.ax.errorbar(off_x, y_vals, yerr=err_vals, fmt='none', ecolor='black', capsize=3)
                    for ox, oy in zip(off_x, y_vals):
                        if not np.isnan(oy):
                            extremes_pts.append((ox, oy, oy))
                elif plot_type == "堆叠柱状图":
                    bars = self.ax.bar(x, y_vals, b_width, bottom=bottoms, label=lbl, color=bar_colors,
                                edgecolor=cfg.edge_color, linewidth=cfg.edge_width, hatch=cfg.hatch_style)
                    for patch, aid in zip(bars, all_atoms):
                        self._bar_to_atom_id[patch] = aid
                    for ox, oy, ob in zip(x, y_vals, bottoms):
                        if not np.isnan(oy):
                            extremes_pts.append((ox, ob + oy, oy))
                    valid_idx = ~np.isnan(y_vals)
                    bottoms[valid_idx] += y_vals[valid_idx]
                elif plot_type == "水平柱状图":
                    off_y = x - b_width / 2.0 + w / 2.0 + j * w
                    bars = self.ax.barh(off_y, y_vals, w, label=lbl, color=bar_colors,
                                 edgecolor=cfg.edge_color, linewidth=cfg.edge_width, hatch=cfg.hatch_style)
                    for patch, aid in zip(bars, all_atoms):
                        self._bar_to_atom_id[patch] = aid
                    for oy, ox in zip(off_y, y_vals):
                        if not np.isnan(ox):
                            extremes_pts.append((ox, oy, ox))
                else:
                    self.ax.plot(x, y_vals, label=lbl, color=bar_colors[0],
                                 linestyle=line_style, linewidth=line_width,
                                 marker=marker_style, markersize=marker_size)

        # ============================================================
        #  Post-render styling (unified method)
        # ============================================================
        self._apply_full_post_render(cfg, plot_type, x, x_labels, extremes_pts)

        self._apply_dark_mode()
        self._safe_draw_idle()
        self._restore_rc()

    # ==================================================================
    #  Unified post-render for ALL chart types (standard + advanced)
    # ==================================================================

    def _format_data_label(self, value, cfg):
        decimals = max(0, int(getattr(cfg, 'data_label_decimals', 3)))
        fmt = getattr(cfg, 'data_label_format', '固定小数')
        if fmt == "科学计数":
            return f"{value:.{decimals}e}"
        if fmt == "带符号":
            return f"{value:+.{decimals}f}"
        return f"{value:.{decimals}f}"

    def _data_label_color(self, value, cfg):
        color = (getattr(cfg, 'data_label_positive_color', 'auto')
                 if value >= 0 else
                 getattr(cfg, 'data_label_negative_color', 'auto'))
        return None if not color or color == "auto" else color

    def _should_skip_data_label(self, px, py, placed, cfg):
        if not getattr(cfg, 'data_label_avoid_overlap', False):
            return False
        for old_x, old_y in placed:
            if abs(float(px) - float(old_x)) < 0.12 and abs(float(py) - float(old_y)) < 0.12:
                return True
        placed.append((px, py))
        return False

    def _apply_origin_axis_settings(self, cfg):
        label_pad = getattr(cfg, 'axes_label_pad', 4.0)
        self.ax.xaxis.labelpad = label_pad
        self.ax.yaxis.labelpad = label_pad

        tick_kwargs = {
            'width': getattr(cfg, 'tick_width', 0.8),
            'length': getattr(cfg, 'major_tick_length', 3.5),
        }
        sides = getattr(cfg, 'tick_sides', '默认')
        if sides == "上下左右":
            tick_kwargs.update(top=True, right=True, bottom=True, left=True)
        elif sides == "仅左下":
            tick_kwargs.update(top=False, right=False, bottom=True, left=True)
        self.ax.tick_params(axis='both', which='major', **tick_kwargs)
        self.ax.tick_params(
            axis='both', which='minor',
            width=getattr(cfg, 'tick_width', 0.8),
            length=getattr(cfg, 'minor_tick_length', 2.0))

        left = getattr(cfg, 'figure_margin_left', 0.0)
        right_margin = getattr(cfg, 'figure_margin_right', 0.0)
        top_margin = getattr(cfg, 'figure_margin_top', 0.0)
        bottom = getattr(cfg, 'figure_margin_bottom', 0.0)
        if any(v > 0 for v in (left, right_margin, top_margin, bottom)):
            right = 1.0 - right_margin if right_margin > 0 else None
            top = 1.0 - top_margin if top_margin > 0 else None
            kwargs = {}
            if left > 0:
                kwargs['left'] = left
            if bottom > 0:
                kwargs['bottom'] = bottom
            if right is not None and right > kwargs.get('left', 0.0):
                kwargs['right'] = right
            if top is not None and top > kwargs.get('bottom', 0.0):
                kwargs['top'] = top
            if kwargs:
                try:
                    self.figure.subplots_adjust(**kwargs)
                except ValueError:
                    pass

    def _apply_plot_title(self, cfg):
        fig_title = getattr(cfg, 'fig_title', '')
        if not fig_title:
            return
        fontsize = cfg.font_size + 2
        pad = getattr(cfg, 'title_pad', 12.0)
        position = getattr(cfg, 'title_position', '顶部居中')
        if position == "顶部左侧":
            self.ax.set_title(fig_title, fontsize=fontsize, weight="bold",
                              pad=pad, loc='left')
        elif position == "图内左上":
            self.ax.text(0.02, 0.98, fig_title, transform=self.ax.transAxes,
                         ha='left', va='top', fontsize=fontsize,
                         weight='bold')
        elif position == "图内右上":
            self.ax.text(0.98, 0.98, fig_title, transform=self.ax.transAxes,
                         ha='right', va='top', fontsize=fontsize,
                         weight='bold')
        else:
            self.ax.set_title(fig_title, fontsize=fontsize, weight="bold",
                              pad=pad)

    def _legend_external_layout(self, cfg, position=None):
        anchor = getattr(cfg, 'legend_external_anchor', '右侧中')
        position = position or getattr(cfg, 'legend_position', '')
        if position == "右侧外部":
            mapping = {
                "右侧上": ((1.02, 1.0), "upper left"),
                "右侧中": ((1.02, 0.5), "center left"),
                "右侧下": ((1.02, 0.0), "lower left"),
            }
            try:
                self.figure.subplots_adjust(right=0.80)
            except Exception:
                pass
            return mapping.get(anchor, mapping["右侧中"])
        if position == "底部外部":
            mapping = {
                "底部左": ((0.0, -0.16), "upper left"),
                "底部中": ((0.5, -0.16), "upper center"),
                "底部右": ((1.0, -0.16), "upper right"),
            }
            try:
                self.figure.subplots_adjust(bottom=0.22)
            except Exception:
                pass
            return mapping.get(anchor, mapping["底部中"])
        return None

    def _legend_kwargs(self, cfg, position=None):
        legend_columns = getattr(cfg, 'legend_columns', 1)
        position = position or getattr(cfg, 'legend_position', '')
        if legend_columns <= 1 and position == "底部外部":
            legend_columns = 3
        return {
            'frameon': cfg.legend_frame,
            'ncol': legend_columns,
            'title': getattr(cfg, 'legend_title', '') or None,
            'handlelength': getattr(cfg, 'legend_handle_length', 2.0),
            'borderpad': getattr(cfg, 'legend_border_pad', 0.4),
        }

    def _style_legend(self, leg, cfg):
        if leg is None:
            return
        bg = "#1E1E1E" if self._is_dark_mode else "#FFFFFF"
        fg = "#E0E0E0" if self._is_dark_mode else "black"
        plt.setp(leg.get_texts(),
                 fontname=self._cjk_font_list(cfg.legend_font),
                 fontsize=cfg.legend_size)
        if leg.get_title() is not None:
            leg.get_title().set_fontname(self._cjk_font_list(cfg.legend_font))
            leg.get_title().set_fontsize(cfg.legend_size)
        if cfg.legend_frame:
            frame = leg.get_frame()
            frame.set_facecolor(bg)
            frame.set_edgecolor(fg)
            frame.set_alpha(getattr(cfg, 'legend_alpha', 1.0))
            for text in leg.get_texts():
                text.set_color(fg)
            if leg.get_title() is not None:
                leg.get_title().set_color(fg)

    def _apply_full_post_render(self, cfg, chart_type, x=None, x_labels=None,
                                extremes_pts=None):
        """Apply all post-render styling. Advanced charts get subset; standard get full."""
        is_pie = (chart_type == "饼图")
        is_radar = (chart_type == "雷达图")
        is_heatmap = (chart_type == "热力图")
        is_advanced = chart_type in ("瀑布图", "箱线图", "热力图", "雷达图", "饼图")
        is_horizontal = (chart_type == "水平柱状图")

        # ── 1. Axis labels (standard only; advanced set their own) ──
        ax_weight = "bold" if getattr(cfg, 'bold_ax_lbl', False) else "normal"
        if not is_advanced:
            if is_horizontal:
                self.ax.set_yticks(x)
                self.ax.set_yticklabels(x_labels)
                if cfg.show_x_label:
                    self.ax.set_ylabel(cfg.x_label, weight=ax_weight,
                                       fontname=self._cjk_font_list(cfg.axis_label_font),
                                       fontsize=cfg.axis_label_size)
                if cfg.show_y_label:
                    self.ax.set_xlabel(cfg.y_label, weight=ax_weight,
                                       fontname=self._cjk_font_list(cfg.axis_label_font),
                                       fontsize=cfg.axis_label_size)
            else:
                self.ax.set_xticks(x)
                self.ax.set_xticklabels(x_labels)
                if cfg.show_x_label:
                    self.ax.set_xlabel(cfg.x_label, weight=ax_weight,
                                       fontname=self._cjk_font_list(cfg.axis_label_font),
                                       fontsize=cfg.axis_label_size)
                if cfg.show_y_label:
                    self.ax.set_ylabel(cfg.y_label, weight=ax_weight,
                                       fontname=self._cjk_font_list(cfg.axis_label_font),
                                       fontsize=cfg.axis_label_size)
        else:
            # Advanced: only override label visibility / font if needed
            if not is_pie and not is_radar:
                if cfg.show_x_label and cfg.x_label:
                    self.ax.set_xlabel(cfg.x_label, weight=ax_weight,
                                       fontname=self._cjk_font_list(cfg.axis_label_font),
                                       fontsize=cfg.axis_label_size)
                if cfg.show_y_label and cfg.y_label:
                    self.ax.set_ylabel(cfg.y_label, weight=ax_weight,
                                       fontname=self._cjk_font_list(cfg.axis_label_font),
                                       fontsize=cfg.axis_label_size)

        if is_pie or is_radar:
            # ── Pie / Radar: minimal post-render ──
            if cfg.annotation_text:
                self.ax.text(
                    getattr(cfg, 'annotation_pos_x', 0.05),
                    getattr(cfg, 'annotation_pos_y', 0.95),
                    cfg.annotation_text, transform=self.ax.transAxes,
                    fontsize=cfg.font_size, verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='white',
                              alpha=0.8, edgecolor='gray'))
            if is_radar:
                self._apply_plot_title(cfg)
            else:
                # Pie: handle title override via fig_title, respecting pie_show_title
                pie_show_title = getattr(cfg, 'pie_show_title', True)
                if pie_show_title and cfg.fig_title:
                    pie_title_fs = getattr(cfg, 'pie_title_size', 14)
                    pie_title_w = getattr(cfg, 'pie_title_weight', 'bold')
                    self.ax.set_title(cfg.fig_title, fontsize=pie_title_fs, weight=pie_title_w)
                elif not pie_show_title:
                    self.ax.set_title('')
            # Pie workspace indicator
            if is_pie and getattr(cfg, 'pie_show_workspace_indicator', True):
                _ws = getattr(self, '_workspaces', [])
                if _ws:
                    _ws_fs = getattr(cfg, 'pie_workspace_indicator_size', 9)
                    _ws_text = "工作区: " + ", ".join(_ws)
                    self.figure.text(0.02, 0.98, _ws_text, ha='left', va='top',
                                     fontsize=_ws_fs, color='gray',
                                     bbox=dict(boxstyle='round,pad=0.3',
                                               facecolor='white', alpha=0.7,
                                               edgecolor='#CCCCCC'))
            return

        # ── 2. Tick direction / rotation ──
        _td = TICK_DIR_MAP.get(cfg.tick_direction, cfg.tick_direction)
        if is_horizontal:
            self.ax.tick_params(axis='y', rotation=cfg.x_tick_rotation,
                                direction=_td,
                                labelsize=cfg.tick_label_size)
            self.ax.tick_params(axis='x', direction=_td,
                                labelsize=cfg.tick_label_size)
        else:
            self.ax.tick_params(axis='x', rotation=cfg.x_tick_rotation,
                                direction=_td,
                                labelsize=cfg.tick_label_size)
            self.ax.tick_params(axis='y', direction=_td,
                                labelsize=cfg.tick_label_size)

        # ── 3. Minor ticks ──
        minor_n = getattr(cfg, 'minor_ticks_count', 0)
        if minor_n > 0:
            self.ax.minorticks_on()
            if is_horizontal:
                self.ax.xaxis.set_minor_locator(
                    mticker.AutoMinorLocator(minor_n + 1))
            else:
                self.ax.yaxis.set_minor_locator(
                    mticker.AutoMinorLocator(minor_n + 1))
                self.ax.xaxis.set_minor_locator(
                    mticker.AutoMinorLocator(minor_n + 1))
        else:
            if not is_horizontal:
                self.ax.minorticks_on()
        # Apply minor tick direction in ALL cases (both minor_n > 0 and == 0)
        self.ax.tick_params(
            axis='both', which='minor',
            direction=TICK_DIR_MAP.get(cfg.tick_direction,
                                       cfg.tick_direction))

        # ── 4. Tick label font/weight ──
        tick_weight = "bold" if getattr(cfg, 'bold_ticks', False) else "normal"
        for label in (self.ax.get_xticklabels() +
                      self.ax.get_yticklabels()):
            label.set_fontname(self._cjk_font_list(cfg.tick_label_font))
            label.set_fontweight(tick_weight)
        self._apply_origin_axis_settings(cfg)

        # ── 5. Spines ──
        if not is_heatmap:
            self.ax.spines['top'].set_visible(cfg.show_top_right_spines)
            self.ax.spines['right'].set_visible(cfg.show_top_right_spines)
            if cfg.show_top_right_spines:
                self.ax.tick_params(top=False, right=False)
        spine_w = getattr(cfg, 'spine_width', 1.0)
        spine_c = getattr(cfg, 'spine_color', 'black')
        for spine in self.ax.spines.values():
            spine.set_linewidth(spine_w)
            if not self._is_dark_mode:
                spine.set_color(spine_c)

        # ── 6. Tick formatter ──
        tick_fmt = getattr(cfg, 'tick_format', '自动')
        tick_dec = getattr(cfg, 'tick_decimals', 2)
        sci = getattr(cfg, 'scientific_notation', False)
        if tick_fmt == "定点小数":
            fmt = mticker.FormatStrFormatter(f"%.{tick_dec}f")
            if is_horizontal:
                self.ax.xaxis.set_major_formatter(fmt)
            else:
                self.ax.yaxis.set_major_formatter(fmt)
        if sci:
            if is_horizontal:
                self.ax.xaxis.set_major_formatter(
                    mticker.ScalarFormatter(useMathText=True))
                self.ax.ticklabel_format(axis='x', style='sci',
                                         scilimits=(-2, 3))
            else:
                self.ax.yaxis.set_major_formatter(
                    mticker.ScalarFormatter(useMathText=True))
                self.ax.ticklabel_format(axis='y', style='sci',
                                         scilimits=(-2, 3))

        # ── 7. Grid ──
        gc = getattr(cfg, 'grid_color', '#CCCCCC')
        gw = getattr(cfg, 'grid_width', 0.5)
        ga = cfg.grid_alpha
        if is_horizontal:
            if cfg.show_y_major_grid:
                self.ax.grid(True, axis='x', which='major',
                             linestyle=cfg.grid_style, alpha=ga,
                             color=gc, linewidth=gw)
            if cfg.show_y_minor_grid:
                self.ax.grid(True, axis='x', which='minor',
                             linestyle=cfg.grid_style, alpha=ga / 2,
                             color=gc, linewidth=gw)
            if cfg.show_x_major_grid:
                self.ax.grid(True, axis='y', which='major',
                             linestyle=cfg.grid_style, alpha=ga,
                             color=gc, linewidth=gw)
        else:
            if cfg.show_y_major_grid:
                self.ax.grid(True, axis='y', which='major',
                             linestyle=cfg.grid_style, alpha=ga,
                             color=gc, linewidth=gw)
            if cfg.show_y_minor_grid:
                self.ax.grid(True, axis='y', which='minor',
                             linestyle=cfg.grid_style, alpha=ga / 2,
                             color=gc, linewidth=gw)
            if cfg.show_x_major_grid:
                self.ax.grid(True, axis='x', which='major',
                             linestyle=cfg.grid_style, alpha=ga,
                             color=gc, linewidth=gw)

        # ── 8. Reference lines (cartesian charts with numeric Y) ──
        if chart_type not in ("热力图",):
            if cfg.show_zero_line:
                if is_horizontal:
                    self.ax.axvline(0, color=cfg.zero_line_color,
                                    linewidth=1.5, zorder=1)
                else:
                    self.ax.axhline(0, color=cfg.zero_line_color,
                                    linewidth=1.5, zorder=1)
            if cfg.show_ref_05:
                if is_horizontal:
                    self.ax.axvline(0.5, color='gray',
                                    linestyle=':', zorder=1)
                    self.ax.axvline(-0.5, color='gray',
                                    linestyle=':', zorder=1)
                else:
                    self.ax.axhline(0.5, color='gray',
                                    linestyle=':', zorder=1)
                    self.ax.axhline(-0.5, color='gray',
                                    linestyle=':', zorder=1)
            if cfg.show_ref_10:
                if is_horizontal:
                    self.ax.axvline(1.0, color='gray',
                                    linestyle='-.', zorder=1)
                    self.ax.axvline(-1.0, color='gray',
                                    linestyle='-.', zorder=1)
                else:
                    self.ax.axhline(1.0, color='gray',
                                    linestyle='-.', zorder=1)
                    self.ax.axhline(-1.0, color='gray',
                                    linestyle='-.', zorder=1)
            if cfg.show_highlight_span:
                if is_horizontal:
                    self.ax.axvspan(-0.2, 0.2, color='yellow',
                                    alpha=0.1, zorder=0)
                else:
                    self.ax.axhspan(-0.2, 0.2, color='yellow',
                                    alpha=0.1, zorder=0)

        # ── 9. Y range / symmetry (cartesian charts) ──
        if chart_type in ("瀑布图", "箱线图", "面积图", "分组柱状图",
                          "堆叠柱状图", "水平柱状图", "折线图", "散点图"):
            if cfg.y_min != 0.0 or cfg.y_max != 0.0:
                if is_horizontal:
                    self.ax.set_xlim(cfg.y_min, cfg.y_max)
                    if cfg.y_step > 0:
                        self.ax.set_xticks(
                            np.arange(cfg.y_min,
                                      cfg.y_max + cfg.y_step / 2,
                                      cfg.y_step))
                else:
                    self.ax.set_ylim(cfg.y_min, cfg.y_max)
                    if cfg.y_step > 0:
                        self.ax.set_yticks(
                            np.arange(cfg.y_min,
                                      cfg.y_max + cfg.y_step / 2,
                                      cfg.y_step))
            elif cfg.y_symmetric:
                if is_horizontal:
                    min_v, max_v = self.ax.get_xlim()
                    limit = max(abs(min_v), abs(max_v))
                    if limit > 0:
                        self.ax.set_xlim(-limit * 1.05, limit * 1.05)
                else:
                    min_v, max_v = self.ax.get_ylim()
                    limit = max(abs(min_v), abs(max_v))
                    if limit > 0:
                        self.ax.set_ylim(-limit * 1.05, limit * 1.05)

        # ── 10. Log / Symlog scales ──
        if not is_advanced:
            x_scale = getattr(cfg, 'x_scale', '线性')
            y_scale = getattr(cfg, 'y_scale', '线性')
            if is_horizontal:
                if x_scale == "对称对数":
                    self.ax.set_xscale('symlog', linthresh=0.01)
            else:
                if y_scale == "对称对数":
                    self.ax.set_yscale('symlog', linthresh=0.01)
                if x_scale == "对称对数":
                    self.ax.set_xscale('symlog', linthresh=0.01)

        # ── 11. Trend line (standard line/scatter only) ──
        if not is_advanced:
            group_logic = getattr(cfg, 'group_logic', '')
            trend = getattr(cfg, 'trend_line', '无')
            if (trend != "无"
                    and chart_type in ("折线图", "散点图")
                    and group_logic == "X=体系, 柱=原子"
                    and x is not None):
                self._draw_trend_line(
                    trend, x,
                    getattr(self, '_all_atoms', None),
                    getattr(self, '_element_map', None),
                    getattr(self, '_workspaces', None))

        # ── 12. Annotation ──
        if cfg.annotation_text:
            self.ax.text(
                getattr(cfg, 'annotation_pos_x', 0.05),
                getattr(cfg, 'annotation_pos_y', 0.95),
                cfg.annotation_text, transform=self.ax.transAxes,
                fontsize=cfg.font_size, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='white',
                          alpha=0.8, edgecolor='gray'))

        # ── 13. Data labels (standard + waterfall + boxplot) ──
        if not is_advanced and cfg.show_data_labels != "无" and extremes_pts:
            pts_to_label = []
            if cfg.show_data_labels == "仅极值":
                max_pt = max(extremes_pts, key=lambda p: p[2])
                min_pt = min(extremes_pts, key=lambda p: p[2])
                pts_to_label = [max_pt, min_pt]
            elif cfg.show_data_labels == "> 阈值":
                pts_to_label = [p for p in extremes_pts
                                if abs(p[2]) >= cfg.label_threshold]
            else:
                pts_to_label = extremes_pts
            data_weight = ("bold"
                           if getattr(cfg, 'bold_data', False)
                           else "normal")
            placed_labels = []
            for px, py, val in pts_to_label:
                if self._should_skip_data_label(px, py, placed_labels, cfg):
                    continue
                label_color = self._data_label_color(val, cfg)
                label_kwargs = {}
                if label_color is not None:
                    label_kwargs['color'] = label_color
                if is_horizontal:
                    offset = (cfg.data_label_offset if px > 0
                              else -cfg.data_label_offset)
                    ha = 'left' if px > 0 else 'right'
                    self.ax.annotate(
                        self._format_data_label(val, cfg), (px, py),
                        textcoords="offset points",
                        xytext=(offset, 0), ha=ha, va='center',
                        fontsize=cfg.data_label_size,
                        fontname=self._cjk_font_list(cfg.data_label_font),
                        rotation=cfg.data_label_rotation,
                        weight=data_weight, **label_kwargs)
                else:
                    offset = (cfg.data_label_offset if py > 0
                              else -cfg.data_label_offset)
                    va = 'bottom' if py > 0 else 'top'
                    self.ax.annotate(
                        self._format_data_label(val, cfg), (px, py),
                        textcoords="offset points",
                        xytext=(0, offset), ha='center', va=va,
                        fontsize=cfg.data_label_size,
                        fontname=self._cjk_font_list(cfg.data_label_font),
                        rotation=cfg.data_label_rotation,
                        weight=data_weight, **label_kwargs)

        # ── 14. Legend (skip heatmap which uses colorbar) ──
        # Boxplot: single-workspace bars have labels picked up here; multi-workspace
        # boxplot creates its own proxy-patch legend inside _draw_boxplot which is
        # invisible to get_legend_handles_labels, so section 14 gracefully skips.
        if not is_heatmap:
            handles, labels = self.ax.get_legend_handles_labels()
            unique_labels, unique_handles = [], []
            for h, l in zip(handles, labels):
                if l not in unique_labels:
                    unique_labels.append(l)
                    unique_handles.append(h)
            if getattr(cfg, 'custom_legend', "").strip():
                c_legs = [x.strip()
                          for x in cfg.custom_legend.split(",")
                          if x.strip()]
                for i in range(min(len(c_legs), len(unique_labels))):
                    unique_labels[i] = c_legs[i]
            if unique_handles and cfg.legend_position != "隐藏":
                loc_map = {"最佳": "best", "右上": "upper right",
                           "左上": "upper left"}
                leg = None
                legend_kwargs = self._legend_kwargs(cfg)
                if cfg.legend_position in loc_map:
                    leg = self.ax.legend(
                        unique_handles, unique_labels,
                        loc=loc_map[cfg.legend_position],
                        **legend_kwargs)
                elif cfg.legend_position in ("右侧外部", "底部外部"):
                    bbox, loc = self._legend_external_layout(cfg)
                    leg = self.ax.legend(
                        unique_handles, unique_labels,
                        bbox_to_anchor=bbox,
                        loc=loc,
                        **legend_kwargs)
                self._style_legend(leg, cfg)

        # ── 15. Figure title ──
        self._apply_plot_title(cfg)

    # ==================================================================
    #  Trend line helper
    # ==================================================================

    def _draw_trend_line(self, trend, x, all_atoms, element_map, workspaces):
        """Overlay a trend line across the averaged charges per system."""
        cfg = self.config
        avg_y = np.zeros(len(x))
        counts = np.zeros(len(x))
        for i, ws in enumerate(workspaces):
            df = self.current_data[ws]['df']
            if df.empty:
                continue
            for _, row in df.iterrows():
                v = row['Bader_Charge']
                if not np.isnan(v):
                    avg_y[i] += v
                    counts[i] += 1
        mask = counts > 0
        if mask.sum() < 2:
            return
        avg_y[mask] /= counts[mask]
        xf = x[mask].astype(float)
        yf = avg_y[mask]

        if trend == "线性拟合":
            coeffs = np.polyfit(xf, yf, 1)
            poly = np.poly1d(coeffs)
            self.ax.plot(x, poly(x.astype(float)), '--', color='gray', linewidth=1.2,
                         alpha=0.7, label=f"趋势: y={coeffs[0]:.3f}x{coeffs[1]:+.3f}")
        elif trend == "多项式":
            degree = getattr(cfg, 'trend_line_degree', 2)
            if len(xf) > degree:
                coeffs = np.polyfit(xf, yf, degree)
                poly = np.poly1d(coeffs)
                self.ax.plot(x, poly(x.astype(float)), '--', color='gray', linewidth=1.2,
                             alpha=0.7, label=f"多项式阶数={degree}")
        elif trend == "均值":
            mean_val = float(np.mean(yf))
            self.ax.axhline(mean_val, color='gray', linestyle='--', linewidth=1.2,
                            alpha=0.7, label=f"均值: {mean_val:.3f}")
        elif trend == "移动平均 (3)":
            if len(yf) >= 3:
                ma = np.convolve(yf, np.ones(3) / 3, mode='valid')
                ma_x = xf[1:-1] if len(xf) == len(yf) else xf[:len(ma)]
                self.ax.plot(ma_x, ma, '--', color='gray', linewidth=1.2,
                             alpha=0.7, label="移动平均 (3)")

    def _draw_waterfall(self, x_labels, all_atoms, element_map, workspaces, cfg):
        """Waterfall chart: cumulative change across workspaces for selected atom."""
        if not all_atoms or len(workspaces) < 2:
            return
        # Select target atom (0 = auto/first)
        target_id = getattr(cfg, 'waterfall_atom_id', 0)
        if target_id > 0 and target_id in all_atoms:
            a_id = target_id
        else:
            a_id = all_atoms[0]
        el = element_map.get(a_id, "X")
        charges = []
        for ws in workspaces:
            df = self.current_data[ws]['df']
            if not df.empty:
                m = df[df['Atom'] == a_id]
                if not m.empty:
                    charges.append(m.iloc[0]['Bader_Charge'])
                else:
                    charges.append(0.0)
            else:
                charges.append(0.0)

        # Sorting support
        ws_labels = list(workspaces)
        wf_sort = getattr(cfg, 'waterfall_sort', '默认')
        if wf_sort == "按电荷":
            paired = sorted(zip(charges, ws_labels), key=lambda p: p[0])
            charges = [p[0] for p in paired]
            ws_labels = [p[1] for p in paired]
        elif wf_sort == "按元素":
            # Group by element prefix
            def _el_key(ws_name):
                return ws_name[:2] if len(ws_name) >= 2 else ws_name
            paired = sorted(zip(charges, ws_labels), key=lambda p: _el_key(p[1]))
            charges = [p[0] for p in paired]
            ws_labels = [p[1] for p in paired]

        cumulative = np.cumsum(charges)
        pos_c = getattr(cfg, 'waterfall_pos_color', '#2ecc71')
        neg_c = getattr(cfg, 'waterfall_neg_color', '#e74c3c')
        colors_wf = [pos_c if c >= 0 else neg_c for c in charges]
        bar_width = getattr(cfg, 'waterfall_bar_width', 0.6)
        edge_color = getattr(cfg, 'waterfall_edge_color', 'black')
        edge_width = getattr(cfg, 'waterfall_edge_width', 0.5)

        n_bars = len(charges)
        # Add total bar if enabled
        if getattr(cfg, 'waterfall_show_total', True):
            total = sum(charges)
            charges = list(charges) + [total]
            colors_wf.append(getattr(cfg, 'waterfall_total_color', '#3498db'))
            ws_labels = list(ws_labels) + ["总计"]
            n_bars += 1

        bars = self.ax.bar(range(n_bars), charges, width=bar_width, color=colors_wf,
                    edgecolor=edge_color, linewidth=edge_width,
                    hatch=getattr(cfg, 'waterfall_hatch', None))
        # Rounded corners
        bar_round = getattr(cfg, 'waterfall_bar_round', 0.0)
        if bar_round > 0:
            from matplotlib.patches import FancyBboxPatch
            for bar_rect in bars:
                x0, y0 = bar_rect.get_x(), bar_rect.get_y()
                w, h = bar_rect.get_width(), bar_rect.get_height()
                fc, ec, lw = bar_rect.get_facecolor(), bar_rect.get_edgecolor(), bar_rect.get_linewidth()
                ht = getattr(bar_rect, '_hatch', None) or bar_rect.get_hatch()
                bar_rect.set_visible(False)
                fancy = FancyBboxPatch((x0, y0), w, h,
                                       boxstyle=f"round,pad=0,rounding_size={bar_round}",
                                       facecolor=fc, edgecolor=ec, linewidth=lw, hatch=ht)
                self.ax.add_patch(fancy)
        if getattr(cfg, 'waterfall_connectors', True):
            conn_style = getattr(cfg, 'waterfall_connector_style', '-')
            conn_color = getattr(cfg, 'waterfall_connector_color', 'black')
            conn_width = getattr(cfg, 'waterfall_connector_width', 0.5)
            conn_alpha = getattr(cfg, 'waterfall_connector_alpha', 0.3)
            cum = np.cumsum(charges[:len(workspaces)])
            for i in range(1, len(cum)):
                self.ax.plot([i-1, i], [cum[i-1], cum[i-1]],
                             color=conn_color, linestyle=conn_style,
                             linewidth=conn_width, alpha=conn_alpha)
        # Cumulative line overlay
        if getattr(cfg, 'waterfall_cumulative_line', False):
            cum_vals = np.cumsum(charges)
            cum_color = getattr(cfg, 'waterfall_cumulative_color', 'black')
            cum_width = getattr(cfg, 'waterfall_cumulative_width', 1.5)
            self.ax.plot(range(len(cum_vals)), cum_vals, color=cum_color,
                         linewidth=cum_width, marker='o', markersize=4, zorder=5, label="累积")
        # Value labels
        if getattr(cfg, 'waterfall_show_labels', False):
            wf_lbl_fmt = getattr(cfg, 'waterfall_label_format', '.2f')
            wf_lbl_font = getattr(cfg, 'waterfall_label_font', 'Arial')
            wf_lbl_weight = getattr(cfg, 'waterfall_label_weight', 'normal')
            wf_pct_mode = getattr(cfg, 'waterfall_pct_mode', False)
            total_for_pct = sum(abs(v) for v in charges) if wf_pct_mode else 1.0
            if total_for_pct == 0:
                total_for_pct = 1.0
            for i, v in enumerate(charges):
                if wf_pct_mode:
                    pct = v / total_for_pct * 100
                    txt = f"{pct:{wf_lbl_fmt}}%"
                else:
                    txt = f"{v:{wf_lbl_fmt}}"
                self.ax.text(i, v, txt, ha='center', va='bottom' if v >= 0 else 'top',
                             fontsize=cfg.data_label_size, fontname=self._cjk_font_list(wf_lbl_font),
                             fontweight=wf_lbl_weight)
        self.ax.set_xticks(range(n_bars))
        self.ax.set_xticklabels(ws_labels, rotation=cfg.x_tick_rotation)
        self.ax.set_ylabel(cfg.y_label if cfg.y_label else f"{el}{a_id} 累积电荷")
        self.ax.axhline(0, color=getattr(cfg, 'waterfall_zero_line_color', 'black'),
                        linewidth=getattr(cfg, 'waterfall_zero_line_width', 1.0))

    def _draw_boxplot(self, x_labels, all_atoms, element_map, workspaces, cfg):
        """Box plot: distribution of charges across workspaces per atom.
        When only 1 workspace is present, renders as a bar chart of individual charges."""
        max_atoms = getattr(cfg, 'boxplot_max_atoms', 20)
        data_by_atom = []
        labels = []
        plotted_atom_ids = []
        for a_id in all_atoms[:max_atoms]:
            el = element_map.get(a_id, "X")
            charges = []
            for ws in workspaces:
                df = self.current_data[ws]['df']
                if not df.empty:
                    m = df[df['Atom'] == a_id]
                    if not m.empty:
                        charges.append(m.iloc[0]['Bader_Charge'])
            if charges:
                data_by_atom.append(charges)
                labels.append(f"{el}{a_id}")
                plotted_atom_ids.append(a_id)
        if not data_by_atom:
            return

        # ── Boxplot rendering (works for both single and multi workspace) ──
        show_mean = getattr(cfg, 'boxplot_show_mean', True)
        bp_width = getattr(cfg, 'boxplot_width', 0.5)
        bp_horizontal = getattr(cfg, 'boxplot_orientation', '垂直') == "水平"
        bp_gap = getattr(cfg, 'boxplot_category_gap', 1.0)
        bp_positions = [1 + i * bp_gap for i in range(len(data_by_atom))]
        bp_show_caps = getattr(cfg, 'boxplot_show_caps', True)
        bp_cap_width = getattr(cfg, 'boxplot_cap_width', 0.5)
        bp_whisker_color = getattr(cfg, 'boxplot_whisker_color', 'black')
        bp_whisker_width = getattr(cfg, 'boxplot_whisker_width', 1.0)
        bp_outlier_size = getattr(cfg, 'boxplot_outlier_size', 6.0)
        bp_edge_color = getattr(cfg, 'boxplot_edge_color', 'black')
        bp_edge_width = getattr(cfg, 'boxplot_edge_width', 1.0)
        bp_hatch = getattr(cfg, 'boxplot_hatch', None)
        bp_mean_marker = getattr(cfg, 'boxplot_mean_marker', 'D')
        bp_mean_color = getattr(cfg, 'boxplot_mean_color', 'red')
        bp_mean_size = getattr(cfg, 'boxplot_mean_size', 5.0)
        box_color = getattr(cfg, 'boxplot_color', '#3498db')
        alpha = getattr(cfg, 'boxplot_alpha', 0.6)
        meanprops = dict(marker=bp_mean_marker, markerfacecolor=bp_mean_color,
                         markeredgecolor=bp_mean_color, markersize=bp_mean_size)

        if len(workspaces) == 1:
            values = [charges[0] for charges in data_by_atom]
            if bp_horizontal:
                bars = self.ax.barh(bp_positions, values, height=bp_width,
                                    color=box_color, alpha=alpha,
                                    edgecolor=bp_edge_color, linewidth=bp_edge_width,
                                    label=workspaces[0])
                self.ax.set_yticks(bp_positions)
                self.ax.set_yticklabels(labels)
                self.ax.set_xlabel(cfg.y_label if cfg.y_label else "Bader 电荷")
            else:
                bars = self.ax.bar(bp_positions, values, width=bp_width,
                                   color=box_color, alpha=alpha,
                                   edgecolor=bp_edge_color, linewidth=bp_edge_width,
                                   label=workspaces[0])
                self.ax.set_xticks(bp_positions)
                self.ax.set_xticklabels(labels, rotation=cfg.x_tick_rotation)
                self.ax.set_ylabel(cfg.y_label if cfg.y_label else "Bader 电荷")
            if bp_hatch and bp_hatch != "无":
                for bar in bars:
                    bar.set_hatch(bp_hatch)
            for bar, atom_id in zip(bars, plotted_atom_ids):
                self._bar_to_atom_id[bar] = atom_id
            if getattr(cfg, 'boxplot_show_workspace_indicator', True) and workspaces:
                bp_ws_fs = getattr(cfg, 'boxplot_workspace_indicator_size', 9)
                bp_ws_text = "工作区: " + ", ".join(workspaces)
                self.figure.text(0.02, 0.98, bp_ws_text, ha='left', va='top',
                                 fontsize=bp_ws_fs, color='gray',
                                 bbox=dict(boxstyle='round,pad=0.3',
                                           facecolor='white', alpha=0.7,
                                           edgecolor='#CCCCCC'))
            if getattr(cfg, 'boxplot_show_legend', True):
                self.ax.legend(fontsize=cfg.legend_size)
            return

        bp_orientation = 'horizontal' if bp_horizontal else 'vertical'
        bp = self.ax.boxplot(data_by_atom, patch_artist=True, showmeans=show_mean,
                             whis=getattr(cfg, 'boxplot_whisker', 1.5),
                             notch=getattr(cfg, 'boxplot_notch', False),
                             showfliers=getattr(cfg, 'boxplot_show_outliers', True),
                             positions=bp_positions, orientation=bp_orientation,
                             widths=bp_width, showcaps=bp_show_caps,
                             capwidths=bp_cap_width, meanprops=meanprops)
        for patch in bp['boxes']:
            patch.set_facecolor(box_color)
            patch.set_alpha(alpha)
            patch.set_edgecolor(bp_edge_color)
            patch.set_linewidth(bp_edge_width)
            if bp_hatch and bp_hatch != "无":
                patch.set_hatch(bp_hatch)
        # Style median lines
        median_color = getattr(cfg, 'boxplot_median_color', 'black')
        median_width = getattr(cfg, 'boxplot_median_width', 2.0)
        plt.setp(bp['medians'], color=median_color, linewidth=median_width)
        # Style whiskers and caps
        plt.setp(bp['whiskers'], color=bp_whisker_color, linewidth=bp_whisker_width)
        plt.setp(bp['caps'], color=bp_whisker_color, linewidth=bp_whisker_width)
        # Style outlier markers
        outlier_marker = getattr(cfg, 'boxplot_outlier_marker', 'o')
        outlier_color = getattr(cfg, 'boxplot_outlier_color', 'red')
        plt.setp(bp['fliers'], marker=outlier_marker, color=outlier_color,
                 markersize=bp_outlier_size)
        # Violin overlay
        if getattr(cfg, 'boxplot_violin', False):
            try:
                violin_data = [d for d in data_by_atom if len(d) > 1]
                violin_positions = bp_positions
                violin_w_ratio = getattr(cfg, 'boxplot_violin_width_ratio', 0.8)
                if violin_data:
                    vp = self.ax.violinplot(violin_data, positions=violin_positions[:len(violin_data)],
                                            widths=bp_width * violin_w_ratio, vert=not bp_horizontal, showmeans=False,
                                            showmedians=False, showextrema=False)
                    for pc in vp['bodies']:
                        pc.set_alpha(getattr(cfg, 'boxplot_violin_alpha', 0.2))
                        pc.set_facecolor(box_color)
            except Exception:
                pass
        # Scatter points (jitter / swarm)
        bp_show_points = getattr(cfg, 'boxplot_show_points', '无')
        jitter_width = getattr(cfg, 'boxplot_jitter_width', 0.2)
        jitter_alpha = getattr(cfg, 'boxplot_jitter_alpha', 0.6)
        jitter_size = getattr(cfg, 'boxplot_jitter_size', 3.0)
        bp_point_color = getattr(cfg, 'boxplot_point_color', 'black')
        show_individual = getattr(cfg, 'boxplot_show_individual', True)
        if show_individual and bp_show_points in ("抖动", "蜂群"):
            for i, data in enumerate(data_by_atom):
                base_pos = bp_positions[i]
                if bp_show_points == "蜂群":
                    # Real beeswarm: sorted placement avoiding overlap
                    _sorted_idx = np.argsort(data)
                    _offsets = np.zeros(len(data))
                    _placed = []
                    _pt_gap = jitter_size * 0.015
                    for _si in _sorted_idx:
                        _v = data[_si]
                        _best_dx = 0.0
                        for _dx in np.linspace(0, jitter_width, 30):
                            for _sign in ([0] if _dx == 0 else [1, -1]):
                                _cand = _dx * _sign
                                if all(abs(_v - _pv) > _pt_gap
                                       or abs(_cand - _po) > _pt_gap
                                       for _pv, _po in _placed):
                                    _best_dx = _cand
                                    break
                            else:
                                continue
                            break
                        _offsets[_si] = _best_dx
                        _placed.append((_v, _best_dx))
                    jitter = _offsets
                else:
                    jitter = np.random.normal(0, jitter_width * 0.2, size=len(data))
                if bp_horizontal:
                    self.ax.scatter(data, np.full(len(data), base_pos) + jitter,
                                    alpha=jitter_alpha, s=jitter_size,
                                    color=bp_point_color, zorder=3)
                else:
                    self.ax.scatter(np.full(len(data), base_pos) + jitter, data,
                                    alpha=jitter_alpha, s=jitter_size,
                                    color=bp_point_color, zorder=3)
        if bp_horizontal:
            self.ax.set_yticks(bp_positions)
            self.ax.set_yticklabels(labels)
            self.ax.set_xlabel(cfg.y_label if cfg.y_label else "Bader 电荷分布")
        else:
            self.ax.set_xticks(bp_positions)
            self.ax.set_xticklabels(labels, rotation=cfg.x_tick_rotation)
            self.ax.set_ylabel(cfg.y_label if cfg.y_label else "Bader 电荷分布")
        # Workspace indicator
        if getattr(cfg, 'boxplot_show_workspace_indicator', True) and workspaces:
            bp_ws_fs = getattr(cfg, 'boxplot_workspace_indicator_size', 9)
            bp_ws_text = "工作区: " + ", ".join(workspaces)
            self.figure.text(0.02, 0.98, bp_ws_text, ha='left', va='top',
                             fontsize=bp_ws_fs, color='gray',
                             bbox=dict(boxstyle='round,pad=0.3',
                                       facecolor='white', alpha=0.7,
                                       edgecolor='#CCCCCC'))
        # Legend: show workspace names contributing to the distribution
        if getattr(cfg, 'boxplot_show_legend', True) and workspaces:
            from matplotlib.patches import Patch
            bp_leg_pos = getattr(cfg, 'boxplot_legend_position', '最佳')
            bp_loc_map = {"最佳": "best", "右上角": "upper right",
                          "左上角": "upper left", "右下角": "lower right",
                          "左下角": "lower left"}
            bp_proxy = [Patch(facecolor=getattr(cfg, 'boxplot_color', '#3498db'),
                              alpha=getattr(cfg, 'boxplot_alpha', 0.6),
                              label=ws) for ws in workspaces]
            self.ax.legend(handles=bp_proxy,
                           loc=bp_loc_map.get(bp_leg_pos, 'best'),
                           fontsize=cfg.legend_size)

    def _draw_heatmap(self, x_labels, all_atoms, element_map, workspaces, cfg):
        """Heatmap: atoms x workspaces charge matrix."""
        matrix = []
        row_labels = []
        for a_id in all_atoms:
            el = element_map.get(a_id, "X")
            row = []
            for ws in workspaces:
                df = self.current_data[ws]['df']
                if not df.empty:
                    m = df[df['Atom'] == a_id]
                    if not m.empty:
                        row.append(m.iloc[0]['Bader_Charge'])
                    else:
                        row.append(np.nan)
                else:
                    row.append(np.nan)
            matrix.append(row)
            row_labels.append(f"{el}{a_id}")
        if matrix:
            arr = np.array(matrix)

            # Row sorting
            hm_sort = getattr(cfg, 'heatmap_sort_rows', '默认')
            if hm_sort == "按总量":
                _row_totals = [np.nansum(np.abs(row)) for row in arr]
                _sort_idx = np.argsort(_row_totals)
                arr = arr[_sort_idx]
                row_labels = [row_labels[i] for i in _sort_idx]
            elif hm_sort == "按字母":
                _paired = list(zip(row_labels, arr))
                _paired.sort(key=lambda p: p[0])
                row_labels = [p[0] for p in _paired]
                arr = np.array([p[1] for p in _paired])

            cmap = getattr(cfg, 'heatmap_colormap', 'RdBu_r')
            aspect = HEATMAP_ASPECT_MAP.get(getattr(cfg, 'heatmap_aspect', '自动'), 'auto')

            # Normalize handling
            normalize = getattr(cfg, 'heatmap_normalize', '自动')
            norm = None
            vmin_kw = None
            vmax_kw = None
            if normalize == "对称发散":
                vmax_abs = float(np.nanmax(np.abs(arr)))
                vcenter_val = getattr(cfg, 'heatmap_vcenter', 0.0)
                if vmax_abs > 0:
                    norm = matplotlib.colors.TwoSlopeNorm(vmin=-vmax_abs, vcenter=vcenter_val, vmax=vmax_abs)
            elif normalize == "手动":
                vmin_kw = getattr(cfg, 'heatmap_vmin', 0.0)
                vmax_kw = getattr(cfg, 'heatmap_vmax', 0.0)

            # Interpolation
            interp_map = {"最近邻": "nearest", "双线性": "bilinear", "双三次": "bicubic"}
            hm_interp = getattr(cfg, 'heatmap_interpolation', '最近邻')
            interp_val = interp_map.get(hm_interp, "nearest")

            # NaN color: use masked array and set_bad
            hm_nan_color = getattr(cfg, 'heatmap_nan_color', '#E0E0E0')
            cmap_obj = plt.get_cmap(cmap)
            cmap_obj.set_bad(color=hm_nan_color)
            masked_arr = np.ma.masked_invalid(arr)

            # Cell border handling
            im_kw = dict(aspect=aspect, cmap=cmap_obj, interpolation=interp_val)
            if norm is not None:
                im_kw['norm'] = norm
            if vmin_kw is not None:
                im_kw['vmin'] = vmin_kw
            if vmax_kw is not None:
                im_kw['vmax'] = vmax_kw
            if getattr(cfg, 'heatmap_cell_border', False):
                im_kw['edgecolors'] = getattr(cfg, 'heatmap_cell_border_color', 'white')
                im_kw['linewidths'] = getattr(cfg, 'heatmap_cell_border_width', 0.5)

            im = self.ax.imshow(masked_arr, **im_kw)
            # Colorbar
            if getattr(cfg, 'heatmap_colorbar', True):
                cb_label = getattr(cfg, 'heatmap_colorbar_label', 'Bader 电荷')
                cb_pos = getattr(cfg, 'heatmap_colorbar_position', '右侧')
                cb_shrink = getattr(cfg, 'heatmap_colorbar_shrink', 1.0)
                cb_pad = getattr(cfg, 'heatmap_colorbar_pad', 0.05)
                cb_fs = getattr(cfg, 'heatmap_colorbar_fontsize', 10)
                cb_ticks_n = getattr(cfg, 'heatmap_colorbar_ticks', 0)
                cb_kw = dict(shrink=cb_shrink, pad=cb_pad)
                if cb_ticks_n > 0:
                    from matplotlib.ticker import MaxNLocator
                    cb_kw['ticks'] = MaxNLocator(nbins=cb_ticks_n)
                if cb_pos == "底部":
                    cbar = self.figure.colorbar(im, ax=self.ax, label=cb_label,
                                         orientation='horizontal', pad=0.15, **cb_kw)
                else:
                    cbar = self.figure.colorbar(im, ax=self.ax, label=cb_label, **cb_kw)
                cbar.ax.tick_params(labelsize=cb_fs)
                cb_label_fs = getattr(cfg, 'heatmap_colorbar_label_size', 10)
                cbar.set_label(cb_label, fontsize=cb_label_fs)
            self.ax.set_xticks(range(len(workspaces)))
            self.ax.set_xticklabels(workspaces, rotation=cfg.x_tick_rotation)
            self.ax.set_yticks(range(len(row_labels)))
            self.ax.set_yticklabels(row_labels)
            if getattr(cfg, 'heatmap_show_x_label', True):
                self.ax.set_xlabel(getattr(cfg, 'heatmap_x_label', '工作区'))
            if getattr(cfg, 'heatmap_show_y_label', True):
                self.ax.set_ylabel(getattr(cfg, 'heatmap_y_label', '原子'))
            # Optional value display
            if getattr(cfg, 'heatmap_show_values', False):
                fmt = getattr(cfg, 'heatmap_value_format', '.2f')
                fsize = getattr(cfg, 'heatmap_value_size', 8)
                hm_txt_color = getattr(cfg, 'heatmap_value_text_color', 'auto')
                hm_txt_bg_alpha = getattr(cfg, 'heatmap_value_bg_alpha', 0.0)
                hm_val_weight = getattr(cfg, 'heatmap_value_font_weight', 'normal')
                hm_val_rot = getattr(cfg, 'heatmap_value_rotation', 0)
                _arr_max = np.nanmax(np.abs(arr))
                _txt_bbox = dict(boxstyle='round,pad=0.15', facecolor='white',
                                 alpha=hm_txt_bg_alpha, edgecolor='none') if hm_txt_bg_alpha > 0 else None
                for i in range(len(row_labels)):
                    for j in range(len(workspaces)):
                        v = arr[i, j]
                        if not np.isnan(v):
                            if hm_txt_color == "auto":
                                _tc = "white" if abs(v) > _arr_max * 0.6 else "black"
                            else:
                                _tc = hm_txt_color
                            self.ax.text(j, i, f"{v:{fmt}}", ha="center", va="center",
                                         fontsize=fsize, color=_tc, fontweight=hm_val_weight,
                                         rotation=hm_val_rot,
                                         bbox=_txt_bbox)

    def _draw_radar(self, x_labels, all_atoms, element_map, workspaces, cfg):
        """Radar chart: polar plot of charges."""
        if not workspaces or not all_atoms:
            return
        max_atoms = getattr(cfg, 'radar_max_atoms', 12)
        line_color = getattr(cfg, 'radar_line_color', '#1f77b4')
        line_width = getattr(cfg, 'radar_line_width', 2.0)
        fill_alpha = getattr(cfg, 'radar_fill_alpha', 0.25)
        marker_size = getattr(cfg, 'radar_marker_size', 6.0)
        marker_style = getattr(cfg, 'radar_marker_style', 'o')
        grid_rings = getattr(cfg, 'radar_grid_rings', 4)
        start_angle = getattr(cfg, 'radar_start_angle', 90)
        show_values = getattr(cfg, 'radar_show_values', False)
        radar_fill_color = getattr(cfg, 'radar_fill_color', '')
        radar_show_rings = getattr(cfg, 'radar_show_rings_labels', True)
        radar_clockwise = getattr(cfg, 'radar_clockwise', False)
        radar_spoke_size = getattr(cfg, 'radar_spoke_label_size', 10)
        radar_line_style = getattr(cfg, 'radar_line_style', '-')
        radar_grid_shape = getattr(cfg, 'radar_grid_shape', '多边形')
        radar_value_fs = getattr(cfg, 'radar_value_font_size', 8)
        radar_scale_max_val = getattr(cfg, 'radar_scale_max', 0.0)
        radar_value_fmt = getattr(cfg, 'radar_value_format', '.2f')
        radar_grid_color = getattr(cfg, 'radar_grid_color', 'gray')
        radar_grid_width = getattr(cfg, 'radar_grid_width', 0.5)
        radar_grid_alpha = getattr(cfg, 'radar_grid_alpha', 0.4)
        radar_grid_style = getattr(cfg, 'radar_grid_style', '--')
        radar_scale_padding = getattr(cfg, 'radar_scale_padding', 1.2)
        radar_spoke_dist = getattr(cfg, 'radar_spoke_label_distance', 1.15)
        radar_fill_edge_w = getattr(cfg, 'radar_fill_edge_width', 0.0)
        radar_fill_edge_c = getattr(cfg, 'radar_fill_edge_color', '')

        # Use first workspace for labels, draw all workspaces
        ws0 = workspaces[0]
        df0 = self.current_data[ws0]['df']
        if df0.empty:
            return
        charges0 = []
        labels = []
        for a_id in all_atoms[:max_atoms]:
            el = element_map.get(a_id, "X")
            m = df0[df0['Atom'] == a_id]
            if not m.empty:
                charges0.append(m.iloc[0]['Bader_Charge'])
                labels.append(f"{el}{a_id}")
        if not charges0:
            return
        n = len(charges0)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()

        # Apply start angle offset
        theta_offset = np.radians(start_angle - 90)
        angles_shifted = [a + theta_offset for a in angles]

        # Clockwise: reverse theta direction
        if radar_clockwise:
            angles_shifted = [-a for a in angles_shifted]

        # Grid rings
        if radar_scale_max_val > 0:
            max_val = radar_scale_max_val
        else:
            max_val = max(abs(v) for v in charges0 if not np.isnan(v)) * radar_scale_padding if any(not np.isnan(v) for v in charges0) else 1.0
        ring_vals = np.linspace(0, max_val, grid_rings + 1)[1:] if grid_rings > 0 else np.array([])
        ring_label_fmt = getattr(cfg, 'radar_ring_label_format', '.2f')
        ring_labels = [f"{v:{ring_label_fmt}}" for v in ring_vals] if radar_show_rings and grid_rings > 0 else [''] * max(grid_rings, 1) if grid_rings > 0 else []
        if grid_rings > 0:
            self.ax.set_rgrids(ring_vals, labels=ring_labels, angle=angles_shifted[0])

        label_pad_pts = max(0, (radar_spoke_dist - 1.0) * 72)

        # Circular grid shape
        if radar_grid_shape == "圆形":
            self.ax.set_thetagrids(np.degrees(angles_shifted), labels=labels,
                                   fontsize=radar_spoke_size)
            self.ax.grid(False)
            theta_full = np.linspace(0, 2 * np.pi, 360)
            for rv in ring_vals:
                self.ax.plot(theta_full, [rv] * len(theta_full),
                             linestyle=radar_grid_style, alpha=radar_grid_alpha,
                             color=radar_grid_color, linewidth=radar_grid_width)

        # Draw each workspace
        palette = getattr(self, '_expanded_colors', None) or PALETTES.get(cfg.theme, PALETTES.get("Origin Classic"))
        for wi, ws in enumerate(workspaces):
            df = self.current_data[ws]['df']
            charges = []
            for a_id in all_atoms[:max_atoms]:
                m = df[df['Atom'] == a_id]
                if not m.empty:
                    charges.append(m.iloc[0]['Bader_Charge'])
                else:
                    charges.append(np.nan)
            if len(charges) != n:
                continue
            if len(workspaces) > 1:
                c = palette[wi % len(palette)]
            else:
                c = line_color
            fill_c = radar_fill_color if radar_fill_color else c
            fill_edge_c = radar_fill_edge_c if radar_fill_edge_c else c
            charges_closed = charges + [charges[0]]
            angles_closed = angles_shifted + [angles_shifted[0]]
            self.ax.plot(angles_closed, charges_closed,
                         marker=marker_style, linestyle=radar_line_style, linewidth=line_width,
                         color=c, markersize=marker_size, label=ws)
            self.ax.fill(angles_closed, charges_closed, alpha=fill_alpha, color=fill_c,
                         linewidth=radar_fill_edge_w, edgecolor=fill_edge_c if radar_fill_edge_w > 0 else 'none')
            # Show values annotation
            if show_values:
                for ai, (ang, ch) in enumerate(zip(angles_shifted, charges)):
                    if not np.isnan(ch):
                        self.ax.annotate(f"{ch:{radar_value_fmt}}", xy=(ang, ch),
                                         fontsize=radar_value_fs, ha='center', va='bottom',
                                         color=c)
        # Spoke label visibility
        show_spokes = getattr(cfg, 'radar_show_spoke_labels', True)
        self.ax.set_xticks(angles_shifted)
        if show_spokes:
            self.ax.set_xticklabels(labels, fontsize=radar_spoke_size)
        else:
            self.ax.set_xticklabels([''] * len(labels))
        if label_pad_pts > 0:
            self.ax.tick_params(axis='x', pad=label_pad_pts)
        # Title
        radar_title_text = getattr(cfg, 'radar_title', '电荷分布')
        radar_show_title = getattr(cfg, 'radar_show_title', True)
        if radar_show_title and radar_title_text:
            radar_title_fs = getattr(cfg, 'radar_title_size', 14)
            self.ax.set_title(radar_title_text, fontsize=radar_title_fs)
        # Legend with configurable position and size
        if len(workspaces) > 1:
            _position = "右侧外部" if getattr(cfg, 'radar_legend_outside', True) else getattr(cfg, 'legend_position', '最佳')
            if _position != "隐藏":
                if _position in ("右侧外部", "底部外部"):
                    _bbox, _loc = self._legend_external_layout(cfg, _position)
                    leg = self.ax.legend(bbox_to_anchor=_bbox, loc=_loc,
                                         **self._legend_kwargs(cfg, _position))
                else:
                    _loc_map = {"最佳": "best", "右上": "upper right", "左上": "upper left"}
                    leg = self.ax.legend(loc=_loc_map.get(_position, "best"),
                                         **self._legend_kwargs(cfg, _position))
                self._style_legend(leg, cfg)

    def _draw_pie(self, cfg, all_atoms, element_map, workspaces):
        """Draw pie or donut chart of absolute Bader charges."""
        # Collect data: sum |charge| per atom across workspaces
        labels = []
        values = []
        for a_id in all_atoms:
            total = 0.0
            for ws in workspaces:
                df = self.current_data[ws]['df']
                if not df.empty:
                    m = df[df['Atom'] == a_id]
                    if not m.empty:
                        v = m.iloc[0]['Bader_Charge']
                        if not np.isnan(v):
                            total += abs(v)
            if total > 0:
                el = element_map.get(a_id, 'X')
                labels.append(f"{el}{a_id}")
                values.append(total)

        if not values:
            self.ax.text(0.5, 0.5, "无数据", ha='center', va='center',
                         transform=self.ax.transAxes, fontsize=14, color='gray')
            return

        # Merge small slices into "其他"
        total_sum = sum(values)
        min_pct = cfg.pie_min_slice
        merged_labels = []
        merged_values = []
        other_sum = 0.0
        for lbl, val in zip(labels, values):
            pct = val / total_sum * 100
            if pct < min_pct:
                other_sum += val
            else:
                merged_labels.append(lbl)
                merged_values.append(val)
        if other_sum > 0:
            merged_labels.append("其他")
            merged_values.append(other_sum)

        # Explode
        pie_explode_offset = getattr(cfg, 'pie_explode_offset', 0.1)
        explode = None
        if cfg.pie_explode_largest and merged_values:
            max_idx = merged_values.index(max(merged_values))
            explode = [pie_explode_offset if i == max_idx else 0 for i in range(len(merged_values))]

        # Sort slices
        pie_sort = getattr(cfg, 'pie_sort', '默认')
        if pie_sort == "按大小升序" and merged_values:
            _paired = sorted(zip(merged_values, merged_labels), key=lambda p: p[0])
            merged_values = [p[0] for p in _paired]
            merged_labels = [p[1] for p in _paired]
            if explode:
                explode = [0] * len(merged_values)
                max_idx = merged_values.index(max(merged_values))
                explode[max_idx] = pie_explode_offset
        elif pie_sort == "按大小降序" and merged_values:
            _paired = sorted(zip(merged_values, merged_labels), key=lambda p: p[0], reverse=True)
            merged_values = [p[0] for p in _paired]
            merged_labels = [p[1] for p in _paired]
            if explode:
                explode = [0] * len(merged_values)
                max_idx = merged_values.index(max(merged_values))
                explode[max_idx] = pie_explode_offset

        # Colors from theme (expanded for distinct colors)
        _ec = getattr(self, '_expanded_colors', None) or PALETTES.get(cfg.theme, PALETTES.get("Origin Classic"))
        pie_colors = [_ec[i % len(_ec)] for i in range(len(merged_values))]

        # Wedge properties
        pie_gap = getattr(cfg, 'pie_gap', 0.0)
        pie_edge_width = getattr(cfg, 'pie_edge_width', 1.0)
        wedge_width = 1.0 - cfg.pie_inner_radius if cfg.pie_mode == "环形图" else 1.0
        wedgeprops = dict(width=wedge_width, edgecolor=cfg.pie_edge_color, linewidth=pie_edge_width)
        if pie_gap > 0:
            wedgeprops['linewidth'] = pie_gap * 20

        # Label format
        pie_label_size = getattr(cfg, 'pie_label_size', 10)
        pie_pct_precision = getattr(cfg, 'pie_pct_precision', 1)
        pie_label_dist = getattr(cfg, 'pie_label_distance', 1.1)
        pie_pct_dist = getattr(cfg, 'pie_pct_distance', 0.6)
        pie_counterclockwise = getattr(cfg, 'pie_counterclockwise', True)
        autopct = None
        labels_to_use = merged_labels
        if cfg.pie_label_position == "图例":
            labels_to_use = [''] * len(merged_values)
            autopct = None
        elif cfg.pie_label_format == "百分比":
            if getattr(cfg, 'pie_show_percentage_symbol', True):
                autopct = f'%1.{pie_pct_precision}f%%'
            else:
                autopct = f'%1.{pie_pct_precision}f'
        elif cfg.pie_label_format == "数值":
            autopct = lambda p: f'{p * total_sum / 100:.2f}'
        else:  # "两者"
            autopct = lambda p: f'{p:.{pie_pct_precision}f}%\n({p * total_sum / 100:.2f})'

        pie_shadow = getattr(cfg, 'pie_shadow', False)
        pie_result = self.ax.pie(
            merged_values, labels=labels_to_use, autopct=autopct,
            colors=pie_colors, explode=explode,
            startangle=cfg.pie_start_angle,
            wedgeprops=wedgeprops,
            textprops={'fontsize': pie_label_size},
            shadow=pie_shadow,
            labeldistance=pie_label_dist,
            pctdistance=pie_pct_dist,
            counterclock=pie_counterclockwise,
        )
        if len(pie_result) == 3:
            wedges, texts, autotexts = pie_result
        else:
            wedges, texts = pie_result
            autotexts = []

        if getattr(cfg, 'pie_show_leader_lines', False) and cfg.pie_label_position != "图例":
            for wedge, text in zip(wedges, texts):
                theta = np.deg2rad((wedge.theta1 + wedge.theta2) / 2.0)
                radius = 1.0
                x0, y0 = np.cos(theta) * radius, np.sin(theta) * radius
                x1, y1 = text.get_position()
                self.ax.plot([x0, x1], [y0, y1],
                             color=getattr(cfg, 'pie_edge_color', 'gray'),
                             linewidth=0.8, alpha=0.7)

        if autotexts:
            pie_pct_color = getattr(cfg, 'pie_pct_color', 'auto')
            for at in autotexts:
                at.set_fontsize(pie_label_size - 1)
                if pie_pct_color != "auto":
                    at.set_color(pie_pct_color)

        # Center label
        pie_center_label = getattr(cfg, 'pie_center_label', '')
        if pie_center_label:
            center_fs = getattr(cfg, 'pie_center_label_size', 14)
            center_lbl_color = getattr(cfg, 'pie_center_label_color', 'black')
            self.ax.text(0, 0, pie_center_label, ha='center', va='center',
                         fontsize=center_fs, weight='bold', color=center_lbl_color)

        # Legend if label_position is "图例"
        if cfg.pie_label_position == "图例":
            legend_labels = [f"{lbl} ({val:.2f})" for lbl, val in zip(merged_labels, merged_values)]
            _position = "右侧外部" if getattr(cfg, 'pie_legend_outside', True) else getattr(cfg, 'legend_position', '最佳')
            if _position != "隐藏":
                if _position in ("右侧外部", "底部外部"):
                    _bbox, _loc = self._legend_external_layout(cfg, _position)
                    leg = self.ax.legend(wedges, legend_labels, bbox_to_anchor=_bbox,
                                         loc=_loc, **self._legend_kwargs(cfg, _position))
                else:
                    _loc_map = {"最佳": "best", "右上": "upper right", "左上": "upper left"}
                    leg = self.ax.legend(wedges, legend_labels,
                                         loc=_loc_map.get(_position, "best"),
                                         **self._legend_kwargs(cfg, _position))
                self._style_legend(leg, cfg)

        # Title
        pie_show_title = getattr(cfg, 'pie_show_title', True)
        if pie_show_title:
            title = cfg.fig_title if cfg.fig_title else getattr(cfg, 'pie_title', 'Bader 电荷分布')
            pie_title_fs = getattr(cfg, 'pie_title_size', 14)
            pie_title_w = getattr(cfg, 'pie_title_weight', 'bold')
            self.ax.set_title(title, fontsize=pie_title_fs, weight=pie_title_w)

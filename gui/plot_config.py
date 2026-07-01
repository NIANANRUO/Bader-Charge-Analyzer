# -*- coding: utf-8 -*-
import dataclasses
import json

SUPPORTED_PLOT_TYPES = {
    "分组柱状图", "水平柱状图", "折线图", "散点图",
    "箱线图", "热力图", "雷达图", "饼图",
}
DEPRECATED_PLOT_TYPES = {"堆叠柱状图", "面积图", "瀑布图"}
PLOT_TYPE_FALLBACK = "分组柱状图"


@dataclasses.dataclass
class PlotConfig:
    plot_type: str = "分组柱状图"
    group_logic: str = "X=体系, 柱=原子"
    filter_threshold: float = 0.0
    show_top_n: int = 0

    fig_title: str = ""

    x_label: str = "工作区 (体系)"
    y_label: str = "Bader 电荷 (e)"

    y_min: float = 0.0
    y_max: float = 0.0
    y_step: float = 0.0

    x_scale: str = "线性"
    y_scale: str = "线性"
    tick_direction: str = "向外"
    x_tick_rotation: int = 0
    y_symmetric: bool = True
    show_top_right_spines: bool = True
    show_x_label: bool = True
    show_y_label: bool = True
    tick_format: str = "自动"
    tick_decimals: int = 2
    scientific_notation: bool = False
    minor_ticks_count: int = 0
    axis_break: bool = False
    axis_break_pos: float = 0.0
    axis_break_range_low: float = 0.0
    axis_break_range_high: float = 0.0
    panel_layout: str = "单面板"
    panel_views: str = "相同"

    figure_margin_left: float = 0.0
    figure_margin_right: float = 0.0
    figure_margin_top: float = 0.0
    figure_margin_bottom: float = 0.0
    axes_label_pad: float = 4.0
    title_position: str = "顶部居中"
    title_pad: float = 12.0

    show_y_major_grid: bool = True
    show_y_minor_grid: bool = False
    show_x_major_grid: bool = False
    grid_style: str = "--"
    grid_alpha: float = 0.5
    grid_color: str = "#CCCCCC"
    grid_width: float = 0.5

    show_zero_line: bool = True
    zero_line_color: str = "black"
    show_ref_05: bool = False
    show_ref_10: bool = False
    show_highlight_span: bool = False

    spine_width: float = 1.0
    spine_color: str = "black"

    theme: str = "红白蓝电荷图"
    hatch_style: str = None
    bar_width: int = 80
    edge_color: str = "none"
    edge_width: float = 0.0
    line_style: str = "-"
    line_width: float = 1.5
    marker_style: str = "o"
    marker_size: float = 6.0

    trend_line: str = "无"
    trend_line_degree: int = 1

    legend_position: str = "最佳"
    legend_frame: bool = True

    show_data_labels: str = "仅极值"
    label_threshold: float = 0.5
    font_family: str = "Arial"
    font_size: int = 12

    axis_label_font: str = "Arial"
    axis_label_size: int = 12
    tick_label_font: str = "Arial"
    tick_label_size: int = 10
    data_label_font: str = "Arial"
    data_label_size: int = 10
    legend_font: str = "Arial"
    legend_size: int = 10

    data_label_offset: float = 5.0
    data_label_rotation: int = 0

    data_label_format: str = "固定小数"
    data_label_decimals: int = 3
    data_label_positive_color: str = "auto"
    data_label_negative_color: str = "auto"
    data_label_avoid_overlap: bool = False

    major_tick_length: float = 3.5
    minor_tick_length: float = 2.0
    tick_width: float = 0.8
    tick_sides: str = "默认"

    bold_ax_lbl: bool = False
    bold_ticks: bool = False
    bold_data: bool = False
    custom_legend: str = ""

    legend_columns: int = 1
    legend_alpha: float = 1.0
    legend_title: str = ""
    legend_handle_length: float = 2.0
    legend_border_pad: float = 0.4
    legend_external_anchor: str = "右侧中"

    show_error_bars: bool = False
    error_bar_type: str = "固定 5%"

    annotation_text: str = ""
    annotation_pos_x: float = 0.05
    annotation_pos_y: float = 0.95
    latex_rendering: bool = False
    series_colors: dict = dataclasses.field(default_factory=dict)
    journal_preset: str = "自定义"
    realtime_preview: bool = False
    export_dpi: int = 300
    export_width: float = 8.0
    export_height: float = 6.0
    export_transparent: bool = False

    # ── Chart-type-specific settings ──

    # Waterfall
    waterfall_pos_color: str = "#2ecc71"
    waterfall_neg_color: str = "#e74c3c"
    waterfall_connectors: bool = True
    waterfall_atom_id: int = 0  # 0 = auto (first atom in sorted list)
    waterfall_bar_width: float = 0.6
    waterfall_edge_color: str = "black"
    waterfall_edge_width: float = 0.5
    waterfall_sort: str = "默认"          # 默认 / 按电荷排序 / 按元素
    waterfall_show_total: bool = True
    waterfall_connector_style: str = "-"
    waterfall_connector_color: str = "black"
    waterfall_connector_width: float = 0.5
    waterfall_connector_alpha: float = 0.3
    waterfall_show_labels: bool = False
    waterfall_total_color: str = "#3498db"
    waterfall_zero_line_color: str = "black"
    waterfall_zero_line_width: float = 1.0
    waterfall_label_format: str = ".2f"
    waterfall_label_font: str = "Arial"
    waterfall_label_weight: str = "normal"
    waterfall_hatch: str = "无"
    waterfall_bar_round: float = 0.0
    waterfall_cumulative_line: bool = False
    waterfall_cumulative_color: str = "black"
    waterfall_cumulative_width: float = 1.5
    waterfall_pct_mode: bool = False

    # Box Plot
    boxplot_color: str = "#3498db"
    boxplot_show_mean: bool = True
    boxplot_alpha: float = 0.6
    boxplot_max_atoms: int = 20
    boxplot_whisker: float = 1.5
    boxplot_notch: bool = False
    boxplot_median_color: str = "black"
    boxplot_median_width: float = 2.0
    boxplot_outlier_marker: str = "o"
    boxplot_outlier_color: str = "red"
    boxplot_show_outliers: bool = True
    boxplot_show_points: str = "无"          # 无 / 抖动 / 蜂群
    boxplot_violin: bool = False
    boxplot_cap_width: float = 0.5
    boxplot_show_caps: bool = True
    boxplot_width: float = 0.5
    boxplot_whisker_color: str = "black"
    boxplot_jitter_width: float = 0.2
    boxplot_jitter_alpha: float = 0.6
    boxplot_jitter_size: float = 3.0
    boxplot_violin_alpha: float = 0.2
    boxplot_show_individual: bool = True
    boxplot_point_color: str = "black"
    boxplot_violin_width_ratio: float = 0.8
    boxplot_whisker_width: float = 1.0
    boxplot_outlier_size: float = 6.0
    boxplot_mean_marker: str = "D"
    boxplot_mean_color: str = "red"
    boxplot_mean_size: float = 5.0
    boxplot_edge_color: str = "black"
    boxplot_edge_width: float = 1.0
    boxplot_hatch: str = "无"
    boxplot_orientation: str = "垂直"
    boxplot_category_gap: float = 1.0
    boxplot_show_workspace_indicator: bool = True
    boxplot_workspace_indicator_size: int = 9
    boxplot_show_legend: bool = True
    boxplot_legend_position: str = "最佳"

    # Heatmap
    heatmap_colormap: str = "RdBu_r"
    heatmap_show_values: bool = False
    heatmap_value_format: str = ".2f"
    heatmap_value_size: int = 8
    heatmap_aspect: str = "自动"
    heatmap_normalize: str = "自动"       # 自动 / 对称发散 / 手动
    heatmap_vmin: float = 0.0
    heatmap_vmax: float = 0.0
    heatmap_cell_border: bool = False
    heatmap_cell_border_color: str = "white"
    heatmap_colorbar: bool = True
    heatmap_colorbar_label: str = "Bader 电荷"
    heatmap_interpolation: str = "最近邻"    # 最近邻 / 双线性 / 双三次
    heatmap_nan_color: str = "#E0E0E0"
    heatmap_sort_rows: str = "默认"          # 默认 / 按总量 / 按字母
    heatmap_cell_border_width: float = 0.5
    heatmap_value_text_color: str = "auto"
    heatmap_value_bg_alpha: float = 0.0
    heatmap_colorbar_position: str = "右侧"  # 右侧 / 底部
    heatmap_vcenter: float = 0.0
    heatmap_colorbar_shrink: float = 1.0
    heatmap_colorbar_pad: float = 0.05
    heatmap_colorbar_fontsize: int = 10
    heatmap_colorbar_ticks: int = 0
    heatmap_value_font_weight: str = "normal"
    heatmap_value_rotation: int = 0
    heatmap_x_label: str = "工作区"
    heatmap_y_label: str = "原子"
    heatmap_show_x_label: bool = True
    heatmap_show_y_label: bool = True
    heatmap_colorbar_label_size: int = 10

    # Radar
    radar_line_color: str = "#1f77b4"
    radar_line_width: float = 2.0
    radar_fill_alpha: float = 0.25
    radar_marker_size: float = 6.0
    radar_max_atoms: int = 12
    radar_grid_shape: str = "多边形"     # 多边形 / 圆形
    radar_grid_rings: int = 4
    radar_marker_style: str = "圆形"     # 复用 MARKER_MAP 键名
    radar_start_angle: int = 90
    radar_show_values: bool = False
    radar_fill_color: str = ""               # 空 = 使用线条颜色
    radar_show_rings_labels: bool = True
    radar_clockwise: bool = False
    radar_spoke_label_size: int = 10
    radar_line_style: str = "-"
    radar_value_font_size: int = 8
    radar_scale_max: float = 0.0
    radar_value_format: str = ".2f"
    radar_grid_color: str = "gray"
    radar_grid_width: float = 0.5
    radar_grid_alpha: float = 0.4
    radar_grid_style: str = "--"
    radar_legend_position: str = "最佳"
    radar_legend_size: int = 8
    radar_scale_padding: float = 1.2
    radar_spoke_label_distance: float = 1.15
    radar_fill_edge_width: float = 0.0
    radar_fill_edge_color: str = ""
    radar_legend_outside: bool = True
    radar_title: str = "电荷分布"
    radar_show_title: bool = True
    radar_title_size: int = 14
    radar_show_spoke_labels: bool = True
    radar_ring_label_format: str = ".2f"

    # Area
    area_alpha: float = 0.3
    area_mode: str = "堆叠"          # 堆叠 / 重叠 / 100% 归一化
    area_interpolation: str = "线性"  # 线性 / 阶梯
    area_edge_line: bool = True
    area_edge_width: float = 1.0
    area_edge_style: str = "-"
    area_order: str = "默认"          # 默认 / 按总量升序 / 按总量降序
    area_gradient: bool = False
    area_negative: bool = True

    # Pie
    pie_mode: str = "饼图"              # 饼图 / 环形图
    pie_inner_radius: float = 0.0
    pie_start_angle: int = 90
    pie_label_position: str = "外部"   # 外部 / 内部 / 图例
    pie_label_format: str = "百分比"   # 百分比 / 数值 / 两者
    pie_min_slice: float = 2.0
    pie_explode_largest: bool = False
    pie_edge_color: str = "white"
    pie_center_label: str = ""
    pie_explode_offset: float = 0.1
    pie_gap: float = 0.0
    pie_shadow: bool = False
    pie_sort: str = "默认"            # 默认 / 按大小升序 / 按大小降序
    pie_label_size: int = 10
    pie_center_label_size: int = 14
    pie_show_percentage_symbol: bool = True
    pie_pct_precision: int = 1
    pie_legend_position: str = "最佳"
    pie_label_distance: float = 1.1
    pie_pct_distance: float = 0.6
    pie_edge_width: float = 1.0
    pie_counterclockwise: bool = True
    pie_pct_color: str = "auto"
    pie_center_label_color: str = "black"
    pie_show_leader_lines: bool = False
    pie_legend_outside: bool = True
    pie_title: str = "Bader 电荷分布"
    pie_show_title: bool = True
    pie_title_size: int = 14
    pie_title_weight: str = "bold"
    pie_show_workspace_indicator: bool = True
    pie_workspace_indicator_size: int = 9

    def to_dict(self):
        self._normalize()
        return dataclasses.asdict(self)

    def from_dict(self, d):
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self._normalize()

    def _normalize(self):
        if self.plot_type in DEPRECATED_PLOT_TYPES or self.plot_type not in SUPPORTED_PLOT_TYPES:
            self.plot_type = PLOT_TYPE_FALLBACK

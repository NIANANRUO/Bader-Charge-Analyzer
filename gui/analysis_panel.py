# -*- coding: utf-8 -*-
from copy import deepcopy

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QRadioButton, QButtonGroup, 
                               QPushButton, QCheckBox, QScrollArea, QFrame, QComboBox, QSlider,
                               QColorDialog, QTableWidget, QTableWidgetItem, QHeaderView)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
import qtawesome as qta
from gui.analysis_dialogs import FragmentAnalysisDialog, WorkspaceTargetDialog
from gui.components.collapsible import CollapsiblePanel

class AnalysisPanel(QWidget):
    request_calculation = Signal(dict)
    draft_scope_changed = Signal(str)
    request_export_csv = Signal()
    request_export_full_csv = Signal()
    request_export_image = Signal()
    request_export_fragments = Signal()
    workspace_targets_changed = Signal(dict)
    fragments_changed = Signal(dict, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_workspaces = []
        self._current_workspace = None
        self._workspace_targets = {}
        self._fragments = {}
        self._fragment_results = []
        self._committed_scope = None
        self._committed_atom_count = None
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        scroll = QScrollArea()
        self.scroll_area = scroll
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 1. File Status
        grp_file = CollapsiblePanel("1. 文件状态")
        self.lbl_file_status = QLabel("未选择工作区")
        self.lbl_file_status.setStyleSheet("color: #666;")
        grp_file.addWidget(self.lbl_file_status)
        layout.addWidget(grp_file)
        
        # 2. Valence Settings
        grp_zval = CollapsiblePanel("2. 价电子 (ZVAL)")
        self.bg_zval = QButtonGroup(self)
        
        self.rad_auto = QRadioButton("自动读取（推荐）")
        self.rad_auto.setChecked(True)
        self.rad_manual = QRadioButton("手动输入 ZVAL")
        
        self.bg_zval.addButton(self.rad_auto)
        self.bg_zval.addButton(self.rad_manual)
        
        self.txt_manual_zval = QLineEdit()
        self.txt_manual_zval.setPlaceholderText("例如，C 4, O 6")
        self.txt_manual_zval.setVisible(False)
        self.rad_manual.toggled.connect(self.txt_manual_zval.setVisible)
        
        grp_zval.addWidget(self.rad_auto)
        grp_zval.addWidget(self.rad_manual)
        grp_zval.addWidget(self.txt_manual_zval)
        layout.addWidget(grp_zval)
        
        # 3. Target
        grp_target = CollapsiblePanel("3. 分析目标")
        grp_target.addWidget(QLabel("目标原子："))
        self.line_target = QLineEdit()
        self.line_target.setPlaceholderText("例如 1-10, 15")
        self.line_target.textChanged.connect(self._on_draft_scope_changed)
        grp_target.addWidget(self.line_target)

        self.btn_use_all_atoms = QPushButton("使用全部原子")
        self.btn_use_all_atoms.clicked.connect(self.use_all_atoms)
        grp_target.addWidget(self.btn_use_all_atoms)

        self.lbl_target_scope = QLabel("当前生效：尚未分析")
        self.lbl_target_scope.setStyleSheet("color: #555;")
        self.lbl_target_scope.setWordWrap(True)
        self.lbl_active_scope = self.lbl_target_scope
        grp_target.addWidget(self.lbl_target_scope)

        self.lbl_selection_summary = QLabel("未选择工作区")
        self.lbl_selection_summary.setStyleSheet("color: #666;")
        self.lbl_selection_summary.setWordWrap(True)
        grp_target.addWidget(self.lbl_selection_summary)

        self.btn_edit_targets = QPushButton(" 批量设置目标")
        self.btn_edit_targets.setIcon(qta.icon("fa5s.edit"))
        self.btn_edit_targets.setToolTip("为每个已选工作区设置独立的目标原子表达式")
        self.btn_edit_targets.clicked.connect(self.open_target_dialog)
        self.btn_edit_targets.setVisible(False)
        grp_target.addWidget(self.btn_edit_targets)

        # Kept for backward-compatible calculation configuration migration.
        self.line_fragment = QLineEdit()
        self.line_fragment.setVisible(False)
        self.lbl_advanced_analysis = QLabel("高级分析（可选）")
        self.lbl_advanced_analysis.setStyleSheet("font-weight: bold; margin-top: 8px;")
        grp_target.addWidget(self.lbl_advanced_analysis)
        self.lbl_fragment_summary = QLabel("尚未定义片段")
        self.lbl_fragment_summary.setStyleSheet("color: #666;")
        self.lbl_fragment_summary.setWordWrap(True)
        grp_target.addWidget(self.lbl_fragment_summary)

        self.btn_manage_fragments = QPushButton(" 管理片段")
        self.btn_manage_fragments.setIcon(qta.icon("fa5s.layer-group"))
        self.btn_manage_fragments.clicked.connect(self.open_fragment_dialog)
        self.btn_manage_fragments.setEnabled(False)
        grp_target.addWidget(self.btn_manage_fragments)

        self.btn_export_fragments = QPushButton("导出片段统计")
        self.btn_export_fragments.setIcon(qta.icon("fa5s.file-export"))
        self.btn_export_fragments.clicked.connect(self.request_export_fragments.emit)
        self.btn_export_fragments.setVisible(False)
        grp_target.addWidget(self.btn_export_fragments)
        layout.addWidget(grp_target)
        
        # 4. Compute
        grp_calc = CollapsiblePanel("4. 计算")
        self.btn_calc = QPushButton(" 计算 / 分析")
        self.btn_calc.setIcon(qta.icon('fa5s.rocket', color="white"))
        self.btn_calc.setStyleSheet("background-color: #198754; color: white; font-weight: bold; border-radius: 4px; padding: 8px 15px;")
        self.btn_calc.clicked.connect(self.emit_calculation)
        self.btn_calc.setEnabled(False) 
        
        self.lbl_summary = QLabel("结果摘要：\n无")
        self.lbl_summary.setStyleSheet("color: #666; margin-top: 10px; font-size: 12px;")
        
        btn_exp_lay = QHBoxLayout()
        self.btn_csv = QPushButton(" CSV")
        self.btn_csv.clicked.connect(self.request_export_csv.emit)
        self.btn_img = QPushButton(" 图片")
        self.btn_img.clicked.connect(self.request_export_image.emit)
        self.btn_export_full_csv = QPushButton("导出完整原始结果")
        self.btn_export_full_csv.clicked.connect(self.request_export_full_csv.emit)
        self.btn_csv.setEnabled(False)
        self.btn_img.setEnabled(False)
        self.btn_export_full_csv.setEnabled(False)
        btn_exp_lay.addWidget(self.btn_csv)
        btn_exp_lay.addWidget(self.btn_img)
        
        grp_calc.addWidget(self.btn_calc)
        grp_calc.addWidget(self.lbl_summary)
        grp_calc.addLayout(btn_exp_lay)
        grp_calc.addWidget(self.btn_export_full_csv)
        layout.addWidget(grp_calc)
        
        layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def update_file_status(self, ws_name, files):
        if not ws_name:
            self.lbl_file_status.setText("未选择工作区")
            self.btn_calc.setEnabled(False)
            return
            
        status_lines = []
        has_acf = "ACF.dat" in files
        has_struct = "CONTCAR" in files or "POSCAR" in files
        has_potcar = "POTCAR" in files
        
        check_icon = "🟢"
        cross_icon = "🔴"
        
        status_lines.append(f"{check_icon if has_acf else cross_icon} ACF.dat")
        
        if "CONTCAR" in files:
            status_lines.append(f"{check_icon} CONTCAR")
        elif "POSCAR" in files:
            status_lines.append(f"{check_icon} POSCAR")
        else:
            status_lines.append(f"{cross_icon} 结构文件")
            
        status_lines.append(f"{check_icon if has_potcar else cross_icon} POTCAR")
        
        if has_acf and has_struct:
            status_lines.append("\n<span style='color:#198754; font-weight:bold;'>就绪</span>")
            self.btn_calc.setEnabled(True)
        else:
            status_lines.append("\n<span style='color:#dc3545; font-weight:bold;'>缺少文件</span>")
            self.btn_calc.setEnabled(False)
            
        self.lbl_file_status.setText("<br>".join(status_lines))

    def update_summary(self, target_str, total_charge, max_gain_str, max_loss_str, stats=None):
        html = f"""
        <table width='100%' style='margin-top:5px; color:#555;'>
            <tr><td><b>目标原子：</b></td><td align='right'>{target_str or '全部'}</td></tr>
        """
        if total_charge is not None:
            html += f"<tr><td><b>总和：</b></td><td align='right'>{total_charge:.3f} e</td></tr>"
        if stats:
            html += (
                f"<tr><td><b>原子数：</b></td><td align='right'>{stats['count']}</td></tr>"
                f"<tr><td><b>平均值：</b></td><td align='right'>{stats['mean']:.3f} e</td></tr>"
                f"<tr><td><b>标准差：</b></td><td align='right'>{stats['std']:.3f} e</td></tr>"
                f"<tr><td><b>最大值：</b></td><td align='right'>{stats['max']:.3f} e</td></tr>"
                f"<tr><td><b>最小值：</b></td><td align='right'>{stats['min']:.3f} e</td></tr>"
            )
            
        html += f"""
            <tr><td><b>最大增益：</b></td><td align='right' style='color:#198754;'>{max_gain_str}</td></tr>
            <tr><td><b>最大损失：</b></td><td align='right' style='color:#dc3545;'>{max_loss_str}</td></tr>
        </table>
        """
        self.lbl_summary.setText(html)
        self.btn_csv.setEnabled(True)
        self.btn_img.setEnabled(True)

    def set_committed_scope(self, expression, atom_count):
        """Record the active analysis scope independently from the editable draft."""
        self._committed_scope = str(expression or "").strip()
        self._committed_atom_count = atom_count
        self.btn_export_full_csv.setEnabled(True)
        self._refresh_scope_state()

    def _on_draft_scope_changed(self, expression):
        self._refresh_scope_state()
        self.draft_scope_changed.emit(str(expression).strip())

    def use_all_atoms(self):
        """Clear only the editable draft; analysis remains an explicit action."""
        self.line_target.clear()

    def _refresh_scope_state(self):
        if self._committed_scope is None:
            self.lbl_target_scope.setText("当前生效：尚未分析")
            self.btn_calc.setText(" 计算 / 分析")
            return

        scope_text = self._committed_scope or "全部原子"
        count_text = (
            f"（{self._committed_atom_count} 个原子）"
            if self._committed_atom_count is not None
            else ""
        )
        dirty = self.line_target.text().strip() != self._committed_scope
        suffix = "\n有未应用更改" if dirty else ""
        self.lbl_target_scope.setText(
            f"当前生效：{scope_text}{count_text}{suffix}"
        )
        self.btn_calc.setText(" 应用范围并分析" if dirty else " 重新分析")

    def emit_calculation(self):
        config = {
            "zval": {"mode": "auto" if self.rad_auto.isChecked() else "manual", "manual_str": self.txt_manual_zval.text().strip()},
            "target": self.line_target.text().strip(),
            "fragment": self.line_fragment.text().strip(),
            "fragments": self.get_fragments(),
            "targets_by_workspace": self._targets_by_workspace(),
        }
        self.request_calculation.emit(config)

    def set_selected_workspaces(self, names, current_targets=None, current_workspace=None):
        """Refresh the compact selection summary and dialog context."""
        self._selected_workspaces = list(names or [])
        self._current_workspace = current_workspace
        self._workspace_targets = dict(current_targets or {})
        count = len(self._selected_workspaces)
        if count:
            self.lbl_selection_summary.setText(f"已选择 {count} 个工作区")
        elif self._current_workspace:
            self.lbl_selection_summary.setText(f"当前工作区：{self._current_workspace}")
        else:
            self.lbl_selection_summary.setText("未选择工作区")
        self.btn_edit_targets.setVisible(count > 1)
        self.btn_manage_fragments.setEnabled(bool(count or self._current_workspace))

    def add_fragment_row(self, name="", expression=""):
        """Compatibility helper used by existing integrations and tests."""
        if name:
            self._fragments[name] = {"expression": expression, "overrides": {}}
            self._update_fragment_summary()

    def get_fragments(self):
        return deepcopy(self._fragments)

    def set_fragments(self, fragments):
        self._fragments = deepcopy(fragments or {})
        self._update_fragment_summary()

    def update_fragment_results(self, rows):
        self._fragment_results = deepcopy(list(rows or []))
        self._update_fragment_summary()
        self.btn_export_fragments.setVisible(bool(self._fragment_results))

    def _update_fragment_summary(self):
        fragment_count = len(self._fragments)
        result_count = len(self._fragment_results)
        if fragment_count:
            self.lbl_fragment_summary.setText(
                f"已定义 {fragment_count} 个片段，已有 {result_count} 条统计结果"
            )
        else:
            self.lbl_fragment_summary.setText("尚未定义片段")

    def open_target_dialog(self):
        if len(self._selected_workspaces) <= 1:
            return
        dialog = WorkspaceTargetDialog(
            self._selected_workspaces,
            self._workspace_targets,
            self.line_target.text().strip(),
            self,
        )
        if dialog.exec():
            self._workspace_targets = dialog.targets()
            self.workspace_targets_changed.emit(dict(self._workspace_targets))

    def open_fragment_dialog(self):
        workspaces = self._selected_workspaces or (
            [self._current_workspace] if self._current_workspace else []
        )
        dialog = FragmentAnalysisDialog(
            workspaces,
            self._fragments,
            self._fragment_results,
            self,
        )
        dialog.request_export.connect(self.request_export_fragments.emit)
        if dialog.exec():
            definitions = dialog.fragments()
            self._fragments = deepcopy(definitions)
            self._update_fragment_summary()
            self.fragments_changed.emit(definitions, list(workspaces))

    def _targets_by_workspace(self):
        if len(self._selected_workspaces) <= 1:
            return {}
        default_target = self.line_target.text().strip()
        return {
            workspace: self._workspace_targets.get(workspace, default_target)
            for workspace in self._selected_workspaces
        }

class AnalysisPanel3D(QWidget):
    """Right sidebar for the 3D View tab"""
    request_render_update = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(10)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 1. Selection & Inspection
        grp_inspect = CollapsiblePanel("1. 选择与检查")
        self.lbl_inspect = QLabel("未选择原子。\n点击 3D 视图中的原子。")
        self.lbl_inspect.setStyleSheet("color: #666; font-size: 13px;")
        
        btn_lay = QHBoxLayout()
        btn_focus = QPushButton(" 聚焦")
        btn_focus.setIcon(qta.icon('fa5s.eye', color="#198754"))
        btn_focus.clicked.connect(lambda: self.request_render_update.emit({"action": "focus"}))
        btn_isolate = QPushButton(" 隔离")
        btn_isolate.setIcon(qta.icon('fa5s.bullseye', color="#0D6EFD"))
        btn_isolate.clicked.connect(lambda: self.request_render_update.emit({"action": "isolate"}))
        btn_clear = QPushButton(" 清除")
        btn_clear.setIcon(qta.icon('fa5s.times-circle', color="#dc3545"))
        btn_clear.clicked.connect(lambda: self.request_render_update.emit({"action": "clear"}))
        
        for btn in [btn_focus, btn_isolate, btn_clear]:
            btn.setStyleSheet("border: 1px solid #E0E0E0; border-radius: 4px; padding: 4px; background: white;")
            btn_lay.addWidget(btn)
            
        grp_inspect.addWidget(self.lbl_inspect)
        grp_inspect.addLayout(btn_lay)
        layout.addWidget(grp_inspect)
        
        # 2. Visualization Options
        grp_vis = CollapsiblePanel("2. 可视化选项")
        
        grid = QVBoxLayout()
        self.chk_hide_bg = QCheckBox("淡化背景原子")
        self.chk_hide_bg.setChecked(False)
        self.chk_hide_bg.toggled.connect(self.emit_render_update)
        self.chk_show_bonds = QCheckBox("显示化学键")
        self.chk_show_bonds.setChecked(True)
        self.chk_show_bonds.toggled.connect(self.emit_render_update)
        self.chk_show_labels = QCheckBox("显示原子标签")
        self.chk_show_labels.toggled.connect(self.emit_render_update)
        
        self.chk_show_cell = QCheckBox("显示晶胞")
        self.chk_show_cell.setChecked(False)
        self.chk_show_cell.toggled.connect(self.emit_render_update)
        
        self.chk_show_axes = QCheckBox("显示坐标轴")
        self.chk_show_axes.setChecked(False)
        self.chk_show_axes.toggled.connect(self.emit_render_update)
        
        grid.addWidget(self.chk_hide_bg)
        grid.addWidget(self.chk_show_bonds)
        grid.addWidget(self.chk_show_labels)
        grid.addWidget(self.chk_show_cell)
        grid.addWidget(self.chk_show_axes)
        
        # Representation mode
        lay_rep = QHBoxLayout()
        lay_rep.addWidget(QLabel("样式："))
        self.combo_rep = QComboBox()
        self.combo_rep.addItems(["球棍模型", "空间填充"])
        self.combo_rep.currentTextChanged.connect(self.emit_render_update)
        lay_rep.addWidget(self.combo_rep)
        grid.addLayout(lay_rep)
        
        self.line_label_target = QLineEdit()
        self.line_label_target.setPlaceholderText("标签目标（空表示全部）")
        self.line_label_target.setVisible(False)
        self.chk_show_labels.toggled.connect(self.line_label_target.setVisible)
        grid.addWidget(self.line_label_target)
        
        lay_trans = QHBoxLayout()
        lay_trans.addWidget(QLabel("透明度："))
        self.slider_trans = QSlider(Qt.Horizontal)
        self.slider_trans.setRange(0, 100)
        self.slider_trans.setValue(10)
        self.slider_trans.valueChanged.connect(self.emit_render_update)
        lay_trans.addWidget(self.slider_trans)
        
        grp_vis.addLayout(grid)
        grp_vis.addLayout(lay_trans)
        layout.addWidget(grp_vis)
        
        # 3. Scene Controls
        grp_scene = CollapsiblePanel("3. 场景控制")
        
        lay_scale = QHBoxLayout()
        lay_scale.addWidget(QLabel("球体缩放："))
        self.slider_scale = QSlider(Qt.Horizontal)
        self.slider_scale.setRange(50, 200)
        self.slider_scale.setValue(100)
        self.slider_scale.valueChanged.connect(self.emit_render_update)
        lay_scale.addWidget(self.slider_scale)
        
        lay_light = QHBoxLayout()
        lay_light.addWidget(QLabel("环境光："))
        self.slider_light = QSlider(Qt.Horizontal)
        self.slider_light.setRange(0, 100)
        self.slider_light.setValue(0)
        self.slider_light.valueChanged.connect(self.emit_render_update)
        lay_light.addWidget(self.slider_light)
        
        lay_bond = QHBoxLayout()
        lay_bond.addWidget(QLabel("键半径："))
        self.slider_bond = QSlider(Qt.Horizontal)
        self.slider_bond.setRange(1, 30)
        self.slider_bond.setValue(8)
        self.slider_bond.valueChanged.connect(self.emit_render_update)
        lay_bond.addWidget(self.slider_bond)
        
        grp_scene.addLayout(lay_scale)
        grp_scene.addLayout(lay_light)
        grp_scene.addLayout(lay_bond)
        layout.addWidget(grp_scene)
        
        # 4. Color Mapping
        grp_color = CollapsiblePanel("4. 颜色映射")
        
        lay_color_by = QHBoxLayout()
        lay_color_by.addWidget(QLabel("着色方式："))
        self.combo_color_by = QComboBox()
        self.combo_color_by.addItems(["Bader 电荷", "元素", "自定义"])
        self.combo_color_by.currentTextChanged.connect(self._on_color_by_changed)
        lay_color_by.addWidget(self.combo_color_by)
        
        self.lay_cmap = QHBoxLayout()
        self.lbl_cmap = QLabel("色图：")
        self.lay_cmap.addWidget(self.lbl_cmap)
        self.combo_cmap = QComboBox()
        self.combo_cmap.addItems(["RdBu_r", "coolwarm", "seismic", "RdYlBu_r", "bwr"])
        self.combo_cmap.currentTextChanged.connect(self.emit_render_update)
        self.lay_cmap.addWidget(self.combo_cmap)
        
        # Custom element color picker (hidden unless "Custom" is selected)
        self.custom_color_widget = QWidget()
        custom_layout = QVBoxLayout(self.custom_color_widget)
        custom_layout.setContentsMargins(0, 5, 0, 0)
        custom_layout.setSpacing(4)
        custom_hint = QLabel("点击色块自定义颜色：")
        custom_hint.setStyleSheet("color: #888; font-size: 11px;")
        custom_layout.addWidget(custom_hint)
        self.custom_colors_container = QWidget()
        self.custom_colors_layout = QHBoxLayout(self.custom_colors_container)
        self.custom_colors_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_colors_layout.setSpacing(4)
        custom_layout.addWidget(self.custom_colors_container)
        self.custom_color_widget.setVisible(False)
        
        # State for custom colors
        self.custom_colors: dict[str, tuple[float, float, float]] = {}
        self.custom_color_buttons: dict[str, QPushButton] = {}
        
        grp_color.addLayout(lay_color_by)
        grp_color.addLayout(self.lay_cmap)

        # -- Color profile (affects ChargeColorMapper endpoint colors) --
        self._lay_profile_w = QWidget()
        lay_profile = QHBoxLayout(self._lay_profile_w)
        lay_profile.setContentsMargins(0, 0, 0, 0)
        lay_profile.addWidget(QLabel("配色："))
        self.combo_profile = QComboBox()
        self.combo_profile.addItems(["标准", "柔和", "鲜明"])
        self.combo_profile.currentTextChanged.connect(self.emit_render_update)
        lay_profile.addWidget(self.combo_profile)
        grp_color.addWidget(self._lay_profile_w)

        # -- Gamma normalization --
        self._lay_gamma_w = QWidget()
        lay_gamma = QHBoxLayout(self._lay_gamma_w)
        lay_gamma.setContentsMargins(0, 0, 0, 0)
        lay_gamma.addWidget(QLabel("Gamma："))
        self.slider_gamma = QSlider(Qt.Horizontal)
        self.slider_gamma.setRange(10, 100)   # 0.1 – 1.0
        self.slider_gamma.setValue(100)        # default 1.0 = linear
        self.slider_gamma.setToolTip("降低 Gamma 值可增强小电荷的颜色对比度")
        self.lbl_gamma_val = QLabel("1.00")
        self.lbl_gamma_val.setMinimumWidth(32)
        self.slider_gamma.valueChanged.connect(self._on_gamma_changed)
        lay_gamma.addWidget(self.slider_gamma)
        lay_gamma.addWidget(self.lbl_gamma_val)
        grp_color.addWidget(self._lay_gamma_w)

        # -- Range mode --
        self._lay_range_w = QWidget()
        lay_range = QHBoxLayout(self._lay_range_w)
        lay_range.setContentsMargins(0, 0, 0, 0)
        lay_range.addWidget(QLabel("范围："))
        self.combo_range = QComboBox()
        self.combo_range.addItems(["极值", "95%位", "80%位"])
        self.combo_range.currentTextChanged.connect(self.emit_render_update)
        lay_range.addWidget(self.combo_range)
        grp_color.addWidget(self._lay_range_w)

        grp_color.addWidget(self.custom_color_widget)
        layout.addWidget(grp_color)
        
        # 5. Analyze & Export
        grp_exp = CollapsiblePanel("5. 分析与导出")
        btn_update = QPushButton(" 分析 / 刷新视图")
        btn_update.setIcon(qta.icon('fa5s.sync', color="white"))
        btn_update.setObjectName("PrimaryButton")
        btn_update.setStyleSheet("""
            QPushButton#PrimaryButton {
                background-color: #198754;
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton#PrimaryButton:hover { background-color: #157347; }
        """)
        btn_update.clicked.connect(self.emit_render_update)
        
        lay_exp_btns = QHBoxLayout()
        self.btn_exp_img = QPushButton(" 导出图片")
        self.btn_exp_img.setStyleSheet("border: 1px solid #E0E0E0; border-radius: 4px; padding: 6px; background: white;")
        self.btn_exp_img.setIcon(qta.icon('fa5s.image', color="#555"))
        
        self.btn_exp_mdl = QPushButton(" 导出模型")
        self.btn_exp_mdl.setStyleSheet("border: 1px solid #E0E0E0; border-radius: 4px; padding: 6px; background: white;")
        self.btn_exp_mdl.setIcon(qta.icon('fa5s.cube', color="#555"))
        self.btn_exp_mdl.clicked.connect(lambda: self.request_render_update.emit({"action": "export_model"}))
        
        lay_exp_btns.addWidget(self.btn_exp_img)
        lay_exp_btns.addWidget(self.btn_exp_mdl)
        
        grp_exp.addWidget(btn_update)
        grp_exp.addLayout(lay_exp_btns)
        layout.addWidget(grp_exp)
        
        layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def update_selection_info(self, data):
        if not data:
            self.lbl_inspect.setText(
                "未选择原子。\n点击 3D 视图中的原子。")
        else:
            bader = data.get('charge', 0.0)
            raw_c = data.get('bader_raw', 0.0)
            zv = data.get('zval', 0.0)
            info = (
                f"原子 ID: <b>{data['id']}</b> ({data['element']})<br>"
                f"Bader 电荷: "
                f"<span style='color:{'red' if bader>0 else 'blue' if bader<0 else 'gray'};'>"
                f"<b>{bader:+.4f} e</b></span><br>"
                f"CHARGE: <b>{raw_c:.4f}</b> | ZVAL: <b>{zv}</b><br>"
                f"配位数: {data['coord']}<br>"
                f"位置: [{data['pos'][0]:.2f}, {data['pos'][1]:.2f}, "
                f"{data['pos'][2]:.2f}]"
            )
            self.lbl_inspect.setText(info)

    def update_file_status(self, ws_name, files):
        pass # Optional logic if 3D panel needs to know
        
    def _on_color_by_changed(self):
        """Toggle visibility of colormap / custom-color controls based on mode."""
        mode = self.combo_color_by.currentText()
        cmap_visible = (mode == "Bader 电荷")
        self.lbl_cmap.setVisible(cmap_visible)
        self.combo_cmap.setVisible(cmap_visible)
        for w in (self._lay_profile_w, self._lay_gamma_w, self._lay_range_w):
            w.setVisible(cmap_visible)
        self.custom_color_widget.setVisible(mode == "自定义")
        self.emit_render_update()

    def _on_gamma_changed(self, value):
        """Update the gamma label text when the slider moves."""
        self.lbl_gamma_val.setText(f"{value / 100.0:.2f}")
        self.emit_render_update()

    def update_elements(self, elements):
        """Populate custom color buttons for the given element set.
        
        Called from main_window when new structure data is loaded.
        Preserves any previously customized colors for elements still present.
        """
        from rendering.pyvista_structure_renderer import ELEMENT_COLORS, FALLBACK_ELEMENT_COLOR

        # Clear old buttons
        for btn in self.custom_color_buttons.values():
            btn.deleteLater()
        self.custom_color_buttons.clear()

        # Remove stale custom colors for elements no longer present
        stale = [e for e in self.custom_colors if e not in elements]
        for e in stale:
            del self.custom_colors[e]

        for elem in sorted(elements):
            if elem not in self.custom_colors:
                color = ELEMENT_COLORS.get(elem, FALLBACK_ELEMENT_COLOR)
                self.custom_colors[elem] = color

            r, g, b = self.custom_colors[elem]
            ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)

            btn = QPushButton(f" {elem}")
            btn.setFixedSize(50, 28)
            btn.setStyleSheet(
                f"background-color: rgb({ri},{gi},{bi}); "
                f"font-weight: bold; border: 1px solid #999; border-radius: 3px;"
            )
            btn.clicked.connect(lambda checked, e=elem: self._pick_element_color(e))
            self.custom_color_buttons[elem] = btn
            self.custom_colors_layout.addWidget(btn)

        self.custom_colors_layout.addStretch()

    def _pick_element_color(self, element):
        """Open a color dialog to customize the given element's color."""
        current = self.custom_colors.get(element, (0.7, 0.7, 0.72))
        initial = QColor.fromRgbF(current[0], current[1], current[2])
        color = QColorDialog.getColor(initial, self, f"选择 {element} 的颜色")
        if color.isValid():
            r, g, b = color.redF(), color.greenF(), color.blueF()
            self.custom_colors[element] = (r, g, b)
            ri, gi, bi = color.red(), color.green(), color.blue()
            self.custom_color_buttons[element].setStyleSheet(
                f"background-color: rgb({ri},{gi},{bi}); "
                f"font-weight: bold; border: 1px solid #999; border-radius: 3px;"
            )
            self.emit_render_update()
        
    def emit_render_update(self):
        # Map UI representation names to internal keys
        rep_map = {"球棍模型": "ball_stick", "空间填充": "space_filling"}
        rep_key = rep_map.get(self.combo_rep.currentText(), "ball_stick")

        settings = {
            "action": "render",
            "hide_bg": self.chk_hide_bg.isChecked(),
            "show_labels": self.chk_show_labels.isChecked(),
            "show_bonds": self.chk_show_bonds.isChecked(),
            "show_cell": self.chk_show_cell.isChecked(),
            "show_axes": self.chk_show_axes.isChecked(),
            "label_target_str": self.line_label_target.text().strip(),
            "transparency": self.slider_trans.value(),
            "sphere_scale": self.slider_scale.value(),
            "ambient_light": self.slider_light.value(),
            "bond_radius": self.slider_bond.value(),
            "color_by": self.combo_color_by.currentText(),
            "cmap": self.combo_cmap.currentText(),
            "cmap_gamma": self.slider_gamma.value() / 100.0,
            "cmap_range": self.combo_range.currentText(),
            "color_profile": self.combo_profile.currentText(),
            "representation": rep_key,
            "custom_colors": dict(self.custom_colors) if self.combo_color_by.currentText() == "自定义" else None,
        }
        self.request_render_update.emit(settings)

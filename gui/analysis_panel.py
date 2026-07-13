# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QRadioButton, QButtonGroup, 
                               QPushButton, QCheckBox, QScrollArea, QFrame, QComboBox, QSlider,
                               QColorDialog, QTableWidget, QTableWidgetItem, QHeaderView)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
import qtawesome as qta
from gui.components.collapsible import CollapsiblePanel

class AnalysisPanel(QWidget):
    request_calculation = Signal(dict)
    request_export_csv = Signal()
    request_export_image = Signal()
    request_export_fragments = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_workspaces = []
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
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
        grp_target.addWidget(self.line_target)

        self.btn_apply_target_to_all = QPushButton("\u6240\u9009\u5de5\u4f5c\u533a\u5747\u4f7f\u7528\u5f53\u524d\u8f93\u5165")
        self.btn_apply_target_to_all.clicked.connect(self._apply_target_to_selected)
        self.btn_apply_target_to_all.setVisible(False)
        grp_target.addWidget(self.btn_apply_target_to_all)

        self.target_table = QTableWidget()
        self.target_table.setColumnCount(2)
        self.target_table.setHorizontalHeaderLabels(["\u5de5\u4f5c\u533a", "\u76ee\u6807\u539f\u5b50"])
        self.target_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.target_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.target_table.verticalHeader().setVisible(False)
        self.target_table.setMaximumHeight(150)
        self.target_table.setVisible(False)
        grp_target.addWidget(self.target_table)
        
        grp_target.addWidget(QLabel("片段求和："))
        self.line_fragment = QLineEdit()
        self.line_fragment.setPlaceholderText("例如 1-15")
        self.line_fragment.setVisible(False)
        self.fragment_table = QTableWidget()
        self.fragment_table.setColumnCount(2)
        self.fragment_table.setHorizontalHeaderLabels(["片段名称", "默认原子表达式"])
        self.fragment_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fragment_table.verticalHeader().setVisible(False)
        self.fragment_table.setMaximumHeight(180)
        grp_target.addWidget(self.fragment_table)
        fragment_actions = QHBoxLayout()
        self.btn_add_fragment = QPushButton("新增片段")
        self.btn_remove_fragment = QPushButton("删除片段")
        self.btn_add_fragment.clicked.connect(lambda: self.add_fragment_row())
        self.btn_remove_fragment.clicked.connect(self.remove_selected_fragment)
        fragment_actions.addWidget(self.btn_add_fragment)
        fragment_actions.addWidget(self.btn_remove_fragment)
        grp_target.addLayout(fragment_actions)
        self.fragment_results = QTableWidget()
        self.fragment_results.setColumnCount(8)
        self.fragment_results.setHorizontalHeaderLabels(
            ["工作区", "片段", "表达式", "原子数", "总和(e)",
             "平均值(e)", "最大值(e)", "最小值(e)"]
        )
        self.fragment_results.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.fragment_results.verticalHeader().setVisible(False)
        self.fragment_results.setMaximumHeight(190)
        grp_target.addWidget(self.fragment_results)
        self.btn_export_fragments = QPushButton("导出片段统计")
        self.btn_export_fragments.clicked.connect(self.request_export_fragments.emit)
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
        self.btn_csv.setEnabled(False)
        self.btn_img.setEnabled(False)
        btn_exp_lay.addWidget(self.btn_csv)
        btn_exp_lay.addWidget(self.btn_img)
        
        grp_calc.addWidget(self.btn_calc)
        grp_calc.addWidget(self.lbl_summary)
        grp_calc.addLayout(btn_exp_lay)
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

    def emit_calculation(self):
        config = {
            "zval": {"mode": "auto" if self.rad_auto.isChecked() else "manual", "manual_str": self.txt_manual_zval.text().strip()},
            "target": self.line_target.text().strip(),
            "fragment": self.line_fragment.text().strip(),
            "fragments": self.get_fragments(),
            "targets_by_workspace": self._targets_by_workspace(),
        }
        self.request_calculation.emit(config)

    def set_selected_workspaces(self, names, current_targets=None):
        """Refresh the optional per-workspace target table."""
        self._selected_workspaces = list(names or [])
        current_targets = current_targets or {}
        multi = len(self._selected_workspaces) > 1
        self.btn_apply_target_to_all.setVisible(multi)
        self.target_table.setVisible(multi)
        self.target_table.setRowCount(len(self._selected_workspaces) if multi else 0)

        if not multi:
            self._rebuild_fragment_columns()
            return

        default_target = self.line_target.text().strip()
        for row, name in enumerate(self._selected_workspaces):
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.target_table.setItem(row, 0, name_item)
            self.target_table.setItem(
                row, 1, QTableWidgetItem(current_targets.get(name, default_target))
            )
        self._rebuild_fragment_columns()

    def add_fragment_row(self, name="", expression=""):
        row = self.fragment_table.rowCount()
        self.fragment_table.insertRow(row)
        self.fragment_table.setItem(row, 0, QTableWidgetItem(name))
        self.fragment_table.setItem(row, 1, QTableWidgetItem(expression))
        for column in range(2, self.fragment_table.columnCount()):
            self.fragment_table.setItem(row, column, QTableWidgetItem(""))

    def remove_selected_fragment(self):
        rows = sorted(
            {index.row() for index in self.fragment_table.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            self.fragment_table.removeRow(row)

    def get_fragments(self):
        fragments = {}
        for row in range(self.fragment_table.rowCount()):
            name_item = self.fragment_table.item(row, 0)
            expression_item = self.fragment_table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            expression = expression_item.text().strip() if expression_item else ""
            if not name:
                continue
            overrides = {}
            for column, workspace in enumerate(self._selected_workspaces, start=2):
                item = self.fragment_table.item(row, column)
                value = item.text().strip() if item else ""
                if value:
                    overrides[workspace] = value
            fragments[name] = {"expression": expression, "overrides": overrides}
        return fragments

    def set_fragments(self, fragments):
        self.fragment_table.setRowCount(0)
        for name, definition in (fragments or {}).items():
            self.add_fragment_row(name, definition.get("expression", ""))
            row = self.fragment_table.rowCount() - 1
            overrides = definition.get("overrides", {}) or {}
            for column, workspace in enumerate(self._selected_workspaces, start=2):
                self.fragment_table.setItem(
                    row, column, QTableWidgetItem(overrides.get(workspace, ""))
                )

    def _rebuild_fragment_columns(self):
        existing = self.get_fragments()
        self.fragment_table.setColumnCount(2 + len(self._selected_workspaces))
        self.fragment_table.setHorizontalHeaderLabels(
            ["片段名称", "默认原子表达式"] + self._selected_workspaces
        )
        self.set_fragments(existing)

    def update_fragment_results(self, rows):
        self.fragment_results.setRowCount(len(rows))
        for row_index, result in enumerate(rows):
            values = [
                result["workspace"], result["fragment"], result["expression"],
                str(result["count"]), f'{result["sum"]:.6f}',
                f'{result["mean"]:.6f}', f'{result["max"]:.6f}',
                f'{result["min"]:.6f}',
            ]
            for column, value in enumerate(values):
                self.fragment_results.setItem(
                    row_index, column, QTableWidgetItem(value)
                )

    def _apply_target_to_selected(self):
        target = self.line_target.text().strip()
        for row in range(self.target_table.rowCount()):
            item = self.target_table.item(row, 1)
            if item is None:
                item = QTableWidgetItem()
                self.target_table.setItem(row, 1, item)
            item.setText(target)

    def _targets_by_workspace(self):
        if len(self._selected_workspaces) <= 1:
            return {}
        targets = {}
        for row in range(self.target_table.rowCount()):
            name_item = self.target_table.item(row, 0)
            target_item = self.target_table.item(row, 1)
            if name_item is not None:
                targets[name_item.text()] = target_item.text().strip() if target_item else ""
        return targets

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
            "target_str": "",
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

# -*- coding: utf-8 -*-
import os
import sys
import math
import re
import json
import numpy as np
import datetime
import qtawesome as qta

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog,
    QHeaderView, QListWidget, QListWidgetItem, QInputDialog,
    QTabBar, QTabWidget, QStackedWidget, QLineEdit, QMenu,
    QDialog, QComboBox, QCheckBox, QSizePolicy, QSpacerItem,
    QAbstractItemView,
)
from PySide6.QtGui import (
    QColor, QBrush, QAction, QKeySequence, QShortcut,
)
from PySide6.QtCore import Qt, Signal

from core.workspace_manager import WorkspaceManager
from core.runtime_paths import bundled_bader_candidates
from gui.analysis_panel import AnalysisPanel
# Deferred (lazy) imports — these pull in heavy dependencies:
#   Visualizer3D  → pyvistaqt / VTK  (~10-30s)
#   AnalysisPanel3D → depends on Visualizer3D ecosystem
#   AnalysisWorker → core.parser → pymatgen (~17s)
# They are imported on first use, not at module load time,
# to dramatically reduce application startup time.
from gui.plot_panel import PlotPanel
from gui.style_manager import get_app_stylesheet
from gui.app_icon import load_app_icon


class WorkspaceTreeWidget(QTreeWidget):
    workspaceDropped = Signal(list, str)
    itemDeleteRequested = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.itemDeleteRequested.emit()
        else:
            super().keyPressEvent(event)

    def dropEvent(self, event):
        target = self.itemAt(event.position().toPoint())
        if target is None:
            event.ignore()
            return

        target_workspace = target.data(0, Qt.UserRole)
        target_group_item = target.parent() if target_workspace else target
        if target_group_item is None:
            event.ignore()
            return

        group = target_group_item.text(0)
        workspaces = [
            selected.data(0, Qt.UserRole)
            for selected in self.selectedItems()
            if selected.data(0, Qt.UserRole)
        ]
        current = self.currentItem()
        current_workspace = current.data(0, Qt.UserRole) if current is not None else None
        if current_workspace and current_workspace not in workspaces:
            workspaces = [current_workspace]
        if not workspaces:
            event.ignore()
            return
        event.acceptProposedAction()
        self.workspaceDropped.emit(workspaces, group)

# ── Column constants ──
BASE_COLUMNS = [
    "Atom", "Element", "X", "Y", "Z",
    "CHARGE", "ZVAL", "Bader Charge", "Min_Dist", "Volume",
]
N_BASE_COLS = len(BASE_COLUMNS)  # 10
BADER_COL = BASE_COLUMNS.index("Bader Charge")  # 7

# Translated display labels for table headers (user-visible only)
DISPLAY_BASE_COLUMNS = [
    "原子", "元素", "X", "Y", "Z",
    "CHARGE", "ZVAL", "Bader 电荷", "最小距离", "体积",
]


# ═══════════════════════════════════════════════════════════════
#  Helper classes
# ═══════════════════════════════════════════════════════════════

class SortableFloatItem(QTableWidgetItem):
    """Table item that sorts numerically (NaN sinks to bottom)."""

    def __init__(self, text=""):
        super().__init__(str(text))
        self.setTextAlignment(int(Qt.AlignCenter))

    def __lt__(self, other):
        def _num(item):
            try:
                v = float(item.text())
                return (1, v) if not math.isnan(v) else (2, 0.0)
            except (ValueError, TypeError):
                return (0, item.text().lower())
        return _num(self) < _num(other)


class SummaryItem(SortableFloatItem):
    """Item for summary rows — always sorts to bottom."""

    def __init__(self, text=""):
        super().__init__(text)
        self.setData(Qt.UserRole + 100, True)
        font = self.font()
        font.setBold(True)
        self.setFont(font)

    def __lt__(self, other):
        if self.data(Qt.UserRole + 100):
            return False
        if other.data(Qt.UserRole + 100):
            return True
        return super().__lt__(other)


class AtomDetailDialog(QDialog):
    """Popup showing full details for a single atom."""

    def __init__(self, row_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"原子 {row_data.get('Atom', '?')} — 详情")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        tbl = QTableWidget()
        tbl.setColumnCount(2)
        tbl.setHorizontalHeaderLabels(["属性", "值"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        props = [
            ("原子 ID", str(row_data.get("Atom", ""))),
            ("元素", str(row_data.get("Element", ""))),
            ("X", f"{row_data.get('X', 0):.6f}"),
            ("Y", f"{row_data.get('Y', 0):.6f}"),
            ("Z", f"{row_data.get('Z', 0):.6f}"),
            ("CHARGE (原始值)", f"{row_data.get('CHARGE', 0):.4f}"),
            ("ZVAL", str(row_data.get("ZVAL", ""))),
            ("Bader 电荷 (净值)", f"{row_data.get('Bader_Charge', 0):.4f}"),
            ("最小距离", f"{row_data.get('Min_Dist', 0):.4f}"),
            ("体积", f"{row_data.get('Volume', 0):.4f}"),
        ]

        tbl.setRowCount(len(props))
        for i, (k, v) in enumerate(props):
            tbl.setItem(i, 0, QTableWidgetItem(k))
            item = QTableWidgetItem(v)
            item.setTextAlignment(int(Qt.AlignCenter))
            tbl.setItem(i, 1, item)

        layout.addWidget(tbl)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


# ═══════════════════════════════════════════════════════════════
#  MainWindow
# ═══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):

    def __init__(self, workspace_manager=None):
        super().__init__()
        self.setWindowTitle("Bader Charge Analyzer Pro")
        self.setWindowIcon(load_app_icon())
        self.resize(1400, 900)

        self.ws_mgr = workspace_manager or WorkspaceManager()
        self.current_ws = None
        self.selected_workspaces = []
        self._workspace_targets = {}
        self._syncing_ws_tree = False
        self._batch_queue = []
        self._batch_errors = []
        self._batch_config = None
        self._batch_worker = None
        self.all_calculated_data = {}
        self.current_df = None

        self.data_table_subtab = None
        self.tab_multi_compare = None

        self.is_dark_theme = False

        # New state
        self._delta_mode = False
        self._baseline_ws = None
        self._custom_columns = {}  # name -> expression str

        self.init_ui()
        self.load_workspaces()
        self.apply_theme()

    # ────────────────────────────────────────────────────────────
    #  UI Construction
    # ────────────────────────────────────────────────────────────

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. Top Header Bar ──
        self.header_bar = QWidget()
        self.header_bar.setObjectName("HeaderBar")
        self.header_bar.setFixedHeight(60)
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(20, 0, 20, 0)

        self.nav_tabs = QTabBar()
        self.nav_tabs.setObjectName("NavTabs")
        self.nav_tabs.setExpanding(True)
        self.nav_tabs.setMinimumWidth(460)
        self.nav_tabs.setStyleSheet("""
            QTabBar#NavTabs::tab {
                font-size: 14px;
                min-width: 120px;
                padding-left: 18px;
                padding-right: 18px;
            }
        """)
        self.nav_tabs.addTab(qta.icon("fa5s.table", color="#198754"), " 数据表")
        self.nav_tabs.addTab(qta.icon("fa5s.chart-bar", color="#198754"), " 对比图")
        self.nav_tabs.addTab(qta.icon("fa5s.cube", color="#198754"), " 3D 结构视图")
        self.nav_tabs.currentChanged.connect(self.on_tab_changed)

        btn_open = QPushButton(" 打开")
        btn_open.setIcon(qta.icon("fa5s.folder-open"))
        btn_open.setFlat(True)
        btn_open.clicked.connect(self.open_file_dialog)

        btn_save = QPushButton(" 保存项目")
        btn_save.setIcon(qta.icon("fa5s.save"))
        btn_save.setFlat(True)
        btn_save.clicked.connect(self.save_project)

        btn_settings = QPushButton(" 设置")
        btn_settings.setIcon(qta.icon("fa5s.cog"))
        btn_settings.setFlat(True)
        btn_settings.clicked.connect(self.toggle_theme)

        for btn in [btn_open, btn_save, btn_settings]:
            btn.setStyleSheet("font-weight: bold; color: #555; padding: 5px 10px;")

        self.btn_theme = QPushButton(" 夜间模式")
        self.btn_theme.setIcon(qta.icon("fa5s.moon"))
        self.btn_theme.setFlat(True)
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_theme.setStyleSheet(self._header_action_button_style())
        self._header_action_width = 112
        self.btn_theme.setFixedWidth(self._header_action_width)

        self.header_left_balance = QSpacerItem(
            self._header_action_width, 0, QSizePolicy.Fixed, QSizePolicy.Minimum
        )
        header_layout.addItem(self.header_left_balance)
        header_layout.addStretch(1)
        header_layout.addWidget(self.nav_tabs)
        header_layout.addStretch(1)
        header_layout.addWidget(self.btn_theme)

        # ── 2. Main Content Area ──
        content_area = QWidget()
        content_layout = QHBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 2a. Left Sidebar
        self.left_sidebar = QWidget()
        self.left_sidebar.setObjectName("LeftSidebar")
        self.left_sidebar.setFixedWidth(260)
        left_layout = QVBoxLayout(self.left_sidebar)
        left_layout.setContentsMargins(15, 20, 15, 20)
        left_layout.setSpacing(10)

        ws_header = QHBoxLayout()
        ws_header.setSpacing(4)
        lbl_ws = QLabel("\u5de5\u4f5c\u533a")
        lbl_ws.setStyleSheet("font-weight: bold; font-size: 14px;")
        lbl_ws.setMinimumWidth(50)
        lbl_ws.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        btn_ws_add = QPushButton()
        btn_ws_add.setIcon(qta.icon("fa5s.plus"))
        btn_ws_add.setFlat(True)
        btn_ws_add.setFixedSize(34, 28)
        btn_ws_add.setToolTip("\u65b0\u5efa\u5de5\u4f5c\u533a\u6216\u5206\u7ec4")
        btn_ws_add.setMenu(self._build_create_workspace_menu(btn_ws_add))
        btn_ws_menu = QPushButton()
        btn_ws_menu.setIcon(qta.icon("fa5s.trash-alt"))
        btn_ws_menu.setFlat(True)
        btn_ws_menu.setFixedSize(30, 28)
        btn_ws_menu.setToolTip("\u5220\u9664\u5de5\u4f5c\u533a")
        self._btn_ws_delete = btn_ws_menu  # keep reference for tooltip updates
        btn_ws_menu.clicked.connect(self.delete_selected_item)
        btn_ws_rename = QPushButton()
        btn_ws_rename.setIcon(qta.icon("fa5s.edit"))
        btn_ws_rename.setFlat(True)
        btn_ws_rename.setFixedSize(30, 28)
        btn_ws_rename.setToolTip("\u91cd\u547d\u540d")
        btn_ws_rename.clicked.connect(self.rename_selected_item)
        btn_ws_group = QPushButton()
        btn_ws_group.setIcon(qta.icon("fa5s.layer-group"))
        btn_ws_group.setFlat(True)
        btn_ws_group.setFixedSize(30, 28)
        btn_ws_group.setToolTip("\u79fb\u52a8\u5230\u5206\u7ec4")
        btn_ws_group.clicked.connect(self.move_ws_to_group)
        ws_header.addWidget(lbl_ws)
        ws_header.addStretch()
        ws_header.addWidget(btn_ws_add)
        ws_header.addWidget(btn_ws_group)
        ws_header.addWidget(btn_ws_rename)
        ws_header.addWidget(btn_ws_menu)

        self.ws_tree = WorkspaceTreeWidget()
        self.ws_tree.setHeaderHidden(True)
        self.ws_tree.setDragEnabled(True)
        self.ws_tree.setAcceptDrops(True)
        self.ws_tree.setDropIndicatorShown(True)
        self.ws_tree.setDefaultDropAction(Qt.MoveAction)
        self.ws_tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.ws_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.ws_tree.setStyleSheet(
            "QTreeWidget { border: none; background: transparent; font-size: 13px; }"
            " QTreeWidget::item { padding: 5px; }"
        )
        self.ws_tree.itemClicked.connect(self.on_ws_selected)
        self.ws_tree.itemDoubleClicked.connect(self.rename_selected_item)
        self.ws_tree.itemChanged.connect(self._on_workspace_item_changed)
        self.ws_tree.itemSelectionChanged.connect(self.refresh_workspace_selection_context)
        self.ws_tree.itemSelectionChanged.connect(self._update_delete_tooltip)
        self.ws_tree.workspaceDropped.connect(self.move_workspace_to_group_name)
        self.ws_tree.itemDeleteRequested.connect(self.delete_selected_item)

        self.lbl_files = QLabel("项目中的文件")
        self.lbl_files.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 15px;")
        self.list_files = QListWidget()
        self.list_files.setStyleSheet(
            "QListWidget { border: none; background: transparent; }"
            " QListWidget::item { padding: 4px; }"
        )
        file_actions = QHBoxLayout()
        file_actions.setSpacing(4)
        self.btn_file_add = QPushButton()
        self.btn_file_add.setIcon(qta.icon("fa5s.plus"))
        self.btn_file_add.setToolTip("添加文件")
        self.btn_file_replace = QPushButton()
        self.btn_file_replace.setIcon(qta.icon("fa5s.exchange-alt"))
        self.btn_file_replace.setToolTip("替换选中文件")
        self.btn_file_delete = QPushButton()
        self.btn_file_delete.setIcon(qta.icon("fa5s.trash"))
        self.btn_file_delete.setToolTip("删除选中文件")
        self.btn_file_folder = QPushButton()
        self.btn_file_folder.setIcon(qta.icon("fa5s.folder-open"))
        self.btn_file_folder.setToolTip("打开工作区目录")
        self.btn_file_add.clicked.connect(self.open_file_dialog)
        self.btn_file_replace.clicked.connect(self.replace_selected_file)
        self.btn_file_delete.clicked.connect(self.delete_selected_file)
        self.btn_file_folder.clicked.connect(self.open_workspace_folder)
        for button in (
            self.btn_file_add, self.btn_file_replace,
            self.btn_file_delete, self.btn_file_folder,
        ):
            button.setFixedSize(30, 28)
            file_actions.addWidget(button)
        file_actions.addStretch()

        project_actions = QHBoxLayout()
        project_actions.setSpacing(6)
        self.btn_open_project = QPushButton(" 打开")
        self.btn_open_project.setIcon(qta.icon("fa5s.folder-open"))
        self.btn_open_project.clicked.connect(self.open_file_dialog)
        self.btn_save_project = QPushButton(" 保存项目")
        self.btn_save_project.setIcon(qta.icon("fa5s.save"))
        self.btn_save_project.clicked.connect(self.save_project)
        for btn in (self.btn_open_project, self.btn_save_project):
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(self._sidebar_action_button_style())
        project_actions.addWidget(self.btn_open_project)
        project_actions.addWidget(self.btn_save_project)

        btn_import = QPushButton(" 导入文件")
        btn_import.setIcon(qta.icon("fa5s.upload"))
        btn_import.setStyleSheet(
            "border: 1px solid #E0E0E0; border-radius: 6px; padding: 10px;"
            " font-weight: bold; background: white;"
        )
        btn_import.clicked.connect(self.open_file_dialog)

        btn_new_ws = QPushButton(" \u65b0\u5efa")
        btn_new_ws.setIcon(qta.icon("fa5s.plus-circle"))
        btn_new_ws.setMenu(self._build_create_workspace_menu(btn_new_ws))
        btn_new_ws.setStyleSheet(
            "border: 1px solid #E0E0E0; border-radius: 6px; padding: 10px;"
            " font-weight: bold; background: white;"
        )

        self.btn_import = btn_import
        self.btn_new_ws = btn_new_ws
        self.btn_import.setStyleSheet(self._sidebar_action_button_style())
        self.btn_new_ws.setStyleSheet(self._sidebar_action_button_style())

        left_layout.addLayout(project_actions)
        left_layout.addLayout(ws_header)
        left_layout.addWidget(self.ws_tree, 1)
        left_layout.addWidget(self.lbl_files)
        left_layout.addLayout(file_actions)
        left_layout.addWidget(self.list_files, 1)
        left_layout.addWidget(btn_import)
        left_layout.addWidget(btn_new_ws)

        # 2b. Center Area
        self.center_stack = QStackedWidget()

        # ── Data-table sub-tabs container ──
        self.data_table_subtab = QTabWidget()
        self.data_table_subtab.setDocumentMode(True)
        self.data_table_subtab.setObjectName("DataTableSubTabs")

        # ── Tab 0: single-system (filter bar + table + element summary) ──
        single_container = QWidget()
        single_layout = QVBoxLayout(single_container)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_layout.setSpacing(2)
        self._build_single_system_toolbar(single_layout)
        self._build_single_system_table()
        single_layout.addWidget(self.tab_data, 1)
        self._build_element_summary(single_layout)

        # ── Tab 1: multi-system (toolbar + table) ──
        multi_container = QWidget()
        multi_layout = QVBoxLayout(multi_container)
        multi_layout.setContentsMargins(0, 0, 0, 0)
        multi_layout.setSpacing(2)
        self._build_multi_compare_toolbar(multi_layout)
        self._build_multi_compare_table()
        multi_layout.addWidget(self.tab_multi_compare, 1)

        self.data_table_subtab.addTab(
            single_container, qta.icon("fa5s.atom", color="#198754"), " \u5355\u4e00\u4f53\u7cfb"
        )
        self.data_table_subtab.addTab(
            multi_container, qta.icon("fa5s.th-list", color="#198754"), " \u591a\u4f53\u7edf\u8ba1"
        )
        self.data_table_subtab.currentChanged.connect(self.on_data_subtab_changed)

        self.plot_panel = PlotPanel()
        self.plot_panel.data_point_selected.connect(self.on_plot_atom_selected)

        # ── Lazy 3D: defer pyvista/VTK import until user opens 3D tab ──
        self._has_3d = False
        self._3d_loaded = False
        self._3d_dirty = False
        self.visualizer_3d = None
        self.analysis_panel_3d = None

        self.center_stack.addWidget(self.data_table_subtab)
        self.center_stack.addWidget(self.plot_panel)

        # Placeholder for 3D tab (index 2) — replaced on first activation
        self._3d_placeholder = QWidget()
        ph_layout = QVBoxLayout(self._3d_placeholder)
        self._3d_ph_label = QLabel("3D 结构视图\n（首次使用时加载...）")
        self._3d_ph_label.setAlignment(Qt.AlignCenter)
        self._3d_ph_label.setStyleSheet("color: #999; font-size: 16px;")
        ph_layout.addWidget(self._3d_ph_label)
        self.center_stack.addWidget(self._3d_placeholder)

        # 2c. Right Sidebar
        self.right_stack = QStackedWidget()
        self.right_stack.setObjectName("RightSidebar")
        self.right_stack.setFixedWidth(320)

        self.analysis_panel_plot = AnalysisPanel()
        self.analysis_panel_plot.line_target.textChanged.connect(
            self._on_target_filter_changed
        )
        self.analysis_panel_plot.request_calculation.connect(self.run_analysis)
        self.analysis_panel_plot.request_export_csv.connect(self.export_csv)
        self.analysis_panel_plot.request_export_image.connect(self.export_image)
        self.analysis_panel_plot.request_export_fragments.connect(
            self.export_fragment_results
        )
        self.right_stack.addWidget(self.analysis_panel_plot)

        # Placeholder for 3D analysis panel (index 1) — replaced on first activation
        self._3d_panel_placeholder = QWidget()
        self.right_stack.addWidget(self._3d_panel_placeholder)

        content_layout.addWidget(self.left_sidebar)
        self.center_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.center_stack.setMinimumWidth(300)
        content_layout.addWidget(self.center_stack, 1)
        content_layout.addWidget(self.right_stack)

        # ── 3. Bottom Status Bar ──
        self.status_bar_widget = QWidget()
        self.status_bar_widget.setFixedHeight(40)
        self.status_bar_widget.setStyleSheet(
            "background-color: #F8F9FA; border-top: 1px solid #E0E0E0;"
        )
        status_layout = QHBoxLayout(self.status_bar_widget)
        status_layout.setContentsMargins(15, 0, 15, 0)

        self.lbl_status_indicator = QLabel("\u25cf 就绪")
        self.lbl_status_indicator.setStyleSheet("color: #198754; font-weight: bold;")

        self.lbl_status_rows = QLabel("行数: 0")
        self.lbl_status_atoms = QLabel("原子数: 0")
        self.lbl_status_sys = QLabel("体系数: 0")
        self.lbl_status_time = QLabel("最后更新: -")
        self.lbl_status_proj = QLabel("项目: 无")

        status_layout.addWidget(self.lbl_status_indicator)
        status_layout.addSpacing(30)
        status_layout.addWidget(self.lbl_status_rows)
        status_layout.addSpacing(15)
        status_layout.addWidget(self.lbl_status_atoms)
        status_layout.addSpacing(15)
        status_layout.addWidget(self.lbl_status_sys)
        status_layout.addSpacing(30)
        status_layout.addWidget(self.lbl_status_time)
        status_layout.addStretch()
        lbl_proj_icon = QLabel()
        lbl_proj_icon.setPixmap(qta.icon("fa5s.database", color="#666").pixmap(14, 14))
        status_layout.addWidget(lbl_proj_icon)
        status_layout.addWidget(self.lbl_status_proj)

        main_layout.addWidget(self.header_bar)
        main_layout.addWidget(content_area, 1)
        main_layout.addWidget(self.status_bar_widget)

        self.nav_tabs.setCurrentIndex(1)
        self.on_tab_changed(1)

    # ── sub-builders ──

    def _build_single_system_toolbar(self, parent_layout):
        """Filter / search bar above the single-system table."""
        bar = QWidget()
        bar.setFixedHeight(34)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "筛选: 元素 (O)、范围 (1-10)、电荷 (>0.5, <-0.3) 或文本\u2026"
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_single_table)
        lay.addWidget(self.search_input, 1)

        btn_clear = QPushButton("清除")
        btn_clear.setFixedWidth(50)
        btn_clear.clicked.connect(lambda: self.search_input.clear())
        lay.addWidget(btn_clear)

        self.btn_elem_summary = QPushButton("元素汇总")
        self.btn_elem_summary.setIcon(qta.icon("fa5s.chart-pie", color="#198754"))
        self.btn_elem_summary.setCheckable(True)
        self.btn_elem_summary.clicked.connect(self._toggle_element_summary)
        self.btn_elem_summary.setEnabled(False)
        lay.addWidget(self.btn_elem_summary)

        btn_add_col = QPushButton("添加列")
        btn_add_col.setIcon(qta.icon("fa5s.plus-circle", color="#0D6EFD"))
        btn_add_col.clicked.connect(self._add_custom_column)
        lay.addWidget(btn_add_col)

        parent_layout.addWidget(bar)

    def _build_single_system_table(self):
        self.tab_data = QTableWidget()
        self.tab_data.setColumnCount(N_BASE_COLS)
        self.tab_data.setHorizontalHeaderLabels(DISPLAY_BASE_COLUMNS)
        self.tab_data.horizontalHeader().setStretchLastSection(True)
        self.tab_data.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tab_data.setStyleSheet("border: none; background: white;")
        self.tab_data.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab_data.setSortingEnabled(True)
        self.tab_data.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_data.customContextMenuRequested.connect(self._show_context_menu_single)

        # Ctrl+C shortcut
        sc_copy = QShortcut(QKeySequence.Copy, self.tab_data)
        sc_copy.activated.connect(self._copy_selection_tsv)

        # Tooltips on column headers
        tips = {
            "Atom": "原子索引（从1开始）",
            "Element": "元素符号",
            "X": "笛卡尔 X 坐标 (\u00c5)",
            "Y": "笛卡尔 Y 坐标 (\u00c5)",
            "Z": "笛卡尔 Z 坐标 (\u00c5)",
            "CHARGE": "来自 ACF.dat 的原始 Bader 电荷",
            "ZVAL": "来自 POTCAR 的价电子数",
            "Bader Charge": "净电荷 = CHARGE \u2212 ZVAL（+ = 获得电子\u207b）",
            "Min_Dist": "到最近原子的最小距离 (\u00c5)",
            "Volume": "Bader 原子体积 (\u00c5\u00b3)",
        }
        for col, name in enumerate(BASE_COLUMNS):
            self.tab_data.horizontalHeaderItem(col).setToolTip(tips.get(name, ""))

    def _build_element_summary(self, parent_layout):
        """Collapsible element-group summary table below the main table."""
        self.element_summary_container = QWidget()
        es_lay = QVBoxLayout(self.element_summary_container)
        es_lay.setContentsMargins(0, 0, 0, 0)
        es_lay.setSpacing(2)

        hdr = QLabel("  元素分组汇总")
        hdr.setStyleSheet("font-weight: bold; font-size: 12px; color: #198754;")
        es_lay.addWidget(hdr)

        self.tab_element_summary = QTableWidget()
        self.tab_element_summary.setColumnCount(7)
        self.tab_element_summary.setHorizontalHeaderLabels(
            ["元素", "计数", "平均 Bader 电荷", "总和", "标准差", "最大值", "最小值"]
        )
        self.tab_element_summary.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tab_element_summary.setMaximumHeight(180)
        self.tab_element_summary.setStyleSheet("border: none; background: white;")
        es_lay.addWidget(self.tab_element_summary)

        self.element_summary_container.setVisible(False)
        parent_layout.addWidget(self.element_summary_container)

    def _build_multi_compare_toolbar(self, parent_layout):
        bar = QWidget()
        bar.setFixedHeight(34)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(8)

        self.chk_delta_mode = QCheckBox("\u0394 电荷模式")
        self.chk_delta_mode.setToolTip(
            "显示相对于基准体系的电荷差异"
        )
        self.chk_delta_mode.toggled.connect(self._on_delta_mode_changed)
        lay.addWidget(self.chk_delta_mode)

        lay.addWidget(QLabel("基准:"))
        self.cb_baseline = QComboBox()
        self.cb_baseline.setMinimumWidth(100)
        self.cb_baseline.currentTextChanged.connect(self._on_baseline_changed)
        lay.addWidget(self.cb_baseline)

        lay.addSpacing(12)

        btn_col_mgr = QPushButton("列")
        btn_col_mgr.setIcon(qta.icon("fa5s.columns", color="#555"))
        self._multi_col_menu = QMenu(self)
        btn_col_mgr.setMenu(self._multi_col_menu)
        lay.addWidget(btn_col_mgr)

        btn_export = QPushButton("导出")
        btn_export.setIcon(qta.icon("fa5s.download", color="#198754"))
        btn_export.clicked.connect(self._export_multi_compare)
        lay.addWidget(btn_export)

        lay.addStretch()

        parent_layout.addWidget(bar)

    def _build_multi_compare_table(self):
        self.tab_multi_compare = QTableWidget()
        self.tab_multi_compare.setStyleSheet("border: none; background: white;")
        self.tab_multi_compare.horizontalHeader().setStretchLastSection(True)
        self.tab_multi_compare.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tab_multi_compare.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab_multi_compare.setSortingEnabled(True)
        self.tab_multi_compare.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_multi_compare.customContextMenuRequested.connect(
            self._show_context_menu_multi
        )
        sc_copy2 = QShortcut(QKeySequence.Copy, self.tab_multi_compare)
        sc_copy2.activated.connect(self._copy_selection_tsv)

    # ────────────────────────────────────────────────────────────
    #  Event handlers
    # ────────────────────────────────────────────────────────────

    def on_atom_selected(self, data):
        if self.analysis_panel_3d is not None:
            self.analysis_panel_3d.update_selection_info(data)

    def on_plot_atom_selected(self, atom_id):
        """Plot \u2192 Table linkage: highlight table row for clicked bar."""
        self.nav_tabs.setCurrentIndex(0)
        self.on_tab_changed(0)
        if self.data_table_subtab:
            self.data_table_subtab.setCurrentIndex(0)
        if self.tab_data and atom_id:
            self.tab_data.setSortingEnabled(False)
            self.tab_data.clearSelection()
            for row in range(self.tab_data.rowCount()):
                item = self.tab_data.item(row, 0)
                if item and item.text() == str(atom_id):
                    self.tab_data.selectRow(row)
                    self.tab_data.scrollToItem(item)
                    break
            self.tab_data.setSortingEnabled(True)

    def _ensure_3d_loaded(self):
        """Lazy-load Visualizer3D and AnalysisPanel3D on first 3D-tab activation.

        This defers the heavy pyvista/VTK import (~10-30s) from application
        startup to the moment the user actually opens the 3D view tab.
        """
        if self._3d_loaded:
            return
        self._3d_ph_label.setText("正在加载 3D 引擎（导入模块）...")
        QApplication.processEvents()
        try:
            from gui.visualizer_3d import MultiVisualizer3DPanel
            from gui.analysis_panel import AnalysisPanel3D

            self._3d_ph_label.setText("正在初始化渲染窗口...")
            QApplication.processEvents()

            self.visualizer_3d = MultiVisualizer3DPanel()
            self.visualizer_3d.atom_selected.connect(self.on_atom_selected)
            self._has_3d = True

            self.analysis_panel_3d = AnalysisPanel3D()
            self.analysis_panel_3d.request_render_update.connect(self.update_3d_render_settings)
            self.analysis_panel_3d.btn_exp_img.clicked.connect(self.export_image)

            # Replace placeholders with real widgets
            self.center_stack.removeWidget(self._3d_placeholder)
            self._3d_placeholder.deleteLater()
            self.center_stack.insertWidget(2, self.visualizer_3d)

            self.right_stack.removeWidget(self._3d_panel_placeholder)
            self._3d_panel_placeholder.deleteLater()
            self.right_stack.insertWidget(1, self.analysis_panel_3d)

            self._3d_dirty = True
            self._3d_loaded = True  # Only mark loaded after full success

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._has_3d = False
            self.visualizer_3d = None
            self.analysis_panel_3d = None
            self._3d_ph_label.setText(
                f"3D 结构视图不可用\n({type(e).__name__}: {e})"
            )

    def on_tab_changed(self, index):
        if index == 2:
            self._ensure_3d_loaded()
            self._request_3d_sync(force=True)
        self.center_stack.setCurrentIndex(index)
        if index == 0 or index == 1:
            self.right_stack.setCurrentIndex(0)
        else:
            self.right_stack.setCurrentIndex(1)

    def toggle_theme(self):
        self.is_dark_theme = not self.is_dark_theme
        self.apply_theme()

    def closeEvent(self, event):
        visualizer = getattr(self, "visualizer_3d", None)
        if visualizer is not None:
            try:
                if hasattr(visualizer, "cleanup"):
                    visualizer.cleanup()
            except Exception:
                pass
        super().closeEvent(event)

    def _header_action_button_style(self):
        fg = "#E6E6E6" if self.is_dark_theme else "#444444"
        hover = "#2A2A2A" if self.is_dark_theme else "#F2F4F6"
        return (
            f"font-weight: bold; color: {fg}; padding: 6px 12px;"
            " border: none; border-radius: 6px;"
            f" background: transparent;"
            f" selection-background-color: {hover};"
        )

    def _sidebar_action_button_style(self):
        bg = "#2A2A2A" if self.is_dark_theme else "#FFFFFF"
        fg = "#E6E6E6" if self.is_dark_theme else "#0D6EFD"
        border = "#3A3A3A" if self.is_dark_theme else "#E0E0E0"
        hover = "#333333" if self.is_dark_theme else "#F5F7F9"
        return (
            f"border: 1px solid {border}; border-radius: 6px; padding: 9px;"
            f" font-weight: bold; background: {bg}; color: {fg};"
            f" selection-background-color: {hover};"
        )

    def _build_create_workspace_menu(self, parent):
        menu = QMenu(parent)
        menu.addAction("\u65b0\u5efa\u5de5\u4f5c\u533a", self.create_ws)
        menu.addAction("\u65b0\u5efa\u5206\u7ec4", self.create_group)
        return menu

    def load_workspaces(self):
        selected_before = set(self.selected_workspaces)
        self._syncing_ws_tree = True
        self.ws_tree.clear()
        grouped = self.ws_mgr.get_grouped_workspaces()
        total = 0
        for group, workspaces in grouped.items():
            group_item = QTreeWidgetItem([group])
            group_item.setIcon(0, qta.icon("fa5s.layer-group", color="#6c757d"))
            group_item.setData(0, Qt.UserRole, None)
            group_item.setFlags(group_item.flags() | Qt.ItemIsUserCheckable)
            group_item.setCheckState(0, Qt.Unchecked)
            self.ws_tree.addTopLevelItem(group_item)
            for ws in workspaces:
                meta = self.ws_mgr.get_workspace_meta(ws)
                label = meta.get("display_name") or ws
                item = QTreeWidgetItem([label])
                item.setIcon(0, qta.icon("fa5s.folder", color="#198754"))
                item.setData(0, Qt.UserRole, ws)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    0, Qt.Checked if ws in selected_before else Qt.Unchecked
                )
                group_item.addChild(item)
                total += 1
            if workspaces and all(ws in selected_before for ws in workspaces):
                group_item.setCheckState(0, Qt.Checked)
            group_item.setExpanded(True)
        self.lbl_status_sys.setText(f"\u4f53\u7cfb\u6570: {total}")
        self._syncing_ws_tree = False
        self.refresh_workspace_selection_context()

    def _group_name_for_item(self, item):
        if item is None:
            return self.ws_mgr.DEFAULT_GROUP
        if item.data(0, Qt.UserRole):
            parent = item.parent()
            return parent.text(0) if parent is not None else self.ws_mgr.DEFAULT_GROUP
        return item.text(0) or self.ws_mgr.DEFAULT_GROUP

    def _select_workspace_in_tree(self, workspace_name):
        for i in range(self.ws_tree.topLevelItemCount()):
            group_item = self.ws_tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                if child.data(0, Qt.UserRole) == workspace_name:
                    group_item.setExpanded(True)
                    self.ws_tree.setCurrentItem(child)
                    child.setSelected(True)
                    return child
        return None

    def _selected_workspace_name(self):
        item = self.ws_tree.currentItem()
        if not item:
            return None
        return item.data(0, Qt.UserRole)

    def _first_workspace_in_group(self, group_item):
        if group_item is None or group_item.data(0, Qt.UserRole):
            return None
        for i in range(group_item.childCount()):
            child_name = group_item.child(i).data(0, Qt.UserRole)
            if child_name:
                return child_name
        return None

    def get_selected_workspace_names(self):
        """Return batch-selected workspace names from checkboxes only."""
        ordered = []
        for i in range(self.ws_tree.topLevelItemCount()):
            group_item = self.ws_tree.topLevelItem(i)
            for j in range(group_item.childCount()):
                child = group_item.child(j)
                child_name = child.data(0, Qt.UserRole)
                if child_name and child.checkState(0) == Qt.Checked:
                    ordered.append(child_name)
        return ordered

    def set_group_checked(self, group_item, checked):
        if group_item is None or group_item.data(0, Qt.UserRole):
            return
        self._syncing_ws_tree = True
        group_item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
        for i in range(group_item.childCount()):
            group_item.child(i).setCheckState(
                0, Qt.Checked if checked else Qt.Unchecked
            )
        self._syncing_ws_tree = False
        self.refresh_workspace_selection_context()

    def _on_workspace_item_changed(self, item, column):
        if self._syncing_ws_tree or column != 0:
            return
        if item.data(0, Qt.UserRole):
            parent = item.parent()
            if parent is not None:
                states = [
                    parent.child(i).checkState(0)
                    for i in range(parent.childCount())
                ]
                if states and all(state == Qt.Checked for state in states):
                    parent_state = Qt.Checked
                elif any(state != Qt.Unchecked for state in states):
                    parent_state = Qt.PartiallyChecked
                else:
                    parent_state = Qt.Unchecked
                self._syncing_ws_tree = True
                parent.setCheckState(0, parent_state)
                self._syncing_ws_tree = False
            self.refresh_workspace_selection_context()
            return
        self.set_group_checked(item, item.checkState(0) == Qt.Checked)

    def refresh_workspace_selection_context(self):
        if self._syncing_ws_tree:
            return
        self.selected_workspaces = self.get_selected_workspace_names()
        current_targets = {
            name: self._workspace_targets.get(name, "")
            for name in self.selected_workspaces
        }
        if hasattr(self, "analysis_panel_plot"):
            self.analysis_panel_plot.set_selected_workspaces(
                self.selected_workspaces, current_targets
            )
        if self.plot_panel:
            # Push latest calculated data to plot panel so that Apply / chart
            # type change produce visible output (root-cause fix for stale
            # current_data after workspace activation).
            _plot_data = self._calculated_data_for_current_selection()
            if _plot_data:
                self.plot_panel.plot_data(
                    _plot_data,
                    target=self.analysis_panel_plot.line_target.text(),
                    fragments=self._fragment_expressions_for_workspaces(
                        list(_plot_data.keys()),
                        self.analysis_panel_plot.get_fragments(),
                    ),
                )
            else:
                self.plot_panel.plot_data({}, target="", fragments={})
            if getattr(self.plot_panel, "_ws_all", None):
                all_ws = set(self.plot_panel._ws_all)
                selected = set(self.selected_workspaces) & all_ws
                self.plot_panel._ws_selected = None if not selected or selected == all_ws else selected
                self.plot_panel._update_ws_button_text()
        self._request_3d_sync()

    def create_ws(self):
        import random
        target_group = self._group_name_for_item(self.ws_tree.currentItem())
        name = f"Workspace_{random.randint(1000, 9999)}"
        self.ws_mgr.create_workspace(name)
        self.ws_mgr.update_workspace_meta(name, group=target_group, display_name=name)
        self.selected_workspaces = [name]
        self.load_workspaces()
        self._select_workspace_in_tree(name)

    def create_group(self):
        group, ok = QInputDialog.getText(self, "\u65b0\u5efa\u5206\u7ec4", "\u5206\u7ec4\u540d\u79f0:")
        if ok and group.strip():
            self.ws_mgr.create_group(group)
            self.load_workspaces()

    def delete_selected_item(self):
        """Delete the currently selected workspace or entire group."""
        item = self.ws_tree.currentItem()
        if item is None:
            return
        ws_name = item.data(0, Qt.UserRole)
        if ws_name:
            # Single workspace deletion
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除工作区 '{ws_name}' 吗？\n此操作不可撤销。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.ws_mgr.delete_workspace(ws_name)
                self.load_workspaces()
                self.current_ws = None
                self.update_file_status()
        else:
            # Group header selected — delete all workspaces in the group
            group_name = item.text(0)
            child_count = item.childCount()
            if child_count == 0:
                # Empty group: just remove from group list
                groups = self.ws_mgr.get_groups()
                if group_name in groups:
                    groups.remove(group_name)
                    self.ws_mgr.save_groups(groups)
                    self.load_workspaces()
                return
            ws_names = [item.child(i).data(0, Qt.UserRole)
                        for i in range(child_count)
                        if item.child(i).data(0, Qt.UserRole)]
            reply = QMessageBox.question(
                self, "确认删除分组",
                f"确定要删除分组 '{group_name}' 及其包含的 {len(ws_names)} 个工作区吗？\n"
                f"工作区: {', '.join(ws_names)}\n此操作不可撤销。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                for ws in ws_names:
                    self.ws_mgr.delete_workspace(ws)
                # Remove group from registry
                groups = self.ws_mgr.get_groups()
                if group_name in groups:
                    groups.remove(group_name)
                    self.ws_mgr.save_groups(groups)
                self.load_workspaces()
                self.current_ws = None
                self.update_file_status()

    def _update_delete_tooltip(self):
        """Update delete button tooltip based on current tree selection."""
        item = self.ws_tree.currentItem()
        if item and not item.data(0, Qt.UserRole):
            self._btn_ws_delete.setToolTip(f"删除分组 '{item.text(0)}' 及全部子工作区")
        else:
            self._btn_ws_delete.setToolTip("删除工作区")

    def rename_ws(self):
        old_name = self._selected_workspace_name()
        if old_name:
            new_name, ok = QInputDialog.getText(
                self, "\u91cd\u547d\u540d\u5de5\u4f5c\u533a", "\u65b0\u540d\u79f0:", text=old_name
            )
            new_name = new_name.strip() if new_name else ""
            if ok and new_name and new_name != old_name:
                if self.ws_mgr.rename_workspace(old_name, new_name):
                    self.selected_workspaces = [new_name]
                    self.load_workspaces()
                    self._select_workspace_in_tree(new_name)
                    self.current_ws = new_name
                    self.update_file_status()
                else:
                    QMessageBox.warning(self, "\u8b66\u544a", "\u91cd\u547d\u540d\u5931\u8d25\u3002")

    def rename_selected_item(self, item=None, column=0):
        item = item or self.ws_tree.currentItem()
        if item is None:
            return
        ws_name = item.data(0, Qt.UserRole)
        if ws_name:
            self.ws_tree.setCurrentItem(item)
            self.rename_ws()
            return

        old_group = item.text(0)
        new_group, ok = QInputDialog.getText(
            self, "\u91cd\u547d\u540d\u5206\u7ec4", "\u65b0\u5206\u7ec4\u540d\u79f0:", text=old_group
        )
        if ok and new_group.strip() and new_group.strip() != old_group:
            if self.ws_mgr.rename_group(old_group, new_group.strip()):
                self.load_workspaces()
            else:
                QMessageBox.warning(self, "\u8b66\u544a", "\u91cd\u547d\u540d\u5206\u7ec4\u5931\u8d25\u3002")

    def move_workspace_to_group_name(self, name, group):
        names = name if isinstance(name, list) else [name]
        names = [n for n in names if n]
        if not names or not group:
            return
        moved = self.ws_mgr.move_workspaces_to_group(names, group)
        self.selected_workspaces = moved
        self.load_workspaces()
        for moved_name in moved:
            self._select_workspace_in_tree(moved_name)

    def move_ws_to_group(self):
        names = self.get_selected_workspace_names()
        if not names:
            QMessageBox.information(self, "\u63d0\u793a", "\u8bf7\u5148\u9009\u62e9\u5de5\u4f5c\u533a\u3002")
            return
        current_group = self.ws_mgr.get_workspace_meta(names[0]).get(
            "group", self.ws_mgr.DEFAULT_GROUP
        )
        group, ok = QInputDialog.getText(
            self, "\u79fb\u52a8\u5230\u5206\u7ec4", "\u5206\u7ec4\u540d\u79f0:", text=current_group
        )
        if ok:
            self.move_workspace_to_group_name(names, group.strip() or self.ws_mgr.DEFAULT_GROUP)

    def on_ws_selected(self, item, column):
        ws_name = item.data(0, Qt.UserRole)
        if not ws_name:
            focus_ws = self._first_workspace_in_group(item)
            if focus_ws:
                self._activate_workspace(focus_ws)
            return
        self._activate_workspace(ws_name)

    def _activate_workspace(self, ws_name):
        if not ws_name:
            return
        self.current_ws = ws_name
        self.analysis_panel_plot.set_fragments(self.ws_mgr.get_fragments(ws_name))
        self.lbl_files.setText(f"{self.current_ws} \u4e2d\u7684\u6587\u4ef6")
        self.lbl_status_proj.setText(f"\u9879\u76ee: {self.current_ws}")
        self.update_file_status()

        if self.data_table_subtab:
            self.data_table_subtab.setCurrentIndex(0)

        if self.current_ws in self.all_calculated_data:
            data = self.all_calculated_data[self.current_ws]
            self.current_df = data["df"]
            self.update_table_view(self.current_df)
            if self._has_3d:
                self._request_3d_sync()
        else:
            data = self._load_ws_data_from_disk(self.current_ws)
            if data is not None:
                self.current_df = data["df"]
                self.update_table_view(self.current_df)
                if self._has_3d:
                    self._request_3d_sync()
            else:
                self.tab_data.setRowCount(0)
                if self._has_3d:
                    self._request_3d_sync()

        self._rebuild_multi_compare()
        self._refresh_fragment_results()
        # Always refresh selection context — this also pushes calculated data
        # to the plot panel so the comparison chart stays in sync.
        self.refresh_workspace_selection_context()

    def save_project(self):
        """Save current workspace results to disk."""
        if not self.current_ws:
            QMessageBox.warning(self, "警告", "未选择工作区。")
            return
        if self.current_df is not None and not self.current_df.empty:
            self._save_results(self.current_ws, self.current_df)
            QMessageBox.information(self, "已保存", f"'{self.current_ws}' 的结果已保存。")
        else:
            QMessageBox.information(self, "信息", "没有可保存的数据，请先运行分析。")

    def open_file_dialog(self, event=None):
        if not self.current_ws:
            QMessageBox.warning(self, "警告", "请先选择或创建一个工作区。")
            return
        files, _ = QFileDialog.getOpenFileNames(self, "选择 VASP 文件", "", "所有文件 (*)")
        overwrite_all = False
        for f in files:
            filename = os.path.basename(f)
            destination = os.path.join(
                self.ws_mgr.get_workspace_path(self.current_ws), filename
            )
            overwrite = overwrite_all
            if os.path.exists(destination) and not overwrite:
                reply = QMessageBox.question(
                    self,
                    "确认覆盖",
                    f"工作区“{self.current_ws}”已存在 {filename}。\n"
                    f"来源：{f}\n\n是否替换？",
                    QMessageBox.Yes | QMessageBox.YesToAll
                    | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Cancel:
                    break
                if reply == QMessageBox.No:
                    continue
                overwrite_all = reply == QMessageBox.YesToAll
                overwrite = True
            self.ws_mgr.import_file(self.current_ws, f, overwrite=overwrite)
            if filename in self.ws_mgr.CRITICAL_INPUT_FILES:
                self._invalidate_workspace_cache(self.current_ws, filename)
        self.update_file_status()

    def _selected_imported_filename(self):
        item = self.list_files.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def replace_selected_file(self):
        if not self.current_ws:
            return
        filename = self._selected_imported_filename()
        if not filename:
            QMessageBox.information(self, "替换文件", "请先选择要替换的文件。")
            return
        source, _ = QFileDialog.getOpenFileName(
            self, f"选择用于替换 {filename} 的文件", "", "所有文件 (*)"
        )
        if not source:
            return
        reply = QMessageBox.question(
            self, "确认替换",
            f"确定用以下文件替换 {filename}？\n{source}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.ws_mgr.import_file(
            self.current_ws, source, overwrite=True, destination_name=filename
        )
        self._invalidate_workspace_cache(self.current_ws, filename)
        self.update_file_status()

    def delete_selected_file(self):
        if not self.current_ws:
            return
        filename = self._selected_imported_filename()
        if not filename:
            QMessageBox.information(self, "删除文件", "请先选择要删除的文件。")
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除 {filename}？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.ws_mgr.delete_file(self.current_ws, filename)
        self._invalidate_workspace_cache(self.current_ws, filename)
        self.update_file_status()

    def open_workspace_folder(self):
        if self.current_ws:
            os.startfile(self.ws_mgr.get_workspace_path(self.current_ws))

    def _invalidate_workspace_cache(self, workspace, filename):
        if not self.ws_mgr.invalidate_results(workspace, filename):
            return
        self.all_calculated_data.pop(workspace, None)
        if workspace == self.current_ws:
            self.current_df = None
            self.tab_data.setRowCount(0)
            self.tab_multi_compare.setRowCount(0)
        self.plot_panel.plot_data(self._calculated_data_for_current_selection())

    def update_file_status(self):
        self.list_files.clear()
        if not self.current_ws:
            self.analysis_panel_plot.update_file_status(None, [])
            if self.analysis_panel_3d is not None:
                self.analysis_panel_3d.update_file_status(None, [])
            return

        state = self.ws_mgr.load_state(self.current_ws)
        imported = [
            filename for filename in state.get("imported_files", [])
            if os.path.exists(
                os.path.join(self.ws_mgr.get_workspace_path(self.current_ws), filename)
            )
        ]
        if imported != state.get("imported_files", []):
            state["imported_files"] = imported
            self.ws_mgr.save_state(self.current_ws, state)

        if imported:
            for f in imported:
                item = QListWidgetItem(f" {f}")
                item.setIcon(qta.icon("fa5s.check-circle", color="#198754"))
                item.setData(Qt.UserRole, f)
                self.list_files.addItem(item)
        else:
            self.list_files.addItem(" 无文件")

        self.analysis_panel_plot.update_file_status(self.current_ws, imported)
        if self.analysis_panel_3d is not None:
            self.analysis_panel_3d.update_file_status(self.current_ws, imported)

    def run_analysis(self, config):
        names = self.get_selected_workspace_names()
        if not names and self.current_ws:
            names = [self.current_ws]
        if not names:
            return

        fragments = config.get("fragments", {}) or {}
        for name in names:
            self.ws_mgr.save_fragments(name, fragments)

        self._remember_workspace_targets(config)
        if len(names) > 1:
            self._start_batch_analysis(names, config)
            return

        self.current_ws = names[0]
        ws_path = self.ws_mgr.get_workspace_path(self.current_ws)
        bader_exe = self._find_bader_executable()

        from gui.worker import AnalysisWorker  # lazy: pulls in pymatgen chain
        self.worker = AnalysisWorker(ws_path, config, bader_exe)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.on_analysis_finished)

        self.lbl_status_indicator.setText("\u25cf \u8ba1\u7b97\u4e2d...")
        self.lbl_status_indicator.setStyleSheet("color: #0D6EFD; font-weight: bold;")
        self.worker.start()

    def _find_bader_executable(self):
        bader_exe = "bader"
        possible_paths = [
            "bader.exe", "bader",
            os.path.join("bader_engine", "bader.exe"),
            os.path.join("bader_engine", "bader"),
        ] + [os.fspath(path) for path in bundled_bader_candidates()]
        for path in possible_paths:
            if os.path.exists(path):
                bader_exe = path
                break
        return bader_exe

    def _remember_workspace_targets(self, config):
        default_target = config.get("target", "")
        targets = config.get("targets_by_workspace", {}) or {}
        for name in self.get_selected_workspace_names():
            self._workspace_targets[name] = targets.get(name, default_target)

    def _fragment_expressions_for_workspaces(self, workspaces, fragments=None):
        definitions = fragments or {}
        result = {}
        for workspace in workspaces:
            workspace_fragments = {}
            source = definitions or self.ws_mgr.get_fragments(workspace)
            for name, definition in source.items():
                overrides = definition.get("overrides", {}) or {}
                expression = overrides.get(
                    workspace, definition.get("expression", "")
                )
                if str(expression).strip():
                    workspace_fragments[name] = str(expression).strip()
            result[workspace] = workspace_fragments
        return result

    def _refresh_fragment_results(self):
        from core.calculator import ChargeCalculator, TargetSelectionError
        names = self.selected_workspaces or ([self.current_ws] if self.current_ws else [])
        rows = []
        for workspace in names:
            data = self.all_calculated_data.get(workspace)
            if data is None:
                data = self._load_ws_data_from_disk(workspace)
            if not data or data.get("df") is None:
                continue
            definitions = self.ws_mgr.get_fragments(workspace)
            expressions = self._fragment_expressions_for_workspaces(
                [workspace], definitions
            ).get(workspace, {})
            for fragment, expression in expressions.items():
                try:
                    stats = ChargeCalculator.aggregate_charge(data["df"], expression)
                except TargetSelectionError as exc:
                    QMessageBox.warning(
                        self, "片段定义错误",
                        f"{workspace} / {fragment}: {exc}",
                    )
                    continue
                rows.append({
                    "workspace": workspace,
                    "fragment": fragment,
                    **stats,
                })
        self.analysis_panel_plot.update_fragment_results(rows)
        return rows

    def _config_for_workspace(self, base_config, workspace):
        cfg = dict(base_config)
        targets = base_config.get("targets_by_workspace", {}) or {}
        cfg["target"] = targets.get(workspace, base_config.get("target", ""))
        return cfg

    def _calculated_data_for_current_selection(self):
        if not self.selected_workspaces:
            if self.current_ws in self.all_calculated_data:
                return {self.current_ws: self.all_calculated_data[self.current_ws]}
            return {}
        return {
            ws: self.all_calculated_data[ws]
            for ws in self.selected_workspaces
            if ws in self.all_calculated_data
        }

    def _start_batch_analysis(self, names, config):
        self._batch_queue = list(names)
        self._batch_errors = []
        self._batch_config = dict(config)
        self.lbl_status_indicator.setText(
            f"\u25cf \u6279\u91cf\u8ba1\u7b97\u4e2d 0/{len(self._batch_queue)}..."
        )
        self.lbl_status_indicator.setStyleSheet("color: #0D6EFD; font-weight: bold;")
        self._run_next_batch_analysis()

    def _run_next_batch_analysis(self):
        if not self._batch_queue:
            self._finish_batch_analysis()
            return

        workspace = self._batch_queue.pop(0)
        ws_path = self.ws_mgr.get_workspace_path(workspace)
        cfg = self._config_for_workspace(self._batch_config or {}, workspace)
        bader_exe = self._find_bader_executable()

        from gui.worker import AnalysisWorker  # lazy: pulls in pymatgen chain
        self._batch_worker = AnalysisWorker(ws_path, cfg, bader_exe)
        self._batch_worker.progress.connect(self.update_progress)
        self._batch_worker.finished.connect(
            lambda struct, df, err, ws=workspace: self._on_batch_analysis_finished(ws, struct, df, err)
        )

        total = len(self.selected_workspaces) or len(self._batch_queue) + 1
        done = total - len(self._batch_queue)
        self.lbl_status_indicator.setText(
            f"\u25cf \u6279\u91cf\u8ba1\u7b97\u4e2d {done}/{total}: {workspace}"
        )
        self._batch_worker.start()

    def _on_batch_analysis_finished(self, workspace, struct, df, err):
        if err:
            self._batch_errors.append(f"{workspace}: {err}")
        else:
            self.all_calculated_data[workspace] = {"df": df, "struct": struct}
            self._save_results(workspace, df)
        self._run_next_batch_analysis()

    def _finish_batch_analysis(self):
        self.lbl_status_indicator.setText("\u25cf \u5c31\u7eea")
        self.lbl_status_indicator.setStyleSheet("color: #198754; font-weight: bold;")

        first = next(
            (ws for ws in self.selected_workspaces if ws in self.all_calculated_data),
            None,
        )
        if first:
            self.current_ws = first
            data = self.all_calculated_data[first]
            self.current_df = data.get("df")
            if self.current_df is not None:
                self.update_table_view(self.current_df)
                self.btn_elem_summary.setEnabled(not self.current_df.empty)
                self._update_element_summary()

                # Update analysis panel summary (was missing, causing stale text)
                target_str = self.analysis_panel_plot.line_target.text().strip()
                sum_str = self.analysis_panel_plot.line_fragment.text().strip()
                total_charge = None
                if sum_str and not self.current_df.empty:
                    from core.calculator import ChargeCalculator
                    total_charge, _ = ChargeCalculator.calculate_custom_sum(
                        self.current_df, sum_str,
                        [data["Element"] for _, data in self.current_df.iterrows()]
                    )
                self.analysis_panel_plot.update_summary(
                    target_str, total_charge, "", "")

        sum_str = self.analysis_panel_plot.line_fragment.text().strip()
        self.plot_panel.set_fragment_text(sum_str)
        self.plot_panel.plot_data(self._calculated_data_for_current_selection())
        self._rebuild_multi_compare()
        self._refresh_fragment_results()
        self._request_3d_sync()

        # Sync 3D analysis panel elements (was missing after batch)
        if self.analysis_panel_3d is not None and self.current_df is not None and not self.current_df.empty:
            self.analysis_panel_3d.update_elements(set(self.current_df["Element"].values))
            self.analysis_panel_3d.emit_render_update()

        if self._batch_errors:
            QMessageBox.warning(
                self,
                "\u6279\u91cf\u8ba1\u7b97\u90e8\u5206\u5931\u8d25",
                "\n".join(self._batch_errors),
            )

    def update_progress(self, msg):
        pass

    def on_analysis_finished(self, struct, df, err):
        self.lbl_status_indicator.setText("\u25cf 就绪")
        self.lbl_status_indicator.setStyleSheet("color: #198754; font-weight: bold;")

        if err:
            QMessageBox.critical(self, "错误", f"分析失败:\n{err}")
            return

        self.all_calculated_data[self.current_ws] = {"df": df, "struct": struct}
        self.current_df = df

        self.update_table_view(df)

        # Persist results to disk
        self._save_results(self.current_ws, df)

        # Update summary on Plot right panel
        target_str = self.analysis_panel_plot.line_target.text().strip()
        sum_str = self.analysis_panel_plot.line_fragment.text().strip()
        from core.calculator import ChargeCalculator, TargetSelectionError
        stats = None
        selected_df = df
        try:
            stats = ChargeCalculator.aggregate_charge(df, target_str)
            selected_df = df[df["Atom"].isin(stats["atom_indices"])]
        except TargetSelectionError as exc:
            QMessageBox.warning(self, "目标原子错误", str(exc))
        total_charge = stats["sum"] if stats else None

        if not selected_df.empty:
            max_gain_idx = selected_df["Bader_Charge"].idxmax()
            max_loss_idx = selected_df["Bader_Charge"].idxmin()
            max_gain = selected_df.loc[max_gain_idx]
            max_loss = selected_df.loc[max_loss_idx]
            gain_str = f"{max_gain['Element']}{max_gain['Atom']} ({max_gain['Bader_Charge']:.3f} e)"
            loss_str = f"{max_loss['Element']}{max_loss['Atom']} ({max_loss['Bader_Charge']:.3f} e)"
        else:
            gain_str = "无"
            loss_str = "无"

        self.analysis_panel_plot.update_summary(
            target_str, total_charge, gain_str, loss_str, stats=stats
        )

        self.plot_panel.set_fragment_text(sum_str)
        self.plot_panel.plot_data(self._calculated_data_for_current_selection())
        if self._has_3d:
            self._request_3d_sync()
        if self.analysis_panel_3d is not None:
            if df is not None and not df.empty:
                self.analysis_panel_3d.update_elements(set(df["Element"].values))
            self.analysis_panel_3d.emit_render_update()

        self.lbl_status_rows.setText(f"行数: {len(df)}")
        self.lbl_status_atoms.setText(f"原子数: {len(struct) if struct else 0}")
        self.lbl_status_time.setText(
            f"最后更新: {datetime.datetime.now().strftime('%H:%M')}"
        )

        self.btn_elem_summary.setEnabled(not df.empty)
        self._update_element_summary()
        self._rebuild_multi_compare()
        self._refresh_fragment_results()

    def _on_target_filter_changed(self, expression):
        if self.current_df is None or self.current_df.empty:
            return
        from core.calculator import ChargeCalculator, TargetSelectionError
        display_df = self.current_df
        if expression.strip():
            try:
                stats = ChargeCalculator.aggregate_charge(
                    self.current_df, expression.strip()
                )
            except TargetSelectionError:
                return
            display_df = self.current_df[
                self.current_df["Atom"].isin(stats["atom_indices"])
            ]
        self.update_table_view(display_df)
        self.refresh_workspace_selection_context()

    def on_data_subtab_changed(self, index):
        if index == 1:
            self._rebuild_multi_compare()
        elif self.current_df is not None and not self.current_df.empty:
            self.lbl_status_rows.setText(f"行数: {len(self.current_df)}")
        else:
            self.lbl_status_rows.setText("行数: 0")

    # ────────────────────────────────────────────────────────────
    #  Core data methods
    # ────────────────────────────────────────────────────────────

    def update_table_view(self, df):
        """Populate single-system table from DataFrame."""
        self.tab_data.setSortingEnabled(False)
        self.tab_data.setRowCount(0)

        n_rows = len(df)
        n_cols = N_BASE_COLS + len(self._custom_columns)

        # Dynamic column labels (base + custom)
        if self._custom_columns:
            all_labels = list(DISPLAY_BASE_COLUMNS) + list(self._custom_columns.keys())
            self.tab_data.setColumnCount(n_cols)
            self.tab_data.setHorizontalHeaderLabels(all_labels)

        self.tab_data.setRowCount(n_rows)

        highlight_color = "#2A2A2A" if self.is_dark_theme else "#F8F9FA"
        highlight_bg = QBrush(QColor(highlight_color))
        fixed_bg = QBrush(QColor("#2A2A2A" if self.is_dark_theme else "#EAECEF"))

        # Pre-compute charge stats for coloring
        max_abs_charge = max(
            df["Bader_Charge"].abs().max() if not df.empty else 1.0, 0.01
        )
        # Anomaly thresholds
        charge_mean = df["Bader_Charge"].mean() if not df.empty else 0.0
        charge_std = df["Bader_Charge"].std() if len(df) > 1 else 0.0
        min_dist_q = df["Min_Dist"].quantile(0.1) if "Min_Dist" in df.columns and not df.empty else 0.0

        for row, (_, data) in enumerate(df.iterrows()):
            base_items = [
                str(data["Atom"]),
                str(data["Element"]),
                f"{data['X']:.4f}",
                f"{data['Y']:.4f}",
                f"{data['Z']:.4f}",
                f"{data['CHARGE']:.4f}",
                f"{data['ZVAL']}",
                f"{data['Bader_Charge']:.4f}",
                f"{data.get('Min_Dist', 0):.4f}",
                f"{data.get('Volume', 0):.4f}",
            ]

            for col, text in enumerate(base_items):
                item = SortableFloatItem(text)
                if col >= 5:  # CHARGE onward get highlight bg
                    item.setBackground(highlight_bg)
                else:  # Atom, Element, X, Y, Z get fixed bg
                    item.setBackground(fixed_bg)
                self.tab_data.setItem(row, col, item)

            # Custom columns
            for ci, (col_name, expr) in enumerate(self._custom_columns.items()):
                try:
                    val = self._eval_custom_expr(expr, data)
                    item = SortableFloatItem(f"{val:.4f}" if isinstance(val, float) else str(val))
                except Exception:
                    item = SortableFloatItem("错误")
                self.tab_data.setItem(row, N_BASE_COLS + ci, item)

        # Apply charge coloring (on top of highlight bg for the charge column)
        self._apply_charge_coloring_single(max_abs_charge)

        # Apply anomaly markers
        self._apply_anomaly_markers(df, charge_mean, charge_std, min_dist_q)

        self.tab_data.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tab_data.horizontalHeader().setStretchLastSection(True)
        self.tab_data.setSortingEnabled(True)

    def _rebuild_multi_compare(self):
        """Build (or rebuild) the multi-system comparison table."""
        self.tab_multi_compare.setSortingEnabled(False)

        calculated = {
            k: v for k, v in self._calculated_data_for_current_selection().items()
            if v.get("df") is not None and not v["df"].empty
        }

        if not calculated:
            self.tab_multi_compare.setRowCount(0)
            self.tab_multi_compare.setColumnCount(1)
            self.tab_multi_compare.setHorizontalHeaderLabels(["\u6682\u65e0\u53ef\u6bd4\u5bf9\u7684\u6570\u636e"])
            return

        ws_names = list(calculated.keys())
        n_systems = len(ws_names)

        # Update baseline combo
        old_baseline = self._baseline_ws
        self.cb_baseline.blockSignals(True)
        self.cb_baseline.clear()
        self.cb_baseline.addItems(ws_names)
        if old_baseline in ws_names:
            self.cb_baseline.setCurrentText(old_baseline)
            self._baseline_ws = old_baseline
        else:
            self._baseline_ws = ws_names[0]
        self.cb_baseline.blockSignals(False)

        # Column headers
        n_fixed_cols = 6
        fixed_headers = ["原子", "元素", "ZVAL", "X", "Y", "Z"]
        charge_headers = []
        for ws in ws_names:
            if self._delta_mode and ws == self._baseline_ws:
                charge_headers.append(f"{ws}\n(基准)")
            elif self._delta_mode:
                charge_headers.append(f"\u0394 {ws}")
            else:
                charge_headers.append(f"{ws}\nBader 电荷")

        total_cols = n_fixed_cols + n_systems
        self.tab_multi_compare.setColumnCount(total_cols)
        self.tab_multi_compare.setHorizontalHeaderLabels(fixed_headers + charge_headers)

        # Row count = data rows + summary rows
        first_df = calculated[ws_names[0]]["df"]
        n_data = len(first_df)
        summary_labels = ["平均值", "标准差", "极差", "最大值", "最小值"]
        n_summary = len(summary_labels)
        total_rows = n_data + n_summary
        self.tab_multi_compare.setRowCount(total_rows)

        dark = self.is_dark_theme
        highlight_bg = QBrush(QColor("#2A2A2A" if dark else "#F8F9FA"))
        fixed_bg = QBrush(QColor("#2A2A2A" if dark else "#EAECEF"))
        summary_bg = QBrush(QColor("#3A3A3A" if dark else "#E8EAF0"))

        # Pre-compute per-atom, per-ws charge matrix for summary & coloring
        charge_matrix = {}  # atom_idx -> list of charges per ws
        for row_idx in range(n_data):
            charges = []
            for ws in ws_names:
                df_ws = calculated[ws]["df"]
                if row_idx < len(df_ws):
                    val = df_ws.iloc[row_idx].get("Bader_Charge")
                    if val is not None and not (isinstance(val, float) and math.isnan(val)):
                        charges.append(float(val))
                    else:
                        charges.append(float("nan"))
                else:
                    charges.append(float("nan"))
            charge_matrix[row_idx] = charges

        max_abs_charge = 0.01
        for charges in charge_matrix.values():
            for c in charges:
                if not math.isnan(c):
                    max_abs_charge = max(max_abs_charge, abs(c))

        # ── Fill data rows ──
        for row_idx in range(n_data):
            row_data = first_df.iloc[row_idx]
            fixed_vals = [
                str(row_data["Atom"]),
                str(row_data["Element"]),
                self._fmt_val(row_data.get("ZVAL"), ".1f"),
                self._fmt_val(row_data.get("X"), ".4f"),
                self._fmt_val(row_data.get("Y"), ".4f"),
                self._fmt_val(row_data.get("Z"), ".4f"),
            ]
            for col, text in enumerate(fixed_vals):
                item = SummaryItem(text)
                item.setBackground(fixed_bg)
                self.tab_multi_compare.setItem(row_idx, col, item)

            # Charge columns
            for si, ws in enumerate(ws_names):
                charge = charge_matrix[row_idx][si]
                if self._delta_mode and ws != self._baseline_ws:
                    base_charge = charge_matrix[row_idx][ws_names.index(self._baseline_ws)]
                    if not math.isnan(charge) and not math.isnan(base_charge):
                        display_val = charge - base_charge
                    else:
                        display_val = float("nan")
                else:
                    display_val = charge

                text = f"{display_val:.4f}" if not math.isnan(display_val) else "-"
                item = SummaryItem(text)
                item.setBackground(highlight_bg)

                # Charge coloring
                if not math.isnan(display_val):
                    bg = self._charge_bg_color(display_val, max_abs_charge, dark)
                    if bg:
                        item.setBackground(QBrush(bg))

                self.tab_multi_compare.setItem(row_idx, n_fixed_cols + si, item)

        # ── Fill summary rows ──
        for si, label in enumerate(summary_labels):
            row_pos = n_data + si
            # Label in first column
            lbl_item = SummaryItem(label)
            lbl_item.setBackground(summary_bg)
            self.tab_multi_compare.setItem(row_pos, 0, lbl_item)
            # Blank fixed columns
            for col in range(1, n_fixed_cols):
                blank = SummaryItem("")
                blank.setBackground(summary_bg)
                self.tab_multi_compare.setItem(row_pos, col, blank)

            # Per-ws stats
            for wi in range(n_systems):
                vals = [
                    charge_matrix[ri][wi] for ri in range(n_data)
                    if not math.isnan(charge_matrix[ri][wi])
                ]
                stat_val = self._compute_stat(label, vals)
                text = f"{stat_val:.4f}" if stat_val is not None else "-"
                item = SummaryItem(text)
                item.setBackground(summary_bg)
                if stat_val is not None and label in ("平均值", "最大值", "最小值"):
                    bg = self._charge_bg_color(stat_val, max_abs_charge, dark)
                    if bg:
                        item.setBackground(QBrush(bg))
                self.tab_multi_compare.setItem(row_pos, n_fixed_cols + wi, item)

        self.tab_multi_compare.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tab_multi_compare.horizontalHeader().setStretchLastSection(True)
        self.tab_multi_compare.setSortingEnabled(True)

        # Populate column-visibility menu for multi-compare table
        self._multi_col_menu.clear()
        for col in range(self.tab_multi_compare.columnCount()):
            hi = self.tab_multi_compare.horizontalHeaderItem(col)
            name = hi.text().replace("\n", " ") if hi else f"列 {col}"
            act = QAction(name, self._multi_col_menu)
            act.setCheckable(True)
            act.setChecked(True)
            act.toggled.connect(lambda checked, c=col: self.tab_multi_compare.setColumnHidden(c, not checked))
            self._multi_col_menu.addAction(act)

        # Update status bar
        self.lbl_status_rows.setText(f"原子数: {n_data} \u00d7 体系数: {n_systems}")

    # ────────────────────────────────────────────────────────────
    #  3D render settings (unchanged)
    # ────────────────────────────────────────────────────────────

    def _request_3d_sync(self, force=False):
        """Synchronize 3D data only when the 3D tab is active.

        Multi-workspace 3D rendering is expensive because each workspace may
        build a VTK scene. Keep non-3D workflows responsive by marking the 3D
        view dirty and doing the actual sync when the user opens the 3D tab.
        """
        if not getattr(self, "_has_3d", False) or self.visualizer_3d is None:
            self._3d_dirty = True
            return
        if not force and getattr(self, "nav_tabs", None) is not None and self.nav_tabs.currentIndex() != 2:
            self._3d_dirty = True
            return
        self._sync_3d_workspaces()
        self._3d_dirty = False

    def _sync_3d_workspaces(self):
        if not getattr(self, "_has_3d", False) or self.visualizer_3d is None:
            return
        names = list(self.selected_workspaces)
        if not names and self.current_ws:
            names = [self.current_ws]

        data_by_workspace = {}
        elements = set()
        for name in names:
            data = self.all_calculated_data.get(name)
            if data is None:
                data = self._load_ws_data_from_disk(name)
            if data is not None:
                data_by_workspace[name] = data
                df = data.get("df")
                if df is not None and not df.empty and "Element" in df.columns:
                    elements.update(df["Element"].values)

        self.visualizer_3d.set_workspaces_data(data_by_workspace, names)
        if self.analysis_panel_3d is not None and elements:
            self.analysis_panel_3d.update_elements(elements)

    def update_3d_render_settings(self, settings):
        if not self._has_3d:
            return
        action = settings.get("action", "render")
        if action == "focus":
            self.visualizer_3d.focus_atom()
            return
        if action == "isolate":
            self.visualizer_3d.isolate_atom()
            return
        if action == "clear":
            self.visualizer_3d.clear_selection()
            self.analysis_panel_3d.update_selection_info({})
            return
        if action == "export_model":
            path, _ = QFileDialog.getSaveFileName(
                self, "导出 3D 模型", "structure.ply",
                "PLY (*.ply);;VTP (*.vtp);;VTM (*.vtm)",
            )
            if path:
                try:
                    self.visualizer_3d.export_model(path)
                except ValueError as exc:
                    QMessageBox.warning(self, "导出 3D 模型", str(exc))
            return
        self.visualizer_3d.set_render_state(
            hide_bg=settings["hide_bg"],
            show_labels=settings["show_labels"],
            show_bonds=settings["show_bonds"],
            target_str=settings.get("target_str", ""),
            label_target_str=settings.get("label_target_str", ""),
            trans=settings.get("transparency", 10),
            scale=settings.get("sphere_scale", 100),
            light=settings.get("ambient_light", 65),
            bond_radius=settings.get("bond_radius", 8),
            show_cell=settings.get("show_cell", True),
            show_axes_flag=settings.get("show_axes", True),
            color_by=settings.get("color_by", "Bader Charge"),
            cmap=settings.get("cmap", "RdBu_r"),
            cmap_gamma=settings.get("cmap_gamma", 1.0),
            cmap_range=settings.get("cmap_range", "极值"),
            color_profile=settings.get("color_profile", "标准"),
            representation=settings.get("representation", "ball_stick"),
            custom_colors=settings.get("custom_colors"),
        )

    # ────────────────────────────────────────────────────────────
    #  Export methods
    # ────────────────────────────────────────────────────────────

    def export_csv(self):
        """Export current single-system DataFrame as CSV."""
        if self.current_df is None or self.current_df.empty:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "bader_charge.csv", "CSV Files (*.csv)"
        )
        if path:
            try:
                self.current_df.to_csv(path, index=False)
            except Exception as e:
                QMessageBox.warning(self, "导出失败", f"无法写入 CSV:\n{e}")

    def export_fragment_results(self):
        rows = self._refresh_fragment_results()
        if not rows:
            QMessageBox.information(self, "导出片段统计", "没有可导出的片段统计。")
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "导出片段统计", "fragment_statistics.csv",
            "CSV (*.csv);;Excel (*.xlsx)",
        )
        if not path:
            return
        import pandas as pd
        records = []
        for row in rows:
            records.append({
                "工作区": row["workspace"],
                "片段": row["fragment"],
                "表达式": row["expression"],
                "原子编号": ",".join(map(str, row["atom_indices"])),
                "原子数": row["count"],
                "电荷转移总和(e)": row["sum"],
                "平均值(e)": row["mean"],
                "标准差(e)": row["std"],
                "最大值(e)": row["max"],
                "最小值(e)": row["min"],
            })
        frame = pd.DataFrame(records)
        if "xlsx" in selected_filter.lower() or path.lower().endswith(".xlsx"):
            frame.to_excel(path, index=False, engine="openpyxl")
        else:
            frame.to_csv(path, index=False, encoding="utf-8-sig")

    def export_image(self):
        idx = self.center_stack.currentIndex()
        if idx == 1:
            path, _ = QFileDialog.getSaveFileName(
                self, "导出 2D 图片", "plot.png", "Images (*.png *.jpg)"
            )
            if path:
                fig = self.plot_panel.figure
                orig_w, orig_h = fig.get_size_inches()
                try:
                    fig.set_size_inches(
                        self.plot_panel.config.export_width,
                        self.plot_panel.config.export_height,
                    )
                    fig.savefig(
                        path,
                        dpi=self.plot_panel.config.export_dpi,
                        bbox_inches="tight",
                        transparent=self.plot_panel.config.export_transparent,
                    )
                finally:
                    fig.set_size_inches(orig_w, orig_h)
                    fig.canvas.draw_idle()
        elif idx == 2 and self._has_3d:
            path, _ = QFileDialog.getSaveFileName(
                self, "导出 3D 图片", "3d_view.png", "Images (*.png)"
            )
            if path and self.visualizer_3d.plotter is not None:
                self.visualizer_3d.plotter.screenshot(path)

    def export_model(self):
        if not self._has_3d:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 3D 模型", "structure.ply",
            "PLY (*.ply);;VTP (*.vtp);;VTM (*.vtm)",
        )
        if path:
            try:
                self.visualizer_3d.export_model(path)
            except ValueError as exc:
                QMessageBox.warning(self, "导出 3D 模型", str(exc))

    def _export_multi_compare(self):
        """Export multi-compare table as CSV or Excel."""
        calculated = {
            k: v for k, v in self._calculated_data_for_current_selection().items()
            if v.get("df") is not None and not v["df"].empty
        }
        if not calculated:
            return

        path, fmt = QFileDialog.getSaveFileName(
            self, "导出多体系对比", "multi_compare",
            "CSV (*.csv);;Excel (*.xlsx)",
        )
        if not path:
            return

        df_export = self._build_multi_compare_df(calculated)

        if fmt and "xlsx" in fmt:
            try:
                df_export.to_excel(path, index=False, engine="openpyxl")
            except ImportError:
                csv_path = path.rsplit(".", 1)[0] + ".csv"
                df_export.to_csv(csv_path, index=False)
                QMessageBox.warning(
                    self, "提示",
                    f"openpyxl 不可用，已导出为 CSV:\n{csv_path}",
                )
        else:
            df_export.to_csv(path, index=False)

    def _build_multi_compare_df(self, calculated):
        """Build a pandas DataFrame representing the multi-compare table (incl. summary)."""
        import pandas as pd
        ws_names = list(calculated.keys())
        metadata_columns = ["Atom", "Element", "ZVAL", "X", "Y", "Z"]
        metadata = None
        charge_data = None
        for ws in ws_names:
            df_ws = calculated[ws]["df"]
            available_meta = [
                column for column in metadata_columns if column in df_ws.columns
            ]
            ws_meta = df_ws[available_meta].drop_duplicates("Atom").set_index("Atom")
            metadata = ws_meta if metadata is None else metadata.combine_first(ws_meta)
            ws_charge = (
                df_ws[["Atom", "Bader_Charge"]]
                .drop_duplicates("Atom")
                .rename(columns={"Bader_Charge": f"{ws}_Bader_Charge"})
                .set_index("Atom")
            )
            charge_data = (
                ws_charge if charge_data is None
                else charge_data.join(ws_charge, how="outer")
            )

        result = metadata.join(charge_data, how="outer").sort_index().reset_index()
        if self._delta_mode and self._baseline_ws in calculated:
            baseline_column = f"{self._baseline_ws}_Bader_Charge"
            for ws in ws_names:
                column = f"{ws}_Bader_Charge"
                if ws != self._baseline_ws:
                    result[f"\u0394_{ws}"] = result[column] - result[baseline_column]
                    result.drop(columns=[column], inplace=True)

        # Append summary rows
        charge_cols = [c for c in result.columns if c not in ("Atom", "Element", "ZVAL", "X", "Y", "Z")]
        for label, func in [
            ("平均值", lambda s: s.mean()),
            ("标准差", lambda s: s.std()),
            ("极差", lambda s: s.max() - s.min()),
            ("最大值", lambda s: s.max()),
            ("最小值", lambda s: s.min()),
        ]:
            row = {"Atom": label, "Element": "", "ZVAL": "", "X": "", "Y": "", "Z": ""}
            for c in charge_cols:
                try:
                    row[c] = round(func(result[c].astype(float)), 4)
                except Exception:
                    row[c] = ""
            result = pd.concat([result, pd.DataFrame([row])], ignore_index=True)

        return result

    # ────────────────────────────────────────────────────────────
    #  Filter / Search
    # ────────────────────────────────────────────────────────────

    def _filter_single_table(self, text):
        """Real-time filter for the single-system table."""
        self.tab_data.setSortingEnabled(False)
        text = text.strip()
        if not text:
            for row in range(self.tab_data.rowCount()):
                self.tab_data.setRowHidden(row, False)
            self.lbl_status_rows.setText(
                f"行数: {len(self.current_df)}" if self.current_df is not None else "行数: 0"
            )
            self.tab_data.setSortingEnabled(True)
            return

        if self.current_df is None or self.current_df.empty:
            self.tab_data.setSortingEnabled(True)
            return

        df = self.current_df
        # Build atom_id -> row-data lookup (Atom is a column, not the index)
        atom_data = {}
        for _, row in df.iterrows():
            try:
                atom_data[int(row["Atom"])] = row
            except (ValueError, TypeError, KeyError):
                pass

        visible_count = 0

        # Parse filter mode
        mode = "text"
        filter_data = None

        # Element filter: pure letters / commas
        if re.match(r"^[A-Za-z,\s]+$", text):
            mode = "element"
            filter_data = [e.strip().capitalize() for e in re.split(r"[,\s]+", text) if e.strip()]

        # Charge comparison: >0.5, <-0.3, >=1.0
        elif re.match(r"^[><=!]+\s*[\-]?\d", text):
            m = re.match(r"^([><=!]+)\s*([\-]?\d+\.?\d*)$", text)
            if m:
                mode = "charge"
                filter_data = (m.group(1), float(m.group(2)))

        # Range: 1-10, 5-, -20
        elif re.match(r"^\d+\s*-\s*\d*$", text) or re.match(r"^-\s*\d+$", text):
            mode = "range"
            parts = text.split("-")
            start = int(parts[0].strip()) if parts[0].strip() else 1
            end_str = parts[-1].strip() if len(parts) > 1 else ""
            filter_data = (start, int(end_str) if end_str else 999999)

        # Single integer
        elif text.isdigit():
            mode = "single_int"
            filter_data = int(text)

        for row in range(self.tab_data.rowCount()):
            item0 = self.tab_data.item(row, 0)
            if not item0:
                self.tab_data.setRowHidden(row, True)
                continue

            try:
                atom_id = int(item0.text())
            except (ValueError, TypeError):
                self.tab_data.setRowHidden(row, True)
                continue

            if atom_id not in atom_data:
                self.tab_data.setRowHidden(row, True)
                continue

            row_data = atom_data[atom_id]
            show = False

            try:
                if mode == "element":
                    show = str(row_data.get("Element", "")).capitalize() in filter_data

                elif mode == "charge":
                    op, threshold = filter_data
                    charge = float(row_data.get("Bader_Charge", 0))
                    if op in (">", ">\u200b"):
                        show = charge > threshold
                    elif op in ("<", "<\u200b"):
                        show = charge < threshold
                    elif op in (">=", "\u2265"):
                        show = charge >= threshold
                    elif op in ("<=", "\u2264"):
                        show = charge <= threshold
                    elif op in ("==", "="):
                        show = abs(charge - threshold) < 0.001
                    elif op in ("!=", "\u2260"):
                        show = abs(charge - threshold) >= 0.001
                    else:
                        show = True

                elif mode == "range":
                    start, end = filter_data
                    show = start <= atom_id <= end

                elif mode == "single_int":
                    show = atom_id == filter_data

                else:  # text search
                    show = (
                        text.lower() in str(row_data.get("Element", "")).lower()
                        or text.lower() in " ".join(str(v) for v in row_data.values).lower()
                    )
            except Exception:
                show = True

            self.tab_data.setRowHidden(row, not show)
            if show:
                visible_count += 1

        self.lbl_status_rows.setText(f"行数: {visible_count}/{len(df)}")
        self.tab_data.setSortingEnabled(True)

    # ────────────────────────────────────────────────────────────
    #  Context menus
    # ────────────────────────────────────────────────────────────

    def _show_context_menu_single(self, pos):
        menu = QMenu(self)

        act_copy = menu.addAction("复制选中行 (TSV)")
        act_copy_csv = menu.addAction("复制为 CSV")
        act_copy_md = menu.addAction("复制为 Markdown 表格")
        menu.addSeparator()
        act_detail = menu.addAction("查看原子详情")
        act_export_sel = menu.addAction("导出选中内容到 CSV")
        menu.addSeparator()
        act_col_mgr = menu.addAction("管理列\u2026")

        action = menu.exec(self.tab_data.viewport().mapToGlobal(pos))
        if action == act_copy:
            self._copy_selection_tsv()
        elif action == act_copy_csv:
            self._copy_selection_csv()
        elif action == act_copy_md:
            self._copy_selection_markdown()
        elif action == act_detail:
            self._show_atom_detail()
        elif action == act_export_sel:
            self._export_selection_csv()
        elif action == act_col_mgr:
            self._show_column_manager_single()

    def _show_context_menu_multi(self, pos):
        menu = QMenu(self)

        act_copy = menu.addAction("复制选中行 (TSV)")
        act_copy_csv = menu.addAction("复制为 CSV")
        act_copy_md = menu.addAction("复制为 Markdown 表格")
        menu.addSeparator()
        act_export = menu.addAction("导出完整表格到 CSV/Excel")

        action = menu.exec(self.tab_multi_compare.viewport().mapToGlobal(pos))
        if action == act_copy:
            self._copy_selection_tsv()
        elif action == act_copy_csv:
            self._copy_selection_csv()
        elif action == act_copy_md:
            self._copy_selection_markdown()
        elif action == act_export:
            self._export_multi_compare()

    # ────────────────────────────────────────────────────────────
    #  Clipboard / copy
    # ────────────────────────────────────────────────────────────

    def _copy_selection_tsv(self):
        """Copy selected rows as Tab-separated text (Excel-paste friendly)."""
        table = self._active_table()
        if table is None:
            return
        text = self._table_selection_to_text(table, sep="\t", include_header=True)
        if text:
            QApplication.clipboard().setText(text)

    def _copy_selection_csv(self):
        table = self._active_table()
        if table is None:
            return
        text = self._table_selection_to_text(table, sep=",", include_header=True)
        if text:
            QApplication.clipboard().setText(text)

    def _copy_selection_markdown(self):
        table = self._active_table()
        if table is None:
            return
        rows = self._visible_selected_rows(table)
        if not rows:
            return

        headers = []
        for col in range(table.columnCount()):
            if not table.isColumnHidden(col):
                hi = table.horizontalHeaderItem(col)
                headers.append(hi.text().replace("\n", " ") if hi else "")

        lines = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for row in rows:
            cells = []
            for col in range(table.columnCount()):
                if table.isColumnHidden(col):
                    continue
                item = table.item(row, col)
                cells.append(item.text() if item else "")
            lines.append("| " + " | ".join(cells) + " |")

        QApplication.clipboard().setText("\n".join(lines))

    def _active_table(self):
        """Return whichever QTableWidget currently has focus."""
        if self.tab_data.hasFocus() or self.tab_data.viewport().hasFocus():
            return self.tab_data
        if self.tab_multi_compare.hasFocus() or self.tab_multi_compare.viewport().hasFocus():
            return self.tab_multi_compare
        # Fallback: check which sub-tab is active
        if self.data_table_subtab and self.data_table_subtab.currentIndex() == 0:
            return self.tab_data
        return self.tab_multi_compare

    def _visible_selected_rows(self, table):
        """Return sorted list of selected, visible row indices."""
        selected = sorted(set(idx.row() for idx in table.selectedIndexes()))
        return [r for r in selected if not table.isRowHidden(r)]

    def _table_selection_to_text(self, table, sep="\t", include_header=True):
        rows = self._visible_selected_rows(table)
        if not rows:
            return ""

        visible_cols = [c for c in range(table.columnCount()) if not table.isColumnHidden(c)]

        lines = []
        if include_header:
            hdr = []
            for col in visible_cols:
                hi = table.horizontalHeaderItem(col)
                hdr.append(hi.text().replace("\n", " ") if hi else "")
            lines.append(sep.join(hdr))

        for row in rows:
            cells = []
            for col in visible_cols:
                item = table.item(row, col)
                cells.append(item.text() if item else "")
            lines.append(sep.join(cells))

        return "\n".join(lines)

    def _export_selection_csv(self):
        """Export selected rows of single-system table to CSV file."""
        if self.current_df is None or self.current_df.empty:
            return
        rows = self._visible_selected_rows(self.tab_data)
        if not rows:
            QMessageBox.information(self, "信息", "未选中任何行。")
            return

        atom_ids = []
        for r in rows:
            item = self.tab_data.item(r, 0)
            if item:
                try:
                    atom_ids.append(int(item.text()))
                except ValueError:
                    pass

        df_sel = self.current_df.loc[self.current_df["Atom"].isin(atom_ids)]
        path, _ = QFileDialog.getSaveFileName(
            self, "导出选中内容", "selection.csv", "CSV (*.csv)"
        )
        if path:
            df_sel.to_csv(path, index=False)

    # ────────────────────────────────────────────────────────────
    #  Charge coloring helpers
    # ────────────────────────────────────────────────────────────

    def _charge_bg_color(self, charge, max_abs, dark):
        """Return QColor for charge cell background, or None if neutral."""
        if abs(charge) < 0.001 or max_abs < 0.001:
            return None
        intensity = min(abs(charge) / max_abs, 1.0)
        alpha = 0.08 + 0.40 * intensity
        if charge > 0:
            r, g, b = (1.0, 0.78, 0.78) if dark else (1.0, 0.88, 0.88)
        else:
            r, g, b = (0.78, 0.84, 1.0) if dark else (0.88, 0.92, 1.0)
        return QColor.fromRgbF(r, g, b, alpha)

    def _apply_charge_coloring_single(self, max_abs_charge):
        """Apply diverging red/blue background to Bader Charge column."""
        col = BADER_COL
        dark = self.is_dark_theme
        for row in range(self.tab_data.rowCount()):
            item = self.tab_data.item(row, col)
            if not item:
                continue
            try:
                val = float(item.text())
            except (ValueError, TypeError):
                continue
            bg = self._charge_bg_color(val, max_abs_charge, dark)
            if bg:
                item.setBackground(QBrush(bg))

    # ────────────────────────────────────────────────────────────
    #  Anomaly markers
    # ────────────────────────────────────────────────────────────

    def _apply_anomaly_markers(self, df, charge_mean, charge_std, min_dist_q):
        """Highlight rows with suspicious values (yellow bg + tooltip)."""
        if charge_std < 0.001:
            return  # not enough variance to detect anomalies

        threshold_hi = charge_mean + 2.5 * charge_std
        threshold_lo = charge_mean - 2.5 * charge_std

        # Build atom_id -> row-data lookup (Atom is a column, not the index)
        atom_data = {}
        for _, row in df.iterrows():
            try:
                atom_data[int(row["Atom"])] = row
            except (ValueError, TypeError, KeyError):
                pass

        for row in range(self.tab_data.rowCount()):
            item0 = self.tab_data.item(row, 0)
            if not item0:
                continue
            try:
                atom_id = int(item0.text())
            except ValueError:
                continue
            if atom_id not in atom_data:
                continue

            rd = atom_data[atom_id]
            warnings = []

            bc = rd.get("Bader_Charge", 0)
            if bc > threshold_hi or bc < threshold_lo:
                warnings.append(f"Bader 电荷 {bc:.3f} 偏离均值超过 2.5\u03c3")

            md = rd.get("Min_Dist", 999)
            if md < 0.5:
                warnings.append(f"最小距离 {md:.3f} \u00c5 < 0.5 \u00c5（可能存在重叠）")

            vol = rd.get("Volume", 1)
            if vol <= 0:
                warnings.append("体积 \u2264 0（异常）")

            if warnings:
                tip = "\n".join(warnings)
                warn_bg = QBrush(QColor(255, 255, 180, 160) if not self.is_dark_theme
                                  else QColor(120, 110, 50, 160))
                for col in range(self.tab_data.columnCount()):
                    cell = self.tab_data.item(row, col)
                    if cell:
                        cell.setBackground(warn_bg)
                        cell.setToolTip(tip)

    # ────────────────────────────────────────────────────────────
    #  Column visibility
    # ────────────────────────────────────────────────────────────

    def _show_column_manager_single(self):
        """Show a checkable menu to toggle column visibility on single-system table."""
        menu = QMenu("列可见性", self)
        actions = {}
        for col in range(self.tab_data.columnCount()):
            hi = self.tab_data.horizontalHeaderItem(col)
            name = hi.text() if hi else f"列 {col}"
            act = QAction(name, menu)
            act.setCheckable(True)
            act.setChecked(not self.tab_data.isColumnHidden(col))
            actions[act] = col
            menu.addAction(act)

        # Show menu at cursor
        menu.exec(self.tab_data.mapToGlobal(self.tab_data.rect().topRight()))

        for act, col in actions.items():
            self.tab_data.setColumnHidden(col, not act.isChecked())

    # ────────────────────────────────────────────────────────────
    #  Delta mode (multi-compare)
    # ────────────────────────────────────────────────────────────

    def _on_delta_mode_changed(self, checked):
        self._delta_mode = checked
        self._rebuild_multi_compare()

    def _on_baseline_changed(self, text):
        if text:
            self._baseline_ws = text
            if self._delta_mode:
                self._rebuild_multi_compare()

    # ────────────────────────────────────────────────────────────
    #  Element summary
    # ────────────────────────────────────────────────────────────

    def _toggle_element_summary(self):
        vis = self.btn_elem_summary.isChecked()
        self.element_summary_container.setVisible(vis)
        if vis:
            self._update_element_summary()

    def _update_element_summary(self):
        if self.current_df is None or self.current_df.empty:
            self.tab_element_summary.setRowCount(0)
            return

        df = self.current_df
        if "Element" not in df.columns or "Bader_Charge" not in df.columns:
            return

        grouped = df.groupby("Element")["Bader_Charge"]
        stats = grouped.agg(["count", "mean", "sum", "std", "max", "min"])
        stats["std"] = stats["std"].fillna(0.0)
        stats = stats.sort_index()

        self.tab_element_summary.setRowCount(len(stats))
        for row, (elem, s) in enumerate(stats.iterrows()):
            items = [
                QTableWidgetItem(str(elem)),
                QTableWidgetItem(str(int(s["count"]))),
                QTableWidgetItem(f"{s['mean']:.4f}"),
                QTableWidgetItem(f"{s['sum']:.4f}"),
                QTableWidgetItem(f"{s['std']:.4f}"),
                QTableWidgetItem(f"{s['max']:.4f}"),
                QTableWidgetItem(f"{s['min']:.4f}"),
            ]
            for col, item in enumerate(items):
                item.setTextAlignment(int(Qt.AlignCenter))
                self.tab_element_summary.setItem(row, col, item)

            # Color the avg charge cell
            avg_item = self.tab_element_summary.item(row, 2)
            if avg_item:
                bg = self._charge_bg_color(s["mean"], max(abs(s["max"]), abs(s["min"]), 0.01), self.is_dark_theme)
                if bg:
                    avg_item.setBackground(QBrush(bg))

    # ────────────────────────────────────────────────────────────
    #  Custom calculation columns
    # ────────────────────────────────────────────────────────────

    def _add_custom_column(self):
        expr, ok = QInputDialog.getText(
            self,
            "添加自定义列",
            "表达式（变量: CHARGE, ZVAL, Bader_Charge, Min_Dist, Volume）\n"
            "示例:  Bader_Charge / ZVAL\n"
            "       CHARGE - ZVAL\n"
            "       Volume * 0.52",
        )
        if not ok or not expr.strip():
            return

        name, ok2 = QInputDialog.getText(
            self, "列名称", "新列的名称:", text=expr.strip()[:20]
        )
        if not ok2 or not name.strip():
            return

        # Validate expression on first row
        if self.current_df is not None and not self.current_df.empty:
            try:
                self._eval_custom_expr(expr, self.current_df.iloc[0])
            except Exception as e:
                QMessageBox.warning(self, "表达式错误", str(e))
                return

        self._custom_columns[name.strip()] = expr.strip()
        if self.current_df is not None:
            self.update_table_view(self.current_df)

    def _eval_custom_expr(self, expr, row_data):
        """Safely evaluate a simple arithmetic expression using row data."""
        allowed_names = {
            "CHARGE": float(row_data.get("CHARGE", 0)),
            "ZVAL": float(row_data.get("ZVAL", 0)),
            "Bader_Charge": float(row_data.get("Bader_Charge", 0)),
            "Min_Dist": float(row_data.get("Min_Dist", 0)),
            "Volume": float(row_data.get("Volume", 0)),
            "Atom": int(row_data.get("Atom", 0)),
        }
        safe_builtins = {"abs": abs, "round": round, "min": min, "max": max}
        return eval(expr, {"__builtins__": safe_builtins}, allowed_names)

    # ────────────────────────────────────────────────────────────
    #  Atom detail dialog
    # ────────────────────────────────────────────────────────────

    def _show_atom_detail(self):
        rows = self._visible_selected_rows(self.tab_data)
        if not rows:
            return
        item0 = self.tab_data.item(rows[0], 0)
        if not item0:
            return
        try:
            atom_id = int(item0.text())
        except ValueError:
            return
        if self.current_df is None:
            return
        # Atom is a regular column, not the index
        match = self.current_df[self.current_df["Atom"] == atom_id]
        if match.empty:
            return
        dlg = AtomDetailDialog(match.iloc[0], self)
        dlg.exec()

    # ────────────────────────────────────────────────────────────
    #  Data persistence
    # ────────────────────────────────────────────────────────────

    def _save_results(self, ws_name, df):
        """Persist DataFrame to workspace directory as results.json."""
        if df is None or df.empty:
            return
        try:
            ws_path = self.ws_mgr.get_workspace_path(ws_name)
            records = df.where(df.notna(), None).to_dict(orient="records")
            path = os.path.join(ws_path, "results.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
            state = self.ws_mgr.load_state(ws_name)
            state["calculated"] = True
            self.ws_mgr.save_state(ws_name, state)
        except Exception:
            pass  # non-critical

    def _load_results(self, ws_name):
        """Load previously saved results from workspace directory."""
        try:
            import pandas as pd
            ws_path = self.ws_mgr.get_workspace_path(ws_name)
            path = os.path.join(ws_path, "results.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    records = json.load(f)
                df = pd.DataFrame(records)
                if "Atom" in df.columns:
                    df["Atom"] = df["Atom"].astype(int)
                return df
        except Exception:
            pass
        return None

    def _load_ws_data_from_disk(self, ws_name):
        """Load DataFrame + structure from disk and cache in all_calculated_data.

        Returns the ``{"df": ..., "struct": ...}`` dict, or *None* if no
        persisted results exist.  On success the entry is stored in
        ``self.all_calculated_data`` so that subsequent accesses (3D view,
        multi-compare, plot panel) find it without re-reading disk.
        """
        df = self._load_results(ws_name)
        if df is None:
            return None

        struct = None
        try:
            from core.parser import VaspParser
            ws_path = self.ws_mgr.get_workspace_path(ws_name)
            for fname in ("CONTCAR", "POSCAR"):
                fpath = os.path.join(ws_path, fname)
                if os.path.exists(fpath):
                    struct, _ = VaspParser.parse_structure(fpath)
                    break
        except Exception:
            struct = None

        data = {"df": df, "struct": struct}
        self.all_calculated_data[ws_name] = data
        return data

    # ────────────────────────────────────────────────────────────
    #  Theme
    # ────────────────────────────────────────────────────────────

    def apply_theme(self):
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_app_stylesheet(self.is_dark_theme))
        self._apply_local_theme_styles()

        if hasattr(self, "btn_theme"):
            if self.is_dark_theme:
                self.btn_theme.setText(" 日间模式")
                self.btn_theme.setIcon(qta.icon("fa5s.sun", color="#E6E6E6"))
            else:
                self.btn_theme.setText(" 夜间模式")
                self.btn_theme.setIcon(qta.icon("fa5s.moon", color="#444444"))
            self.btn_theme.setStyleSheet(self._header_action_button_style())

        for name in ("btn_import", "btn_new_ws", "btn_open_project", "btn_save_project"):
            if hasattr(self, name):
                getattr(self, name).setStyleSheet(self._sidebar_action_button_style())

        if hasattr(self, "plot_panel"):
            self.plot_panel.chk_dark_mode.setChecked(self.is_dark_theme)
            self.plot_panel.apply_styles()
        if hasattr(self, "visualizer_3d") and self.visualizer_3d is not None:
            self.visualizer_3d.apply_theme(self.is_dark_theme)

        # Re-color tables after theme switch
        if self.current_df is not None and not self.current_df.empty:
            self.update_table_view(self.current_df)
        self._rebuild_multi_compare()
        if hasattr(self, '_elem_summary_dlg') and self._elem_summary_dlg is not None:
            self._update_element_summary()

    def _apply_local_theme_styles(self):
        status_bg = "#1E1E1E" if self.is_dark_theme else "#F8F9FA"
        border = "#333333" if self.is_dark_theme else "#E0E0E0"
        text = "#E6E6E6" if self.is_dark_theme else "#333333"
        muted = "#AAAAAA" if self.is_dark_theme else "#666666"

        if hasattr(self, "status_bar_widget"):
            self.status_bar_widget.setStyleSheet(
                f"background-color: {status_bg}; border-top: 1px solid {border};"
            )
        for name in ("lbl_status_rows", "lbl_status_atoms", "lbl_status_sys", "lbl_status_time", "lbl_status_proj"):
            if hasattr(self, name):
                getattr(self, name).setStyleSheet(f"color: {muted};")
        if hasattr(self, "lbl_files"):
            self.lbl_files.setStyleSheet(
                f"font-weight: bold; font-size: 13px; margin-top: 15px; color: {text};"
            )

    # ────────────────────────────────────────────────────────────
    #  Tiny helpers
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_val(v, fmt=".4f"):
        """Format a value, returning '-' for None / NaN."""
        if v is None:
            return "-"
        if isinstance(v, float) and math.isnan(v):
            return "-"
        return f"{v:{fmt}}"

    @staticmethod
    def _compute_stat(label, vals):
        """Compute a single statistic from a list of floats."""
        if not vals:
            return None
        arr = np.array(vals)
        if label == "平均值":
            return float(np.mean(arr))
        if label == "标准差":
            return float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        if label == "极差":
            return float(np.max(arr) - np.min(arr))
        if label == "最大值":
            return float(np.max(arr))
        if label == "最小值":
            return float(np.min(arr))
        return None


# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(load_app_icon())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

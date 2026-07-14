# -*- coding: utf-8 -*-
from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
import qtawesome as qta


class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            return float(self.text()) < float(other.text())
        except (TypeError, ValueError):
            return super().__lt__(other)


class WorkspaceTargetDialog(QDialog):
    """Edit per-workspace targets without mutating the caller's data."""

    def __init__(
        self, workspaces, targets=None, default_target="", parent=None, resolver=None
    ):
        super().__init__(parent)
        self.setWindowTitle("批量设置目标原子")
        self.resize(640, 440)
        self.setMinimumSize(520, 360)
        self._workspaces = list(workspaces or [])
        self._default_target = str(default_target or "").strip()
        self._resolver = resolver
        targets = dict(targets or {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        default_text = self._default_target or "全部原子"
        self.default_label = QLabel(f"当前输入：{default_text}")
        self.btn_apply_default = QPushButton(" 全部使用当前输入")
        self.btn_apply_default.setIcon(qta.icon("fa5s.copy"))
        self.btn_apply_default.clicked.connect(self.apply_default_to_all)
        top.addWidget(self.default_label)
        top.addStretch()
        top.addWidget(self.btn_apply_default)
        layout.addLayout(top)

        self.table = QTableWidget(len(self._workspaces), 3)
        self.table.setHorizontalHeaderLabels(["工作区", "目标原子", "解析结果"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 240)
        for row, workspace in enumerate(self._workspaces):
            name_item = QTableWidgetItem(workspace)
            name_item.setToolTip(workspace)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(
                row,
                1,
                QTableWidgetItem(str(targets.get(workspace, self._default_target))),
            )
            status_item = QTableWidgetItem()
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, status_item)
        self.table.itemChanged.connect(self._target_item_changed)
        self._refresh_all_statuses()
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_default_to_all(self):
        for row in range(self.table.rowCount()):
            self.table.item(row, 1).setText(self._default_target)

    def targets(self):
        return {
            self.table.item(row, 0).text(): self.table.item(row, 1).text().strip()
            for row in range(self.table.rowCount())
        }

    def _target_item_changed(self, item):
        if item.column() == 1:
            self._refresh_status(item.row())

    def _refresh_all_statuses(self):
        for row in range(self.table.rowCount()):
            self._refresh_status(row)

    def _refresh_status(self, row):
        status_item = self.table.item(row, 2)
        if self._resolver is None:
            status_item.setText("未校验")
            return
        workspace = self.table.item(row, 0).text()
        expression = self.table.item(row, 1).text().strip()
        try:
            result = self._resolver(workspace, expression)
            status_item.setText(str(result))
        except Exception as exc:
            status_item.setText(f"错误：{exc}")


class FragmentAnalysisDialog(QDialog):
    """Manage fragment definitions and inspect their statistics."""

    request_export = Signal()

    RESULT_HEADERS = [
        "工作区", "片段", "表达式", "原子数", "总和(e)",
        "平均值(e)", "最大值(e)", "最小值(e)",
    ]

    def __init__(self, workspaces, fragments=None, results=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("片段分析")
        self.resize(900, 620)
        self.setMinimumSize(720, 480)
        self._workspaces = list(workspaces or [])
        self._overrides_by_row = []
        self._active_fragment_row = -1

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_definition_tab(), "片段定义")
        self.tabs.addTab(self._build_results_tab(), "统计结果")
        root.addWidget(self.tabs, 1)

        self.dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        self.dialog_buttons.button(QDialogButtonBox.Save).setText("保存")
        self.dialog_buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.dialog_buttons.accepted.connect(self._accept_if_valid)
        self.dialog_buttons.rejected.connect(self.reject)
        root.addWidget(self.dialog_buttons)

        self.set_fragments(fragments or {})
        self.set_results(results or [])

    def _build_definition_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 10, 8, 8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        fragment_side = QWidget()
        fragment_layout = QVBoxLayout(fragment_side)
        fragment_layout.setContentsMargins(0, 0, 4, 0)
        fragment_toolbar = QHBoxLayout()
        fragment_toolbar.addWidget(QLabel("片段列表"))
        fragment_toolbar.addStretch()
        self.btn_add_fragment = self._icon_button("fa5s.plus", "新增片段")
        self.btn_rename_fragment = self._icon_button("fa5s.pen", "重命名片段")
        self.btn_remove_fragment = self._icon_button("fa5s.trash-alt", "删除片段")
        self.btn_add_fragment.clicked.connect(self.add_fragment)
        self.btn_rename_fragment.clicked.connect(self.rename_selected_fragment)
        self.btn_remove_fragment.clicked.connect(self.remove_selected_fragment)
        fragment_toolbar.addWidget(self.btn_add_fragment)
        fragment_toolbar.addWidget(self.btn_rename_fragment)
        fragment_toolbar.addWidget(self.btn_remove_fragment)
        fragment_layout.addLayout(fragment_toolbar)

        self.fragment_table = QTableWidget(0, 2)
        self.fragment_table.setHorizontalHeaderLabels(["片段名称", "默认原子表达式"])
        self.fragment_table.verticalHeader().setVisible(False)
        self.fragment_table.setAlternatingRowColors(True)
        self.fragment_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fragment_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.fragment_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.fragment_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.fragment_table.setColumnWidth(0, 170)
        self.fragment_table.currentCellChanged.connect(self._fragment_selection_changed)
        fragment_layout.addWidget(self.fragment_table, 1)
        splitter.addWidget(fragment_side)

        override_side = QWidget()
        override_layout = QVBoxLayout(override_side)
        override_layout.setContentsMargins(4, 0, 0, 0)
        self.override_title = QLabel("工作区专用覆盖")
        override_layout.addWidget(self.override_title)
        self.override_table = QTableWidget(len(self._workspaces), 2)
        self.override_table.setHorizontalHeaderLabels(["工作区", "覆盖表达式"])
        self.override_table.verticalHeader().setVisible(False)
        self.override_table.setAlternatingRowColors(True)
        self.override_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.override_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.override_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.override_table.setColumnWidth(0, 220)
        for row, workspace in enumerate(self._workspaces):
            item = QTableWidgetItem(workspace)
            item.setToolTip(workspace)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.override_table.setItem(row, 0, item)
            self.override_table.setItem(row, 1, QTableWidgetItem(""))
        override_layout.addWidget(self.override_table, 1)
        splitter.addWidget(override_side)
        splitter.setSizes([430, 430])

        layout.addWidget(splitter, 1)
        return tab

    def _build_results_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 10, 8, 8)

        self.results_empty_label = QLabel("暂无片段统计结果，请先保存片段并完成分析。")
        self.results_empty_label.setAlignment(Qt.AlignCenter)
        self.results_empty_label.setStyleSheet("color: #777; padding: 36px;")
        layout.addWidget(self.results_empty_label, 1)

        self.results_table = QTableWidget(0, len(self.RESULT_HEADERS))
        self.results_table.setHorizontalHeaderLabels(self.RESULT_HEADERS)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.results_table.setSortingEnabled(True)
        header = self.results_table.horizontalHeader()
        for column in range(3, len(self.RESULT_HEADERS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.results_table, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        self.btn_copy_results = QPushButton(" 复制选中内容")
        self.btn_copy_results.setIcon(qta.icon("fa5s.copy"))
        self.btn_copy_results.clicked.connect(self.copy_selected_results)
        self.btn_export_results = QPushButton(" 导出统计")
        self.btn_export_results.setIcon(qta.icon("fa5s.file-export"))
        self.btn_export_results.clicked.connect(self.request_export.emit)
        actions.addWidget(self.btn_copy_results)
        actions.addWidget(self.btn_export_results)
        layout.addLayout(actions)

        self.copy_shortcut = QShortcut(QKeySequence.Copy, self.results_table)
        self.copy_shortcut.activated.connect(
            self.copy_selected_results
        )
        return tab

    @staticmethod
    def _icon_button(icon_name, tooltip):
        button = QPushButton()
        button.setIcon(qta.icon(icon_name))
        button.setToolTip(tooltip)
        button.setFixedSize(32, 30)
        return button

    def set_fragments(self, fragments):
        self.fragment_table.blockSignals(True)
        self.fragment_table.setRowCount(0)
        self._overrides_by_row = []
        for name, definition in deepcopy(fragments or {}).items():
            row = self.fragment_table.rowCount()
            self.fragment_table.insertRow(row)
            self.fragment_table.setItem(row, 0, QTableWidgetItem(str(name)))
            self.fragment_table.setItem(
                row, 1, QTableWidgetItem(str(definition.get("expression", "")))
            )
            self._overrides_by_row.append(dict(definition.get("overrides", {}) or {}))
        self.fragment_table.blockSignals(False)
        self._active_fragment_row = -1
        if self.fragment_table.rowCount():
            self.fragment_table.setCurrentCell(0, 0)
        else:
            self._clear_overrides()

    def add_fragment(self, name=None, expression=""):
        existing = {
            self.fragment_table.item(row, 0).text().strip()
            for row in range(self.fragment_table.rowCount())
        }
        if name is None:
            index = 1
            name = f"新片段 {index}"
            while name in existing:
                index += 1
                name = f"新片段 {index}"
        self._store_active_overrides()
        row = self.fragment_table.rowCount()
        self.fragment_table.insertRow(row)
        self.fragment_table.setItem(row, 0, QTableWidgetItem(str(name)))
        self.fragment_table.setItem(row, 1, QTableWidgetItem(str(expression)))
        self._overrides_by_row.append({})
        self.fragment_table.setCurrentCell(row, 0)
        self.fragment_table.editItem(self.fragment_table.item(row, 0))

    def rename_selected_fragment(self):
        row = self.fragment_table.currentRow()
        if row >= 0:
            self.fragment_table.setCurrentCell(row, 0)
            self.fragment_table.editItem(self.fragment_table.item(row, 0))

    def remove_selected_fragment(self):
        row = self.fragment_table.currentRow()
        if row < 0:
            return
        self._store_active_overrides()
        self.fragment_table.blockSignals(True)
        self.fragment_table.removeRow(row)
        self.fragment_table.blockSignals(False)
        del self._overrides_by_row[row]
        self._active_fragment_row = -1
        if self.fragment_table.rowCount():
            next_row = min(row, self.fragment_table.rowCount() - 1)
            self.fragment_table.setCurrentCell(next_row, 0)
            self._active_fragment_row = next_row
            self._load_overrides(next_row)
        else:
            self._clear_overrides()

    def _fragment_selection_changed(self, current_row, _current_column, previous_row, _previous_column):
        if previous_row >= 0:
            self._store_overrides(previous_row)
        self._active_fragment_row = current_row
        self._load_overrides(current_row)

    def _store_active_overrides(self):
        self._store_overrides(self._active_fragment_row)

    def _store_overrides(self, fragment_row):
        if not 0 <= fragment_row < len(self._overrides_by_row):
            return
        overrides = {}
        for row, workspace in enumerate(self._workspaces):
            item = self.override_table.item(row, 1)
            value = item.text().strip() if item else ""
            if value:
                overrides[workspace] = value
        self._overrides_by_row[fragment_row] = overrides

    def _load_overrides(self, fragment_row):
        overrides = (
            self._overrides_by_row[fragment_row]
            if 0 <= fragment_row < len(self._overrides_by_row)
            else {}
        )
        self.override_table.blockSignals(True)
        for row, workspace in enumerate(self._workspaces):
            self.override_table.item(row, 1).setText(overrides.get(workspace, ""))
        self.override_table.blockSignals(False)
        if 0 <= fragment_row < self.fragment_table.rowCount():
            name = self.fragment_table.item(fragment_row, 0).text().strip()
            self.override_title.setText(f"“{name or '未命名片段'}”的工作区专用覆盖")
            self.override_table.setEnabled(True)
        else:
            self.override_title.setText("工作区专用覆盖")
            self.override_table.setEnabled(False)

    def _clear_overrides(self):
        self._active_fragment_row = -1
        self._load_overrides(-1)

    def fragments(self):
        self._store_active_overrides()
        definitions = {}
        for row in range(self.fragment_table.rowCount()):
            name = self.fragment_table.item(row, 0).text().strip()
            expression = self.fragment_table.item(row, 1).text().strip()
            definitions[name] = {
                "expression": expression,
                "overrides": dict(self._overrides_by_row[row]),
            }
        return definitions

    def validate_definitions(self):
        seen = set()
        for row in range(self.fragment_table.rowCount()):
            name = self.fragment_table.item(row, 0).text().strip()
            expression = self.fragment_table.item(row, 1).text().strip()
            if not name:
                return False, "片段名称不能为空。", row, 0
            if name in seen:
                return False, f"片段名称“{name}”不能重复。", row, 0
            if not expression:
                return False, f"片段“{name}”的默认原子表达式不能为空。", row, 1
            seen.add(name)
        return True, "", -1, -1

    def _accept_if_valid(self):
        valid, message, row, column = self.validate_definitions()
        if not valid:
            self.tabs.setCurrentIndex(0)
            self.fragment_table.setCurrentCell(row, column)
            self.fragment_table.scrollToItem(self.fragment_table.item(row, column))
            QMessageBox.warning(self, "片段定义错误", message)
            return
        self._store_active_overrides()
        self.accept()

    def set_results(self, rows):
        rows = list(rows or [])
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(rows))
        for row_index, result in enumerate(rows):
            values = [
                result.get("workspace", ""),
                result.get("fragment", ""),
                result.get("expression", ""),
                str(result.get("count", "")),
                self._format_number(result.get("sum")),
                self._format_number(result.get("mean")),
                self._format_number(result.get("max")),
                self._format_number(result.get("min")),
            ]
            for column, value in enumerate(values):
                item = (
                    NumericTableWidgetItem(value)
                    if column >= 3 and value
                    else QTableWidgetItem(value)
                )
                if column <= 2:
                    item.setToolTip(value)
                if column >= 3:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.results_table.setItem(row_index, column, item)
        self.results_table.setSortingEnabled(True)
        has_rows = bool(rows)
        self.results_empty_label.setVisible(not has_rows)
        self.results_table.setVisible(has_rows)
        self.btn_copy_results.setEnabled(has_rows)
        self.btn_export_results.setEnabled(has_rows)

    @staticmethod
    def _format_number(value):
        if value in (None, ""):
            return ""
        return f"{float(value):.6f}"

    def copy_selected_results(self):
        selected = self.results_table.selectedIndexes()
        if not selected:
            return
        rows = sorted({index.row() for index in selected})
        columns = sorted({index.column() for index in selected})
        lines = []
        for row in rows:
            values = []
            for column in columns:
                item = self.results_table.item(row, column)
                values.append(item.text() if item else "")
            lines.append("\t".join(values))
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(lines))

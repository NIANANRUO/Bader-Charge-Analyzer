import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.analysis_dialogs import FragmentAnalysisDialog, WorkspaceTargetDialog
from gui.analysis_panel import AnalysisPanel


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_sidebar_uses_summaries_instead_of_wide_tables():
    application = app()
    panel = AnalysisPanel()
    panel.resize(320, 720)
    panel.show()

    panel.set_selected_workspaces(["ws1", "ws2"], {"ws2": "5-6"})
    panel.set_fragments({"吸附物": {"expression": "1-3", "overrides": {}}})
    panel.update_fragment_results([{"workspace": "ws1"}])
    application.processEvents()

    assert panel.lbl_selection_summary.text() == "已选择 2 个工作区"
    assert panel.lbl_fragment_summary.text() == "已定义 1 个片段，已有 1 条统计结果"
    assert panel.btn_edit_targets.isVisibleTo(panel) is True
    assert not hasattr(panel, "target_table")
    assert not hasattr(panel, "fragment_table")
    assert not hasattr(panel, "fragment_results")
    assert panel.scroll_area.horizontalScrollBar().maximum() == 0
    for button in (
        panel.btn_edit_targets,
        panel.btn_manage_fragments,
        panel.btn_export_fragments,
    ):
        assert button.width() >= button.sizeHint().width()
    panel.close()


def test_workspace_target_dialog_edits_a_draft_and_applies_default():
    app()
    original = {"ws1": "1-2", "ws2": "7"}
    dialog = WorkspaceTargetDialog(
        ["ws1", "ws2"], original, default_target="10-12"
    )

    dialog.apply_default_to_all()

    assert dialog.targets() == {"ws1": "10-12", "ws2": "10-12"}
    assert original == {"ws1": "1-2", "ws2": "7"}
    assert dialog.size().width() >= 640
    assert dialog.minimumWidth() == 520


def test_workspace_target_dialog_resolves_default_overrides_and_live_edits():
    app()
    original = {"ws2": "4-5"}
    calls = []

    def resolve(workspace, expression):
        calls.append((workspace, expression))
        return {"1-3": 3, "4-5": 2, "7": 1}[expression]

    dialog = WorkspaceTargetDialog(
        ["ws1", "ws2"], original, default_target="1-3", resolver=resolve
    )

    assert dialog.table.columnCount() == 3
    assert dialog.table.item(0, 2).text() == "3"
    assert dialog.table.item(1, 2).text() == "2"
    assert not (dialog.table.item(0, 2).flags() & Qt.ItemIsEditable)

    dialog.table.item(1, 1).setText("7")

    assert dialog.table.item(1, 2).text() == "1"
    assert ("ws2", "7") in calls
    assert original == {"ws2": "4-5"}


def test_workspace_target_dialog_displays_resolver_errors():
    app()

    def resolve(_workspace, expression):
        if expression == "bad":
            raise ValueError("无效表达式")
        return 2

    dialog = WorkspaceTargetDialog(
        ["ws1"], {}, default_target="1-2", resolver=resolve
    )

    dialog.table.item(0, 1).setText("bad")

    assert dialog.table.item(0, 2).text() == "错误：无效表达式"


def test_fragment_dialog_uses_two_column_override_table_for_many_workspaces():
    app()
    workspaces = [f"ws-{index}" for index in range(50)]
    dialog = FragmentAnalysisDialog(
        workspaces,
        {"吸附物": {"expression": "1-3", "overrides": {"ws-2": "4-6"}}},
        [],
    )

    assert dialog.fragment_table.columnCount() == 2
    assert dialog.override_table.columnCount() == 2
    assert dialog.override_table.rowCount() == 50
    assert dialog.override_table.item(2, 1).text() == "4-6"
    assert dialog.minimumWidth() == 720


def test_fragment_dialog_preserves_overrides_when_switching_fragments():
    app()
    dialog = FragmentAnalysisDialog(
        ["ws1", "ws2"],
        {
            "吸附物": {"expression": "1-3", "overrides": {"ws2": "4-6"}},
            "表面": {"expression": "7-9", "overrides": {}},
        },
        [],
    )

    dialog.override_table.item(0, 1).setText("10")
    dialog.fragment_table.setCurrentCell(1, 0)
    dialog.fragment_table.setCurrentCell(0, 0)

    assert dialog.override_table.item(0, 1).text() == "10"
    assert dialog.fragments()["吸附物"]["overrides"] == {
        "ws1": "10",
        "ws2": "4-6",
    }


def test_fragment_dialog_rejects_empty_and_duplicate_definitions():
    app()
    dialog = FragmentAnalysisDialog(
        ["ws1"],
        {
            "片段A": {"expression": "1-3", "overrides": {}},
            "片段B": {"expression": "4-6", "overrides": {}},
        },
        [],
    )

    dialog.fragment_table.item(1, 0).setText("片段A")
    valid, message, row, column = dialog.validate_definitions()
    assert valid is False
    assert "不能重复" in message
    assert (row, column) == (1, 0)

    dialog.fragment_table.item(1, 0).setText("片段B")
    dialog.fragment_table.item(1, 1).setText("")
    valid, message, row, column = dialog.validate_definitions()
    assert valid is False
    assert "不能为空" in message
    assert (row, column) == (1, 1)


def test_fragment_dialog_keeps_override_editor_synced_after_delete():
    app()
    dialog = FragmentAnalysisDialog(
        ["ws1"],
        {
            "片段A": {"expression": "1-3", "overrides": {"ws1": "2"}},
            "片段B": {"expression": "4-6", "overrides": {"ws1": "5"}},
        },
        [],
    )

    dialog.fragment_table.setCurrentCell(0, 0)
    dialog.remove_selected_fragment()

    assert dialog.fragment_table.currentRow() == 0
    assert dialog.override_table.isEnabled() is True
    assert dialog.override_table.item(0, 1).text() == "5"


def test_fragment_results_switch_between_empty_state_and_table():
    app()
    dialog = FragmentAnalysisDialog([], {}, [])

    assert dialog.results_empty_label.isHidden() is False
    assert dialog.results_table.isHidden() is True

    dialog.set_results([
        {
            "workspace": "ws1",
            "fragment": "吸附物",
            "expression": "1-3",
            "count": 3,
            "sum": 0.25,
            "mean": 0.083333,
            "max": 0.2,
            "min": -0.1,
        },
        {
            "workspace": "ws2",
            "fragment": "表面",
            "expression": "4-8",
            "count": 5,
            "sum": -1.5,
            "mean": -0.3,
            "max": 0.1,
            "min": -0.7,
        }
    ])

    assert dialog.results_empty_label.isHidden() is True
    assert dialog.results_table.isHidden() is False
    assert dialog.results_table.columnCount() == 8
    assert {
        dialog.results_table.item(row, 4).text()
        for row in range(dialog.results_table.rowCount())
    } == {"0.250000", "-1.500000"}

    dialog.results_table.sortItems(4, Qt.AscendingOrder)
    assert dialog.results_table.item(0, 4).text() == "-1.500000"

    dialog.results_table.selectRow(0)
    dialog.copy_selected_results()
    assert "ws2\t表面\t4-8\t5\t-1.500000" in QApplication.clipboard().text()

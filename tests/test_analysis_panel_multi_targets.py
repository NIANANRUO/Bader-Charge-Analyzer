import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gui.analysis_panel import AnalysisPanel


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_multi_workspace_target_table_emits_per_workspace_targets():
    app()
    panel = AnalysisPanel()
    emitted = []
    panel.request_calculation.connect(emitted.append)

    panel.set_selected_workspaces(["ws1", "ws2"], {"ws2": "5-6"})
    panel.line_target.setText("1-3")
    panel._apply_target_to_selected()
    panel.target_table.item(1, 1).setText("7")

    panel.emit_calculation()

    assert emitted
    assert emitted[0]["target"] == "1-3"
    assert emitted[0]["targets_by_workspace"] == {"ws1": "1-3", "ws2": "7"}


def test_multi_workspace_target_table_hides_for_single_workspace():
    app()
    panel = AnalysisPanel()

    panel.set_selected_workspaces(["ws1", "ws2"])
    assert panel.target_table.isVisibleTo(panel) is True

    panel.set_selected_workspaces(["ws1"])

    assert panel.target_table.isVisibleTo(panel) is False
    assert panel.btn_apply_target_to_all.isVisibleTo(panel) is False

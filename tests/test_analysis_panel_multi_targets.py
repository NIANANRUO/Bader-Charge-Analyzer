import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gui.analysis_panel import AnalysisPanel


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_multi_workspace_target_draft_emits_per_workspace_targets():
    app()
    panel = AnalysisPanel()
    emitted = []
    panel.request_calculation.connect(emitted.append)

    panel.set_selected_workspaces(["ws1", "ws2"], {"ws2": "5-6"})
    panel.line_target.setText("1-3")

    panel.emit_calculation()

    assert emitted
    assert emitted[0]["target"] == "1-3"
    assert emitted[0]["targets_by_workspace"] == {"ws1": "1-3", "ws2": "5-6"}


def test_multi_workspace_target_button_hides_for_single_workspace():
    app()
    panel = AnalysisPanel()

    panel.set_selected_workspaces(["ws1", "ws2"])
    assert panel.btn_edit_targets.isVisibleTo(panel) is True

    panel.set_selected_workspaces(["ws1"])

    assert panel.btn_edit_targets.isVisibleTo(panel) is False


def test_multi_workspace_without_override_inherits_sidebar_target():
    app()
    panel = AnalysisPanel()
    emitted = []
    panel.request_calculation.connect(emitted.append)
    panel.line_target.setText("10-12")
    panel.set_selected_workspaces(["ws1", "ws2"], {})

    panel.emit_calculation()

    assert emitted[0]["targets_by_workspace"] == {
        "ws1": "10-12",
        "ws2": "10-12",
    }


def test_named_fragments_are_emitted_with_analysis_config():
    app()
    panel = AnalysisPanel()
    emitted = []
    panel.request_calculation.connect(emitted.append)

    panel.add_fragment_row("吸附物", "1-3")
    panel.add_fragment_row("表面", "4-8")
    panel.emit_calculation()

    assert emitted[0]["fragments"] == {
        "吸附物": {"expression": "1-3", "overrides": {}},
        "表面": {"expression": "4-8", "overrides": {}},
    }


def test_editing_committed_scope_only_marks_draft_without_calculating():
    app()
    panel = AnalysisPanel()
    calculations = []
    drafts = []
    panel.request_calculation.connect(calculations.append)
    panel.draft_scope_changed.connect(drafts.append)

    panel.line_target.setText("1-3")
    panel.set_committed_scope("1-3", 3)
    drafts.clear()
    assert panel.lbl_target_scope.text() == "当前生效：1-3（3 个原子）"
    assert panel.btn_calc.text().strip() == "重新分析"

    panel.line_target.setText("4-6")

    assert drafts == ["4-6"]
    assert calculations == []
    assert panel.lbl_target_scope.text() == (
        "当前生效：1-3（3 个原子）\n有未应用更改"
    )
    assert panel.btn_calc.text().strip() == "应用范围并分析"


def test_use_all_atoms_changes_only_the_draft():
    app()
    panel = AnalysisPanel()
    calculations = []
    drafts = []
    panel.request_calculation.connect(calculations.append)
    panel.draft_scope_changed.connect(drafts.append)
    panel.line_target.setText("1-3")
    panel.set_committed_scope("1-3", 3)
    panel.line_target.setText("7")
    drafts.clear()

    panel.use_all_atoms()

    assert panel.line_target.text() == ""
    assert drafts == [""]
    assert calculations == []
    assert "有未应用更改" in panel.lbl_target_scope.text()


def test_clean_committed_scope_uses_reanalysis_button_state():
    app()
    panel = AnalysisPanel()
    panel.line_target.setText("2, 4")

    panel.set_committed_scope("2, 4", 2)

    assert panel.lbl_target_scope.text() == "当前生效：2, 4（2 个原子）"
    assert panel.btn_calc.text().strip() == "重新分析"


def test_full_raw_export_has_a_distinct_signal_and_button():
    app()
    panel = AnalysisPanel()
    full_exports = []
    scoped_exports = []
    panel.request_export_full_csv.connect(lambda: full_exports.append(True))
    panel.request_export_csv.connect(lambda: scoped_exports.append(True))
    panel.set_committed_scope("", 12)

    panel.btn_export_full_csv.click()

    assert full_exports == [True]
    assert scoped_exports == []
    assert panel.btn_export_full_csv.text().strip() == "导出完整原始结果"


def test_fragments_are_optional_and_do_not_disable_ready_calculation():
    app()
    panel = AnalysisPanel()
    panel.update_file_status("ws1", ["ACF.dat", "POSCAR"])

    panel.set_fragments({})

    assert panel.btn_calc.isEnabled() is True
    assert panel.lbl_advanced_analysis.text() == "高级分析（可选）"


def test_selected_workspace_summary_survives_active_scope_updates():
    app()
    panel = AnalysisPanel()
    panel.set_selected_workspaces(["ws1", "ws2"])

    panel.set_committed_scope("1-5", 5)
    panel.line_target.setText("7")

    assert panel.lbl_selection_summary.text() == "已选择 2 个工作区"
    assert panel.lbl_target_scope.text() == (
        "当前生效：1-5（5 个原子）\n有未应用更改"
    )

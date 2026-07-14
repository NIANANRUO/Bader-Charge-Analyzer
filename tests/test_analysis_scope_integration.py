import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from types import MethodType, SimpleNamespace
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from gui.main_window import MainWindow
from core.analysis_session import AnalysisSessionStore
from core.workspace_manager import WorkspaceManager


_APP = None


def app():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def frame(charges=(0.1, -0.2, 0.3)):
    return pd.DataFrame({
        "Atom": [1, 2, 3],
        "Element": ["Li", "O", "S"],
        "ZVAL": [1.0, 6.0, 6.0],
        "X": [0.0, 1.0, 2.0],
        "Y": [0.0, 1.0, 2.0],
        "Z": [0.0, 1.0, 2.0],
        "Bader_Charge": list(charges),
        "CHARGE": [0.9, 5.8, 5.7],
        "Min_Dist": [0.1, 0.2, 0.3],
        "Volume": [10.0, 11.0, 12.0],
    })


def seed(window, workspace="ws", scope="1-2"):
    window.ws_mgr.save_analysis_metadata = lambda *args, **kwargs: None
    window.current_ws = workspace
    window.selected_workspaces = [workspace]
    window.session_store.put_full_result(
        workspace,
        {"df": frame(), "struct": None, "source_revision": "source-1"},
    )
    window.session_store.commit_scopes({workspace: scope})
    window.all_calculated_data[workspace] = {
        "df": window.session_store.full_df(workspace),
        "struct": None,
    }


def test_draft_edit_does_not_refresh_committed_table(monkeypatch):
    app()
    window = MainWindow()
    seed(window)
    monkeypatch.setattr(window, "_request_3d_appearance_update", lambda names: None)
    window._refresh_committed_views(["ws"])
    before = [
        window.tab_data.item(row, 0).text()
        for row in range(window.tab_data.rowCount())
    ]

    window.analysis_panel_plot.line_target.setText("3")

    after = [
        window.tab_data.item(row, 0).text()
        for row in range(window.tab_data.rowCount())
    ]
    assert before == after == ["1", "2"]
    assert window.session_store.session("ws").draft_scope == "3"
    window.close()


def test_commit_updates_table_plot_export_and_panel_scope(monkeypatch):
    app()
    window = MainWindow()
    seed(window, scope="")
    plot_calls = []
    monkeypatch.setattr(window.plot_panel, "plot_data", lambda *a, **k: plot_calls.append((a, k)))
    monkeypatch.setattr(window, "_request_3d_appearance_update", lambda names: None)

    window._commit_scope_and_refresh({"ws": "2-3"})

    assert window.current_df["Atom"].tolist() == [2, 3]
    assert window._current_export_df()["Atom"].tolist() == [2, 3]
    assert plot_calls[-1][0][0]["ws"]["df"]["Atom"].tolist() == [1, 2, 3]
    assert plot_calls[-1][1]["selected_by_workspace"] == {"ws": (2, 3)}
    assert window.analysis_panel_plot._committed_scope == "2-3"
    assert window.analysis_panel_plot._committed_atom_count == 2
    window.close()


def test_scoped_and_full_exports_use_distinct_data(tmp_path, monkeypatch):
    app()
    window = MainWindow()
    seed(window)
    scoped_path = tmp_path / "scope.csv"
    full_path = tmp_path / "full.csv"
    paths = iter(((str(scoped_path), "CSV"), (str(full_path), "CSV")))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: next(paths))

    window.export_csv()
    window.export_full_csv()

    assert pd.read_csv(scoped_path)["Atom"].tolist() == [1, 2]
    assert pd.read_csv(full_path)["Atom"].tolist() == [1, 2, 3]
    window.close()


def test_failed_batch_discards_all_staged_results(monkeypatch):
    app()
    window = MainWindow()
    seed(window, scope="1")
    previous = window.session_store.full_df("ws")
    window.selected_workspaces = ["ws", "other"]
    window._batch_config = {
        "target": "2",
        "targets_by_workspace": {"ws": "2", "other": "3"},
    }
    window._batch_pending_results = {
        "ws": {"df": frame((9.0, 8.0, 7.0)), "struct": object()},
    }
    window._batch_errors = ["other: failed"]
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)

    window._finish_batch_analysis()

    pd.testing.assert_frame_equal(window.session_store.full_df("ws"), previous)
    assert window.session_store.session("ws").selected_atom_ids == (1,)
    assert "other" not in window.all_calculated_data
    window.close()


def test_late_single_worker_callback_is_ignored_and_workspace_is_captured():
    accepted = []
    owner = SimpleNamespace(
        _active_single_run_id=2,
        _active_analysis_generation=2,
        _complete_single_analysis=lambda *args: accepted.append(args),
    )

    MainWindow._on_single_analysis_finished(
        owner, 1, "old", {"target": "1"}, None, frame(), None
    )
    MainWindow._on_single_analysis_finished(
        owner, 2, "captured", {"target": "3"}, None, frame(), None
    )

    assert len(accepted) == 1
    assert accepted[0][0] == "captured"
    assert accepted[0][1] == {"target": "3"}


def test_late_batch_callback_cannot_pollute_new_batch():
    owner = SimpleNamespace(
        _active_batch_id=8,
        _active_analysis_generation=8,
        _batch_errors=[],
        _batch_pending_results={},
        _source_revision_payload=lambda workspace: {},
        _run_next_batch_analysis=lambda batch_id: None,
    )

    MainWindow._on_batch_analysis_finished(
        owner, 7, "old", None, frame((9.0, 9.0, 9.0)), None
    )
    MainWindow._on_batch_analysis_finished(
        owner, 8, "new", None, frame(), None
    )

    assert list(owner._batch_pending_results) == ["new"]


def test_single_then_batch_ignores_late_single_result():
    accepted = []
    owner = SimpleNamespace(
        _active_analysis_generation=2,
        _active_single_run_id=1,
        _active_batch_id=2,
        _batch_errors=[],
        _batch_pending_results={},
        _source_revision_payload=lambda workspace: {},
        _run_next_batch_analysis=lambda generation: accepted.append("batch"),
        _complete_single_analysis=lambda *args: accepted.append("single"),
    )

    MainWindow._on_single_analysis_finished(
        owner, 1, "old-single", {}, None, frame(), None
    )
    MainWindow._on_batch_analysis_finished(
        owner, 2, "new-batch", None, frame(), None
    )

    assert accepted == ["batch"]
    assert list(owner._batch_pending_results) == ["new-batch"]


def test_batch_then_single_ignores_late_batch_result():
    accepted = []
    owner = SimpleNamespace(
        _active_analysis_generation=3,
        _active_single_run_id=3,
        _active_batch_id=2,
        _batch_errors=[],
        _batch_pending_results={},
        _source_revision_payload=lambda workspace: {},
        _run_next_batch_analysis=lambda generation: accepted.append("batch"),
        _complete_single_analysis=lambda *args: accepted.append("single"),
        _active_single_context=("new-single", {}),
    )

    MainWindow._on_batch_analysis_finished(
        owner, 2, "old-batch", None, frame(), None
    )
    MainWindow._on_single_analysis_finished(
        owner, 3, "new-single", {}, None, frame(), None
    )

    assert accepted == ["single"]
    assert owner._batch_pending_results == {}


def test_worker_registry_holds_overlapping_runs_until_completion_signal():
    class Signal:
        def __init__(self):
            self.callbacks = []

        def connect(self, callback):
            self.callbacks.append(callback)

        def emit(self):
            for callback in list(self.callbacks):
                callback()

    first = SimpleNamespace(thread_completed=Signal())
    second = SimpleNamespace(thread_completed=Signal())
    owner = SimpleNamespace(_analysis_workers={})
    owner._release_analysis_worker = MethodType(
        MainWindow._release_analysis_worker, owner
    )

    MainWindow._register_analysis_worker(owner, (1, "single"), first)
    MainWindow._register_analysis_worker(owner, (2, "single"), second)

    assert set(owner._analysis_workers) == {(1, "single"), (2, "single")}
    first.thread_completed.emit()
    assert set(owner._analysis_workers) == {(2, "single")}
    second.thread_completed.emit()
    assert owner._analysis_workers == {}


def test_metadata_failure_rolls_back_sessions_cache_view_and_metadata():
    old = frame()
    store = AnalysisSessionStore()
    store.put_full_result("ws1", {"df": old, "struct": None})
    store.put_full_result("ws2", {"df": old, "struct": None})
    store.commit_scopes({"ws1": "1", "ws2": "1"})
    states = {
        "ws1": {"analysis_scope": "1", "analysis_revision": 1},
        "ws2": {"analysis_scope": "1", "analysis_revision": 1},
    }

    class Manager:
        calls = 0

        def load_state(self, workspace):
            return dict(states[workspace])

        def save_state(self, workspace, state):
            states[workspace] = dict(state)

        def save_analysis_metadata(self, workspace, scope, revision, source):
            self.calls += 1
            if self.calls == 2:
                raise OSError("metadata write failed")
            states[workspace].update(
                analysis_scope=scope, analysis_revision=revision,
                source_revision=source,
            )

    visible = old.iloc[[0]].copy()
    owner = SimpleNamespace(
        session_store=store,
        all_calculated_data={
            "ws1": {"df": old.copy(), "struct": None},
            "ws2": {"df": old.copy(), "struct": None},
        },
        current_df=visible,
        _workspace_targets={"ws1": "1", "ws2": "1"},
        ws_mgr=Manager(),
    )
    before_states = {key: dict(value) for key, value in states.items()}

    with pytest.raises(OSError, match="metadata write failed"):
        MainWindow._publish_analysis_results(
            owner,
            {
                "ws1": {"df": frame((4.0, 5.0, 6.0)), "struct": None},
                "ws2": {"df": frame((7.0, 8.0, 9.0)), "struct": None},
            },
            {"ws1": "2", "ws2": "3"},
        )

    assert store.session("ws1").selected_atom_ids == (1,)
    assert store.session("ws2").selected_atom_ids == (1,)
    assert owner.all_calculated_data["ws1"]["df"].equals(old)
    assert owner.current_df is visible
    assert states == before_states


def test_restart_loads_all_selected_persisted_workspaces(tmp_path):
    manager = WorkspaceManager(str(tmp_path))
    for workspace, scope, revision in (("ws1", "1", 3), ("ws2", "2-3", 5)):
        manager.create_workspace(workspace)
        path = manager.get_workspace_path(workspace)
        frame().to_json(os.path.join(path, "results.json"), orient="records")
        manager.save_analysis_metadata(workspace, scope, revision, f"source-{workspace}")

    owner = SimpleNamespace(
        session_store=AnalysisSessionStore(),
        selected_workspaces=["ws1", "ws2"],
        current_ws=None,
        all_calculated_data={},
        ws_mgr=manager,
        lbl_status_indicator=SimpleNamespace(setText=lambda text: None),
    )
    owner._load_results = MethodType(MainWindow._load_results, owner)
    owner._put_loaded_result = MethodType(MainWindow._put_loaded_result, owner)
    owner._load_ws_data_from_disk = MethodType(MainWindow._load_ws_data_from_disk, owner)

    names = MainWindow._session_names(owner, ["ws1", "ws2"])

    assert names == ["ws1", "ws2"]
    assert owner.session_store.session("ws1").analysis_revision == 3
    assert owner.session_store.session("ws2").analysis_revision == 5
    assert owner.session_store.session("ws2").selected_atom_ids == (2, 3)
    assert (
        owner.session_store.session("ws1").structure_revision
        != owner.session_store.session("ws1").source_revision
    )

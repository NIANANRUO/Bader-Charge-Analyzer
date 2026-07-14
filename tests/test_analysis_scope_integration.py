import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from gui.main_window import MainWindow


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

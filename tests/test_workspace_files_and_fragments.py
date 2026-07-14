from pathlib import Path

import pytest

from core.workspace_manager import WorkspaceManager


def test_fragment_definitions_persist_and_workspace_override_wins(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create_workspace("ws1")

    manager.save_fragments(
        "ws1",
        {"吸附物": {"expression": "1-3", "overrides": {"ws1": "4-5"}}},
    )

    fragments = manager.get_fragments("ws1")
    assert fragments["吸附物"]["expression"] == "1-3"
    assert manager.resolve_fragment_expression("ws1", "吸附物") == "4-5"


def test_import_file_requires_explicit_overwrite(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    manager.create_workspace("ws1")
    first = tmp_path / "first" / "ACF.dat"
    second = tmp_path / "second" / "ACF.dat"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    manager.import_file("ws1", first)
    with pytest.raises(FileExistsError):
        manager.import_file("ws1", second)

    manager.import_file("ws1", second, overwrite=True)
    assert Path(manager.get_workspace_path("ws1"), "ACF.dat").read_text(encoding="utf-8") == "second"


def test_critical_file_change_invalidates_results(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create_workspace("ws1")
    ws_path = Path(manager.get_workspace_path("ws1"))
    (ws_path / "results.json").write_text("[]", encoding="utf-8")
    state = manager.load_state("ws1")
    state["calculated"] = True
    manager.save_state("ws1", state)

    assert manager.invalidate_results("ws1", changed_filename="ACF.dat") is True
    assert not (ws_path / "results.json").exists()
    assert manager.load_state("ws1")["calculated"] is False


def test_analysis_metadata_round_trip_normalizes_values(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create_workspace("ws1")

    manager.save_analysis_metadata(
        "ws1",
        committed_scope="  1-3  ",
        analysis_revision="4",
        source_revision="  source-hash  ",
    )

    assert manager.get_analysis_metadata("ws1") == {
        "committed_scope": "1-3",
        "analysis_revision": 4,
        "source_revision": "source-hash",
    }


def test_legacy_workspace_has_safe_analysis_metadata_defaults(tmp_path):
    manager = WorkspaceManager(tmp_path)
    workspace = Path(manager.get_workspace_path("legacy"))
    workspace.mkdir()
    (workspace / "state.json").write_text('{"name": "legacy"}', encoding="utf-8")

    state = manager.load_state("legacy")

    assert state["analysis_scope"] == ""
    assert state["analysis_revision"] == 0
    assert state["source_revision"] == ""
    assert manager.get_analysis_metadata("legacy") == {
        "committed_scope": "",
        "analysis_revision": 0,
        "source_revision": "",
    }


def test_critical_file_change_clears_versioned_analysis_metadata(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create_workspace("ws1")
    manager.save_analysis_metadata("ws1", "1-3", 7, "old-source")

    assert manager.invalidate_results("ws1", changed_filename="POTCAR") is True

    assert manager.get_analysis_metadata("ws1") == {
        "committed_scope": "1-3",
        "analysis_revision": 0,
        "source_revision": "",
    }


def test_noncritical_file_change_keeps_results(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create_workspace("ws1")
    results = Path(manager.get_workspace_path("ws1"), "results.json")
    results.write_text("[]", encoding="utf-8")

    assert manager.invalidate_results("ws1", changed_filename="notes.txt") is False
    assert results.exists()

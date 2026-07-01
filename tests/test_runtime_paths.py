import sys
from pathlib import Path

import core.runtime_paths as runtime_paths
from core.workspace_manager import WorkspaceManager


def test_source_workspace_root_stays_project_relative(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert runtime_paths.default_workspace_root() == Path("workspaces")
    assert WorkspaceManager().root_dir == "workspaces"


def test_frozen_workspace_root_uses_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    root = runtime_paths.default_workspace_root()

    assert root == tmp_path / "Bader Charge Analyzer" / "workspaces"
    assert WorkspaceManager().root_dir == str(root)


def test_frozen_bader_candidates_are_next_to_executable(monkeypatch, tmp_path):
    exe = tmp_path / "BaderChargeAnalyzer.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))

    candidates = runtime_paths.bundled_bader_candidates()

    assert candidates[0] == tmp_path / "bader.exe"
    assert candidates[1] == tmp_path / "bader"
    assert candidates[2] == tmp_path / "bader_engine" / "bader.exe"
    assert candidates[3] == tmp_path / "bader_engine" / "bader"

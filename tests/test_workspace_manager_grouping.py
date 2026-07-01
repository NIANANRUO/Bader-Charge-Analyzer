# -*- coding: utf-8 -*-
from core.workspace_manager import WorkspaceManager


def test_workspace_defaults_to_ungrouped(tmp_path):
    manager = WorkspaceManager(str(tmp_path))
    manager.create_workspace("ws1")

    meta = manager.get_workspace_meta("ws1")

    assert meta["group"] == "未分组"
    assert meta["display_name"] == "ws1"
    assert meta["order"] == 0


def test_workspace_group_metadata_persists(tmp_path):
    manager = WorkspaceManager(str(tmp_path))
    manager.create_workspace("ws1")

    manager.update_workspace_meta("ws1", group="Group A", display_name="Sample 1", order=3)

    meta = manager.get_workspace_meta("ws1")
    assert meta["group"] == "Group A"
    assert meta["display_name"] == "Sample 1"
    assert meta["order"] == 3


def test_grouped_workspaces_are_sorted(tmp_path):
    manager = WorkspaceManager(str(tmp_path))
    manager.create_workspace("b")
    manager.create_workspace("a")
    manager.update_workspace_meta("b", group="G", order=2)
    manager.update_workspace_meta("a", group="G", order=1)

    grouped = manager.get_grouped_workspaces()

    assert list(grouped.keys()) == ["G"]
    assert grouped["G"] == ["a", "b"]


def test_empty_groups_are_persisted(tmp_path):
    manager = WorkspaceManager(str(tmp_path))

    manager.create_group("Empty Group")

    assert manager.get_groups() == ["Empty Group"]
    assert manager.get_grouped_workspaces()["Empty Group"] == []


def test_rename_group_updates_registry_and_workspace_metadata(tmp_path):
    manager = WorkspaceManager(str(tmp_path))
    manager.create_workspace("ws1")
    manager.create_workspace("ws2")
    manager.update_workspace_meta("ws1", group="Old Group")
    manager.update_workspace_meta("ws2", group="Other Group")

    assert manager.rename_group("Old Group", "New Group") is True

    assert "Old Group" not in manager.get_groups()
    assert "New Group" in manager.get_groups()
    assert manager.get_workspace_meta("ws1")["group"] == "New Group"
    assert manager.get_workspace_meta("ws2")["group"] == "Other Group"


def test_move_workspaces_to_group_updates_each_workspace(tmp_path):
    manager = WorkspaceManager(str(tmp_path))
    manager.create_workspace("ws1")
    manager.create_workspace("ws2")
    manager.create_workspace("ws3")

    moved = manager.move_workspaces_to_group(["ws1", "ws2"], "Batch Group")

    assert moved == ["ws1", "ws2"]
    assert manager.get_workspace_meta("ws1")["group"] == "Batch Group"
    assert manager.get_workspace_meta("ws2")["group"] == "Batch Group"
    assert manager.get_workspace_meta("ws3")["group"] == manager.DEFAULT_GROUP

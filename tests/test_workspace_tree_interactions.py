# -*- coding: utf-8 -*-
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QInputDialog

from core.workspace_manager import WorkspaceManager
from gui import main_window


def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def build_window(tmp_path):
    manager = WorkspaceManager(str(tmp_path))
    window = main_window.MainWindow(workspace_manager=manager)
    window.load_workspaces()
    return window, manager


def find_group_item(window, group_name):
    for i in range(window.ws_tree.topLevelItemCount()):
        item = window.ws_tree.topLevelItem(i)
        if item.text(0) == group_name:
            return item
    raise AssertionError(f"group not found: {group_name}")


def find_workspace_item(window, workspace_name):
    for i in range(window.ws_tree.topLevelItemCount()):
        group = window.ws_tree.topLevelItem(i)
        for j in range(group.childCount()):
            child = group.child(j)
            if child.data(0, main_window.Qt.UserRole) == workspace_name:
                return child
    raise AssertionError(f"workspace not found: {workspace_name}")


def test_create_workspace_uses_selected_group(tmp_path):
    app()
    window, manager = build_window(tmp_path)
    try:
        manager.create_group("Li2S")
        window.load_workspaces()
        group_item = find_group_item(window, "Li2S")
        window.ws_tree.setCurrentItem(group_item)
        group_item.setSelected(True)

        window.create_ws()

        names = manager.get_all_workspaces()
        assert len(names) == 1
        assert manager.get_workspace_meta(names[0])["group"] == "Li2S"
        assert find_workspace_item(window, names[0]).parent().text(0) == "Li2S"
    finally:
        window.close()


def test_rename_selected_workspace_updates_identity_and_display(tmp_path, monkeypatch):
    app()
    window, manager = build_window(tmp_path)
    try:
        manager.create_workspace("ws1")
        manager.update_workspace_meta("ws1", group="Li2S", display_name="ws1")
        window.load_workspaces()
        item = find_workspace_item(window, "ws1")
        window.ws_tree.setCurrentItem(item)
        monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("ws-renamed", True))

        window.rename_selected_item(item, 0)

        assert "ws1" not in manager.get_all_workspaces()
        assert "ws-renamed" in manager.get_all_workspaces()
        assert manager.load_state("ws-renamed")["name"] == "ws-renamed"
        assert manager.get_workspace_meta("ws-renamed")["display_name"] == "ws-renamed"
        assert manager.get_workspace_meta("ws-renamed")["group"] == "Li2S"
        assert find_workspace_item(window, "ws-renamed").text(0) == "ws-renamed"
    finally:
        window.close()


def test_toolbar_rename_group_updates_workspace_metadata(tmp_path, monkeypatch):
    app()
    window, manager = build_window(tmp_path)
    try:
        manager.create_workspace("ws1")
        manager.update_workspace_meta("ws1", group="Li2S")
        window.load_workspaces()
        group_item = find_group_item(window, "Li2S")
        window.ws_tree.setCurrentItem(group_item)
        monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Li2S6", True))

        window.rename_selected_item()

        assert "Li2S" not in manager.get_groups()
        assert "Li2S6" in manager.get_groups()
        assert manager.get_workspace_meta("ws1")["group"] == "Li2S6"
        assert find_workspace_item(window, "ws1").parent().text(0) == "Li2S6"
    finally:
        window.close()


def test_move_selected_workspaces_to_target_group_persists_after_reload(tmp_path):
    app()
    window, manager = build_window(tmp_path)
    try:
        manager.create_workspace("ws1")
        manager.create_workspace("ws2")
        manager.create_group("Li2S6")
        manager.update_workspace_meta("ws1", group="Li2S")
        manager.update_workspace_meta("ws2", group="Li2S")
        window.load_workspaces()

        window.move_workspace_to_group_name(["ws1", "ws2"], "Li2S6")
        window.load_workspaces()

        assert manager.get_workspace_meta("ws1")["group"] == "Li2S6"
        assert manager.get_workspace_meta("ws2")["group"] == "Li2S6"
        assert find_workspace_item(window, "ws1").parent().text(0) == "Li2S6"
        assert find_workspace_item(window, "ws2").parent().text(0) == "Li2S6"
    finally:
        window.close()


def test_drop_event_emits_selected_workspace_names_not_group_headers(tmp_path):
    app_instance = app()
    window, manager = build_window(tmp_path)
    try:
        manager.create_workspace("ws1")
        manager.update_workspace_meta("ws1", group="Li2S")
        manager.create_group("Li2S6")
        window.load_workspaces()
        window.resize(500, 700)
        window.show()
        app_instance.processEvents()

        source_group = find_group_item(window, "Li2S")
        source_child = find_workspace_item(window, "ws1")
        target_group = find_group_item(window, "Li2S6")
        window.ws_tree.setCurrentItem(source_group)
        source_group.setSelected(True)
        source_child.setSelected(True)

        emitted = []
        window.ws_tree.workspaceDropped.connect(lambda names, group: emitted.append((names, group)))

        class FakePosition:
            def __init__(self, point):
                self._point = point

            def toPoint(self):
                return self._point

        class FakeDropEvent:
            def __init__(self, point):
                self._point = point
                self.accepted = False
                self.ignored = False

            def position(self):
                return FakePosition(self._point)

            def acceptProposedAction(self):
                self.accepted = True

            def ignore(self):
                self.ignored = True

        point = window.ws_tree.visualItemRect(target_group).center()
        event = FakeDropEvent(point)

        window.ws_tree.dropEvent(event)

        assert event.accepted is True
        assert event.ignored is False
        assert emitted == [(["ws1"], "Li2S6")]
    finally:
        window.close()


def test_highlight_does_not_select_workspace_for_batch_plot(tmp_path):
    app()
    window, manager = build_window(tmp_path)
    try:
        manager.create_workspace("ws1")
        manager.create_workspace("ws2")
        window.load_workspaces()

        item = find_workspace_item(window, "ws1")
        window.ws_tree.setCurrentItem(item)
        item.setSelected(True)

        assert window.get_selected_workspace_names() == []
    finally:
        window.close()


def test_workspace_checkboxes_are_the_only_batch_selection_source(tmp_path):
    app()
    window, manager = build_window(tmp_path)
    try:
        manager.create_workspace("ws1")
        manager.create_workspace("ws2")
        window.load_workspaces()

        ws1 = find_workspace_item(window, "ws1")
        ws2 = find_workspace_item(window, "ws2")
        ws1.setCheckState(0, main_window.Qt.Checked)
        ws2.setSelected(True)

        assert window.get_selected_workspace_names() == ["ws1"]
    finally:
        window.close()

import json
import os
import shutil

from core.runtime_paths import default_workspace_root


class WorkspaceManager:
    """Manages isolated workspaces for different analysis projects."""

    DEFAULT_GROUP = "\u672a\u5206\u7ec4"

    def __init__(self, root_dir=None):
        self.root_dir = os.fspath(root_dir or default_workspace_root())
        self.groups_path = os.path.join(self.root_dir, "workspace_groups.json")
        if not os.path.exists(self.root_dir):
            os.makedirs(self.root_dir)

    def get_all_workspaces(self):
        """Returns a list of all workspace names."""
        return [
            d for d in os.listdir(self.root_dir)
            if os.path.isdir(os.path.join(self.root_dir, d))
        ]

    def get_groups(self):
        """Return user-created workspace groups."""
        if not os.path.exists(self.groups_path):
            return []
        with open(self.groups_path, "r", encoding="utf-8") as f:
            groups = json.load(f)
        return [g for g in groups if isinstance(g, str) and g.strip()]

    def save_groups(self, groups):
        """Persist user-created workspace groups."""
        unique = []
        seen = set()
        for group in groups:
            name = group.strip()
            if name and name not in seen:
                unique.append(name)
                seen.add(name)
        with open(self.groups_path, "w", encoding="utf-8") as f:
            json.dump(unique, f, indent=4, ensure_ascii=False)

    def create_group(self, name):
        """Create an empty group for organizing workspaces."""
        group = name.strip() or self.DEFAULT_GROUP
        groups = self.get_groups()
        if group not in groups:
            groups.append(group)
            self.save_groups(groups)
        return group

    def rename_group(self, old_name, new_name):
        """Rename a group and move all assigned workspaces to the new name."""
        old_group = (old_name or "").strip()
        new_group = (new_name or "").strip() or self.DEFAULT_GROUP
        if not old_group or old_group == new_group:
            return False

        changed = False
        groups = self.get_groups()
        if old_group in groups:
            groups = [new_group if group == old_group else group for group in groups]
            self.save_groups(groups)
            changed = True

        for workspace in self.get_all_workspaces():
            state = self.load_state(workspace)
            if state.get("group", self.DEFAULT_GROUP) == old_group:
                state["group"] = new_group
                self.save_state(workspace, state)
                changed = True

        if changed:
            self.create_group(new_group)
        return changed

    def move_workspaces_to_group(self, names, group):
        """Move existing workspaces to a group and return the names moved."""
        target_group = self.create_group(group)
        available = set(self.get_all_workspaces())
        moved = []
        for name in names:
            if name in available:
                self.update_workspace_meta(name, group=target_group)
                moved.append(name)
        return moved

    def _with_default_meta(self, name, state):
        state.setdefault("name", name)
        state.setdefault("imported_files", [])
        state.setdefault("calculated", False)
        state.setdefault("group", self.DEFAULT_GROUP)
        state.setdefault("display_name", name)
        state.setdefault("order", 0)
        return state

    def create_workspace(self, name):
        """Creates a new workspace directory."""
        ws_path = os.path.join(self.root_dir, name)
        if not os.path.exists(ws_path):
            os.makedirs(ws_path)
            state = self._with_default_meta(name, {})
            self.save_state(name, state)
        return ws_path

    def delete_workspace(self, name):
        """Deletes a workspace."""
        ws_path = os.path.join(self.root_dir, name)
        if os.path.exists(ws_path):
            shutil.rmtree(ws_path)

    def rename_workspace(self, old_name, new_name):
        """Renames a workspace."""
        old_path = self.get_workspace_path(old_name)
        new_path = self.get_workspace_path(new_name)
        if os.path.exists(old_path) and not os.path.exists(new_path):
            os.rename(old_path, new_path)
            state = self.load_state(new_name)
            state["name"] = new_name
            state.setdefault("display_name", new_name)
            self.save_state(new_name, state)
            return True
        return False

    def delete_file(self, workspace_name, filename):
        """Deletes a specific file from a workspace."""
        ws_path = self.get_workspace_path(workspace_name)
        file_path = os.path.join(ws_path, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        state = self.load_state(workspace_name)
        if filename in state.get("imported_files", []):
            state["imported_files"].remove(filename)
            self.save_state(workspace_name, state)

    def get_workspace_path(self, name):
        return os.path.join(self.root_dir, name)

    def save_state(self, name, state_dict):
        """Saves workspace metadata."""
        path = os.path.join(self.get_workspace_path(name), "state.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, indent=4, ensure_ascii=False)

    def load_state(self, name):
        """Loads workspace metadata."""
        path = os.path.join(self.get_workspace_path(name), "state.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return self._with_default_meta(name, json.load(f))
        return self._with_default_meta(name, {})

    def get_workspace_meta(self, name):
        """Return lightweight grouping/display metadata for a workspace."""
        state = self.load_state(name)
        return {
            "group": state.get("group", self.DEFAULT_GROUP) or self.DEFAULT_GROUP,
            "display_name": state.get("display_name", name) or name,
            "order": int(state.get("order", 0) or 0),
        }

    def update_workspace_meta(self, name, group=None, display_name=None, order=None):
        """Update grouping/display metadata without changing workspace contents."""
        state = self.load_state(name)
        if group is not None:
            state["group"] = group.strip() or self.DEFAULT_GROUP
            self.create_group(state["group"])
        if display_name is not None:
            state["display_name"] = display_name.strip() or name
        if order is not None:
            state["order"] = int(order)
        self.save_state(name, state)
        return state

    def get_grouped_workspaces(self):
        """Return workspaces grouped by metadata and sorted by order/name."""
        grouped = {group: [] for group in self.get_groups()}
        for name in self.get_all_workspaces():
            meta = self.get_workspace_meta(name)
            grouped.setdefault(meta["group"], []).append((meta["order"], name))
        sorted_groups = {}
        for group in sorted(grouped.keys()):
            sorted_groups[group] = [
                name for _, name in sorted(grouped[group], key=lambda item: (item[0], item[1]))
            ]
        return sorted_groups

    def import_file(self, workspace_name, source_filepath):
        """Copies a file into the workspace."""
        ws_path = self.get_workspace_path(workspace_name)
        filename = os.path.basename(source_filepath)
        dest_path = os.path.join(ws_path, filename)
        shutil.copy2(source_filepath, dest_path)

        state = self.load_state(workspace_name)
        if filename not in state["imported_files"]:
            state["imported_files"].append(filename)
            self.save_state(workspace_name, state)

        return dest_path

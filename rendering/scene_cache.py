"""Version-safe scene keys and bounded hidden-workspace retention."""

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Iterable


@dataclass(frozen=True)
class GeometryKey:
    workspace_id: str
    structure_fingerprint: str
    atom_count: int
    element_sequence: tuple[str, ...]


@dataclass(frozen=True)
class AppearanceKey:
    analysis_revision: int
    selected_atom_ids: tuple[int, ...]
    source_revision: str
    charge_revision: str
    render_settings: tuple[Hashable, ...]


class SceneCache:
    """LRU cache that never evicts a scene belonging to a visible workspace."""

    def __init__(
        self,
        capacity: int = 6,
        release: Callable[[Any], None] | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least one")
        self.capacity = capacity
        self.release = release or (lambda _scene: None)
        self._geometry: OrderedDict[GeometryKey, Any] = OrderedDict()
        self._appearance: dict[str, AppearanceKey] = {}
        self._visible: set[str] = set()

    def __len__(self) -> int:
        return len(self._geometry)

    def set_visible(self, workspace_ids: Iterable[str]) -> None:
        self._visible = set(workspace_ids)
        self._evict_hidden()

    def remember_geometry(self, key: GeometryKey, scene: Any) -> None:
        previous = self._geometry.get(key)
        if previous is not None and previous is not scene:
            self.release(previous)
        self._geometry[key] = scene
        self._geometry.move_to_end(key)
        self._evict_hidden()

    def geometry(self, key: GeometryKey) -> Any | None:
        scene = self._geometry.get(key)
        if scene is not None:
            self._geometry.move_to_end(key)
        return scene

    def remember_appearance(self, workspace_id: str, key: AppearanceKey) -> None:
        self._appearance[workspace_id] = key

    def appearance(self, workspace_id: str) -> AppearanceKey | None:
        return self._appearance.get(workspace_id)

    def invalidate_workspace(self, workspace_id: str) -> None:
        keys = [key for key in self._geometry if key.workspace_id == workspace_id]
        for key in keys:
            self.release(self._geometry.pop(key))
        self._appearance.pop(workspace_id, None)

    def _evict_hidden(self) -> None:
        while len(self._geometry) > self.capacity:
            candidate = next(
                (
                    key
                    for key in self._geometry
                    if key.workspace_id not in self._visible
                ),
                None,
            )
            if candidate is None:
                return
            self.release(self._geometry.pop(candidate))

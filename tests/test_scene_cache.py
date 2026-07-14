from rendering.scene_cache import AppearanceKey, GeometryKey, SceneCache


def geometry_key(workspace: str) -> GeometryKey:
    return GeometryKey(workspace, f"structure-{workspace}", 1, ("H",))


def test_geometry_key_isolated_by_workspace_and_structure_identity():
    cache = SceneCache(capacity=6)
    original = GeometryKey("ws-a", "structure", 3, ("Li", "O", "S"))
    cache.remember_geometry(original, "scene")

    assert cache.geometry(original) == "scene"
    assert cache.geometry(GeometryKey("ws-b", "structure", 3, ("Li", "O", "S"))) is None
    assert cache.geometry(GeometryKey("ws-a", "other", 3, ("Li", "O", "S"))) is None
    assert cache.geometry(GeometryKey("ws-a", "structure", 2, ("Li", "O"))) is None
    assert cache.geometry(GeometryKey("ws-a", "structure", 3, ("Li", "S", "O"))) is None


def test_appearance_key_tracks_analysis_charge_source_scope_and_settings():
    base = AppearanceKey(1, (1, 2), "source", "charge", ("RdBu_r",))

    assert base != AppearanceKey(2, (1, 2), "source", "charge", ("RdBu_r",))
    assert base != AppearanceKey(1, (2,), "source", "charge", ("RdBu_r",))
    assert base != AppearanceKey(1, (1, 2), "other", "charge", ("RdBu_r",))
    assert base != AppearanceKey(1, (1, 2), "source", "other", ("RdBu_r",))
    assert base != AppearanceKey(1, (1, 2), "source", "charge", ("viridis",))


def test_lru_evicts_only_hidden_workspaces_and_releases_once():
    released = []
    cache = SceneCache(capacity=2, release=released.append)
    cache.remember_geometry(geometry_key("a"), "a")
    cache.remember_geometry(geometry_key("b"), "b")
    cache.set_visible({"b", "c"})

    cache.remember_geometry(geometry_key("c"), "c")

    assert released == ["a"]
    assert cache.geometry(geometry_key("a")) is None
    assert cache.geometry(geometry_key("b")) == "b"
    assert cache.geometry(geometry_key("c")) == "c"


def test_all_visible_scenes_may_temporarily_exceed_capacity():
    released = []
    cache = SceneCache(capacity=1, release=released.append)
    cache.set_visible({"a", "b"})
    cache.remember_geometry(geometry_key("a"), "a")
    cache.remember_geometry(geometry_key("b"), "b")

    assert len(cache) == 2
    assert released == []


def test_replacing_and_invalidating_release_each_scene_exactly_once():
    released = []
    cache = SceneCache(capacity=6, release=released.append)
    key = geometry_key("ws")
    cache.remember_geometry(key, "first")
    cache.remember_geometry(key, "first")
    cache.remember_geometry(key, "replacement")
    cache.remember_appearance(
        "ws", AppearanceKey(1, (1,), "source", "charge", ("RdBu_r",))
    )

    cache.invalidate_workspace("ws")
    cache.invalidate_workspace("ws")

    assert released == ["first", "replacement"]
    assert cache.geometry(key) is None
    assert cache.appearance("ws") is None


def test_geometry_cache_hit_refreshes_lru_recency():
    released = []
    cache = SceneCache(capacity=2, release=released.append)
    cache.remember_geometry(geometry_key("a"), "a")
    cache.remember_geometry(geometry_key("b"), "b")
    assert cache.geometry(geometry_key("a")) == "a"

    cache.remember_geometry(geometry_key("c"), "c")

    assert released == ["b"]
    assert cache.geometry(geometry_key("a")) == "a"
    assert cache.geometry(geometry_key("c")) == "c"

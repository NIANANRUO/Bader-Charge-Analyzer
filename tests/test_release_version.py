from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_v020_version_is_consistent():
    assert '#define AppVersion    "0.2.0"' in _read("installer/setup.iss")
    assert "BaderChargeAnalyzer_Setup_v0.2.0.exe" in _read(
        "installer/build_windows.ps1"
    )
    assert "v0.2.0" in _read("README.md")


def test_v020_release_notes_document_scope_cache_and_migration():
    notes = _read("docs/releases/v0.2.0.md")

    for expected in (
        "草稿",
        "全部原子",
        "片段",
        "范围结果",
        "完整原始结果",
        "完整结构",
        "目标原子",
        "缓存",
        "results.json",
        "兼容",
    ):
        assert expected in notes

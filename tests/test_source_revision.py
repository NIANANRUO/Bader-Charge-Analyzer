from collections import Counter
import io
import os

from core import source_revision
from core.source_revision import SourceRevision


def _write_inputs(workspace, *, poscar="poscar", contcar=None, acf="acf", potcar="potcar"):
    workspace.mkdir()
    (workspace / "POSCAR").write_text(poscar, encoding="utf-8")
    if contcar is not None:
        (workspace / "CONTCAR").write_text(contcar, encoding="utf-8")
    (workspace / "ACF.dat").write_text(acf, encoding="utf-8")
    (workspace / "POTCAR").write_text(potcar, encoding="utf-8")


def test_structure_change_updates_structure_and_source_fingerprints(tmp_path):
    workspace = tmp_path / "workspace"
    _write_inputs(workspace)
    before = SourceRevision.from_workspace(workspace)

    (workspace / "POSCAR").write_text("changed structure", encoding="utf-8")
    after = SourceRevision.from_workspace(workspace)

    assert after.structure_fingerprint != before.structure_fingerprint
    assert after.source_fingerprint != before.source_fingerprint


def test_acf_change_only_updates_source_fingerprint(tmp_path):
    workspace = tmp_path / "workspace"
    _write_inputs(workspace)
    before = SourceRevision.from_workspace(workspace)

    (workspace / "ACF.dat").write_text("changed acf", encoding="utf-8")
    after = SourceRevision.from_workspace(workspace)

    assert after.structure_fingerprint == before.structure_fingerprint
    assert after.source_fingerprint != before.source_fingerprint


def test_contcar_takes_precedence_over_poscar(tmp_path):
    workspace = tmp_path / "workspace"
    _write_inputs(workspace, contcar="relaxed")
    before = SourceRevision.from_workspace(workspace)

    (workspace / "POSCAR").write_text("ignored change", encoding="utf-8")
    after_poscar_change = SourceRevision.from_workspace(workspace)
    (workspace / "CONTCAR").write_text("new relaxed structure", encoding="utf-8")
    after_contcar_change = SourceRevision.from_workspace(workspace)

    assert after_poscar_change == before
    assert after_contcar_change.structure_fingerprint != before.structure_fingerprint
    assert after_contcar_change.source_fingerprint != before.source_fingerprint


def test_missing_inputs_have_deterministic_fingerprints(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    first = SourceRevision.from_workspace(workspace)
    second = SourceRevision.from_workspace(workspace)

    assert first == second
    assert first.structure_fingerprint
    assert first.source_fingerprint


def test_unchanged_inputs_reuse_cached_content_hashes(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _write_inputs(workspace)
    source_revision._cached_content_hash.cache_clear()
    hashed_paths = []
    original = source_revision._hash_file_content

    def record_hash(path):
        hashed_paths.append(path)
        return original(path)

    monkeypatch.setattr(source_revision, "_hash_file_content", record_hash)

    SourceRevision.from_workspace(workspace)
    SourceRevision.from_workspace(workspace)

    assert Counter(map(os.path.basename, hashed_paths)) == {
        os.path.normcase("POSCAR"): 1,
        os.path.normcase("ACF.dat"): 1,
        os.path.normcase("POTCAR"): 1,
    }


def test_changed_acf_rehashes_only_acf(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    _write_inputs(workspace)
    source_revision._cached_content_hash.cache_clear()
    hashed_paths = []
    original = source_revision._hash_file_content

    def record_hash(path):
        hashed_paths.append(path)
        return original(path)

    monkeypatch.setattr(source_revision, "_hash_file_content", record_hash)
    SourceRevision.from_workspace(workspace)

    acf_path = workspace / "ACF.dat"
    acf_path.write_text("new", encoding="utf-8")
    stat = acf_path.stat()
    os.utime(acf_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))
    SourceRevision.from_workspace(workspace)

    assert Counter(map(os.path.basename, hashed_paths)) == {
        os.path.normcase("POSCAR"): 1,
        os.path.normcase("ACF.dat"): 2,
        os.path.normcase("POTCAR"): 1,
    }


def test_content_hash_reads_in_bounded_chunks(monkeypatch):
    class RecordingReader(io.BytesIO):
        def __init__(self, value):
            super().__init__(value)
            self.read_sizes = []

        def read(self, size=-1):
            self.read_sizes.append(size)
            return super().read(size)

    reader = RecordingReader(b"content")
    monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: reader)

    source_revision._hash_file_content("unused")

    assert reader.read_sizes
    assert set(reader.read_sizes) == {source_revision._HASH_CHUNK_SIZE}

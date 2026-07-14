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

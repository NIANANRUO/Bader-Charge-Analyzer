import pandas as pd
import pytest

from core.analysis_session import AnalysisSessionStore
from core.selection import SelectionError


def payload(*, elements=None, structure_revision=None):
    data = {
        "df": pd.DataFrame(
            {
                "Atom": [1, 2, 3, 4],
                "Element": elements or ["Li", "O", "O", "S"],
                "Bader_Charge": [0.2, -0.3, 0.5, -0.1],
            }
        ),
        "struct": object(),
        "source_revision": "source-1",
    }
    if structure_revision is not None:
        data["structure_revision"] = structure_revision
    return data


def test_draft_does_not_change_committed_projection():
    store = AnalysisSessionStore()
    store.put_full_result("ws", payload())
    store.commit_scopes({"ws": "2-3"})

    store.set_draft("ws", "4")

    session = store.session("ws")
    assert session.draft_scope == "4"
    assert session.committed_scope == "2-3"
    assert store.projected_df("ws")["Atom"].tolist() == [2, 3]


def test_batch_commit_is_atomic_when_one_scope_is_invalid():
    store = AnalysisSessionStore()
    store.put_full_result("ws1", payload())
    store.put_full_result("ws2", payload())
    store.commit_scopes({"ws1": "1", "ws2": "2"})
    before_ws1 = store.session("ws1")
    before_ws2 = store.session("ws2")

    with pytest.raises(SelectionError):
        store.commit_scopes({"ws1": "3", "ws2": "99"})

    assert store.session("ws1") is before_ws1
    assert store.session("ws2") is before_ws2
    assert store.session("ws1").selected_atom_ids == (1,)
    assert store.session("ws2").selected_atom_ids == (2,)
    assert store.session("ws1").analysis_revision == 1
    assert store.session("ws2").analysis_revision == 1


def test_full_result_remains_available_outside_scope():
    store = AnalysisSessionStore()
    store.put_full_result("ws", payload())
    store.commit_scopes({"ws": "4"})

    assert store.projected_df("ws")["Atom"].tolist() == [4]
    assert store.full_df("ws")["Atom"].tolist() == [1, 2, 3, 4]


def test_blank_scope_selects_all_atoms():
    store = AnalysisSessionStore()
    store.put_full_result("ws", payload())

    store.commit_scopes({"ws": "   "})

    assert store.session("ws").selected_atom_ids == (1, 2, 3, 4)
    assert store.projected_df("ws")["Atom"].tolist() == [1, 2, 3, 4]


def test_projection_is_a_copy_of_full_result():
    store = AnalysisSessionStore()
    store.put_full_result("ws", payload())
    store.commit_scopes({"ws": "2"})

    projected = store.projected_df("ws")
    projected.loc[:, "Bader_Charge"] = 99.0

    assert store.full_df("ws").loc[1, "Bader_Charge"] == -0.3


def test_structure_revision_defaults_to_source_revision():
    store = AnalysisSessionStore()

    session = store.put_full_result("ws", payload())

    assert session.source_revision == "source-1"
    assert session.structure_revision == "source-1"


def test_explicit_structure_revision_is_preserved():
    store = AnalysisSessionStore()

    session = store.put_full_result(
        "ws", payload(structure_revision="structure-7")
    )

    assert session.structure_revision == "structure-7"


def test_replacing_full_result_preserves_scopes_and_revision_and_reresolves_ids():
    store = AnalysisSessionStore()
    store.put_full_result("ws", payload())
    store.commit_scopes({"ws": "O"})
    store.set_draft("ws", "4")

    session = store.put_full_result(
        "ws", payload(elements=["O", "Li", "S", "O"])
    )

    assert session.committed_scope == "O"
    assert session.draft_scope == "4"
    assert session.analysis_revision == 1
    assert session.selected_atom_ids == (1, 4)

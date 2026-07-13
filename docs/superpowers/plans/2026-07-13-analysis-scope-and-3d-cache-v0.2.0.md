# Unified Analysis Scope and 3D Cache v0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release v0.2.0 with one committed per-workspace atom-analysis scope shared by tables, statistics, plots, exports, and 3D charge highlighting, plus version-safe per-workspace 3D caching.

**Architecture:** Keep worker output and persisted `results.json` as full-atom scientific data. Add focused core modules for selection resolution, atomic session commits, projections, and source fingerprints; make `MainWindow` orchestrate these modules. Split 3D into stable geometry construction and lightweight appearance updates keyed by workspace, structure revision, analysis revision, and render settings.

**Tech Stack:** Python 3.10+, pandas, PySide6, PyVista/VTK, pymatgen, pytest, Inno Setup, PowerShell.

---

## Preflight and file map

The working tree already contains user-owned changes in `gui/analysis_panel.py`, `gui/main_window.py`, `tests/test_analysis_panel_multi_targets.py`, `tests/test_workspace_tree_interactions.py`, plus untracked `gui/analysis_dialogs.py` and `tests/test_analysis_dialogs.py`. Preserve and integrate them. Never reset, checkout, or overwrite them.

Create focused modules:

- `core/selection.py`: the only atom-expression parser.
- `core/analysis_session.py`: session state, atomic batch commit, and projections.
- `core/source_revision.py`: stable source fingerprints.
- `rendering/scene_cache.py`: geometry/appearance keys and six-entry LRU policy.
- Matching focused tests under `tests/`.

Modify `core/calculator.py`, `core/workspace_manager.py`, `gui/analysis_panel.py`, `gui/analysis_dialogs.py`, `gui/main_window.py`, `gui/plot_panel.py`, `core/structure_model.py`, `rendering/pyvista_structure_renderer.py`, `gui/visualizer_3d.py`, relevant tests, installer metadata, and README.

### Task 1: Centralize selection parsing

**Files:**
- Create: `core/selection.py`
- Create: `tests/test_selection.py`
- Modify: `core/calculator.py`
- Test: `tests/test_charge_aggregation.py`

- [ ] **Step 1: Write the failing parser contract tests**

```python
import pytest
from core.selection import SelectionError, SelectionResolver


def test_empty_expression_selects_every_atom():
    assert SelectionResolver.resolve("", ["Li", "O", "O", "S"]) == (1, 2, 3, 4)


def test_mixed_expression_is_unique_and_sorted():
    assert SelectionResolver.resolve("4, 2-3, O", ["Li", "O", "O", "S"]) == (2, 3, 4)


@pytest.mark.parametrize("expression", ["0", "5", "3-1", "Xx"])
def test_invalid_expression_raises_without_partial_selection(expression):
    with pytest.raises(SelectionError):
        SelectionResolver.resolve(expression, ["Li", "O", "O", "S"])
```

- [ ] **Step 2: Run tests and verify the missing-module failure**

Run: `pytest tests/test_selection.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'core.selection'`.

- [ ] **Step 3: Implement the single parser**

```python
from __future__ import annotations
import re


class SelectionError(ValueError):
    pass


class SelectionResolver:
    @staticmethod
    def resolve(expression: str, elements: list[str]) -> tuple[int, ...]:
        total_atoms = len(elements)
        text = str(expression or "").strip()
        if not text:
            return tuple(range(1, total_atoms + 1))
        selected: set[int] = set()
        known_elements = set(elements)
        for token in (part for part in re.split(r"[,\s]+", text) if part):
            if re.fullmatch(r"\d+-\d+", token):
                start, end = map(int, token.split("-", 1))
                if start > end:
                    raise SelectionError(f"原子范围不能倒序: {token}")
                if start < 1 or end > total_atoms:
                    raise SelectionError(f"原子编号超出有效范围 1-{total_atoms}: {token}")
                selected.update(range(start, end + 1))
            elif token.isdigit():
                atom_id = int(token)
                if atom_id < 1 or atom_id > total_atoms:
                    raise SelectionError(f"原子编号超出有效范围 1-{total_atoms}: {token}")
                selected.add(atom_id)
            else:
                if token not in known_elements:
                    raise SelectionError(f"未知元素: {token}")
                selected.update(i for i, element in enumerate(elements, 1) if element == token)
        if not selected:
            raise SelectionError(f"表达式未匹配任何原子: {text}")
        return tuple(sorted(selected))
```

In `core/calculator.py`, import these types, set `TargetSelectionError = SelectionError`, and make `parse_target_atoms()` return `list(SelectionResolver.resolve(target_str, elements))`. Remove its duplicate parser body.

- [ ] **Step 4: Run parser and calculator regressions**

Run: `pytest tests/test_selection.py tests/test_charge_aggregation.py -q`

Expected: all pass and old imports of `TargetSelectionError` still work.

- [ ] **Step 5: Commit**

```powershell
git add core/selection.py core/calculator.py tests/test_selection.py tests/test_charge_aggregation.py
git commit -m "refactor: centralize atom selection parsing"
```

### Task 2: Add atomic sessions and projections

**Files:**
- Create: `core/analysis_session.py`
- Create: `tests/test_analysis_session.py`

- [ ] **Step 1: Write failing session tests**

```python
import pandas as pd
import pytest
from core.analysis_session import AnalysisSessionStore
from core.selection import SelectionError


def payload():
    return {"df": pd.DataFrame({
        "Atom": [1, 2, 3, 4], "Element": ["Li", "O", "O", "S"],
        "Bader_Charge": [0.2, -0.3, 0.5, -0.1],
    }), "struct": object(), "source_revision": "source-1"}


def test_draft_does_not_change_committed_projection():
    store = AnalysisSessionStore()
    store.put_full_result("ws", payload())
    store.commit_scopes({"ws": "2-3"})
    store.set_draft("ws", "4")
    assert store.session("ws").committed_scope == "2-3"
    assert store.projected_df("ws")["Atom"].tolist() == [2, 3]


def test_batch_commit_is_atomic_when_one_scope_is_invalid():
    store = AnalysisSessionStore()
    store.put_full_result("ws1", payload())
    store.put_full_result("ws2", payload())
    store.commit_scopes({"ws1": "1", "ws2": "2"})
    with pytest.raises(SelectionError):
        store.commit_scopes({"ws1": "3", "ws2": "99"})
    assert store.session("ws1").selected_atom_ids == (1,)
    assert store.session("ws2").selected_atom_ids == (2,)


def test_full_result_remains_available_outside_scope():
    store = AnalysisSessionStore()
    store.put_full_result("ws", payload())
    store.commit_scopes({"ws": "4"})
    assert store.projected_df("ws")["Atom"].tolist() == [4]
    assert store.full_df("ws")["Atom"].tolist() == [1, 2, 3, 4]
```

- [ ] **Step 2: Run and verify missing-module failure**

Run: `pytest tests/test_analysis_session.py -q`

Expected: collection fails because `core.analysis_session` is absent.

- [ ] **Step 3: Implement immutable state and two-phase commit**

```python
from dataclasses import dataclass, replace
from typing import Any, Mapping
import pandas as pd
from core.selection import SelectionResolver


@dataclass(frozen=True)
class AnalysisSession:
    workspace_id: str
    source_revision: str
    structure_revision: str
    full_result: pd.DataFrame
    structure: Any
    draft_scope: str = ""
    committed_scope: str = ""
    selected_atom_ids: tuple[int, ...] = ()
    analysis_revision: int = 0


class AnalysisProjection:
    @staticmethod
    def dataframe(session: AnalysisSession) -> pd.DataFrame:
        return session.full_result[
            session.full_result["Atom"].isin(session.selected_atom_ids)
        ].copy()


class AnalysisSessionStore:
    def __init__(self):
        self._sessions = {}

    def put_full_result(self, workspace_id, payload):
        df = payload["df"]
        old = self._sessions.get(workspace_id)
        scope = old.committed_scope if old else ""
        ids = SelectionResolver.resolve(scope, df.sort_values("Atom")["Element"].astype(str).tolist())
        session = AnalysisSession(
            workspace_id=workspace_id,
            source_revision=str(payload.get("source_revision", "")),
            structure_revision=str(payload.get("structure_revision", payload.get("source_revision", ""))),
            full_result=df,
            structure=payload.get("struct"),
            draft_scope=old.draft_scope if old else scope,
            committed_scope=scope,
            selected_atom_ids=ids,
            analysis_revision=old.analysis_revision if old else 0,
        )
        self._sessions[workspace_id] = session
        return session

    def session(self, workspace_id):
        return self._sessions[workspace_id]

    def set_draft(self, workspace_id, expression):
        current = self.session(workspace_id)
        self._sessions[workspace_id] = replace(current, draft_scope=str(expression or "").strip())

    def commit_scopes(self, scopes: Mapping[str, str]):
        resolved = {}
        for workspace_id, expression in scopes.items():
            current = self.session(workspace_id)
            elements = current.full_result.sort_values("Atom")["Element"].astype(str).tolist()
            text = str(expression or "").strip()
            resolved[workspace_id] = (text, SelectionResolver.resolve(text, elements))
        committed = {}
        for workspace_id, (text, ids) in resolved.items():
            current = self.session(workspace_id)
            committed[workspace_id] = replace(current, draft_scope=text,
                committed_scope=text, selected_atom_ids=ids,
                analysis_revision=current.analysis_revision + 1)
        self._sessions.update(committed)
        return committed

    def full_df(self, workspace_id):
        return self.session(workspace_id).full_result

    def projected_df(self, workspace_id):
        return AnalysisProjection.dataframe(self.session(workspace_id))
```

- [ ] **Step 4: Run session tests**

Run: `pytest tests/test_analysis_session.py -q`

Expected: all pass, including rollback.

- [ ] **Step 5: Commit**

```powershell
git add core/analysis_session.py tests/test_analysis_session.py
git commit -m "feat: add atomic analysis sessions"
```

### Task 3: Add stable source revisions and persisted metadata

**Files:**
- Create: `core/source_revision.py`
- Create: `tests/test_source_revision.py`
- Modify: `core/workspace_manager.py`
- Modify: `tests/test_workspace_files_and_fragments.py`

- [ ] **Step 1: Write failing fingerprint tests**

```python
from core.source_revision import SourceRevision


def test_structure_content_change_invalidates_geometry(tmp_path):
    for name, content in (("CONTCAR", "a"), ("ACF.dat", "acf"), ("POTCAR", "p")):
        (tmp_path / name).write_text(content, encoding="utf-8")
    first = SourceRevision.from_workspace(tmp_path)
    (tmp_path / "CONTCAR").write_text("b", encoding="utf-8")
    second = SourceRevision.from_workspace(tmp_path)
    assert first.structure_fingerprint != second.structure_fingerprint
    assert first.source_fingerprint != second.source_fingerprint


def test_acf_change_preserves_geometry_revision(tmp_path):
    for name, content in (("POSCAR", "s"), ("ACF.dat", "a"), ("POTCAR", "p")):
        (tmp_path / name).write_text(content, encoding="utf-8")
    first = SourceRevision.from_workspace(tmp_path)
    (tmp_path / "ACF.dat").write_text("b", encoding="utf-8")
    second = SourceRevision.from_workspace(tmp_path)
    assert first.structure_fingerprint == second.structure_fingerprint
    assert first.source_fingerprint != second.source_fingerprint
```

Add this workspace test:

```python
def test_workspace_persists_committed_analysis_metadata(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.create_workspace("ws")
    manager.save_analysis_metadata("ws", "72-74", 3, "source-hash")
    assert manager.get_analysis_metadata("ws") == {
        "committed_scope": "72-74",
        "analysis_revision": 3,
        "source_revision": "source-hash",
    }
```

- [ ] **Step 2: Run and verify missing APIs**

Run: `pytest tests/test_source_revision.py tests/test_workspace_files_and_fragments.py -q`

Expected: failures report missing `SourceRevision` and workspace metadata methods.

- [ ] **Step 3: Implement SHA-256 revisions and metadata persistence**

```python
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


def _fingerprint(path):
    path = Path(path)
    if not path.exists():
        return "missing"
    stat = path.stat()
    return f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{sha256(path.read_bytes()).hexdigest()}"


@dataclass(frozen=True)
class SourceRevision:
    structure_fingerprint: str
    source_fingerprint: str

    @classmethod
    def from_workspace(cls, workspace_path):
        root = Path(workspace_path)
        structure = root / "CONTCAR" if (root / "CONTCAR").exists() else root / "POSCAR"
        structure_fp = _fingerprint(structure)
        joined = "|".join((structure_fp, _fingerprint(root / "ACF.dat"), _fingerprint(root / "POTCAR")))
        return cls(structure_fp, sha256(joined.encode("utf-8")).hexdigest())
```

Add `analysis_scope`, `analysis_revision`, and `source_revision` defaults in `_with_default_meta()`, plus normalized `save_analysis_metadata()` and `get_analysis_metadata()` methods.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_source_revision.py tests/test_workspace_files_and_fragments.py -q`

Expected: all pass and ACF-only changes preserve geometry revision.

- [ ] **Step 5: Commit**

```powershell
git add core/source_revision.py core/workspace_manager.py tests/test_source_revision.py tests/test_workspace_files_and_fragments.py
git commit -m "feat: persist versioned analysis metadata"
```

### Task 4: Make plot and aggregation projections scope-aware

**Files:**
- Modify: `core/calculator.py`
- Modify: `gui/plot_panel.py`
- Modify: `tests/test_charge_aggregation.py`
- Modify: `tests/test_plot_data_levels.py`

- [ ] **Step 1: Write failing projection tests**

```python
def test_prepare_plot_data_filters_atom_and_element_but_not_fragments(charge_df):
    data = {"ws1": {"df": charge_df, "struct": None}}
    selected = {"ws1": (2, 3)}
    atoms = ChargeCalculator.prepare_plot_data(data, level="atom", selected_by_workspace=selected)
    elements = ChargeCalculator.prepare_plot_data(
        data, level="element", metric="sum", selected_by_workspace=selected)
    fragments = ChargeCalculator.prepare_plot_data(
        data, level="fragment", fragments={"ws1": {"outside": "1,4"}},
        selected_by_workspace=selected)
    assert atoms["ws1"]["df"]["Atom"].tolist() == [2, 3]
    assert elements["ws1"]["df"].set_index("Atom").loc["O", "Bader_Charge"] == pytest.approx(0.2)
    assert fragments["ws1"]["df"].iloc[0]["Bader_Charge"] == pytest.approx(0.1)
```

Add this `PlotPanel` test:

```python
def test_plot_panel_uses_selected_ids_without_parsing_text(monkeypatch):
    app()
    panel = PlotPanel()
    monkeypatch.setattr(panel, "apply_styles", lambda: None)
    data = {"ws": {"df": pd.DataFrame({
        "Atom": [1, 2, 3], "Element": ["Li", "O", "O"],
        "Bader_Charge": [0.1, -0.2, 0.3],
    }), "struct": None}}
    panel.plot_data(data, selected_by_workspace={"ws": (2, 3)})
    assert panel.current_data["ws"]["df"]["Atom"].tolist() == [2, 3]
    panel.close()
```

- [ ] **Step 2: Run and verify signature failures**

Run: `pytest tests/test_charge_aggregation.py tests/test_plot_data_levels.py -q`

Expected: failures report unexpected keyword `selected_by_workspace`.

- [ ] **Step 3: Replace target strings with resolved IDs**

Change `ChargeCalculator.prepare_plot_data()` to accept `selected_by_workspace=None`. Use:

```python
selected_ids = (selected_by_workspace or {}).get(workspace)
scoped_df = df if selected_ids is None else df[df["Atom"].isin(selected_ids)]
if level == "atom":
    plot_df = scoped_df.copy()
elif level == "element":
    grouped = scoped_df.groupby("Element")["Bader_Charge"]
elif level == "fragment":
    stats = ChargeCalculator.aggregate_charge(df, expression)
```

Change `PlotPanel.plot_data()` and `set_analysis_context()` to store `_selected_by_workspace`; remove `_target_expression` parsing from the plot path.

- [ ] **Step 4: Run plot regressions**

Run: `pytest tests/test_charge_aggregation.py tests/test_plot_data_levels.py tests/test_boxplot_rendering.py -q`

Expected: all pass; fragment values may come from outside the target scope.

- [ ] **Step 5: Commit**

```powershell
git add core/calculator.py gui/plot_panel.py tests/test_charge_aggregation.py tests/test_plot_data_levels.py
git commit -m "feat: apply committed scope to plot projections"
```

### Task 5: Convert the analysis panel from live filtering to draft/commit UI

**Files:**
- Modify: `gui/analysis_panel.py`
- Modify: `gui/analysis_dialogs.py`
- Modify: `tests/test_analysis_panel_multi_targets.py`
- Modify: `tests/test_analysis_dialogs.py`

- [ ] **Step 1: Write failing UI-state tests**

```python
def test_target_edit_marks_draft_without_emitting_calculation():
    app()
    panel = AnalysisPanel()
    calculations = []
    panel.request_calculation.connect(calculations.append)
    panel.set_committed_scope("72-74", 3)
    panel.line_target.setText("65-68")
    assert calculations == []
    assert panel.lbl_target_scope.text() == "当前生效：72-74（3 个原子）\n有未应用更改"
    assert panel.btn_calc.text().strip() == "应用范围并分析"


def test_use_all_atoms_only_changes_draft():
    app()
    panel = AnalysisPanel()
    panel.set_committed_scope("72-74", 3)
    panel.use_all_atoms()
    assert panel.line_target.text() == ""
    assert "有未应用更改" in panel.lbl_target_scope.text()


def test_fragments_do_not_gate_calculation():
    app()
    panel = AnalysisPanel()
    panel.update_file_status("ws", ["ACF.dat", "CONTCAR", "POTCAR"])
    panel.set_fragments({})
    assert panel.btn_calc.isEnabled() is True
    assert "可选" in panel.lbl_fragment_summary.text()
```

Add this dialog test:

```python
def test_target_dialog_preserves_default_override_and_counts():
    app()
    original = {"ws2": "70-72"}
    dialog = WorkspaceTargetDialog(
        ["ws1", "ws2"], original, default_target="72-74",
        resolver=lambda workspace, text: 3 if text else 74)
    assert dialog.targets() == {"ws1": "72-74", "ws2": "70-72"}
    assert [dialog.table.item(row, 2).text() for row in range(2)] == ["3", "3"]
    assert original == {"ws2": "70-72"}
```

- [ ] **Step 2: Run and verify missing UI APIs**

Run: `pytest tests/test_analysis_panel_multi_targets.py tests/test_analysis_dialogs.py -q`

Expected: failures mention `set_committed_scope()` and `use_all_atoms()`.

- [ ] **Step 3: Implement explicit draft and committed UI state**

```python
draft_scope_changed = Signal(str)
request_export_full_csv = Signal()

def set_committed_scope(self, expression, atom_count):
    self._committed_scope = str(expression or "").strip()
    self._committed_atom_count = int(atom_count)
    self._refresh_scope_state()

def _on_target_edited(self, text):
    self.draft_scope_changed.emit(text.strip())
    self._refresh_scope_state()

def use_all_atoms(self):
    self.line_target.clear()

def _refresh_scope_state(self):
    committed = self._committed_scope or "全部原子"
    dirty = self.line_target.text().strip() != self._committed_scope
    suffix = "\n有未应用更改" if dirty else ""
    self.lbl_target_scope.setText(
        f"当前生效：{committed}（{self._committed_atom_count} 个原子）{suffix}")
    self.btn_calc.setText(" 应用范围并分析" if dirty else " 重新分析")
```

Connect `line_target.textChanged` only to `_on_target_edited`. Add “使用全部原子” and “导出完整原始结果” buttons. Put fragments under “高级分析（可选）”. Update `WorkspaceTargetDialog` with a public default, override column, and resolved-count/status column populated through a callback from `MainWindow`.

- [ ] **Step 4: Run UI regressions**

Run: `pytest tests/test_analysis_panel_multi_targets.py tests/test_analysis_dialogs.py tests/test_ui_text_encoding.py -q`

Expected: all pass with readable Chinese labels.

- [ ] **Step 5: Commit**

```powershell
git add gui/analysis_panel.py gui/analysis_dialogs.py tests/test_analysis_panel_multi_targets.py tests/test_analysis_dialogs.py
git commit -m "feat: make analysis scope an explicit commit"
```

### Task 6: Orchestrate sessions across tables, statistics, plots, and exports

**Files:**
- Modify: `gui/main_window.py`
- Create: `tests/test_analysis_scope_integration.py`
- Modify: `tests/test_multi_compare_alignment.py`
- Modify: `tests/test_workspace_tree_interactions.py`

- [ ] **Step 1: Write failing cross-view tests**

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pandas as pd
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow


def app():
    return QApplication.instance() or QApplication([])


def frame():
    return pd.DataFrame({
        "Atom": [1, 2, 3], "Element": ["Li", "O", "S"], "ZVAL": [1., 6., 6.],
        "X": [0., 1., 2.], "Y": [0., 1., 2.], "Z": [0., 1., 2.],
        "Bader_Charge": [0.1, -0.2, 0.3],
    })


def test_draft_edit_does_not_refresh_visible_table():
    app()
    window = MainWindow()
    window.current_ws = "ws"
    window.session_store.put_full_result("ws", {"df": frame(), "struct": None, "source_revision": "1"})
    window.session_store.commit_scopes({"ws": "1-2"})
    window._refresh_committed_views(["ws"])
    window.analysis_panel_plot.line_target.setText("3")
    assert [window.tab_data.item(r, 0).text() for r in range(window.tab_data.rowCount())] == ["1", "2"]
    window.close()


def test_committed_scope_updates_every_projection():
    app()
    window = MainWindow()
    window.current_ws = "ws"
    window.selected_workspaces = ["ws"]
    window.session_store.put_full_result("ws", {"df": frame(), "struct": None, "source_revision": "1"})
    window._commit_scope_and_refresh({"ws": "2-3"})
    assert window.current_df["Atom"].tolist() == [2, 3]
    assert window.plot_panel._selected_by_workspace == {"ws": (2, 3)}
    assert window._current_export_df()["Atom"].tolist() == [2, 3]
    window.close()
```

Extend multi-compare coverage with different selected-ID subsets and assert union alignment by `Atom`, with missing cells shown as `NaN`/`—`.

- [ ] **Step 2: Run and verify orchestration failures**

Run: `pytest tests/test_analysis_scope_integration.py tests/test_multi_compare_alignment.py tests/test_workspace_tree_interactions.py -q`

Expected: missing `session_store`, `_refresh_committed_views()`, and `_commit_scope_and_refresh()`.

- [ ] **Step 3: Integrate the session store and atomic batch staging**

Add `self.session_store = AnalysisSessionStore()` but retain `all_calculated_data` as a temporary compatibility view. Remove `line_target.textChanged -> _on_target_filter_changed`.

Implement:

```python
def _selected_ids_by_workspace(self, names):
    return {name: self.session_store.session(name).selected_atom_ids for name in names}

def _commit_scope_and_refresh(self, scopes):
    committed = self.session_store.commit_scopes(scopes)
    for name, session in committed.items():
        self.ws_mgr.save_analysis_metadata(
            name, session.committed_scope, session.analysis_revision, session.source_revision)
    self._refresh_committed_views(list(committed))

def _refresh_committed_views(self, names):
    current = self.current_ws if self.current_ws in names else names[0]
    self.current_df = self.session_store.projected_df(current)
    self.update_table_view(self.current_df)
    selected = self._selected_ids_by_workspace(names)
    full_data = {name: {"df": self.session_store.full_df(name),
                        "struct": self.session_store.session(name).structure}
                 for name in names}
    self.plot_panel.plot_data(full_data, selected_by_workspace=selected,
                              fragments=self._fragment_expressions_for_workspaces(names))
    self._rebuild_multi_compare()
    self._update_element_summary()
    self._refresh_fragment_results()
    self._request_3d_appearance_update(names)
```

Stage batch worker payloads in a pending dictionary. Do not call `commit_scopes()` or refresh visible views until every worker succeeds. If any fails, retain prior sessions. On success, `put_full_result()` for each payload, then commit the entire scope map once.

Make `_rebuild_multi_compare()` consume projected DataFrames and `_build_multi_compare_df()`; remove row-position `iloc` alignment.

- [ ] **Step 4: Add scoped and full-result exports**

Make `export_csv()` use `_current_export_df()` from the session projection. Add `export_full_csv()` from `session_store.full_df(current_ws)`. Wire `request_export_full_csv`; use filenames `bader_charge_scope.csv` and `bader_charge_full.csv`.

- [ ] **Step 5: Run integrated regressions**

Run: `pytest tests/test_analysis_session.py tests/test_analysis_scope_integration.py tests/test_multi_compare_alignment.py tests/test_workspace_tree_interactions.py tests/test_worker_full_results.py tests/test_plot_data_levels.py -q`

Expected: all pass; worker output stays full while visible projections use committed IDs.

- [ ] **Step 6: Commit**

```powershell
git add gui/main_window.py tests/test_analysis_scope_integration.py tests/test_multi_compare_alignment.py tests/test_workspace_tree_interactions.py
git commit -m "feat: synchronize committed scope across views"
```

### Task 7: Separate 3D geometry from charge appearance

**Files:**
- Modify: `core/structure_model.py`
- Modify: `rendering/pyvista_structure_renderer.py`
- Modify: `rendering/charge_color_mapper.py`
- Modify: `tests/test_structure_model.py`
- Modify: `tests/test_pyvista_structure_renderer.py`
- Modify: `tests/test_charge_color_mapper.py`

- [ ] **Step 1: Write failing target-color and zero-rebuild tests**

Make `FakePlotter.add_mesh()` return a `FakeActor` with mutable `prop.color`, `prop.opacity`, and `prop.ambient`. Add:

```python
def test_charge_mapper_uses_only_target_atom_charges():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)
    model = make_model()
    renderer.build_geometry(model, RenderSettings(show_bonds=False, show_cell=False))
    renderer.update_appearance(model, RenderSettings(
        visible_atom_ids={1}, color_by="Bader Charge",
        show_bonds=False, show_cell=False))
    assert renderer.last_charge_clim == pytest.approx((-0.6, 0.6))
    assert renderer.atom_actors[1].prop.color != renderer.atom_actors[2].prop.color


def test_appearance_update_does_not_rebuild_geometry():
    plotter = FakePlotter()
    renderer = PyVistaStructureRenderer(plotter)
    model = make_model()
    renderer.build_geometry(model, RenderSettings(show_bonds=False, show_cell=False))
    clears, mesh_count = plotter.clears, len(plotter.meshes)
    renderer.update_appearance(model, RenderSettings(
        visible_atom_ids={2}, color_by="Bader Charge",
        show_bonds=False, show_cell=False))
    assert plotter.clears == clears
    assert len(plotter.meshes) == mesh_count
```

Add this structure-model test:

```python
def test_with_charges_preserves_geometry_and_bonds():
    model = make_model()
    updated = model.with_charges(pd.DataFrame({
        "Atom": [1, 2], "Bader_Charge": [-0.1, 0.8],
        "CHARGE": [5.9, 5.8], "ZVAL": [6.0, 5.0],
    }))
    assert updated.lattice_matrix == model.lattice_matrix
    assert updated.bonds == model.bonds
    assert [atom.cart_coords for atom in updated.atoms] == [atom.cart_coords for atom in model.atoms]
    assert [atom.charge for atom in updated.atoms] == [-0.1, 0.8]
```

- [ ] **Step 2: Run and verify missing renderer APIs**

Run: `pytest tests/test_structure_model.py tests/test_pyvista_structure_renderer.py tests/test_charge_color_mapper.py -q`

Expected: missing `build_geometry()`, `update_appearance()`, `atom_actors`, and `with_charges()`.

- [ ] **Step 3: Implement charge replacement and actor updates**

Add `Structure3D.with_charges(df)` using `dataclasses.replace()` on atoms and preserving lattice and bonds.

Retain these renderer fields:

```python
self.atom_actors: dict[int, Any] = {}
self.bond_actors: list[Any] = []
self.cell_actors: list[Any] = []
self.last_charge_clim = (-1.0, 1.0)
```

`build_geometry()` clears once, creates meshes/actors, and records them. `update_appearance()` constructs `ChargeColorMapper` from target atoms only and updates actor properties in place. In Bader mode, target atoms use charge colors while non-target atoms keep the current structure-context treatment: element base color plus the existing background-opacity rule. Recreate only labels/scalar-bar actors when needed. Keep compatibility:

```python
def render(self, model, settings):
    self.build_geometry(model, settings)
    self.update_appearance(model, settings)
```

- [ ] **Step 4: Run renderer and smoke tests**

Run: `pytest tests/test_structure_model.py tests/test_pyvista_structure_renderer.py tests/test_charge_color_mapper.py tests/test_3d_renderer_smoke.py -q`

Expected: unit tests pass; offscreen smoke may skip only for its documented OpenGL limitation.

- [ ] **Step 5: Commit**

```powershell
git add core/structure_model.py rendering/pyvista_structure_renderer.py rendering/charge_color_mapper.py tests/test_structure_model.py tests/test_pyvista_structure_renderer.py tests/test_charge_color_mapper.py
git commit -m "refactor: split 3d geometry and appearance"
```

### Task 8: Add version-safe 3D caching and zero-work tab switching

**Files:**
- Create: `rendering/scene_cache.py`
- Create: `tests/test_scene_cache.py`
- Modify: `gui/visualizer_3d.py`
- Modify: `gui/main_window.py`
- Modify: `gui/analysis_panel.py`
- Modify: `tests/test_performance_guards.py`

- [ ] **Step 1: Write failing cache and LRU tests**

```python
from rendering.scene_cache import AppearanceKey, GeometryKey, SceneCache


def test_cache_never_reuses_geometry_across_workspaces():
    cache = SceneCache(capacity=6)
    a = GeometryKey("ws-a", "structure", 3, ("Li", "O", "S"))
    b = GeometryKey("ws-b", "structure", 3, ("Li", "O", "S"))
    cache.remember_geometry(a, object())
    assert cache.geometry(a) is not None
    assert cache.geometry(b) is None


def test_appearance_revision_does_not_invalidate_geometry():
    cache = SceneCache(capacity=6)
    key = GeometryKey("ws", "structure", 3, ("Li", "O", "S"))
    scene = object()
    cache.remember_geometry(key, scene)
    cache.remember_appearance("ws", AppearanceKey(2, (2, 3), "charge-2", ("RdBu_r",)))
    assert cache.geometry(key) is scene


def test_lru_evicts_only_hidden_workspace():
    released = []
    cache = SceneCache(capacity=2, release=released.append)
    for name in ("a", "b"):
        cache.remember_geometry(GeometryKey(name, name, 1, ("H",)), name)
    cache.set_visible({"b"})
    cache.remember_geometry(GeometryKey("c", "c", 1, ("H",)), "c")
    assert released == ["a"]
```

Extend performance tests:

```python
def test_reentering_3d_tab_does_not_sync_when_clean(monkeypatch):
    app()
    window = MainWindow()
    window._3d_loaded = True
    window._has_3d = True
    calls = []
    monkeypatch.setattr(window, "_sync_3d_workspaces", lambda: calls.append("sync"))
    window._3d_dirty = False
    window.on_tab_changed(2)
    window.on_tab_changed(0)
    window.on_tab_changed(2)
    assert calls == []
    window.close()


def test_scope_change_updates_appearance_without_geometry_reload(monkeypatch):
    app()
    panel = MultiVisualizer3DPanel()
    visualizer = DummyVisualizer()
    visualizer.appearance_updates = []
    visualizer.update_appearance = lambda *args: visualizer.appearance_updates.append(args)
    monkeypatch.setattr(panel, "_create_tile", lambda _workspace: {
        "frame": QFrame(), "visualizer": visualizer,
        "button": QPushButton(), "geometry_key": None, "appearance_key": None})
    base = {"ws": {"struct": object(), "df": object(),
                   "structure_fingerprint": "s", "analysis_revision": 1,
                   "selected_atom_ids": (1,)}}
    panel.set_workspaces_data(base, ["ws"])
    changed = {"ws": dict(base["ws"], analysis_revision=2, selected_atom_ids=(2,))}
    panel.set_workspaces_data(changed, ["ws"])
    assert len(visualizer.loads) == 1
    assert len(visualizer.appearance_updates) == 1
    panel.close()
```

- [ ] **Step 2: Run and verify failures**

Run: `pytest tests/test_scene_cache.py tests/test_performance_guards.py -q`

Expected: missing scene-cache classes and forced tab sync failure.

- [ ] **Step 3: Implement pure keys and six-entry LRU**

```python
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable


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
    charge_revision: str
    render_settings: tuple[Any, ...]


class SceneCache:
    def __init__(self, capacity=6, release: Callable[[Any], None] | None = None):
        self.capacity = capacity
        self.release = release or (lambda scene: None)
        self._geometry, self._appearance, self._visible = OrderedDict(), {}, set()

    def set_visible(self, workspace_ids):
        self._visible = set(workspace_ids)

    def remember_geometry(self, key, scene):
        self._geometry[key] = scene
        self._geometry.move_to_end(key)
        while len(self._geometry) > self.capacity:
            candidate = next((k for k in self._geometry if k.workspace_id not in self._visible), None)
            if candidate is None:
                break
            self.release(self._geometry.pop(candidate))

    def geometry(self, key):
        scene = self._geometry.get(key)
        if scene is not None:
            self._geometry.move_to_end(key)
        return scene

    def remember_appearance(self, workspace_id, key):
        self._appearance[workspace_id] = key

    def appearance(self, workspace_id):
        return self._appearance.get(workspace_id)

    def invalidate_workspace(self, workspace_id):
        for key in [k for k in self._geometry if k.workspace_id == workspace_id]:
            self.release(self._geometry.pop(key))
        self._appearance.pop(workspace_id, None)
```

- [ ] **Step 4: Wire semantic keys and clean tab entry**

Pass structure fingerprint, analysis revision, selected IDs, and source revision from sessions to `MultiVisualizer3DPanel`. Rebuild only for a changed `GeometryKey`; call `update_appearance()` only for a changed `AppearanceKey`. Remove the hard-coded empty `target_str` from `AnalysisPanel3D`; session-selected IDs are authoritative.

Change tab handling to:

```python
def on_tab_changed(self, index):
    if index == 2:
        self._ensure_3d_loaded()
        if self._3d_dirty:
            self._request_3d_sync(force=True)
    self.center_stack.setCurrentIndex(index)
    self.right_stack.setCurrentIndex(0 if index in (0, 1) else 1)
```

Successful scope changes with unchanged structure use only the appearance path. Workspace selection or structure revision changes mark geometry dirty. Preserve camera, selection, and maximized tile state.

- [ ] **Step 5: Run cache and 3D regressions**

Run: `pytest tests/test_scene_cache.py tests/test_performance_guards.py tests/test_pyvista_structure_renderer.py tests/test_3d_renderer_smoke.py tests/test_workspace_tree_interactions.py -q`

Expected: all unit tests pass; clean 3D re-entry performs zero sync calls.

- [ ] **Step 6: Commit**

```powershell
git add rendering/scene_cache.py gui/visualizer_3d.py gui/main_window.py gui/analysis_panel.py tests/test_scene_cache.py tests/test_performance_guards.py tests/test_workspace_tree_interactions.py
git commit -m "feat: cache versioned 3d scenes per workspace"
```

### Task 9: Complete v0.2.0 metadata and release verification

**Files:**
- Modify: `installer/setup.iss`
- Modify: `installer/build_windows.ps1`
- Modify: `README.md`
- Create: `docs/releases/v0.2.0.md`
- Create: `tests/test_release_version.py`

- [ ] **Step 1: Write the version consistency test**

```python
from pathlib import Path


def test_v020_version_is_consistent():
    root = Path(__file__).resolve().parents[1]
    assert '#define AppVersion    "0.2.0"' in (root / "installer/setup.iss").read_text(encoding="utf-8")
    assert "BaderChargeAnalyzer_Setup_v0.2.0.exe" in (root / "installer/build_windows.ps1").read_text(encoding="utf-8")
    assert "v0.2.0" in (root / "README.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run and verify old-version failure**

Run: `pytest tests/test_release_version.py -q`

Expected: FAIL because installer/build metadata still says `0.1.2`.

- [ ] **Step 3: Update metadata and release notes**

Set installer and build output to `0.2.0`, update README examples, and add `docs/releases/v0.2.0.md` covering committed scope, optional fragments, scoped/full exports, target-only 3D color normalization, cache behavior, and migration of old `results.json`/workspace state.

- [ ] **Step 4: Run focused suites**

Run: `pytest tests/test_selection.py tests/test_analysis_session.py tests/test_source_revision.py tests/test_analysis_scope_integration.py tests/test_plot_data_levels.py tests/test_multi_compare_alignment.py tests/test_scene_cache.py tests/test_performance_guards.py tests/test_pyvista_structure_renderer.py -q`

Expected: all focused tests pass without unexpected skips.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`

Expected: all pass; only documented offscreen VTK skips are allowed.

- [ ] **Step 6: Perform manual v0.2.0 acceptance**

Run: `python main.py`

Verify:

1. Blank target and no fragments analyze all 74 atoms.
2. Typing `72-74` changes no view before clicking the button.
3. Applying it makes table, summary, plots, and scoped CSV contain exactly 72–74.
4. 3D retains the full structure but normalizes Bader colors only from 72–74.
5. Table → plot → 3D → table → 3D returns immediately with the same camera.
6. Applying `65-68` updates colors without rebuilding geometry/bonds.
7. Switching systems shows each correct structure and restores its own cache.
8. Replacing a structure file rebuilds only that workspace geometry.
9. A fragment outside the target range still calculates.
10. Scoped and full CSV exports have the expected different row counts.

- [ ] **Step 7: Commit release metadata**

```powershell
git add installer/setup.iss installer/build_windows.ps1 README.md docs/releases/v0.2.0.md tests/test_release_version.py
git commit -m "chore: prepare v0.2.0 release"
```

- [ ] **Step 8: Review history and working tree**

Run: `git log --oneline -10` and then `git status --short`.

Expected: focused commits represent the version; no task-owned files remain uncommitted, while any unrelated pre-existing user changes remain identified and untouched.

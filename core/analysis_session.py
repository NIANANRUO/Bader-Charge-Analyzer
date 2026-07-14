"""Immutable analysis state and scoped DataFrame projections."""

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
    """Produce analysis views without mutating the stored full result."""

    @staticmethod
    def dataframe(session: AnalysisSession) -> pd.DataFrame:
        selected_rows = session.full_result["Atom"].isin(session.selected_atom_ids)
        return session.full_result.loc[selected_rows].copy()


class AnalysisSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AnalysisSession] = {}

    @staticmethod
    def _elements_for(session: AnalysisSession) -> list[str]:
        return (
            session.full_result.sort_values("Atom")["Element"]
            .astype(str)
            .tolist()
        )

    def put_full_result(
        self, workspace_id: str, payload: Mapping[str, Any]
    ) -> AnalysisSession:
        full_result = payload["df"]
        previous = self._sessions.get(workspace_id)
        committed_scope = previous.committed_scope if previous else ""
        elements = (
            full_result.sort_values("Atom")["Element"].astype(str).tolist()
        )
        selected_atom_ids = SelectionResolver.resolve(committed_scope, elements)
        source_revision = str(payload.get("source_revision", ""))

        session = AnalysisSession(
            workspace_id=workspace_id,
            source_revision=source_revision,
            structure_revision=str(
                payload.get("structure_revision", source_revision)
            ),
            full_result=full_result,
            structure=payload.get("struct"),
            draft_scope=previous.draft_scope if previous else committed_scope,
            committed_scope=committed_scope,
            selected_atom_ids=selected_atom_ids,
            analysis_revision=previous.analysis_revision if previous else 0,
        )
        self._sessions[workspace_id] = session
        return session

    def session(self, workspace_id: str) -> AnalysisSession:
        return self._sessions[workspace_id]

    def set_draft(self, workspace_id: str, expression: str) -> None:
        current = self.session(workspace_id)
        draft_scope = str(expression or "").strip()
        self._sessions[workspace_id] = replace(
            current, draft_scope=draft_scope
        )

    def commit_scopes(
        self, scopes: Mapping[str, str]
    ) -> dict[str, AnalysisSession]:
        resolved: dict[str, tuple[str, tuple[int, ...]]] = {}

        # Phase one only reads and validates, so any failure leaves every
        # existing session untouched.
        for workspace_id, expression in scopes.items():
            current = self.session(workspace_id)
            committed_scope = str(expression or "").strip()
            selected_atom_ids = SelectionResolver.resolve(
                committed_scope, self._elements_for(current)
            )
            resolved[workspace_id] = (committed_scope, selected_atom_ids)

        # Phase two builds all replacements before publishing them together.
        committed = {
            workspace_id: replace(
                self.session(workspace_id),
                draft_scope=committed_scope,
                committed_scope=committed_scope,
                selected_atom_ids=selected_atom_ids,
                analysis_revision=(
                    self.session(workspace_id).analysis_revision + 1
                ),
            )
            for workspace_id, (committed_scope, selected_atom_ids) in resolved.items()
        }
        self._sessions.update(committed)
        return committed

    def full_df(self, workspace_id: str) -> pd.DataFrame:
        return self.session(workspace_id).full_result

    def projected_df(self, workspace_id: str) -> pd.DataFrame:
        return AnalysisProjection.dataframe(self.session(workspace_id))

"""Immutable analysis state and scoped DataFrame projections."""

from dataclasses import dataclass, replace
from typing import Any, Mapping

import pandas as pd

from core.selection import SelectionError, SelectionResolver


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

    def _stored_session(self, workspace_id: str) -> AnalysisSession:
        return self._sessions[workspace_id]

    @staticmethod
    def _snapshot(session: AnalysisSession) -> AnalysisSession:
        return replace(session, full_result=session.full_result.copy(deep=True))

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
        full_result = payload["df"].copy(deep=True)
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
        return self._snapshot(session)

    def session(self, workspace_id: str) -> AnalysisSession:
        return self._snapshot(self._stored_session(workspace_id))

    def set_draft(self, workspace_id: str, expression: str) -> None:
        current = self._stored_session(workspace_id)
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
            current = self._stored_session(workspace_id)
            committed_scope = str(expression or "").strip()
            try:
                selected_atom_ids = SelectionResolver.resolve(
                    committed_scope, self._elements_for(current)
                )
            except SelectionError as error:
                raise SelectionError(
                    f"{workspace_id}: {committed_scope}: {error}"
                ) from error
            resolved[workspace_id] = (committed_scope, selected_atom_ids)

        # Phase two builds all replacements before publishing them together.
        committed: dict[str, AnalysisSession] = {}
        for workspace_id, (committed_scope, selected_atom_ids) in resolved.items():
            current = self._stored_session(workspace_id)
            committed[workspace_id] = replace(
                current,
                draft_scope=committed_scope,
                committed_scope=committed_scope,
                selected_atom_ids=selected_atom_ids,
                analysis_revision=current.analysis_revision + 1,
            )
        self._sessions.update(committed)
        return {
            workspace_id: self._snapshot(session)
            for workspace_id, session in committed.items()
        }

    def full_df(self, workspace_id: str) -> pd.DataFrame:
        return self._stored_session(workspace_id).full_result.copy(deep=True)

    def projected_df(self, workspace_id: str) -> pd.DataFrame:
        return AnalysisProjection.dataframe(self._stored_session(workspace_id))

    def snapshot(self) -> dict[str, AnalysisSession]:
        """Return an owned snapshot suitable for transactional rollback."""
        return {
            workspace_id: self._snapshot(session)
            for workspace_id, session in self._sessions.items()
        }

    def restore(self, snapshot: Mapping[str, AnalysisSession]) -> None:
        """Atomically replace the store with a previously owned snapshot."""
        restored = {
            workspace_id: self._snapshot(session)
            for workspace_id, session in snapshot.items()
        }
        self._sessions = restored

    def remove(self, workspace_id: str) -> None:
        self._sessions.pop(workspace_id, None)

    def put_persisted_result(
        self,
        workspace_id: str,
        payload: Mapping[str, Any],
        *,
        committed_scope: str,
        analysis_revision: int,
    ) -> AnalysisSession:
        """Hydrate a saved result without inventing a new analysis revision."""
        full_result = payload["df"].copy(deep=True)
        text = str(committed_scope or "").strip()
        elements = full_result.sort_values("Atom")["Element"].astype(str).tolist()
        selected_atom_ids = SelectionResolver.resolve(text, elements)
        source_revision = str(payload.get("source_revision", ""))
        session = AnalysisSession(
            workspace_id=workspace_id,
            source_revision=source_revision,
            structure_revision=str(
                payload.get("structure_revision", source_revision)
            ),
            full_result=full_result,
            structure=payload.get("struct"),
            draft_scope=text,
            committed_scope=text,
            selected_atom_ids=selected_atom_ids,
            analysis_revision=int(analysis_revision or 0),
        )
        self._sessions[workspace_id] = session
        return self._snapshot(session)

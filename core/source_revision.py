"""Deterministic revision fingerprints for workspace analysis inputs."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


def _digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_signature(path):
    resolved = path.resolve()
    if not path.is_file():
        return {"path": str(resolved), "missing": True}
    stat = path.stat()
    return {
        "path": str(resolved),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


@dataclass(frozen=True)
class SourceRevision:
    structure_fingerprint: str
    source_fingerprint: str

    @classmethod
    def from_workspace(cls, workspace_path):
        workspace = Path(workspace_path)
        contcar = workspace / "CONTCAR"
        structure_path = contcar if contcar.is_file() else workspace / "POSCAR"
        structure_fingerprint = _digest(_file_signature(structure_path))
        source_fingerprint = _digest(
            {
                "structure": structure_fingerprint,
                "acf": _file_signature(workspace / "ACF.dat"),
                "potcar": _file_signature(workspace / "POTCAR"),
            }
        )
        return cls(structure_fingerprint, source_fingerprint)

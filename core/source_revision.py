"""Deterministic revision fingerprints for workspace analysis inputs."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path


_HASH_CHUNK_SIZE = 1024 * 1024


def _digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _hash_file_content(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _file_signature(path):
    resolved = path.resolve()
    if not path.is_file():
        return {"path": str(resolved), "missing": True}
    stat = path.stat()
    canonical_path = os.path.normcase(str(resolved))
    return {
        "path": canonical_path,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": _hash_file_content(canonical_path),
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

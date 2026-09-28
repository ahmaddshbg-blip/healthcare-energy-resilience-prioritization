"""Canonical serialization and hashing helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for analytical identities."""

    text = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return text.encode("utf-8")


def sha256_json(value: Any) -> str:
    """Return the SHA-256 identity of canonical JSON content."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 identity of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_snapshot_identity(source_files: list[dict[str, Any]]) -> str:
    """Reproduce the accepted content identity for a frozen source snapshot."""

    lines = [
        f"{item['filename']}|{item['bytes']}|{item['sha256']}"
        for item in source_files
    ]
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

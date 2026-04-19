from __future__ import annotations

import hashlib
from pathlib import Path

FINGERPRINT_SCHEMA_VERSION = "fp1"

_IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}
_IGNORED_SUFFIXES = {".pyc", ".pyo"}


def _iter_fingerprint_files(bot_dir: Path):
    for path in sorted(bot_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _IGNORED_DIRS for part in path.parts):
            continue
        if path.suffix in _IGNORED_SUFFIXES:
            continue
        if path.name.startswith("."):
            continue
        yield path


def compute_build_fingerprint(bot_dir: Path | None = None, *, short_len: int = 12) -> str:
    """Deterministic content fingerprint for deployment parity checks."""
    base = (bot_dir or Path(__file__).resolve().parent.parent).resolve()
    digest = hashlib.sha256()
    digest.update(FINGERPRINT_SCHEMA_VERSION.encode("utf-8"))
    digest.update(b"\0")
    for path in _iter_fingerprint_files(base):
        rel = path.relative_to(base).as_posix().encode("utf-8")
        digest.update(rel)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:short_len]

"""Atomic two-file output commit for the offline pre-Milestone 2 readiness
builder (DesignSuggestionLog.md, "2026-08-29 20:18 Australia/Sydney -
Suggested hardening increment: readiness integrity and contract
corrections", "Atomic pair commit").

``spatial-split-manifest.json`` and ``readiness-report.json`` are one
indivisible output pair: either both land on disk in a mutually consistent
state, or neither does. This module owns that guarantee as one independent,
typed, testable component - not as two sequential, independently-rolled-back
writes.

Algorithm (:func:`commit_pair_atomically`):

1. Guard - if not ``overwrite`` and either final path already exists, raise
   before touching anything.
2. Stage both - write each to a temp file in the destination directory,
   read it back, and verify its declared checksum. Any staging failure
   cleans up whatever temp file(s) exist so far; no final path is touched.
3. Backup - only for a final path that exists under ``overwrite``, reserve a
   unique nonexistent path and move the existing final there.
4. Commit both - move each temp file onto its final path.
5. Post-commit verify - read back both finals and call ``verify_committed``.
6. On any failure from step 3 onward: restore each final from its backup if
   one was successfully made, delete it if it was newly committed with no
   backup, or leave it untouched if neither happened yet (a backup-creation
   failure must not delete a pre-existing file it never touched).
7. Guaranteed cleanup - every temp/backup path still present on disk is
   unlinked before returning, on every success or handled-failure path.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class AtomicPairCommitError(Exception):
    """A pair-commit failure. Any partially-applied state has already been
    rolled back (or was never applied) by the time this is raised."""


@dataclass(frozen=True)
class StagedOutput:
    """One half of the pair to commit."""

    final_path: Path
    data: bytes
    sha256: str


def _reserve_unique_path(final_path: Path) -> Path:
    """Returns a guaranteed-unique, guaranteed-nonexistent path in the same
    directory as ``final_path``, suitable as an ``os.replace`` backup
    destination."""
    fd, tmp_name = tempfile.mkstemp(
        dir=final_path.parent, prefix=f".{final_path.name}.bak.", suffix=".tmp"
    )
    os.close(fd)
    path = Path(tmp_name)
    path.unlink()
    return path


def _stage(output: StagedOutput) -> Path:
    fd, tmp_name = tempfile.mkstemp(
        dir=output.final_path.parent, prefix=f".{output.final_path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(output.data)
        readback = tmp_path.read_bytes()
        if hashlib.sha256(readback).hexdigest() != output.sha256:
            raise AtomicPairCommitError(
                f"checksum verification failed while staging '{output.final_path.name}'"
            )
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path


def commit_pair_atomically(
    first: StagedOutput,
    second: StagedOutput,
    *,
    overwrite: bool,
    verify_committed: Callable[[bytes, bytes], None],
) -> None:
    """Commits ``first`` and ``second`` as one indivisible pair. Raises
    :class:`AtomicPairCommitError` and leaves no partial pair on disk if any
    step fails - see module docstring for the exact rollback semantics."""
    if not overwrite:
        existing = [
            output.final_path.name for output in (first, second) if output.final_path.exists()
        ]
        if existing:
            raise AtomicPairCommitError(
                "refusing to overwrite existing artifact(s) without overwrite: "
                + ", ".join(existing)
            )

    first_tmp = _stage(first)
    try:
        second_tmp = _stage(second)
    except Exception:
        first_tmp.unlink(missing_ok=True)
        raise

    first_backup: Path | None = None
    second_backup: Path | None = None
    first_committed = False
    second_committed = False
    try:
        if overwrite and first.final_path.exists():
            candidate = _reserve_unique_path(first.final_path)
            os.replace(first.final_path, candidate)
            first_backup = candidate
        if overwrite and second.final_path.exists():
            candidate = _reserve_unique_path(second.final_path)
            os.replace(second.final_path, candidate)
            second_backup = candidate

        os.replace(first_tmp, first.final_path)
        first_committed = True
        os.replace(second_tmp, second.final_path)
        second_committed = True

        verify_committed(first.final_path.read_bytes(), second.final_path.read_bytes())
    except Exception as exc:
        if first_backup is not None:
            os.replace(first_backup, first.final_path)
        elif first_committed:
            first.final_path.unlink(missing_ok=True)
        if second_backup is not None:
            os.replace(second_backup, second.final_path)
        elif second_committed:
            second.final_path.unlink(missing_ok=True)
        message = f"atomic pair commit failed and was rolled back: {exc}"
        raise AtomicPairCommitError(message) from exc
    finally:
        first_tmp.unlink(missing_ok=True)
        second_tmp.unlink(missing_ok=True)
        if first_backup is not None:
            first_backup.unlink(missing_ok=True)
        if second_backup is not None:
            second_backup.unlink(missing_ok=True)

"""Unit tests for the atomic two-file output commit
(experiments/atomic_output_pair.py - DesignSuggestionLog.md "Atomic pair
commit"). Uses ``tmp_path`` for real (but isolated) filesystem I/O and
``monkeypatch`` to inject ``os.replace`` failures that would otherwise
require an unreproducible disk fault.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from s3_ecological.experiments.atomic_output_pair import (
    AtomicPairCommitError,
    StagedOutput,
    commit_pair_atomically,
)


def _staged(path: Path, content: bytes) -> StagedOutput:
    return StagedOutput(final_path=path, data=content, sha256=hashlib.sha256(content).hexdigest())


def _no_op_verify(first: bytes, second: bytes) -> None:
    return None


def _files_in(directory: Path) -> set[str]:
    return {entry.name for entry in directory.iterdir()}


def test_fresh_success_writes_both_files_with_no_leftovers(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = _staged(first_path, b"first-content")
    second = _staged(second_path, b"second-content")

    verified: list[tuple[bytes, bytes]] = []
    commit_pair_atomically(
        first, second, overwrite=False, verify_committed=lambda a, b: verified.append((a, b))
    )

    assert first_path.read_bytes() == b"first-content"
    assert second_path.read_bytes() == b"second-content"
    assert verified == [(b"first-content", b"second-content")]
    assert _files_in(tmp_path) == {"first.json", "second.json"}


def test_refuses_to_overwrite_existing_without_overwrite_flag_before_staging(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_path.write_bytes(b"old-first")
    first = _staged(first_path, b"new-first")
    second = _staged(second_path, b"new-second")

    with pytest.raises(AtomicPairCommitError, match="overwrite"):
        commit_pair_atomically(first, second, overwrite=False, verify_committed=_no_op_verify)

    # Nothing was staged - only the pre-existing first.json remains untouched.
    assert _files_in(tmp_path) == {"first.json"}
    assert first_path.read_bytes() == b"old-first"


def test_overwrite_success_replaces_both_files_with_no_leftovers(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_path.write_bytes(b"old-first")
    second_path.write_bytes(b"old-second")
    first = _staged(first_path, b"new-first")
    second = _staged(second_path, b"new-second")

    commit_pair_atomically(first, second, overwrite=True, verify_committed=_no_op_verify)

    assert first_path.read_bytes() == b"new-first"
    assert second_path.read_bytes() == b"new-second"
    assert _files_in(tmp_path) == {"first.json", "second.json"}


def test_staging_failure_on_first_file_touches_no_finals_and_leaves_no_temp(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = StagedOutput(final_path=first_path, data=b"content", sha256="0" * 64)
    second = _staged(second_path, b"second-content")

    with pytest.raises(AtomicPairCommitError, match="checksum verification failed"):
        commit_pair_atomically(first, second, overwrite=False, verify_committed=_no_op_verify)

    assert _files_in(tmp_path) == set()


def test_staging_failure_on_second_file_cleans_up_first_temp_and_touches_no_finals(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = _staged(first_path, b"first-content")
    second = StagedOutput(final_path=second_path, data=b"content", sha256="0" * 64)

    with pytest.raises(AtomicPairCommitError, match="checksum verification failed"):
        commit_pair_atomically(first, second, overwrite=False, verify_committed=_no_op_verify)

    assert _files_in(tmp_path) == set()


def test_second_replace_failure_in_new_directory_removes_first_with_no_leftovers(
    tmp_path, monkeypatch
):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = _staged(first_path, b"first-content")
    second = _staged(second_path, b"second-content")

    real_replace = os.replace
    call_count = {"n": 0}

    def flaky_replace(src, dst):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated failure on second replace")
        return real_replace(src, dst)

    monkeypatch.setattr("s3_ecological.experiments.atomic_output_pair.os.replace", flaky_replace)

    with pytest.raises(AtomicPairCommitError, match="rolled back"):
        commit_pair_atomically(first, second, overwrite=False, verify_committed=_no_op_verify)

    # The first file's commit succeeded and had no backup (new directory) -
    # it must be deleted again, leaving the directory empty.
    assert _files_in(tmp_path) == set()


def test_second_replace_failure_with_overwrite_restores_exact_old_bytes(tmp_path, monkeypatch):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_path.write_bytes(b"old-first")
    second_path.write_bytes(b"old-second")
    first = _staged(first_path, b"new-first")
    second = _staged(second_path, b"new-second")

    real_replace = os.replace
    call_count = {"n": 0}

    def flaky_replace(src, dst):
        call_count["n"] += 1
        # Call order: backup-first, backup-second, commit-first, commit-second.
        if call_count["n"] == 4:
            raise OSError("simulated failure on second commit replace")
        return real_replace(src, dst)

    monkeypatch.setattr("s3_ecological.experiments.atomic_output_pair.os.replace", flaky_replace)

    with pytest.raises(AtomicPairCommitError, match="rolled back"):
        commit_pair_atomically(first, second, overwrite=True, verify_committed=_no_op_verify)

    assert first_path.read_bytes() == b"old-first"
    assert second_path.read_bytes() == b"old-second"
    assert _files_in(tmp_path) == {"first.json", "second.json"}


def test_verify_committed_failure_in_new_directory_removes_both_files(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = _staged(first_path, b"first-content")
    second = _staged(second_path, b"second-content")

    def failing_verify(first_bytes: bytes, second_bytes: bytes) -> None:
        raise ValueError("cross-file consistency check failed")

    with pytest.raises(AtomicPairCommitError, match="rolled back"):
        commit_pair_atomically(first, second, overwrite=False, verify_committed=failing_verify)

    assert _files_in(tmp_path) == set()


def test_verify_committed_failure_with_overwrite_restores_exact_old_bytes(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first_path.write_bytes(b"old-first")
    second_path.write_bytes(b"old-second")
    first = _staged(first_path, b"new-first")
    second = _staged(second_path, b"new-second")

    def failing_verify(first_bytes: bytes, second_bytes: bytes) -> None:
        raise ValueError("cross-file consistency check failed")

    with pytest.raises(AtomicPairCommitError, match="rolled back"):
        commit_pair_atomically(first, second, overwrite=True, verify_committed=failing_verify)

    assert first_path.read_bytes() == b"old-first"
    assert second_path.read_bytes() == b"old-second"
    assert _files_in(tmp_path) == {"first.json", "second.json"}

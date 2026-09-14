#!/usr/bin/env python3
"""Offline, bounded verification for a full-tree Trading Sentinel data backup.

This tool deliberately proves archive/file and SQLite integrity only.  It cannot
observe the writers that existed while an archive was made, so it never claims
that a backup was live-quiescent or transactionally consistent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_MAX_MEMBERS = 100_000
DEFAULT_MAX_BYTES = 10 * 1024 * 1024 * 1024
SQLITE_HEADER = b"SQLite format 3\x00"
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *{f"COM{i}" for i in range(1, 10)},
                    *{f"LPT{i}" for i in range(1, 10)}}


class VerificationError(RuntimeError):
    pass


def _validate_limits(max_members: int, max_bytes: int) -> None:
    if (isinstance(max_members, bool) or not isinstance(max_members, int) or max_members < 1
            or isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 0):
        raise VerificationError("limits must be positive (max-bytes may be zero only for an empty tree)")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _exclusive_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise VerificationError(f"refusing to overwrite existing output: {path}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
    except Exception:
        # Do not leave an apparently successful receipt if writing failed.
        try:
            path.unlink()
        except OSError:
            pass
        raise


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def inventory_source(source: Path, *, max_members: int = DEFAULT_MAX_MEMBERS,
                     max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    """Hash a regular-file-only source tree, detecting mutation while reading."""
    _validate_limits(max_members, max_bytes)
    try:
        root_stat = source.lstat()
    except FileNotFoundError as exc:
        raise VerificationError(f"source does not exist: {source}") from exc
    if stat.S_ISLNK(root_stat.st_mode):
        raise VerificationError("source must be a real directory, not a symlink")
    root = source.resolve(strict=True)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise VerificationError("source must be a real directory, not a symlink")
    before_tree = _source_tree_state(root, max_members)
    files: list[dict[str, Any]] = []
    total = 0
    # os.walk does not follow links; inspect all entries so a link cannot hide.
    for directory, directories, filenames in os.walk(root, topdown=True, followlinks=False,
                                                   onerror=_walk_error):
        base = Path(directory)
        for name in sorted([*directories, *filenames]):
            candidate = base / name
            try:
                before = candidate.lstat()
            except FileNotFoundError as exc:
                raise VerificationError(f"source changed while inventorying: {candidate}") from exc
            if stat.S_ISLNK(before.st_mode):
                raise VerificationError(f"symlink is not allowed in source: {_relative(candidate, root)}")
            if stat.S_ISDIR(before.st_mode):
                continue
            if not stat.S_ISREG(before.st_mode):
                raise VerificationError(f"special file is not allowed in source: {_relative(candidate, root)}")
            if before.st_size > max_bytes - total:
                raise VerificationError(f"source exceeds byte limit ({max_bytes})")
            digest = _sha256_file(candidate)
            try:
                after = candidate.lstat()
            except FileNotFoundError as exc:
                raise VerificationError(f"source changed while inventorying: {candidate}") from exc
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise VerificationError(f"source changed while inventorying: {_relative(candidate, root)}")
            total += before.st_size
            files.append({"path": _relative(candidate, root), "size": before.st_size, "sha256": digest})
    files.sort(key=lambda item: item["path"])
    if before_tree != _source_tree_state(root, max_members):
        raise VerificationError("source changed while inventorying")
    return {"format": "trading_sentinel_data_inventory_v1", "source_file_count": len(files),
            "source_total_bytes": total, "files": files}


def _walk_error(error: OSError) -> None:
    raise VerificationError("cannot enumerate the complete source tree") from error


def _source_tree_state(root: Path, max_members: int) -> dict[str, tuple[int, int, int, int, int]]:
    """Metadata snapshot catches additions/removals and directory replacements."""
    state: dict[str, tuple[int, int, int, int, int]] = {}
    folded: set[str] = set()
    for directory, directories, filenames in os.walk(root, topdown=True, followlinks=False,
                                                   onerror=_walk_error):
        base = Path(directory)
        for name in [*directories, *filenames]:
            path = base / name
            if len(state) >= max_members:
                raise VerificationError(f"source exceeds member limit ({max_members})")
            relative = _canonical_member_name(_relative(path, root))
            if relative.casefold() in folded:
                raise VerificationError("source has case-colliding paths")
            folded.add(relative.casefold())
            try:
                item = path.lstat()
            except FileNotFoundError as exc:
                raise VerificationError("source changed while inventorying") from exc
            state[relative] = (item.st_mode, item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    return state


def _load_inventory(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        if path.stat().st_size > 64 * 1024 * 1024:
            raise VerificationError("expected inventory is too large")
        payload = path.read_bytes()
        raw = json.loads(payload.decode("utf-8"))
        files = raw["files"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise VerificationError(f"invalid expected inventory: {path}") from exc
    if not isinstance(raw, dict) or raw.get("format") != "trading_sentinel_data_inventory_v1" or not isinstance(files, list):
        raise VerificationError("inventory files must be a list")
    result: dict[str, dict[str, Any]] = {}
    folded: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(("path", "size", "sha256")) - set(item):
            raise VerificationError("inventory file entry is malformed")
        name = _canonical_member_name(str(item["path"]))
        if (not name or name in result or name.casefold() in folded or isinstance(item["size"], bool)
                or not isinstance(item["size"], int) or item["size"] < 0):
            raise VerificationError("inventory has duplicate or invalid file entry")
        if not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise VerificationError("inventory has invalid SHA-256")
        result[name] = {"size": item["size"], "sha256": item["sha256"]}
        folded.add(name.casefold())
    declared_count, declared_bytes = raw.get("source_file_count"), raw.get("source_total_bytes")
    if (isinstance(declared_count, bool) or not isinstance(declared_count, int) or declared_count != len(result)
            or isinstance(declared_bytes, bool) or not isinstance(declared_bytes, int)
            or declared_bytes != sum(item["size"] for item in result.values())):
        raise VerificationError("inventory count or total does not match file entries")
    return result, hashlib.sha256(payload).hexdigest()


def _canonical_member_name(name: str) -> str:
    # GNU/Alpine tar uses '.' and './foo'; accept only that harmless spelling.
    while name.startswith("./"):
        name = name[2:]
    if not name or name == ".":
        return ""
    if "\\" in name or ":" in name or name.startswith("/") or name.startswith("~"):
        raise VerificationError(f"unsafe tar member path: {name!r}")
    parts = name.split("/")
    if any(not part or part in (".", "..") or part.endswith((".", " "))
           or part.split(".", 1)[0].upper() in WINDOWS_RESERVED for part in parts):
        raise VerificationError(f"unsafe tar member path: {name!r}")
    canonical = PurePosixPath(*parts).as_posix()
    if canonical != name:
        raise VerificationError(f"unsafe tar member path: {name!r}")
    return canonical


def _safe_extract(archive: Path, destination: Path, *, max_members: int,
                  max_bytes: int) -> dict[str, Path]:
    seen: set[str] = set()
    seen_folded: set[str] = set()
    path_spellings: dict[str, str] = {}
    extracted: dict[str, Path] = {}
    total = 0
    try:
        handle = tarfile.open(archive, "r:*")
    except (OSError, tarfile.TarError) as exc:
        raise VerificationError(f"cannot read archive: {archive}") from exc
    with handle:
        for count, member in enumerate(handle, start=1):
            if count > max_members:
                raise VerificationError(f"archive exceeds member limit ({max_members})")
            name = _canonical_member_name(member.name)
            if not name:  # the root '.' directory marker
                if "" in seen:
                    raise VerificationError("archive has duplicate root marker")
                seen.add("")
                if not member.isdir():
                    raise VerificationError("archive root marker must be a directory")
                continue
            if name in seen:
                raise VerificationError(f"archive has duplicate member: {name}")
            seen.add(name)
            if name.casefold() in seen_folded:
                raise VerificationError(f"archive has case-colliding member: {name}")
            seen_folded.add(name.casefold())
            # Implicit parents also count: 'dir/a' and 'DIR/b' must not merge
            # silently when the verifier runs on a case-insensitive host.
            parts = name.split("/")
            for length in range(1, len(parts) + 1):
                prefix = "/".join(parts[:length])
                folded = prefix.casefold()
                if folded in path_spellings and path_spellings[folded] != prefix:
                    raise VerificationError(f"archive has case-colliding parent path: {name}")
                path_spellings[folded] = prefix
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise VerificationError(f"archive has prohibited link or special member: {name}")
            target = destination.joinpath(*name.split("/"))
            if member.isdir():
                if target.exists() and not target.is_dir():
                    raise VerificationError(f"archive has file/directory collision: {name}")
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise VerificationError(f"archive has unsupported member: {name}")
            if member.size < 0 or member.size > max_bytes - total:
                raise VerificationError(f"archive exceeds expanded byte limit ({max_bytes})")
            if target.parent.exists() and not target.parent.is_dir():
                raise VerificationError(f"archive has file/directory collision: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = handle.extractfile(member)
            if source is None:
                raise VerificationError(f"cannot read archive member: {name}")
            with source, target.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            total += member.size
            extracted[name] = target
    return extracted


def _sqlite_observations(files: dict[str, Path], scratch: Path) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    candidates: list[tuple[str, Path]] = []
    for name, path in sorted(files.items()):
        with path.open("rb") as stream:
            if stream.read(16) != SQLITE_HEADER:
                continue
        candidates.append((name, path))
    for name, path in candidates:
        # This is the extracted temporary tree, never the source/archive. Opening
        # writable lets SQLite replay an accompanying WAL before integrity_check.
        try:
            connection = sqlite3.connect(path)
            try:
                integrity = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
                if integrity != ["ok"]:
                    raise VerificationError(f"SQLite integrity_check failed for {name}: {integrity!r}")
                tables = [str(row[0]) for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                row_counts = {table: int(connection.execute(
                    'SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0]) for table in tables}
            finally:
                connection.close()
        except (sqlite3.Error, OSError) as exc:
            raise VerificationError(f"SQLite validation failed for {name}: {exc}") from exc
        observations.append({"path": name, "integrity_check": "ok", "row_counts": row_counts})
    return observations


def verify_archive(archive: Path, expected_inventory: Path, *, max_members: int = DEFAULT_MAX_MEMBERS,
                   max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    _validate_limits(max_members, max_bytes)
    expected, inventory_digest = _load_inventory(expected_inventory)
    if not archive.is_file():
        raise VerificationError(f"archive is not a regular file: {archive}")
    archive_before = archive.stat()
    archive_digest = _sha256_file(archive)
    with tempfile.TemporaryDirectory(prefix="sentinel-backup-verify-") as temp:
        scratch = Path(temp)
        extracted = _safe_extract(archive, scratch, max_members=max_members, max_bytes=max_bytes)
        actual = {name: {"size": path.stat().st_size, "sha256": _sha256_file(path)}
                  for name, path in extracted.items()}
        if actual != expected:
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            changed = sorted(name for name in set(actual) & set(expected) if actual[name] != expected[name])
            raise VerificationError(f"archive inventory mismatch (missing={missing}, extra={extra}, changed={changed})")
        sqlite = _sqlite_observations(extracted, scratch)
    archive_after = archive.stat()
    if (archive_before.st_dev, archive_before.st_ino, archive_before.st_size, archive_before.st_mtime_ns) != (
            archive_after.st_dev, archive_after.st_ino, archive_after.st_size, archive_after.st_mtime_ns) or archive_digest != _sha256_file(archive):
        raise VerificationError("archive changed during verification")
    return {"format": "trading_sentinel_data_backup_receipt_v1",
            "status": "INTEGRITY_VERIFIED_CONSISTENCY_UNPROVEN",
            "consistency_note": "Offline verification cannot infer live writer quiescence or transactional consistency.",
            "archive": str(archive), "archive_sha256": archive_digest,
            "inventory": str(expected_inventory), "inventory_sha256": inventory_digest,
            "file_count": len(expected), "total_bytes": sum(item["size"] for item in expected.values()),
            "sqlite": sqlite}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory", help="make an exclusive source inventory")
    inv.add_argument("source", type=Path); inv.add_argument("--output", required=True, type=Path)
    ver = sub.add_parser("verify", help="verify a tar archive against an inventory")
    ver.add_argument("archive", type=Path); ver.add_argument("--expected-inventory", required=True, type=Path)
    ver.add_argument("--receipt", required=True, type=Path)
    for command in (inv, ver):
        command.add_argument("--max-members", type=int, default=DEFAULT_MAX_MEMBERS)
        command.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args(argv)
    try:
        _validate_limits(args.max_members, args.max_bytes)
        if args.command == "inventory":
            root = args.source.resolve(strict=True)
            # Writing the manifest inside the source would violate read-only source inventory.
            try:
                args.output.resolve().relative_to(root)
                raise VerificationError("inventory output must be outside source")
            except ValueError:
                pass
            result = inventory_source(args.source, max_members=args.max_members, max_bytes=args.max_bytes)
            _exclusive_json(args.output, result)
        else:
            result = verify_archive(args.archive, args.expected_inventory,
                                    max_members=args.max_members, max_bytes=args.max_bytes)
            result["verified_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            _exclusive_json(args.receipt, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (VerificationError, OSError, tarfile.TarError, json.JSONDecodeError) as exc:
        print(f"data backup verification FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

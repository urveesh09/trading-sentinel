import importlib.util
import io
import json
import os
import sqlite3
import tarfile
from pathlib import Path

import pytest


_path = Path(__file__).parents[2] / "scripts" / "verify_data_backup.py"
_spec = importlib.util.spec_from_file_location("verify_data_backup", _path)
backup = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(backup)


def _tree(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "research").mkdir()
    (source / "research" / "manifest.json").write_text('{"safe": true}', encoding="utf-8")
    db = source / "cache.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("CREATE TABLE ledger (id INTEGER PRIMARY KEY, note TEXT)")
    con.commit()
    con.execute("INSERT INTO ledger(note) VALUES ('uncheckpointed')")
    con.commit()
    assert (source / "cache.db-wal").exists()
    return source, con


def _archive(source, archive, *, omit=()):
    with tarfile.open(archive, "w") as tar:
        for path in source.rglob("*"):
            if path.is_file() and path.name not in omit:
                tar.add(path, arcname="./" + path.relative_to(source).as_posix())


@pytest.fixture
def wal_tree(tmp_path):
    source, connection = _tree(tmp_path)
    try:
        yield source, connection
    finally:
        connection.close()


def _empty_inventory(path):
    path.write_text(json.dumps({"format": "trading_sentinel_data_inventory_v1", "source_file_count": 0,
                                "source_total_bytes": 0, "files": []}), encoding="utf-8")


def _inventory(source, path):
    result = backup.inventory_source(source)
    path.write_text(json.dumps(result), encoding="utf-8")
    return result


def test_wal_backup_verifies_and_recovers_uncheckpointed_row(tmp_path, wal_tree):
    source, con = wal_tree
    inventory = tmp_path / "inventory.json"
    expected = _inventory(source, inventory)
    assert "cache.db-wal" in {item["path"] for item in expected["files"]}
    archive = tmp_path / "data.tar"
    _archive(source, archive)
    before = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    receipt = backup.verify_archive(archive, inventory)
    assert receipt["status"] == "INTEGRITY_VERIFIED_CONSISTENCY_UNPROVEN"
    assert receipt["sqlite"] == [{"path": "cache.db", "integrity_check": "ok", "row_counts": {"ledger": 1}}]
    assert before == {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation", ["missing_wal", "hash", "corrupt"])
def test_missing_wal_tamper_and_corruption_are_rejected(tmp_path, mutation, wal_tree):
    source, con = wal_tree
    inventory = tmp_path / "inventory.json"
    _inventory(source, inventory)
    if mutation == "missing_wal":
        archive = tmp_path / "data.tar"; _archive(source, archive, omit={"cache.db-wal"})
    elif mutation == "hash":
        (source / "research" / "manifest.json").write_text("tampered", encoding="utf-8")
        archive = tmp_path / "data.tar"; _archive(source, archive)
    else:
        con.close()
        (source / "cache.db").write_bytes(b"SQLite format 3\x00broken")
        _inventory(source, inventory)
        archive = tmp_path / "data.tar"; _archive(source, archive)
    with pytest.raises(backup.VerificationError):
        backup.verify_archive(archive, inventory)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/drive", "dir\\backslash", "a/./b",
                                 "longname:stream", "NUL.txt", "dir/COM1", "trailing.", "trailing "])
def test_unsafe_tar_paths_are_rejected(tmp_path, name):
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo(name); info.size = 1
        import io
        tar.addfile(info, io.BytesIO(b"x"))
    inventory = tmp_path / "inventory.json"; _empty_inventory(inventory)
    with pytest.raises(backup.VerificationError, match="unsafe tar member path"):
        backup.verify_archive(archive, inventory)


@pytest.mark.parametrize("kind", [tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE])
def test_hardlinks_and_devices_are_rejected(tmp_path, kind):
    archive = tmp_path / "special.tar"
    with tarfile.open(archive, "w") as tar:
        member = tarfile.TarInfo("special"); member.type = kind; member.linkname = "target"
        tar.addfile(member)
    inventory = tmp_path / "inventory.json"; _empty_inventory(inventory)
    with pytest.raises(backup.VerificationError, match="prohibited"):
        backup.verify_archive(archive, inventory)


def test_case_aliases_and_duplicate_root_are_rejected(tmp_path):
    inventory = tmp_path / "inventory.json"; _empty_inventory(inventory)
    for names, message in [(["A", "a"], "case-colliding"),
                           (["dir/a", "DIR/b"], "case-colliding"),
                           ([".", "./"], "duplicate root")]:
        archive = tmp_path / (message + ".tar")
        with tarfile.open(archive, "w") as tar:
            for name in names:
                member = tarfile.TarInfo(name)
                if name.startswith("."):
                    member.type = tarfile.DIRTYPE; tar.addfile(member)
                else:
                    member.size = 1; tar.addfile(member, io.BytesIO(b"x"))
        with pytest.raises(backup.VerificationError, match=message):
            backup.verify_archive(archive, inventory)


def test_file_before_directory_is_valid_and_expansion_is_bounded(tmp_path):
    source = tmp_path / "source"; source.mkdir(); (source / "dir").mkdir()
    (source / "dir" / "file").write_bytes(b"xx")
    inventory = tmp_path / "inventory.json"; _inventory(source, inventory)
    archive = tmp_path / "order.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(source / "dir" / "file", arcname="./dir/file")
        member = tarfile.TarInfo("dir"); member.type = tarfile.DIRTYPE; tar.addfile(member)
    assert backup.verify_archive(archive, inventory)["file_count"] == 1
    with pytest.raises(backup.VerificationError, match="expanded byte limit"):
        backup.verify_archive(archive, inventory, max_bytes=1)
    with pytest.raises(backup.VerificationError, match="member limit"):
        backup.inventory_source(source, max_members=1)


def test_archive_mutation_during_verification_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir(); (source / "file").write_text("x")
    inventory = tmp_path / "inventory.json"; _inventory(source, inventory)
    archive = tmp_path / "data.tar"; _archive(source, archive)
    original = backup._sqlite_observations
    def mutate(files, scratch):
        result = original(files, scratch)
        with archive.open("ab") as stream:
            stream.write(b"changed")
        return result
    monkeypatch.setattr(backup, "_sqlite_observations", mutate)
    with pytest.raises(backup.VerificationError, match="archive changed"):
        backup.verify_archive(archive, inventory)


def test_source_enumeration_errors_fail_closed(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir()
    def failed_walk(root, **options):
        options["onerror"](PermissionError("unreadable subtree"))
        return iter(())
    monkeypatch.setattr(backup.os, "walk", failed_walk)
    with pytest.raises(backup.VerificationError, match="complete source tree"):
        backup.inventory_source(source)


def test_duplicate_link_and_limits_are_rejected(tmp_path):
    inventory = tmp_path / "inventory.json"; _empty_inventory(inventory)
    duplicate = tmp_path / "duplicate.tar"
    with tarfile.open(duplicate, "w") as tar:
        import io
        for _ in range(2):
            info = tarfile.TarInfo("x"); info.size = 1; tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(backup.VerificationError, match="duplicate"):
        backup.verify_archive(duplicate, inventory)
    link = tmp_path / "link.tar"
    with tarfile.open(link, "w") as tar:
        info = tarfile.TarInfo("linked"); info.type = tarfile.SYMTYPE; info.linkname = "target"; tar.addfile(info)
    with pytest.raises(backup.VerificationError, match="prohibited"):
        backup.verify_archive(link, inventory)
    many = tmp_path / "many.tar"
    with tarfile.open(many, "w") as tar:
        import io
        for name in ("a", "b"):
            info = tarfile.TarInfo(name); info.size = 1; tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(backup.VerificationError, match="member limit"):
        backup.verify_archive(many, inventory, max_members=1)


def test_inventory_rejects_symlink_and_cli_receipts_are_exclusive(tmp_path):
    source = tmp_path / "source"; source.mkdir(); (source / "file").write_text("x")
    try:
        os.symlink(source / "file", source / "link")
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(backup.VerificationError, match="symlink"):
        backup.inventory_source(source)


def test_cli_receipts_are_exclusive(tmp_path):
    source = tmp_path / "source"; source.mkdir(); (source / "file").write_text("x")

    # Clean source proves both inventory and success receipts cannot overwrite.
    inventory = tmp_path / "inventory.json"
    assert backup.main(["inventory", str(source), "--output", str(inventory)]) == 0
    assert backup.main(["inventory", str(source), "--output", str(inventory)]) == 1
    archive = tmp_path / "data.tar"; _archive(source, archive)
    receipt = tmp_path / "receipt.json"
    assert backup.main(["verify", str(archive), "--expected-inventory", str(inventory), "--receipt", str(receipt)]) == 0
    assert backup.main(["verify", str(archive), "--expected-inventory", str(inventory), "--receipt", str(receipt)]) == 1


def test_inventory_detects_source_change_during_hashing(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir()
    watched = source / "watched"; watched.write_text("before", encoding="utf-8")
    real_hash = backup._sha256_file

    def changing_hash(path):
        value = real_hash(path)
        watched.write_text("after-and-different-size", encoding="utf-8")
        return value

    monkeypatch.setattr(backup, "_sha256_file", changing_hash)
    with pytest.raises(backup.VerificationError, match="source changed"):
        backup.inventory_source(source)

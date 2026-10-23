"""Take a backup, and prove it can be restored.

    python scripts/verify_backup.py backup   var/sessions.sqlite out.sqlite
    python scripts/verify_backup.py verify   out.sqlite
    python scripts/verify_backup.py roundtrip var/knowledge.sqlite

WHY THIS EXISTS BESIDE THE SHELL SCRIPTS. `deploy/scripts/backup.sh` and
`restore-test.sh` are what runs on the EC2 host, and they need the `sqlite3`
binary. This does the same checks through Python's own sqlite3 module, so the
backup procedure can be exercised in the test suite and on a developer machine
that has no sqlite3 CLI — which is most of them, including every Windows one.

A BACKUP NOBODY HAS RESTORED IS A HYPOTHESIS. Every way a backup system fails
— a `cp` of a live database, a truncated upload, a wrong volume name producing
a valid but empty file — looks exactly like a working one until the restore.
`roundtrip` performs the whole cycle and checks the result, so the mechanism
is known to work rather than assumed to.

ONLINE, NOT A FILE COPY. `Connection.backup()` is SQLite's own online backup
API. A plain copy of a live database is not a backup: the -wal and -shm
sidecars mean the copy is frequently inconsistent, and the inconsistency is
not detected until somebody tries to use it.
"""

from __future__ import annotations

import argparse
import contextlib
import sqlite3
import sys
from pathlib import Path

#: A database smaller than this is empty in practice: SQLite's own header and
#: an empty schema come to a couple of pages.
_MINIMUM_BYTES = 1024


def backup(source: Path, target: Path) -> None:
    """An online backup, safe to take while the service is serving."""
    target.parent.mkdir(parents=True, exist_ok=True)
    # `contextlib.closing`, not sqlite3's own context manager. `with
    # sqlite3.connect(...)` commits or rolls back the transaction and leaves
    # the connection OPEN — which on Windows holds the file and makes the
    # scratch directory undeletable, and on any platform leaks a handle per
    # call. This was caught the first time the roundtrip was run, which is
    # exactly what a roundtrip test is for.
    live = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        live.backup(copy)
    finally:
        copy.close()
        live.close()


def verify(path: Path) -> tuple[bool, list[str]]:
    """Check a restored file. Returns (ok, lines to print)."""
    lines: list[str] = []
    problems: list[str] = []

    if not path.exists():
        return False, [f"  FAIL: {path} does not exist"]

    size = path.stat().st_size
    lines.append(f"  size              {size:,} bytes")
    if size < _MINIMUM_BYTES:
        problems.append("a database this small is almost certainly empty")

    # A truncated download or a failed decrypt still produces a file.
    header = path.read_bytes()[:15]
    if header == b"SQLite format 3":
        lines.append("  header            SQLite format 3")
    else:
        problems.append(f"not a SQLite database (header {header!r})")
        return False, lines + [f"  FAIL: {p}" for p in problems]

    try:
        with contextlib.closing(
                sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
            integrity = db.execute("PRAGMA integrity_check;").fetchone()[0]
            lines.append(f"  integrity_check   {integrity}")
            if integrity != "ok":
                problems.append(f"integrity_check returned {integrity!r}")

            tables = [row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name;")]
            lines.append(f"  tables            {len(tables)}")
            if not tables:
                problems.append("no tables — this database is empty")

            # A VIRTUAL TABLE FROM AN EXTENSION IS NOT CORRUPTION. The knowledge
            # corpus keeps its vectors in a sqlite-vec `vec0` table, which
            # cannot be read without that extension loaded. The first version
            # of this check counted every table and reported the knowledge
            # backup as FAILED — over a file holding all 8,344 chunks intact.
            # The extension is loaded where available; where it is not, the
            # table is reported as unreadable-here rather than as damaged.
            # Its shadow tables (`chunks_vec_rowids` and friends) are ordinary
            # tables and are still counted, so a vector table that really is
            # empty is still visible.
            try:
                import sqlite_vec

                db.enable_load_extension(True)
                sqlite_vec.load(db)
                db.enable_load_extension(False)
            except Exception:  # noqa: BLE001
                pass

            total = 0
            for table in tables:
                try:
                    count = db.execute(
                        f'SELECT count(*) FROM "{table}";').fetchone()[0]
                except sqlite3.DatabaseError as exc:
                    if "no such module" in str(exc):
                        lines.append(f"      {table:<28} (virtual; its module "
                                     f"is not loaded here)")
                        continue
                    problems.append(f"{table}: {exc}")
                    continue
                total += count
                lines.append(f"      {table:<28} {count:>8,}")
            # AN EMPTY BUT VALID DATABASE is what a wrong volume name produces,
            # and it passes every check above it.
            if tables and total == 0:
                problems.append("every table is empty")
    except sqlite3.DatabaseError as exc:
        problems.append(f"could not be opened: {exc}")

    return not problems, lines + [f"  FAIL: {p}" for p in problems]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backup", "verify", "roundtrip"))
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path, nargs="?")
    args = parser.parse_args(argv)

    if args.command == "verify":
        ok, lines = verify(args.source)
        print(f"checking {args.source}")
        print("\n".join(lines))
        print("\nRESTORE CHECK PASSED" if ok else "\nRESTORE CHECK FAILED")
        return 0 if ok else 1

    if args.command == "backup":
        if not args.target:
            print("backup needs a target path")
            return 2
        backup(args.source, args.target)
        print(f"backed up {args.source} -> {args.target}")
        return 0

    # roundtrip: back it up, check the copy, report.
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / "restored.sqlite"
        print(f"==> online backup of {args.source}")
        backup(args.source, copy)
        ok, lines = verify(copy)
        print("\n".join(lines))
        print()
        if ok:
            print("==> ROUND TRIP PASSED: the backup restores and is intact")
            return 0
        print("==> ROUND TRIP FAILED. Do not rely on this procedure.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

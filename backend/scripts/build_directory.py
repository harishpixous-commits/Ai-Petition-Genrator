"""Build the local-body directory from the official datasets.

    python scripts/fetch_directory.py        # download (see fetch_corpus.py style)
    python scripts/build_directory.py        # parse what was downloaded
    python scripts/build_directory.py --verify

WHAT THIS IS. Tamil Nadu's local bodies, from the Rural Development and
Panchayat Raj Department's own published datasets: 12,525 village panchayats,
388 blocks, 37 districts, the municipalities, the town panchayats and the
corporations — with the Tamil name beside the English one wherever the
department publishes both.

WHY IT MATTERS. A petition goes to a body, and which body depends on where the
citizen lives. Until now the service could say "I cannot tell", which was
honest and useless. The alternative — guessing a local body from a district or
a street name — is the one failure this layer exists to prevent, because a
citizen acts on it by travelling to an office.

THE FORMATS ARE NOT WHAT THEIR NAMES SAY. Three of these files are served with
Content-Type application/msexcel and an `xls=1` parameter, and are HTML
`<table>` documents. Three others are genuine OLE2 workbooks. A parser that
trusted the extension would read nothing from half of them, so the format is
detected from the magic bytes and not from the URL.

THE TAMIL JOIN IS BY CODE, NEVER BY NAME. The department publishes each list
twice, once per language, with identical LGD codes. Joining on the code is
exact; joining on a transliterated name would be guesswork, and a village
whose Tamil name was attached to the wrong English one is worse than a village
with no Tamil name at all.

NOTHING IS INVENTED. Every record carries the dataset and URL it came from. A
body that is not in these files does not appear here, and the application says
it cannot tell rather than inferring one.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

RAW = Path(__file__).resolve().parent.parent / "var" / "directory"
OUT = Path(__file__).resolve().parent.parent / "var" / "local_bodies.sqlite"

BASE = "https://www.tnrd.tn.gov.in"

#: Every dataset, what it holds, and where it came from. The URL travels with
#: each record so a jurisdiction answer can be traced to a government file.
SOURCES: dict[str, dict] = {
    "district_en": {"url": f"{BASE}/project/admin/district_lgd_dcode.php?xls=1&lang=en",
                    "kind": "district", "lang": "en"},
    "district_ta": {"url": f"{BASE}/project/admin/district_lgd_dcode.php?xls=1&lang=ta",
                    "kind": "district", "lang": "ta"},
    "block_en": {"url": f"{BASE}/project/admin/block_lgd_bcode.php?xls=1&lang=en",
                 "kind": "block_panchayat", "lang": "en"},
    "block_ta": {"url": f"{BASE}/project/admin/block_lgd_bcode.php?xls=1&lang=ta",
                 "kind": "block_panchayat", "lang": "ta"},
    "village_en": {"url": f"{BASE}/project/admin/village_lgd_pvcode.php?xls=1&lang=en",
                   "kind": "village_panchayat", "lang": "en"},
    "village_ta": {"url": f"{BASE}/project/admin/village_lgd_pvcode.php?xls=1&lang=ta",
                   "kind": "village_panchayat", "lang": "ta"},
    "town_panchayats": {"url": f"{BASE}/databases/Town%20Panchayats.xls",
                        "kind": "town_panchayat", "lang": "en"},
    "municipalities": {"url": f"{BASE}/databases/Municipality.xls",
                       "kind": "municipality", "lang": "en"},
    "corporations": {"url": f"{BASE}/databases/tn_corporation_details.xls",
                     "kind": "municipal_corporation", "lang": "en"},
}

_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_PUNCT = re.compile(r"[.’'`\-_,()]")


def normalise(text: str) -> str:
    """One spelling of a name reduced to something comparable.

    Case, punctuation and spacing go; letters do not. Two villages can differ
    by one letter and they are different villages.
    """
    cleaned = _PUNCT.sub(" ", str(text or ""))
    return " ".join(cleaned.lower().split())


def _rows(path: Path) -> list[list[str]]:
    """Rows from whichever format this actually is."""
    head = path.read_bytes()[:8]
    if head[:4] == b"\xd0\xcf\x11\xe0":
        import xlrd

        book = xlrd.open_workbook(str(path))
        for sheet in book.sheets():
            if sheet.nrows > 1:
                return [[str(sheet.cell_value(r, c)).strip()
                         for c in range(sheet.ncols)]
                        for r in range(sheet.nrows)]
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    out = []
    for row in _ROW.findall(text):
        cells = [_TAG.sub("", c).replace("&nbsp;", " ").strip()
                 for c in _CELL.findall(row)]
        if cells:
            out.append(cells)
    return out


def _clean_code(value: str) -> str:
    """"528" or "1.0" depending on the file. Both mean the same thing."""
    value = str(value or "").strip()
    if value.endswith(".0"):
        value = value[:-2]
    return value


def parse() -> tuple[list[dict], list[str]]:
    """Every record, and every problem found on the way."""
    records: list[dict] = []
    problems: list[str] = []

    # --- districts, blocks, villages: header-driven --------------------- #
    def table(name: str) -> list[dict]:
        path = RAW / f"{name}.raw"
        if not path.exists():
            problems.append(f"{name}: not downloaded")
            return []
        rows = _rows(path)
        if len(rows) < 2:
            problems.append(f"{name}: {len(rows)} rows — nothing to parse")
            return []
        header = [h.strip() for h in rows[0]]
        return [dict(zip(header, row, strict=False)) for row in rows[1:]
                if len(row) >= len(header)]

    def pick(row: dict, *names: str) -> str:
        for name in names:
            if name in row and str(row[name]).strip():
                return str(row[name]).strip()
        return ""

    # Tamil names, keyed by LGD code, so the join is exact.
    tamil: dict[tuple[str, str], str] = {}
    for name, column in (("district_ta", "District Name"),
                         ("block_ta", "Block Name"),
                         ("village_ta", "Village Name")):
        kind = SOURCES[name]["kind"]
        code_column = {"district_ta": "LGD District Code",
                       "block_ta": "LGD Block code",
                       "village_ta": "LGD Village Code"}[name]
        for row in table(name):
            code = _clean_code(pick(row, code_column))
            value = pick(row, column)
            if code and value:
                tamil[(kind, code)] = value

    def add(kind: str, code: str, name_en: str, district: str,
            district_code: str, parent: str, source: str) -> None:
        if not name_en or not code:
            return
        records.append({
            "lgd_code": code,
            "body_type": kind,
            "name_en": name_en,
            "name_ta": tamil.get((kind, code), ""),
            "district": district,
            "district_code": district_code,
            "parent": parent,
            "source_dataset": source,
            "source_url": SOURCES[source]["url"],
        })

    for row in table("district_en"):
        code = _clean_code(pick(row, "LGD District Code"))
        add("district", code, pick(row, "District Name"),
            pick(row, "District Name"), code, "", "district_en")

    for row in table("block_en"):
        add("block_panchayat", _clean_code(pick(row, "LGD Block code")),
            pick(row, "Block Name"), pick(row, "District Name"),
            _clean_code(pick(row, "LGD District Code")),
            pick(row, "District Name"), "block_en")

    for row in table("village_en"):
        add("village_panchayat", _clean_code(pick(row, "LGD Village Code")),
            pick(row, "Village Name"), pick(row, "District Name"),
            _clean_code(pick(row, "LGD District Code")),
            pick(row, "Block Name"), "village_en")

    # --- the OLE2 workbooks, each with its own column names ------------- #
    for source, code_col, name_col in (
            ("town_panchayats", "Town Panchayat Code", "Town Panchayat Name"),
            ("municipalities", "Municipality Code", "Municipality Name"),
            ("corporations", "Corporation Code", "Corporation Name")):
        kind = SOURCES[source]["kind"]
        for row in table(source):
            # These codes are per-district sequence numbers, not LGD codes, so
            # they repeat across districts. Qualified with the district code to
            # make a key that is actually unique.
            district_code = _clean_code(pick(row, "District Code"))
            code = _clean_code(pick(row, code_col))
            add(kind, f"{source[:2]}-{district_code}-{code}",
                pick(row, name_col), pick(row, "District Name"),
                district_code, pick(row, "District Name"), source)

    return records, problems


def write(records: list[dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    db = sqlite3.connect(OUT)
    try:
        db.execute("""
            CREATE TABLE local_bodies (
                lgd_code       TEXT,
                body_type      TEXT NOT NULL,
                name_en        TEXT NOT NULL,
                name_ta        TEXT,
                district       TEXT,
                district_code  TEXT,
                parent         TEXT,
                source_dataset TEXT NOT NULL,
                source_url     TEXT NOT NULL,
                key_en         TEXT NOT NULL,
                key_ta         TEXT,
                PRIMARY KEY (body_type, lgd_code)
            )""")
        db.executemany(
            "INSERT OR REPLACE INTO local_bodies VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(r["lgd_code"], r["body_type"], r["name_en"], r["name_ta"],
              r["district"], r["district_code"], r["parent"],
              r["source_dataset"], r["source_url"],
              normalise(r["name_en"]), normalise(r["name_ta"]))
             for r in records])
        db.execute("CREATE INDEX body_by_name_en ON local_bodies(key_en)")
        db.execute("CREATE INDEX body_by_name_ta ON local_bodies(key_ta)")
        db.execute("CREATE INDEX body_by_district ON local_bodies(district_code)")
        db.commit()
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true",
                        help="report what is in the built directory")
    args = parser.parse_args(argv)

    if args.verify:
        if not OUT.exists():
            print(f"{OUT} does not exist. Run without --verify first.")
            return 1
        db = sqlite3.connect(f"file:{OUT}?mode=ro", uri=True)
        try:
            print(f"{OUT}\n")
            for kind, count, tamil in db.execute(
                    "SELECT body_type, count(*), "
                    "sum(CASE WHEN name_ta<>'' THEN 1 ELSE 0 END) "
                    "FROM local_bodies GROUP BY body_type ORDER BY count(*) DESC"):
                print(f"  {kind:<22} {count:>7,}   with Tamil name: {tamil:>7,}")
            total = db.execute("SELECT count(*) FROM local_bodies").fetchone()[0]
            print(f"  {'TOTAL':<22} {total:>7,}")
            print("\n  duplicate names within a district (ambiguous by name alone):")
            rows = db.execute(
                "SELECT key_en, district, count(*) c FROM local_bodies "
                "GROUP BY key_en, district, body_type HAVING c > 1 "
                "ORDER BY c DESC LIMIT 5").fetchall()
            for key, district, count in rows:
                print(f"    {key[:34]:<34} {district[:18]:<18} x{count}")
            if not rows:
                print("    none")
        finally:
            db.close()
        return 0

    records, problems = parse()
    if problems:
        print("problems:")
        for problem in problems:
            print("  -", problem)
    if not records:
        print("nothing parsed; refusing to write an empty directory")
        return 1

    write(records)
    print(f"wrote {len(records):,} records to {OUT}")
    kinds: dict[str, int] = {}
    for record in records:
        kinds[record["body_type"]] = kinds.get(record["body_type"], 0) + 1
    for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {kind:<22} {count:>7,}")
    manifest = OUT.with_suffix(".sources.json")
    manifest.write_text(json.dumps(SOURCES, indent=2), encoding="utf-8")
    print(f"sources recorded in {manifest.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

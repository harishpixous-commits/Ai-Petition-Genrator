"""Every script this service serves has a font the renderer can actually find.

RUN AT BUILD TIME, so a missing face is a failed build rather than a petition
printed as a row of dotted boxes. A missing font raises nothing at render time:
LibreOffice substitutes, PyMuPDF draws `.notdef`, and the only trace is a log
line nobody reads — on the one artifact the citizen carries to a counter.

The list comes from `app.domain.languages`, so adding a language to the service
and forgetting to ship its font fails here instead of in an office.

    python scripts/check_fonts.py            # files ship, families registered
    python scripts/check_fonts.py --files-only   # before fontconfig exists
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.languages import LANGUAGES  # noqa: E402

FONT_DIR = Path(__file__).resolve().parent.parent / "app" / "assets" / "fonts"


def registered_families() -> set[str] | None:
    """Families fontconfig knows about, or None where fc-list is unavailable."""
    try:
        out = subprocess.run(["fc-list", "--format", "%{family}\\n"],
                             capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    families: set[str] = set()
    for line in out.stdout.splitlines():
        families.update(part.strip() for part in line.split(",") if part.strip())
    return families


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files-only", action="store_true",
                        help="check the .ttf files ship, and skip fontconfig")
    args = parser.parse_args()

    wanted = {row.font_family: row.font_file for row in LANGUAGES}
    problems: list[str] = []

    for family, filename in sorted(wanted.items()):
        if not (FONT_DIR / filename).is_file():
            problems.append(f"{filename} is not in app/assets/fonts "
                            f"(needed for the {family} family)")

    # WHICH FAMILIES THE RENDERER CAN ACTUALLY NAME. `render._face_for` returns
    # a language's family only for a language with a script of its own; English
    # text falls through to the configured `letter_font`. "Noto Sans App" is a
    # CSS alias for the browser and fontconfig will never know it, so asking
    # for it here would fail every build for no reason.
    from app.config import get_settings
    system = {row.font_family for row in LANGUAGES if row.script is not None}
    system.add(get_settings().letter_font)

    families = None if args.files_only else registered_families()
    if families is None:
        if not args.files_only:
            print("fc-list unavailable; checked the shipped files only.")
    else:
        for family in sorted(system):
            if family not in families:
                problems.append(f'"{family}" is not registered with fontconfig, '
                                f"so LibreOffice will substitute and the PDF "
                                f"will print boxes")

    if problems:
        print("FATAL: fonts missing")
        for problem in problems:
            print("  -", problem)
        return 1

    scripts = ", ".join(sorted(wanted))
    print(f"fonts present for every language: {scripts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bash scripts in `deploy/scripts/` must parse.

A `bash -n` syntax check cannot catch everything — it does not run the
script, so a missing `aws` CLI or a wrong S3 bucket surfaces at the first
real cron fire, not here. What it DOES catch is a stray `fi` or a dangling
heredoc that would make the script fail to even load, which is exactly the
class of regression the backup pipeline cannot afford: the scheduler would
log a syntax error at 02:45 UTC and nobody would notice until the restore
day.

Three operational scripts are checked: `backup.sh`, `backup-offsite.sh` and
`restore-test.sh`. They are the ones the Phase 0.5 baseline asks for. Other
scripts under `deploy/scripts/` are already exercised by the deploy
pipeline itself.

Skips cleanly if `bash` is not on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "deploy" / "scripts"
TO_CHECK = ("backup.sh", "backup-offsite.sh", "restore-test.sh")
BASH = shutil.which("bash")
if BASH:
    try:
        _bash_check = subprocess.run([BASH, "--version"], capture_output=True,
                                     text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        BASH = None
    else:
        if _bash_check.returncode != 0:
            BASH = None


@pytest.mark.skipif(BASH is None, reason="a working bash executable is not available")
@pytest.mark.parametrize("script", TO_CHECK)
def test_the_shell_script_parses(script: str):
    path = SCRIPTS_DIR / script
    assert path.is_file(), f"{script} is missing from deploy/scripts/"
    result = subprocess.run(
        [BASH, "-n", str(path)],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0, (
        f"{script} failed `bash -n`:\n{result.stderr}"
    )

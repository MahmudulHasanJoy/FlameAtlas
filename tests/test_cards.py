"""Runs the source check for evidence cards when the raw NASA files exist."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    shutil.which("pdftotext") is None or not (REPO / "data/raw/ntrs/20210011385.pdf").exists(),
    reason="needs pdftotext and the raw NTRS PDFs (python scripts/fetch_ntrs.py)",
)
def test_every_card_quote_is_in_its_source():
    r = subprocess.run([sys.executable, "scripts/verify_cards.py"], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

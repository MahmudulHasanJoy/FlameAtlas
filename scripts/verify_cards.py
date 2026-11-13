"""Verify FlameAtlas evidence cards against their NASA sources.

Checks, for data/processed/cards.json:
  1. Structure: required fields, text length limits (data spec 4.5), and that
     every source, related card and quote reference resolves.
  2. Quotes: each quote appears word for word in its source. NTRS quotes are
     checked against the stated PDF page; PSI quotes against the raw CSV.
     Comparison ignores whitespace and line breaks, treats curly quotes and
     dashes as their ASCII forms, and drops private-use symbol-font glyphs
     (arrows and bullets from Wingdings-style fonts); nothing else.

Writes data/processed/cards_verification.json with the result per quote and
the SHA-256 of each source file, so the check is reproducible.

Needs the raw sources (python scripts/fetch_ntrs.py, scripts/fetch_psi.py) and
pdftotext (poppler). Exit code 0 only if every check passes.

    python scripts/verify_cards.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CARDS = REPO / "data" / "processed" / "cards.json"
REPORT = REPO / "data" / "processed" / "cards_verification.json"

REQUIRED = [
    "card_id", "title", "experiment", "source_ids", "linked_report_ids",
    "material_ids", "conditions", "outcome_summary", "key_finding",
    "safety_takeaway", "takeaway_is_interpretation", "locator", "quotes",
    "related_card_ids",
]
MAX_LEN = {"key_finding": 200, "safety_takeaway": 300, "outcome_summary": 300}

_TRANSLATE = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", "­": "",
})


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_TRANSLATE)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Co")
    return re.sub(r"\s+", "", text)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pdf_pages(path: Path) -> list[str]:
    """Return per-page text, joining layout and reading-order extractions so
    quotes from tables (layout) and multi-column posters (raw) both match."""
    pages: list[str] = []
    for mode in (["-layout"], []):
        out = subprocess.run(
            ["pdftotext", *mode, str(path), "-"],
            capture_output=True, text=True, check=True,
        ).stdout.split("\f")
        for i, page in enumerate(out):
            if i == len(pages):
                pages.append("")
            pages[i] += "\n" + page
    return pages


def main() -> int:
    data = json.loads(CARDS.read_text(encoding="utf-8"))
    sources, cards = data["sources"], data["cards"]
    card_ids = {c["card_id"] for c in cards}
    errors: list[str] = []

    if len(card_ids) != len(cards):
        errors.append("duplicate card_id")

    for c in cards:
        cid = c.get("card_id", "?")
        for field in REQUIRED:
            if field not in c:
                errors.append(f"{cid}: missing field {field}")
        for field, limit in MAX_LEN.items():
            if len(c.get(field, "")) > limit:
                errors.append(f"{cid}: {field} is {len(c[field])} chars (max {limit})")
        for sid in c.get("source_ids", []):
            if sid not in sources:
                errors.append(f"{cid}: unknown source {sid}")
        for rid in c.get("related_card_ids", []):
            if rid not in card_ids:
                errors.append(f"{cid}: unknown related card {rid}")
        if not c.get("quotes"):
            errors.append(f"{cid}: no quotes")
        for q in c.get("quotes", []):
            if q["source_id"] not in c.get("source_ids", []):
                errors.append(f"{cid}: quote source {q['source_id']} not in source_ids")

    if shutil.which("pdftotext") is None:
        print("pdftotext not found (install poppler).", file=sys.stderr)
        return 2

    texts: dict[str, list[str] | str] = {}
    hashes: dict[str, str] = {}
    for sid, src in sources.items():
        path = REPO / src["file"]
        if not path.exists():
            errors.append(f"source file missing: {src['file']} (run the fetch scripts)")
            continue
        hashes[sid] = sha256(path)
        if src["type"] == "ntrs":
            texts[sid] = [normalize(p) for p in pdf_pages(path)]
        else:
            texts[sid] = normalize(path.read_text(encoding="utf-8-sig"))

    results: dict[str, list[dict]] = {}
    for c in cards:
        rows = []
        for i, q in enumerate(c["quotes"]):
            sid = q["source_id"]
            if sid not in texts:
                ok = False
            elif sources[sid]["type"] == "ntrs":
                pages = texts[sid]
                page = q.get("page")
                ok = isinstance(page, int) and 1 <= page <= len(pages) and normalize(q["text"]) in pages[page - 1]
            else:
                ok = normalize(q["text"]) in texts[sid]
            rows.append({"quote": i, "source_id": sid, "page": q.get("page"), "ok": ok})
            if not ok:
                errors.append(f"{c['card_id']} quote {i} not found in {sid} p.{q.get('page')}: {q['text'][:70]!r}")
        results[c["card_id"]] = rows

    n_quotes = sum(len(r) for r in results.values())
    n_ok = sum(x["ok"] for r in results.values() for x in r)
    REPORT.write_text(json.dumps({
        "checked_on": dt.date.today().isoformat(),
        "method": "Each quote matched word for word against the source page text (pdftotext layout and reading order) or PSI CSV, ignoring whitespace, quote/dash styles and private-use symbol glyphs.",
        "cards": len(cards),
        "quotes": n_quotes,
        "quotes_verified": n_ok,
        "all_passed": not errors,
        "source_sha256": hashes,
        "results": results,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"{len(cards)} cards, {n_ok}/{n_quotes} quotes verified against sources")
    for e in errors:
        print("FAIL", e)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())

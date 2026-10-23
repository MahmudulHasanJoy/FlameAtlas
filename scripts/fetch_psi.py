#!/usr/bin/env python3
"""Download NASA PSI combustion data used by FlameAtlas.

Source: NASA Physical Sciences Informatics (https://psi.nasa.gov), linked from
https://science.nasa.gov/biological-physical/data/. Data is CC0-1.0.

What it downloads (raw video and image data is skipped; it is terabytes):
  * every Combustion Science investigation: metadata JSON, experimental table,
    metadata, science documents, reports, representative images
  * core solid-material investigations (BASS, BASS-II, Saffire I-III):
    additionally engineering documents, presentations, reference and analyzed
    data, and tabular raw telemetry (csv/xls/xlsx/txt/dat)

Usage:
  python scripts/fetch_psi.py                 # default selection
  python scripts/fetch_psi.py --only PSI-26   # one investigation
  python scripts/fetch_psi.py --dry-run       # list what would be fetched

Output: data/raw/psi/<accession>_<acronym>/<folder>/<file> and
data/raw/psi/manifest.csv. Re-running skips files already downloaded.
Standard library only.
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://psi.nasa.gov/geode-py/ws"
ROOT = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "psi")

CORE_SOLIDS = {"PSI-25", "PSI-26", "PSI-98", "PSI-99", "PSI-100"}
ALL_FOLDERS = {"Experimental table", "metadata", "Science Documents", "Reports", "Representative Image(s)"}
CORE_FOLDERS = ALL_FOLDERS | {"Engineering Documents", "Presentations", "Reference Data", "Analyzed Data"}
TABULAR = {".csv", ".xls", ".xlsx", ".txt", ".dat"}
MAX_BYTES = 60_000_000


def get(url, as_json=True, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                body = r.read()
            return json.loads(body) if as_json else body
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def combustion_accessions():
    q = urllib.parse.urlencode({"q": "", "data_source": "psi", "data_type": "investigation", "size": 1000})
    hits = get(f"{API}/repo/search?{q}")["hits"]["hits"]
    return sorted(h["_source"]["Accession"] for h in hits if h["_source"].get("Research Area") == "Combustion Science")


def safe(name):
    return re.sub(r"[^\w.\- ()]+", "_", name).strip()


def wanted(acc, f):
    parts = f["remote_path"].split("/")
    folder = parts[4] if len(parts) > 5 else ""
    ext = os.path.splitext(f["file_name"])[1].lower()
    size = f.get("file_size") or 0
    if f.get("restricted") or size > MAX_BYTES:
        return None
    if folder in ALL_FOLDERS:
        return folder
    if acc in CORE_SOLIDS and folder in CORE_FOLDERS:
        return folder
    if acc in CORE_SOLIDS and folder == "Raw Data" and ext in TABULAR:
        return folder
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="accessions to fetch, e.g. PSI-26")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    os.makedirs(ROOT, exist_ok=True)
    accessions = args.only or combustion_accessions()
    rows = []
    for acc in accessions:
        inv = get(f"{API}/repo/investigations/{acc}")
        name = f"{acc}_{safe(inv.get('investigationAcronym') or 'NA').replace(' ', '_').replace('/', '-')}"
        d = os.path.join(ROOT, name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "investigation.json"), "w") as fh:
            json.dump(inv, fh, indent=1)
        files = (inv.get("experimentalTable") or []) + (inv.get("added") or [])
        for f in files:
            folder = wanted(acc, f)
            if not folder:
                continue
            dest = os.path.join(d, safe(folder), safe(f["file_name"]))
            rows.append([acc, inv.get("investigationAcronym", ""), folder, f["file_name"], f.get("file_size") or 0,
                         os.path.relpath(dest, ROOT)])
            if args.dry_run or (os.path.exists(dest) and os.path.getsize(dest) == f.get("file_size")):
                continue
            q = urllib.parse.urlencode({"file": f["file_name"], "version": f.get("version", 1), "redirect": "false"})
            try:
                signed = get(f"{API}/studies/{acc}/download?{q}", as_json=False).decode().strip()
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                data = get(signed, as_json=False)
                with open(dest, "wb") as fh:
                    fh.write(data)
                print(f"ok   {acc} {folder}/{f['file_name']} ({len(data) // 1024} KB)")
            except Exception as e:
                print(f"FAIL {acc} {folder}/{f['file_name']}: {e}", file=sys.stderr)

    with open(os.path.join(ROOT, "manifest.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["accession", "acronym", "folder", "file_name", "bytes", "local_path"])
        w.writerows(rows)
    print(f"{len(rows)} files in selection, {sum(r[4] for r in rows) / 1e6:.0f} MB; manifest at {ROOT}/manifest.csv")


if __name__ == "__main__":
    main()

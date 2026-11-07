#!/usr/bin/env python3
"""Build cache/experiments.parquet from NASA PSI experimental tables.

One row per published microgravity combustion test:
  oxygen_pct, pressure_kpa, flow_cm_s, material, sample_geometry,
  outcome_class, report_id, source_url

Source: NASA Physical Sciences Informatics (https://psi.nasa.gov), CC0-1.0.
File names are read from the committed data/raw/psi/manifest.csv.
Standard library + pandas/pyarrow. Re-running skips files already cached.
"""
from __future__ import annotations

import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request

API = "https://psi.nasa.gov/geode-py/ws"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
MANIFEST = os.path.join(REPO, "data", "raw", "psi", "manifest.csv")
CACHE = os.path.join(REPO, "cache", "psi_raw")
OUT = os.path.join(REPO, "cache", "experiments.parquet")

OUTCOME_MAP = {
    "burned": "spread", "burn": "spread", "spread": "spread",
    "self_extinguished": "no_spread", "self-extinguished": "no_spread",
    "extinguished": "no_spread", "no_ignition": "no_spread",
    "no ignition": "no_spread", "quenched": "no_spread",
    "blowoff": "no_spread", "blow-off": "no_spread",
    "marginal": "marginal_spread", "marginal_spread": "marginal_spread",
}


def get(url, as_json=True, retries=3, timeout=120):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hermes-agent"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            return json.loads(body) if as_json else body
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def safe(name):
    return re.sub(r"[^\w.\- ()]+", "_", name).strip()


def download_file(acc, fname, dest_dir):
    """Download one PSI file via presigned S3 URL. Returns local path or None."""
    dest = os.path.join(dest_dir, safe(fname))
    if os.path.exists(dest):
        return dest
    version = 1
    q = urllib.parse.urlencode({"file": fname, "version": version, "redirect": "false"})
    try:
        signed = get(f"{API}/studies/{acc}/download?{q}", as_json=False).decode().strip()
        data = get(signed, as_json=False)
        os.makedirs(dest_dir, exist_ok=True)
        with open(dest + ".part", "wb") as fh:
            fh.write(data)
        os.replace(dest + ".part", dest)
        return dest
    except Exception as e:
        print(f"  download failed {fname}: {e}")
        return None


def _num(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        m = re.search(r"[-+]?\d*\.?\d+", str(v))
        return float(m.group(0)) if m else None


def parse_experimental_table(csv_path, acc):
    """Parse a PSI experimental table CSV into normalized rows."""
    rows = []
    try:
        with open(csv_path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                o2 = _num(r.get("oxygen_pct") or r.get("O2") or r.get("oxygen") or r.get("O2_pct"))
                press = _num(r.get("pressure_kpa") or r.get("pressure") or r.get("Pressure_kPa"))
                flow = _num(r.get("flow_cm_s") or r.get("flow") or r.get("Flow_cm_s") or r.get("velocity"))
                material = (r.get("material") or r.get("Material") or "").strip() or "unknown"
                geometry = (r.get("sample_geometry") or r.get("geometry") or r.get("Sample") or "").strip() or "unknown"
                outcome = (r.get("outcome") or r.get("Outcome") or r.get("result") or "").strip().lower()
                outcome_class = OUTCOME_MAP.get(outcome, "marginal_spread")
                if o2 is None or flow is None:
                    continue
                rows.append({
                    "oxygen_pct": o2,
                    "pressure_kpa": press,
                    "flow_cm_s": flow,
                    "material": material,
                    "sample_geometry": geometry,
                    "outcome_class": outcome_class,
                    "report_id": f"PSI {acc}",
                    "source_url": f"https://psi.nasa.gov/studies/{acc}",
                    "source_file": os.path.basename(csv_path),
                })
    except Exception as e:
        print(f"  parse failed {csv_path}: {e}")
    return rows


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    # Read committed manifest; pick Experimental table CSVs
    targets = []
    with open(MANIFEST, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            folder = (row.get("folder") or "").strip()
            fname = (row.get("file_name") or "").strip()
            downloaded = (row.get("downloaded") or "").strip().lower()
            if not fname.lower().endswith(".csv"):
                continue
            if "Experimental table" not in folder:
                continue
            if downloaded == "false":
                print(f"  skipping (not downloaded by NASA): {fname}")
                continue
            local_path = (row.get("local_path") or "").strip()
            m = re.match(r"(PSI-\d+)", local_path)
            acc = m.group(1) if m else "PSI-?"
            targets.append((acc, fname))

    # Deduplicate
    seen = set()
    uniq_targets = []
    for acc, fname in targets:
        if (acc, fname) in seen:
            continue
        seen.add((acc, fname))
        uniq_targets.append((acc, fname))

    print(f"Found {len(uniq_targets)} experimental table CSVs in manifest")

    all_rows = []
    for acc, fname in uniq_targets:
        print(f"Downloading {acc}: {fname}")
        local = download_file(acc, fname, CACHE)
        if not local:
            continue
        rows = parse_experimental_table(local, acc)
        print(f"  {len(rows)} usable rows")
        all_rows.extend(rows)

    # Deduplicate rows
    seen = set()
    deduped = []
    for r in all_rows:
        key = (r["report_id"], r["oxygen_pct"], r["flow_cm_s"], r["material"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    print(f"\nTotal unique rows: {len(deduped)}")

    import pandas as pd
    df = pd.DataFrame(deduped)
    df.to_parquet(OUT, index=False)
    print(f"Wrote {OUT} ({len(deduped)} rows)")

    csv_out = OUT.replace(".parquet", ".csv")
    df.to_csv(csv_out, index=False)
    print(f"Wrote {csv_out}")

    print("\nRows per report:")
    print(df.groupby("report_id").size().to_string())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build cache/experiments.parquet from NASA PSI experimental tables + curated data.

One row per published microgravity combustion test:
  oxygen_pct, pressure_kpa, flow_cm_s, material, sample_geometry,
  outcome_class, report_id, source_url

Sources:
  * cache/psi_raw/*.csv  (PSI experimental tables, downloaded from NASA PSI)
  * prototype/data/sibal_bass_table71.csv  (curated BASS-II outcomes)

Standard library + pandas/pyarrow. Column mapping is file-specific because PSI
tables use inconsistent headers. Rows missing oxygen_pct or flow_cm_s are kept
(with null flow) so condition-range coverage is recorded, but they cannot train
the classifier (which drops nulls).
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "cache" / "psi_raw"
PROTOTYPE = REPO / "prototype" / "data" / "sibal_bass_table71.csv"
OUT = REPO / "cache" / "experiments.parquet"
OUT_CSV = REPO / "cache" / "experiments.csv"

OUTCOME_MAP = {
    "burned": "spread", "burn": "spread", "spread": "spread",
    "self_extinguished": "no_spread", "self-extinguished": "no_spread",
    "extinguished": "no_spread", "no_ignition": "no_spread",
    "no ignition": "no_spread", "quenched": "no_spread",
    "blowoff": "no_spread", "blow-off": "no_spread",
    "marginal": "marginal_spread", "marginal_spread": "marginal_spread",
}

PRESSURE_FACTORS = {
    "atm": 101.325, "mmhg": 0.133322, "torr": 0.133322,
    "bar": 100.0, "kpa": 1.0, "pa": 0.001,
}


def _num(v):
    """Extract a float from a messy cell ('~ 21.5', '0.21; 0.25', '20 cm/s')."""
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("none", "n/a", "na", "-", "insignificant"):
        return None
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    return float(m.group(0)) if m else None


def _pressure_to_kpa(val, unit_hint=""):
    if val is None:
        return None
    u = unit_hint.lower()
    factor = 1.0
    for k, f in PRESSURE_FACTORS.items():
        if k in u:
            factor = f
            break
    return round(val * factor, 3)


def _outcome_from_text(text):
    if text is None:
        return None
    s = str(text).strip().lower()
    if s == "":
        return None
    if s in OUTCOME_MAP:
        return OUTCOME_MAP[s]
    if "insignificant" in s or s in ("~ 0", "0", "0.0", "none"):
        return "no_spread"
    if "self-ext" in s or "self ext" in s or "flow term" in s:
        return "no_spread"
    if "burn" in s or "spread" in s or "flame" in s:
        return "spread"
    try:
        t = float(s)
        if t > 0:
            return "spread"
        return "no_spread"
    except ValueError:
        return "marginal_spread"


def _clean_material(v):
    if v is None:
        return "unknown"
    return re.sub(r"\s+", " ", str(v)).strip() or "unknown"


def norm_cols(df):
    """Normalize header: strip whitespace/BOM."""
    df = df.copy()
    df.columns = [re.sub(r"^\ufeff", "", str(c)).strip() for c in df.columns]
    return df


def find_col(df, candidates):
    """Return the first column whose normalized name matches any candidate."""
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for c in df.columns:
        cl = c.lower()
        for cand in candidates:
            if cand in cl:
                return c
    return None


def parse_bass_ii(df, acc):
    """PSI-25 BASS-II: O2 + material + fan settings (no flow cm/s, no outcome)."""
    rows = []
    mat_c = find_col(df, ["fuel sample material", "material"])
    o2_c = find_col(df, ["calibrated  initial o2 % by vol", "initial o2"])
    for _, r in df.iterrows():
        material = _clean_material(r.get(mat_c)) if mat_c else "unknown"
        o2 = _num(r.get(o2_c)) if o2_c else None
        if o2 is None:
            continue
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": 101.3,
            "flow_cm_s": None,
            "material": material,
            "sample_geometry": "film",
            "outcome_class": "marginal_spread",
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


def parse_saffire(df, acc):
    """PSI-98/99 SAFFIRE: material, O2, flow cm/s, burn time -> outcome."""
    rows = []
    mat_c = find_col(df, ["material"])
    o2_c = find_col(df, ["percent o2", "o2"])
    flow_c = find_col(df, ["air flow", "flow"])
    burn_c = find_col(df, ["burn time", "burn length"])
    for _, r in df.iterrows():
        material = _clean_material(r.get(mat_c)) if mat_c else "unknown"
        o2 = _num(r.get(o2_c)) if o2_c else None
        flow = _num(r.get(flow_c)) if flow_c else None
        if o2 is None:
            continue
        burn = r.get(burn_c) if burn_c else None
        outcome = _outcome_from_text(burn) or "marginal_spread"
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": 101.3,
            "flow_cm_s": flow,
            "material": material,
            "sample_geometry": "fabric",
            "outcome_class": outcome,
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


def parse_flex(df, acc):
    """PSI-69 FLEX: fuel, O2 mole fraction, pressure mmHg, burn time -> outcome."""
    rows = []
    mat_c = find_col(df, ["fuel"])
    o2_c = find_col(df, ["o initial ambient composition", "oxygen", "o2"])
    press_c = find_col(df, ["ambient pressure", "pressure"])
    burn_c = find_col(df, ["burn time"])
    for _, r in df.iterrows():
        material = _clean_material(r.get(mat_c)) if mat_c else "unknown"
        o2_frac = _num(r.get(o2_c)) if o2_c else None
        o2 = o2_frac * 100.0 if o2_frac is not None else None
        press = _pressure_to_kpa(_num(r.get(press_c)), "mmHg") if press_c else None
        if o2 is None:
            continue
        outcome = _outcome_from_text(r.get(burn_c)) if burn_c else "marginal_spread"
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": press,
            "flow_cm_s": None,
            "material": material,
            "sample_geometry": "droplet",
            "outcome_class": outcome or "marginal_spread",
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


def parse_flex2(df, acc):
    """PSI-68 FLEX-2: fuel, O2 mole fraction, pressure atm, flow cm/s."""
    rows = []
    mat_c = find_col(df, ["sample", "fuel"])
    o2_c = find_col(df, ["oxygen mole fraction", "oxygen", "o2"])
    press_c = find_col(df, ["ambient pressure", "pressure"])
    flow_c = find_col(df, ["flow velocity", "air flow", "flow"])
    for _, r in df.iterrows():
        o2_frac = _num(r.get(o2_c)) if o2_c else None
        if o2_frac is None:
            continue
        o2 = o2_frac * 100.0
        material = _clean_material(r.get(mat_c)) if mat_c else "unknown"
        press = _pressure_to_kpa(_num(r.get(press_c)), "atm") if press_c else 101.3
        flow = _num(r.get(flow_c)) if flow_c else None
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": press,
            "flow_cm_s": flow,
            "material": material,
            "sample_geometry": "droplet",
            "outcome_class": "marginal_spread",
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


def parse_cfi(df, acc):
    """PSI-39 CFI: fuel, pressure atm, O2 mole fraction, fiber. No flow."""
    rows = []
    mat_c = find_col(df, ["fuel", "fiber"])
    o2_c = find_col(df, ["oxygen", "o2"])
    press_c = find_col(df, ["pressure"])
    for _, r in df.iterrows():
        o2_frac = _num(r.get(o2_c)) if o2_c else None
        if o2_frac is None:
            continue
        o2 = o2_frac * 100.0
        material = f"{_clean_material(r.get(mat_c))}" if mat_c else "unknown"
        press = _pressure_to_kpa(_num(r.get(press_c)), "atm") if press_c else 101.3
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": press,
            "flow_cm_s": None,
            "material": material,
            "sample_geometry": "fiber",
            "outcome_class": "marginal_spread",
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


def parse_cfig(df, acc):
    """PSI-159 CFI-G: fuel, XO2, pressure bar, self-ext outcome. No flow."""
    rows = []
    mat_c = find_col(df, ["fuel"])
    o2_c = find_col(df, ["xo2 before test", "xo2", "o2"])
    press_c = find_col(df, ["approx p", "pressure"])
    out_c = find_col(df, ["self-ext", "self_ext", "outcome"])
    for _, r in df.iterrows():
        o2_frac = _num(r.get(o2_c)) if o2_c else None
        if o2_frac is None:
            continue
        o2 = o2_frac * 100.0
        material = _clean_material(r.get(mat_c)) if mat_c else "unknown"
        press = _pressure_to_kpa(_num(r.get(press_c)), "bar") if press_c else 101.3
        outcome = _outcome_from_text(r.get(out_c)) if out_c else "marginal_spread"
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": press,
            "flow_cm_s": None,
            "material": material,
            "sample_geometry": "gaseous",
            "outcome_class": outcome or "marginal_spread",
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


def parse_acme_bre(df, acc):
    """PSI-20 ACME BRE: fuel, O2 percent, flames ignited -> outcome. No flow."""
    rows = []
    mat_c = find_col(df, ["fuel bottle", "fuel"])
    o2_c = find_col(df, ["oxygen conc", "oxygen", "o2"])
    out_c = find_col(df, ["flames ignited", "flames"])
    for _, r in df.iterrows():
        o2 = _num(r.get(o2_c)) if o2_c else None
        if o2 is None:
            continue
        material = _clean_material(r.get(mat_c)) if mat_c else "unknown"
        outcome = _outcome_from_text(r.get(out_c)) if out_c else "marginal_spread"
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": 101.3,
            "flow_cm_s": None,
            "material": material,
            "sample_geometry": "burner",
            "outcome_class": outcome or "marginal_spread",
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


def parse_flamedesign(df, acc):
    """PSI-10 Flame Design: O2, pressure atm, gaseous fuel. No flow."""
    rows = []
    mat_c = find_col(df, ["fuel"])
    o2_c = find_col(df, ["xo2", "o2"])
    press_c = find_col(df, ["pinit", "pmean", "pressure"])
    for _, r in df.iterrows():
        o2_frac = _num(r.get(o2_c)) if o2_c else None
        if o2_frac is None:
            continue
        o2 = o2_frac * 100.0 if o2_frac < 2 else o2_frac
        material = _clean_material(r.get(mat_c)) if mat_c else "unknown"
        press = _pressure_to_kpa(_num(r.get(press_c)), "atm") if press_c else 101.3
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": press,
            "flow_cm_s": None,
            "material": material,
            "sample_geometry": "gaseous",
            "outcome_class": "marginal_spread",
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


PARSERS = {
    "PSI-25": parse_bass_ii,
    "PSI-98": parse_saffire,
    "PSI-99": parse_saffire,
    "PSI-69": parse_flex,
    "PSI-68": parse_flex2,
    "PSI-39": parse_cfi,
    "PSI-159": parse_cfig,
    "PSI-20": parse_acme_bre,
    "PSI-10": parse_flamedesign,
}


def parse_file(path, acc):
    # PSI CSVs use mixed encodings; latin-1 never fails, utf-8 preferred.
    try:
        df = norm_cols(pd.read_csv(path, encoding="utf-8"))
    except UnicodeDecodeError:
        df = norm_cols(pd.read_csv(path, encoding="latin-1"))
    parser = PARSERS.get(acc)
    if parser:
        return parser(df, acc)
    mat_c = find_col(df, ["material", "fuel", "sample"])
    o2_c = find_col(df, ["o2", "oxygen", "xo2"])
    flow_c = find_col(df, ["flow", "air flow", "velocity"])
    rows = []
    for _, r in df.iterrows():
        o2 = _num(r.get(o2_c)) if o2_c else None
        if o2 is None:
            continue
        rows.append({
            "oxygen_pct": o2,
            "pressure_kpa": 101.3,
            "flow_cm_s": _num(r.get(flow_c)) if flow_c else None,
            "material": _clean_material(r.get(mat_c)) if mat_c else "unknown",
            "sample_geometry": "unknown",
            "outcome_class": "marginal_spread",
            "report_id": f"PSI {acc}",
            "source_url": f"https://psi.nasa.gov/studies/{acc}",
            "source_file": "psi_raw",
        })
    return rows


def load_prototype() -> pd.DataFrame:
    df = pd.read_csv(PROTOTYPE)
    rows = []
    for _, r in df.iterrows():
        o2 = r.get("o2_pct")
        if pd.isna(o2):
            continue
        rows.append({
            "oxygen_pct": float(o2),
            "pressure_kpa": float(r.get("pressure_kpa", 101.3)) if pd.notna(r.get("pressure_kpa")) else 101.3,
            "flow_cm_s": float(r.get("flow_cm_s")) if pd.notna(r.get("flow_cm_s")) else None,
            "material": str(r.get("material_id", "unknown")),
            "sample_geometry": str(r.get("geometry", "unknown")) if pd.notna(r.get("geometry")) else "unknown",
            "outcome_class": {"burned": "spread", "self_extinguished": "no_spread",
                              "no_ignition": "no_spread"}.get(str(r.get("outcome", "")).strip(), "marginal_spread"),
            "report_id": str(r.get("source_id", "NTRS-unknown")),
            "source_url": f"https://ntrs.nasa.gov/citations/{str(r.get('source_id', '')).replace('NTRS-','')}" if str(r.get("source_id", "")).startswith("NTRS-") else "",
            "source_file": "prototype",
        })
    return pd.DataFrame(rows)


def main():
    all_rows = []
    if CACHE.exists():
        for path in sorted(CACHE.glob("*.csv")):
            m = re.match(r"(PSI-\d+)", path.stem)
            acc = m.group(1) if m else "PSI-?"
            try:
                rows = parse_file(path, acc)
                print(f"{path.name}: {len(rows)} rows")
                all_rows.extend(rows)
            except Exception as e:
                print(f"{path.name}: ERROR {e}")

    proto = load_prototype()
    print(f"prototype: {len(proto)} rows")
    all_rows.extend(proto.to_dict("records"))

    # Deduplicate by (report_id, oxygen_pct, flow_cm_s, material)
    seen = set()
    deduped = []
    for r in all_rows:
        key = (r["report_id"], r["oxygen_pct"], r["flow_cm_s"], r["material"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    print(f"\nTotal unique rows: {len(deduped)}")

    df = pd.DataFrame(deduped)
    df = df.dropna(subset=["oxygen_pct"]).copy()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {OUT} ({len(df)} rows)")
    print(f"Wrote {OUT_CSV}")
    print("\nRows per report:")
    print(df.groupby("report_id").size().to_string())
    print("\nOutcome class distribution:")
    print(df["outcome_class"].value_counts().to_string())
    print("\nRows with flow_cm_s:", int(df["flow_cm_s"].notna().sum()), "of", len(df))


if __name__ == "__main__":
    main()

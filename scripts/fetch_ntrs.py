#!/usr/bin/env python3
"""Download the NASA Technical Reports Server (NTRS) papers FlameAtlas uses.

The curated list lives in data/sources/ntrs_papers.csv (one NTRS id per row).
For each id this saves the citation metadata and the PDF:
  data/raw/ntrs/<ntrs_id>.json
  data/raw/ntrs/<ntrs_id>.pdf
and writes data/raw/ntrs/manifest.csv. Re-running skips files already present.

Usage:
  python scripts/fetch_ntrs.py
  python scripts/fetch_ntrs.py --workers 4
Standard library only.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://ntrs.nasa.gov"
HERE = os.path.dirname(__file__)
LIST = os.path.join(HERE, "..", "data", "sources", "ntrs_papers.csv")
ROOT = os.path.join(HERE, "..", "data", "raw", "ntrs")


def get(url, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return r.read()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def fetch(row):
    nid = row["ntrs_id"]
    meta_path = os.path.join(ROOT, f"{nid}.json")
    pdf_path = os.path.join(ROOT, f"{nid}.pdf")
    try:
        if os.path.exists(meta_path):
            meta = json.load(open(meta_path))
        else:
            meta = json.loads(get(f"{API}/api/citations/{nid}"))
            with open(meta_path, "w") as fh:
                json.dump(meta, fh, indent=1)
        pdfs = [d["links"]["pdf"] for d in meta.get("downloads", []) if d.get("links", {}).get("pdf")]
        if not pdfs:
            return False, nid, meta, "no PDF available"
        if not os.path.exists(pdf_path):
            data = get(API + pdfs[0])
            if not data.startswith(b"%PDF"):
                return False, nid, meta, "response is not a PDF"
            with open(pdf_path + ".part", "wb") as fh:
                fh.write(data)
            os.replace(pdf_path + ".part", pdf_path)
        return True, nid, meta, f"{os.path.getsize(pdf_path) // 1024} KB"
    except Exception as e:
        return False, nid, None, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    os.makedirs(ROOT, exist_ok=True)
    rows = list(csv.DictReader(open(LIST)))

    out, failures = [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for (ok, nid, meta, msg), row in zip(pool.map(fetch, rows), rows):
            print(f"{'ok  ' if ok else 'FAIL'} {nid} {row['title'][:70]} ({msg})", flush=True)
            failures += not ok
            pubs = (meta or {}).get("publications") or [{}]
            authors = "; ".join(a.get("meta", {}).get("author", {}).get("name", "")
                                for a in (meta or {}).get("authorAffiliations", []))
            out.append([nid, row["experiment"], row["topic"], (meta or {}).get("title", row["title"]),
                        authors, (pubs[0].get("publicationDate") or "")[:10], (meta or {}).get("stiType", ""),
                        f"{API}/citations/{nid}", f"{nid}.pdf" if ok else ""])

    with open(os.path.join(ROOT, "manifest.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ntrs_id", "experiment", "topic", "title", "authors", "date", "type", "url", "local_pdf"])
        w.writerows(out)
    print(f"{len(rows)} papers, {failures} failed; manifest at {ROOT}/manifest.csv")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

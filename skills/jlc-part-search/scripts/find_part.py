#!/usr/bin/env python3
"""Parametric search of JLCPCB's parts library, through the yaqwsx/jlcparts
catalogue (MIT, https://yaqwsx.github.io/jlcparts/), for choosing board parts.

    find_part.py "Chip Resistor" --value 5.6k --package 0805
    find_part.py "Multilayer Ceramic" --value 10uF --package 1206 --voltage 25
    find_part.py "TVS" --voltage 24 --text SMBJ
    find_part.py "Chip Resistor" --value 1k --package 1206 --bom fab/bom-jlcpcb.csv

The first argument matches a category or subcategory (case-insensitive
substring). Results are ranked basic > preferred > extended (JLC's loading fee
and feeders), then by stock, then by price at --qty boards. With --bom (a JLC
BOM CSV with an "LCSC Part #" column), parts already on the board are flagged:
reusing one adds no BOM line.

The catalogue's manifest, attribute table and each category's shards are
cached for a day in ${XDG_CACHE_HOME:-~/.cache}/hardware-skills/jlcparts.
Exit status 1 if nothing matches.
"""

import argparse
import csv
import gzip
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = "https://yaqwsx.github.io/jlcparts/data/"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hardware-skills" / "jlcparts"
SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
CLASS_RANK = {"Basic": 0, "Preferred": 1, "Extended": 2}
LCSC_COLUMNS = ("LCSC Part #", "LCSC Part", "LCSC", "JLCPCB Part #", "LCSC Part Number")
REF_COLUMNS = ("Designator", "References", "Reference")


def get(name):
    """A catalogue file, through the cache."""
    path = CACHE / name
    if not (path.exists() and time.time() - path.stat().st_mtime < 86400):
        CACHE.mkdir(parents=True, exist_ok=True)
        # curl, not urllib: some bundled Pythons (KiCad's) have no CA certificates
        tmp = path.with_suffix(path.suffix + ".part")
        subprocess.run(["curl", "-sfL", "--max-time", "120", "-o", str(tmp), BASE + name], check=True)
        tmp.replace(path)
    data = path.read_bytes()
    if name.endswith(".gz"):
        data = gzip.decompress(data)
    return data.decode() if name.endswith(".jsonl.gz") else json.loads(data)


def column(fields, names):
    for n in names:
        for f in fields:
            if f.strip().lower() == n.lower():
                return f
    return None


def bom_parts(path):
    """{LCSC number: [refs]} from a BOM CSV."""
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = csv.DictReader(fh)
        lc, rc = column(rows.fieldnames or [], LCSC_COLUMNS), column(rows.fieldnames or [], REF_COLUMNS)
        if not lc:
            raise SystemExit(f"{path}: no LCSC column (looked for {', '.join(LCSC_COLUMNS)})")
        for r in rows:
            part = (r.get(lc) or "").strip()
            if part:
                refs = re.split(r"[,\s]+", (r.get(rc) or "").strip()) if rc else []
                out.setdefault(part, []).extend(x for x in refs if x)
    return out


def number(text):
    """'5.6k' -> 5600, '100nF' -> 1e-7, '4k7' -> 4700."""
    m = re.fullmatch(r"\s*([\d.]+)\s*([pnuµmkKMG]?)([\d]*)\s*[a-zA-ZΩ]*\s*", text)
    if not m:
        raise SystemExit(f"can't read the value {text!r}")
    whole = m.group(1) + ("." + m.group(3) if m.group(3) else "")
    return float(whole) * SI[m.group(2)]


def decode(row, header, lut):
    rec = {k: row[i] for k, i in header.items()}
    rec["attrs"] = {lut[idx][0]: lut[idx][1] for idx in rec.get("attributes") or []}
    return rec


def attr_value(spec, kind=None):
    """The primary (or a given kind's) number of an attribute, or its text."""
    vals = spec["values"]
    if kind:
        for v, k in vals.values():
            if k == kind:
                return v
        return None
    return vals[spec["primary"]][0]


def price_at(prices, qty):
    best = None
    for p in prices or []:
        if p["qFrom"] <= qty and (p["qTo"] is None or qty <= p["qTo"]):
            best = p["price"]
    return best if best is not None else (prices[0]["price"] if prices else float("inf"))


VALUE_KINDS = ("resistance", "capacitance", "inductance")
VOLTAGE_ATTR = re.compile(r"Voltage.*(Rated|Max|VRWM|Stand)|Rated Voltage|Voltage Rating|Reverse Stand")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("category", help="category or subcategory, substring")
    ap.add_argument("--value", help="resistance, capacitance or inductance, e.g. 5.6k, 100nF, 10uH")
    ap.add_argument("--package", help="package, substring (0805, SOT-23, SMB, ...)")
    ap.add_argument("--tolerance", type=float, help="at most this tolerance, percent")
    ap.add_argument("--voltage", type=float, help="at least this rated voltage (or TVS stand-off), volts")
    ap.add_argument("--text", help="substring of the maker part number or description")
    ap.add_argument("--qty", type=int, default=10, help="boards, for the price column (default 10)")
    ap.add_argument("--bom", help="JLC BOM CSV of the board: flag parts already on it")
    ap.add_argument("-n", type=int, default=15, help="rows to show (default 15)")
    a = ap.parse_args()

    on_board = bom_parts(a.bom) if a.bom else {}
    manifest = get("manifest.json")
    lut = get(manifest["attributesLut"])
    cats = [c for c in manifest["categories"]
            if a.category.lower() in (c["category"] + " / " + c["subcategory"]).lower()]
    if not cats:
        raise SystemExit(f"no category matches {a.category!r}")
    want = number(a.value) if a.value else None
    hits = []
    for c in cats:
        for shard in c["shards"]:
            lines = get(shard).splitlines()
            header = json.loads(lines[0])
            for line in lines[1:]:
                r = decode(json.loads(line), header, lut)
                at = r["attrs"]
                if a.text and a.text.lower() not in f'{r["mfr"]} {r["description"]}'.lower():
                    continue
                pkg = attr_value(at["Package"]) if "Package" in at else ""
                if a.package and a.package.lower() not in str(pkg).lower():
                    continue
                if want is not None:
                    got = None
                    for spec in at.values():
                        for kind in VALUE_KINDS:
                            v = attr_value(spec, kind)
                            if v is not None:
                                got = v
                    if got is None or abs(got - want) > want * 1e-6:
                        continue
                if a.tolerance is not None:
                    tol = at.get("Tolerance")
                    t = attr_value(tol, "percentage") if tol else None
                    if t is None or abs(t) > a.tolerance + 1e-9:
                        continue
                if a.voltage is not None:
                    vs = [attr_value(spec, "voltage") for name, spec in at.items() if VOLTAGE_ATTR.search(name)]
                    vs = [v for v in vs if v is not None]
                    if not vs or max(vs) < a.voltage:
                        continue
                cls = attr_value(at["Basic/Extended"]) if "Basic/Extended" in at else "Extended"
                hits.append((CLASS_RANK.get(cls, 3), -(r["stock"] or 0), price_at(r["price"], a.qty),
                             r["lcsc"], cls, r["stock"] or 0, r["mfr"], str(pkg), r["description"]))
    hits.sort()
    print(f"{len(hits)} match(es) in {len(cats)} categor{'y' if len(cats) == 1 else 'ies'}"
          f" (catalogue of {manifest['created'][:10]}; price at {a.qty})")
    for _, _, price, lcsc, cls, stock, mfr, pkg, desc in hits[:a.n]:
        mark = f"  <- on board: {' '.join(on_board[lcsc]) or 'yes'}" if lcsc in on_board else ""
        print(f"  {lcsc:10s} {cls:9s} {stock:>9}  ${price:<8.4f} {mfr[:24]:24s} {pkg[:14]:14s} {desc[:60]}{mark}")
    reused = [h for h in hits if h[3] in on_board]
    if a.bom:
        print(f"{len(reused)} of the matches already on the board" +
              (f": {', '.join(h[3] for h in reused)}" if reused else ""))
    return 0 if hits else 1


if __name__ == "__main__":
    sys.exit(main())

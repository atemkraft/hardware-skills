#!/usr/bin/env python3
"""Checks a board's JLCPCB assembly files against JLC's own parts before ordering.

Run with KiCad's Python (it needs pcbnew), with network access:

    check_jlc.py --pcb board.kicad_pcb --bom bom-jlcpcb.csv --cpl cpl-jlcpcb.csv [--boards 10]
                 [--hand-solder J1,J2] [--skip-prefix Connector_Molex:,MyLib:Terminal]
                 [--shape-only SW1,J3]

1. Placement. JLC places each part with its footprint from the EasyEDA
   library (JLCEDA/EasyEDA official library, https://easyeda.com), at the
   CPL's Mid X/Y and rotation. For every part in the CPL this takes that
   footprint, puts it where JLC will, and checks every one of its pads lands
   on the board's pad with the same number. A part that only fits turned by
   90/180/270 degrees (pin 1 on the wrong side), or off-centre, fails, with the
   rotation that would fit.
2. BOM. Each line's LCSC part must exist, and be in stock at JLC for
   `--boards` boards. Basic/preferred/extended is listed (extended parts carry
   a fee), and a rough assembly cost.

Parts given with --hand-solder (references) or --skip-prefix (footprint
library-id prefixes) are ones JLC won't place by machine (hand-soldered
through-hole, or fitted by you): their placement isn't checked and they count
as hand-soldered lines. Their BOM line is still checked.

Footprints and part data are cached in ${XDG_CACHE_HOME:-~/.cache}/hardware-skills/
jlc-cache (EasyEDA's library terms ask that its content not be redistributed:
keep the cache out of your repository). Exits 1 on any problem, 2 on bad input.
"""

import argparse
import csv
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hardware-skills" / "jlc-cache"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
UNIT = 0.254          # EasyEDA classic footprint unit: 10 mil
LCSC_COLUMNS = ("LCSC Part #", "LCSC Part", "LCSC", "JLCPCB Part #", "LCSC Part Number")
REF_COLUMNS = ("Designator", "References", "Reference")

# Rough JLC prices (US$, late 2026; JLC's quote has the last word).
# Standard PCBA: a loading fee for every SMT part line (basic ones too); THT
# lines are hand-soldered. Moisture-sensitive parts (MSL 4 and up) are baked
# first, for a fee per order and about 2 days.
LOADING_FEE = 1.53
# Economic PCBA: no loading fee for basic and preferred parts, a fee for each
# extended SMT line.
ECONOMIC_EXT_FEE = 3.00
BAKING_FEE = 7.94


def fetch(url, data=None, name=None):
    path = CACHE / name if name else None
    if path and path.exists() and time.time() - path.stat().st_mtime < 86400:
        return json.loads(path.read_text())
    # curl, not urllib: KiCad's bundled Python has no CA certificates
    cmd = ["curl", "-s", "--max-time", "30", "-A", UA, "-H", "Content-Type: application/json", url]
    if data:
        cmd[1:1] = ["-X", "POST", "--data-binary", data.decode()]
    for attempt in range(3):
        try:
            out = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
            break
        except Exception:                       # noqa: BLE001 (retry anything network-ish)
            if attempt == 2:
                # A footprint doesn't change: an older copy beats no check (stock does
                # change, so the BOM lookups' copies are only a day old at most).
                if path and path.exists() and name.endswith("-fp.json"):
                    print(f"   (EasyEDA unreachable: {name} from the cache)", file=sys.stderr)
                    return json.loads(path.read_text())
                raise
            time.sleep(2)
    if path:
        path.write_text(json.dumps(out))
    return out


def easyeda_pads(lcsc):
    """JLC's footprint for a part: {pad number: [(x, y) mm, y down, from its origin]},
    its package name, and {pad number: pin name} from the part's symbol."""
    d = fetch(f"https://easyeda.com/api/products/{lcsc}/components?version=6.4.19.5", name=f"{lcsc}-fp.json")
    r = d.get("result") or {}
    pk = r.get("packageDetail") or {}
    ds = pk.get("dataStr") or {}
    head = ds.get("head") or {}
    ox, oy = float(head.get("x", 0)), float(head.get("y", 0))
    pads = {}
    for sh in ds.get("shape") or []:
        if sh.startswith("PAD~"):
            f = sh.split("~")
            pads.setdefault(f[8], []).append(((float(f[2]) - ox) * UNIT, (float(f[3]) - oy) * UNIT))
    names = {}
    # An SMD electrolytic's outline is chamfered on its + side: name that pad "+"
    names_cap, diag = {}, []
    for sh in ds.get("shape") or []:
        f = sh.split("~")
        if f[0] == "TRACK" and len(f) > 4 and f[2] == "3":           # top silkscreen polyline
            v = list(map(float, f[4].split()))
            pts = [((v[k] - ox) * UNIT, (v[k + 1] - oy) * UNIT) for k in range(0, len(v) - 1, 2)]
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                if abs(ax - bx) > 0.3 and abs(ay - by) > 0.3:     # a diagonal edge: the chamfer
                    diag.append((ax + bx) / 2)
    if diag and len(pads) == 2:
        side = 1 if sum(diag) > 0 else -1
        plus = max(pads, key=lambda n: side * pads[n][0][0])
        names_cap = {n: ("+" if n == plus else "-") for n in pads}
    # Symbol pins: P~show~type~spice index~x~y~...^^...^^path^^name text^^number text,
    # each text "show~x~y~rot~TEXT~...". The spice index isn't always the pad number,
    # so the pad number comes from the number text.
    for sh in (r.get("dataStr") or {}).get("shape") or []:
        if sh.startswith("P~"):
            segs = sh.split("^^")
            if len(segs) < 5:
                continue
            name, num = segs[3].split("~"), segs[4].split("~")
            if len(name) > 4 and len(num) > 4 and num[4]:
                names[num[4]] = name[4]
    for n, nm in names_cap.items():
        if names.get(n, n) in ("1", "2", n):
            names[n] = nm
    return pads, pk.get("title", "?"), names


def jlc_part(lcsc):
    body = json.dumps({"keyword": lcsc, "currentPage": 1, "pageSize": 10}).encode()
    d = fetch("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList",
              body, f"{lcsc}-jlc.json")
    for c in ((d.get("data") or {}).get("componentPageInfo") or {}).get("list") or []:
        if c.get("componentCode") == lcsc:
            return c
    return None


def jlc_detail(lcsc):
    """JLC's part page data: assembly process (SMT / THT) and moisture level."""
    d = fetch(f"https://cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode={lcsc}",
              name=f"{lcsc}-detail.json")
    return d.get("data") or {}


def price_at(prices, qty):
    best = None
    for p in prices or []:
        if p["startNumber"] <= qty and (not p.get("endNumber") or p["endNumber"] < 0 or qty <= p["endNumber"]):
            best = p["productPrice"]
    return best if best is not None else (prices[-1]["productPrice"] if prices else 0.0)


def column(fields, names):
    for n in names:
        for f in fields:
            if f.strip().lower() == n.lower():
                return f
    return None


def read_bom(path):
    """[(lcsc, [refs], comment)] in file order, one per BOM line."""
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = csv.DictReader(fh)
        lc, rc = column(rows.fieldnames or [], LCSC_COLUMNS), column(rows.fieldnames or [], REF_COLUMNS)
        if not (lc and rc):
            sys.exit(f"{path}: needs a designator and an LCSC column (e.g. Designator, LCSC Part #)")
        cc = column(rows.fieldnames, ("Comment", "Value"))
        for r in rows:
            refs = [x for x in re.split(r"[,\s]+", (r.get(rc) or "").strip()) if x]
            out.append(((r.get(lc) or "").strip(), refs, (r.get(cc) or "").strip() if cc else ""))
    return out


def read_cpl(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return []
    f = rows[0].keys()
    ref = column(f, ("Designator", "Ref"))
    x, y = column(f, ("Mid X", "PosX", "X")), column(f, ("Mid Y", "PosY", "Y"))
    rot, layer = column(f, ("Rotation", "Rot")), column(f, ("Layer", "Side"))
    if not all((ref, x, y, rot)):
        sys.exit(f"{path}: needs Designator, Mid X, Mid Y and Rotation columns")
    mm = lambda s: float(re.sub(r"\s*mm\s*$", "", s.strip()))   # noqa: E731
    return [(r[ref].strip(), mm(r[x]), mm(r[y]), float(r[rot]), (r.get(layer) or "Top").strip() if layer else "Top")
            for r in rows]


class Part:
    def __init__(self, fp, pcbnew, origin):
        self.ref = fp.GetReference()
        self.value = fp.GetValue()
        self.footprint = fp.GetFPID().GetUniStringLibId()
        self.tht = bool(fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE)
        ox, oy = origin
        pos = fp.GetPosition()
        self.pos = (pcbnew.ToMM(pos.x) - ox, oy - pcbnew.ToMM(pos.y))
        self.pads = []
        self.pinfn = {}
        for pd in fp.Pads():
            if pd.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH or not pd.GetNumber():
                continue
            bb = pd.GetBoundingBox()
            self.pads.append((pd.GetNumber(), pcbnew.ToMM(bb.GetLeft()) - ox, oy - pcbnew.ToMM(bb.GetBottom()),
                              pcbnew.ToMM(bb.GetRight()) - ox, oy - pcbnew.ToMM(bb.GetTop())))
            if pd.GetPinFunction():
                self.pinfn[pd.GetNumber()] = pd.GetPinFunction()


def board_parts(pcb):
    """ref -> Part, with pads as boxes in CPL coordinates (mm, y up), and which
    origin the CPL uses is decided later: returns {origin name: (origin, parts)}."""
    import pcbnew
    board = pcbnew.LoadBoard(str(pcb))
    edge = board.GetBoardEdgesBoundingBox()
    ds = board.GetDesignSettings()
    origins = {"board edge, bottom-left": (pcbnew.ToMM(edge.GetLeft()), pcbnew.ToMM(edge.GetBottom()))}
    for name, getter in (("drill/place (aux) origin", "GetAuxOrigin"), ("grid origin", "GetGridOrigin")):
        try:
            o = getattr(ds, getter)()
            origins[name] = (pcbnew.ToMM(o.x), pcbnew.ToMM(o.y))
        except AttributeError:
            pass
    origins.setdefault("page origin", (0.0, 0.0))
    fps = list(board.GetFootprints())
    return {n: (o, {fp.GetReference(): Part(fp, pcbnew, o) for fp in fps}) for n, o in origins.items()}


def pick_origin(candidates, cpl):
    """The origin under which the CPL's positions best match the footprints'."""
    best = None
    for name, (o, parts) in candidates.items():
        d = [math.hypot(x - parts[ref].pos[0], y - parts[ref].pos[1]) for ref, x, y, _, side in cpl
             if ref in parts and side.lower().startswith("t")]
        if d:
            med = statistics.median(d)
            if best is None or med < best[0]:
                best = (med, name, parts)
    return best


def place(pads, x, y, rot):
    """JLC's pads (y down) where JLC puts them: rotated `rot` degrees CCW about the
    footprint origin, which goes at (x, y), y up."""
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return {n: [(x + px * c + py * s, y + px * s - py * c) for px, py in pts] for n, pts in pads.items()}


# KiCad's standard-library pin names, where a pad number alone doesn't say which end
# is which (JLC often numbers LEDs A = 1, K = 2; KiCad K = 1, A = 2).
POLAR_NAMES = ({"K", "A"}, {"+", "-"})
DIODE_FP = re.compile(r"^(Diode_SMD|Diode_THT|LED_SMD|LED_THT):(D_|LED_)", re.I)
POLCAP_FP = re.compile(r":(CP_|C_Elec|CP_Elec|C_Tantalum|CP_Tantalum)", re.I)
SWITCH_FP = re.compile(r"^Button_Switch_\w+:SW_", re.I)


def polar_names(part):
    """{our pad number: pin name} for a two-terminal polarised part, else None."""
    fn = {n: v.upper() for n, v in part.pinfn.items() if v.upper() in ("K", "A", "+", "-")}
    if len(fn) == 2:
        return fn
    numbers = {p[0] for p in part.pads}
    if numbers != {"1", "2"}:
        return None
    if DIODE_FP.search(part.footprint):
        return {"1": "K", "2": "A"}
    if POLCAP_FP.search(part.footprint):
        return {"1": "+", "2": "-"}
    return None


def targets(num, part, jlc_names, shape_only):
    """Which of our pads JLC's pad `num` must land on."""
    our = part.pads
    ours = polar_names(part)
    name = jlc_names.get(num)
    if ours and any({name} <= s and set(ours.values()) <= s for s in POLAR_NAMES):
        want = [n for n, nm in ours.items() if nm == name]
        return [b for b in our if b[0] in want]
    if shape_only or (SWITCH_FP.search(part.footprint) and len(our) == 4):
        return our                       # e.g. a 4-pad switch, two pairs: the shape decides
    tokens = re.findall(r"[AB]\d+", num) if re.fullmatch(r"([AB]\d+)+", num) else [num]
    hit = [b for b in our if b[0] in tokens]
    if not hit and num in "1234" and any(b[0] == "S1" for b in our):   # USB-C shell stakes: S1 in KiCad
        hit = [b for b in our if b[0] == "S1"]
    numeric = [int(b[0]) for b in our if b[0].isdigit()]
    if not hit and any(b[0] == "MP" for b in our) and num.isdigit() and numeric \
            and int(num) > max(numeric):                 # mounting stakes: JLC numbers them on
        hit = [b for b in our if b[0] == "MP"]
    if not hit and num == "4" and len(our) == 4 and not any(b[0] == "4" for b in our):
        hit = [b for b in our if b[0] == "2"]              # SOT-223: JLC numbers the tab 4, KiCad 2
    return hit


def fit(placed, part, jlc_names, shape_only, slack=0.05):
    """(ok, detail): every JLC pad inside one of the pads it belongs on, and
    every one of our pads covered by some JLC pad."""
    covered = set()
    for num, pts in placed.items():
        tg = targets(num, part, jlc_names, shape_only)
        if not tg:
            return False, f"pad {num}: no pad of ours with that number"
        for (px, py) in pts:
            inside = [b for b in tg if b[1] - slack <= px <= b[3] + slack and b[2] - slack <= py <= b[4] + slack]
            if not inside:
                d = min(math.hypot(px - (b[1] + b[3]) / 2, py - (b[2] + b[4]) / 2) for b in tg)
                return False, f"pad {num} misses ours by {d:.2f} mm"
            covered.update(id(b) for b in inside)
    missing = [b[0] for b in part.pads if id(b) not in covered]
    if missing:
        return False, f"our pad(s) {', '.join(sorted(set(missing)))} get no pin"
    return True, ""


def split_list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pcb", required=True, help="the .kicad_pcb the fab files were made from")
    ap.add_argument("--bom", required=True, help="JLC BOM CSV (Comment, Designator, Footprint, LCSC Part #)")
    ap.add_argument("--cpl", required=True, help="JLC CPL CSV (Designator, Mid X, Mid Y, Layer, Rotation)")
    ap.add_argument("--boards", type=int, default=10, help="boards assembled, for the stock check (default 10)")
    ap.add_argument("--hand-solder", default="", help="references JLC won't place, comma-separated")
    ap.add_argument("--skip-prefix", default="",
                    help="footprint library-id prefixes JLC won't place, comma-separated (e.g. Connector_Molex:)")
    ap.add_argument("--shape-only", default="",
                    help="references whose pads match by shape, not number (e.g. a 2xN socket numbered differently)")
    a = ap.parse_args()
    for p in (a.pcb, a.bom, a.cpl):
        if not Path(p).is_file():
            print(f"no such file: {p}", file=sys.stderr)
            return 2
    hand, prefixes, shape_only = set(split_list(a.hand_solder)), tuple(split_list(a.skip_prefix)), \
        set(split_list(a.shape_only))
    CACHE.mkdir(parents=True, exist_ok=True)

    bom = read_bom(a.bom)
    cpl = read_cpl(a.cpl)
    lcsc_of = {ref: lc for lc, refs, _ in bom if lc for ref in refs}
    best = pick_origin(board_parts(a.pcb), cpl)
    if best is None:
        print("no CPL designator is on the board", file=sys.stderr)
        return 2
    med, origin_name, parts = best
    failed = []

    def skipped(ref):
        p = parts.get(ref)
        return ref in hand or bool(prefixes and p is not None and p.footprint.startswith(prefixes))

    print(f"== placement: {Path(a.cpl).name} against JLC's (EasyEDA) footprints"
          f" (CPL origin: {origin_name}, median offset {med:.2f} mm)")
    if med > 1.0:
        print("   (the CPL's positions don't match the footprints' under any origin: expect misses)")
    unchecked = []
    for ref, x, y, rot, side in cpl:
        part = parts.get(ref)
        if part is None:
            print(f"   FAIL {ref:5s} in the CPL, not on the board")
            failed.append(ref)
            continue
        if skipped(ref):
            print(f"   skip {ref:5s} {part.footprint}: hand-soldered, placement not checked")
            unchecked.append(ref)
            continue
        if ref not in lcsc_of:
            print(f"   FAIL {ref:5s} in the CPL, no LCSC part in the BOM")
            failed.append(ref)
            continue
        if not side.lower().startswith("t"):
            print(f"   skip {ref:5s} on the {side} side: bottom placement not checked")
            unchecked.append(ref)
            continue
        try:
            pads, pkg, names = easyeda_pads(lcsc_of[ref])
        except Exception as e:                  # noqa: BLE001
            print(f"   ?    {ref:5s} {lcsc_of[ref]}: no footprint ({e})")
            failed.append(ref)
            continue
        if not pads:
            print(f"   ?    {ref:5s} {lcsc_of[ref]}: EasyEDA has no pads for it")
            failed.append(ref)
            continue
        so = ref in shape_only
        ok, why = fit(place(pads, x, y, rot), part, names, so)
        if ok:
            print(f"   ok   {ref:5s} {rot:5.0f}  {pkg}")
            continue
        alt = [d for d in (90, 180, 270) if fit(place(pads, x, y, rot + d), part, names, so)[0]]
        hint = f"fits at {(rot + alt[0]) % 360:.0f} (add {alt[0]})" if alt else "no rotation fits"
        print(f"   FAIL {ref:5s} {rot:5.0f}  {pkg}: {why}; {hint}")
        failed.append(ref)
    in_cpl = {r[0] for r in cpl}
    for lc, refs, _ in bom:
        for ref in refs:
            if lc and ref not in in_cpl and not skipped(ref):
                print(f"   FAIL {ref:5s} in the BOM ({lc}), not in the CPL")
                failed.append(ref)

    print(f"== BOM: {Path(a.bom).name}, stock for {a.boards} boards")
    cost = {"smt": 0, "tht": 0, "ext": 0, "pref": 0, "econ_ext": 0, "msl": [], "parts": 0.0}
    for lc, refs, comment in bom:
        if not lc:
            print(f"   --   {'':10s} {' '.join(refs)}: no LCSC part (not assembled by JLC)")
            continue
        try:
            c = jlc_part(lc)
        except Exception as e:                  # noqa: BLE001
            print(f"   ?    {lc:10s} {' '.join(refs)}: JLC lookup failed ({e})")
            failed.append(lc)
            continue
        if not c:
            print(f"   FAIL {lc:10s} {' '.join(refs)}: not in JLC's parts library")
            failed.append(lc)
            continue
        need = len(refs) * a.boards
        stock = c.get("stockCount") or 0
        kind = ("basic" if c.get("componentLibraryType") == "base"
                else "preferred" if c.get("preferredComponentFlag") else "extended")
        try:
            det = jlc_detail(lc)
        except Exception:                       # noqa: BLE001 (cost only; the fit check stands)
            det = {}
        tht = det.get("assemblyProcess") == "THT" or any(
            skipped(r) or (parts.get(r) is not None and parts[r].tht) for r in refs)
        cost["tht" if tht else "smt"] += 1
        cost["ext"] += kind != "basic"
        cost["pref"] += kind == "preferred"
        cost["econ_ext"] += (not tht) and kind == "extended"
        msl = det.get("moistureSensitivityLevelEn") or ""
        if re.search(r"MSL ?([4-6])", msl):
            cost["msl"].append(f"{lc} {c.get('componentModelEn', '')} ({msl})")
        cost["parts"] += price_at(c.get("componentPrices"), need) * len(refs)
        notes = []
        if stock < need:
            notes.append(f"stock {stock} < {need} needed")
        missing = [r for r in refs if r not in parts]
        if missing:
            notes.append(f"not on the board: {' '.join(missing)}")
        tag = "FAIL" if notes else "ok  "
        print(f"   {tag} {lc:10s} {kind:9s} {'THT' if tht else 'SMT'} stock {stock:>8}  "
              f"{c.get('componentModelEn', '')[:28]:28s} {' '.join(refs)}" + (f"  <- {'; '.join(notes)}" if notes else ""))
        if notes:
            failed.append(lc)

    lines = cost["smt"] + cost["tht"]
    print(f"== cost ({a.boards} boards, Standard PCBA, rough): {lines} BOM lines, {cost['smt']} SMT x"
          f" US${LOADING_FEE:.2f} loading = US${cost['smt'] * LOADING_FEE:.2f}/order; {cost['tht']} THT lines"
          f" hand-soldered; {cost['ext']} extended ({cost['pref']} of them preferred);"
          f" parts US${cost['parts']:.2f}/board")
    print(f"== cost (Economic PCBA, rough): {cost['econ_ext']} extended SMT lines x US${ECONOMIC_EXT_FEE:.2f}"
          f" = US${cost['econ_ext'] * ECONOMIC_EXT_FEE:.2f}/order (basic and preferred load free)")
    for m in cost["msl"]:
        print(f"   bake {m}: JLC bakes it first, about US${BAKING_FEE:.2f} per order and 2 days")
    if unchecked:
        print(f"== placement not checked for {len(unchecked)}: {', '.join(unchecked)}")
    print(f"== {len(failed)} problem(s)" + (f": {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

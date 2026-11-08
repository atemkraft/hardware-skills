#!/usr/bin/env python3
"""Printability review of FDM parts, from the slicer project itself (3MF) so every part
is checked in the orientation it prints in. Plain Python; PIL for the plots.

    print_review.py <out dir> <project.3mf | part.stl> ... [--material PETG] [--config print-review.json]

For each object on each plate it finds the downward-facing surfaces (the ones a
printer lays over air) and sorts them:
  - bridge: a flat ceiling held in two or more separate places (or all round); its
    span is twice its farthest point from support; flagged over the material's
    bridge limit (sag);
  - ledge: any other held flat overhang; flagged when its farthest point is more than
    ledge_max_mm from the nearest edge that holds it (it droops: box 1.6's 0.8 mm
    flat roof on the face-gasket pocket is the example that prompted this check);
  - island: a downward surface held on no side (a floating start, needs support);
  - steep overhang: sloped downward faces past overhang_max_deg from vertical, by
    area (the tops of horizontal holes show up here: use a teardrop or a chamfer).
It also reports the first-layer contact area (adhesion, warping), parts taller than
tall_ratio x their narrowest base side (wobble), and whether everything fits the bed.
Not checked: wall thickness against the nozzle, internal stresses, support settings,
anything the slicer adds (supports, brims). Run the slicer too.

Config (all optional): {"bed_mm": [256, 256], "overhang_max_deg": 45,
"bridge_max_mm": {"PETG": 15, "PLA": 20, "TPU": 5, "*": 10}, "ledge_max_mm": 0.5,
"min_area_mm2": 2,
"tall_ratio": 5, "material": {"<3mf file name>": "PETG", ...}}
"""
import json
import math
import os
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
DEF = {"bed_mm": [256, 256], "overhang_max_deg": 45,
       "bridge_max_mm": {"PETG": 15, "PLA": 20, "TPU": 5, "*": 10},
       "ledge_max_mm": 0.5, "min_area_mm2": 2, "tall_ratio": 5, "material": {}}


def mat(t):
    v = [float(x) for x in t.split()] if t else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
    return v


def apply(m, p):
    x, y, z = p
    return (x * m[0] + y * m[3] + z * m[6] + m[9], x * m[1] + y * m[4] + z * m[7] + m[10],
            x * m[2] + y * m[5] + z * m[8] + m[11])


def compose(a, b):
    """a then b (3MF row-vector convention)."""
    out = []
    for i in range(3):
        for j in range(3):
            out.append(sum(a[i * 3 + k] * b[k * 3 + j] for k in range(3)))
    t = apply(b, (a[9], a[10], a[11]))
    return out + list(t)


def read_3mf(path):
    """[(name, plate item index, triangles as ((x,y,z),(x,y,z),(x,y,z)))] in plate coordinates."""
    z = zipfile.ZipFile(path)
    files = {n: ET.fromstring(z.read(n)) for n in z.namelist() if n.endswith(".model")}
    objs = {}
    for fname, root in files.items():
        for o in root.iter(NS + "object"):
            objs[(fname, o.get("id"))] = o

    def tris(fname, oid, m):
        o = objs[(fname, oid)]
        mesh = o.find(NS + "mesh")
        out = []
        if mesh is not None:
            vs = [apply(m, (float(v.get("x")), float(v.get("y")), float(v.get("z"))))
                  for v in mesh.find(NS + "vertices")]
            for t in mesh.find(NS + "triangles"):
                out.append((vs[int(t.get("v1"))], vs[int(t.get("v2"))], vs[int(t.get("v3"))]))
        comps = o.find(NS + "components")
        if comps is not None:
            for c in comps:
                ref = c.get("{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path") or c.get("path")
                f2 = ref.lstrip("/") if ref else fname
                out += tris(f2, c.get("objectid"), compose(mat(c.get("transform")), m))
        return out
    root_name = next(n for n in files if n.endswith("3dmodel.model"))
    out = []
    for k, it in enumerate(files[root_name].iter(NS + "item")):
        o = objs[(root_name, it.get("objectid"))]
        out.append((o.get("name") or f"object {it.get('objectid')}", k, tris(root_name, it.get("objectid"), mat(it.get("transform")))))
    return out


def read_stl(path):
    data = open(path, "rb").read()
    if data[:5] == b"solid" and b"facet" in data[:400]:
        nums = [float(x) for x in re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data) for x in x]
        t = [tuple(tuple(nums[i + 3 * k:i + 3 * k + 3]) for k in range(3)) for i in range(0, len(nums), 9)]
    else:
        n = struct.unpack("<I", data[80:84])[0]
        t = []
        for i in range(n):
            v = struct.unpack("<12f", data[84 + 50 * i: 84 + 50 * i + 48])
            t.append((v[3:6], v[6:9], v[9:12]))
    return [(os.path.basename(path), 0, t)]


def normal_area(t):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    L = math.sqrt(nx * nx + ny * ny + nz * nz)
    return ((nx / L, ny / L, nz / L), L / 2) if L > 0 else ((0, 0, 0), 0)


def key(p):
    return (round(p[0], 3), round(p[1], 3), round(p[2], 3))


def analyse(tris, cfg, material):
    zmin = min(min(p[2] for p in t) for t in tris)
    xs = [p[0] for t in tris for p in t]; ys = [p[1] for t in tris for p in t]
    height = max(p[2] for t in tris for p in t) - zmin
    cos_lim = math.cos(math.radians(90 - cfg["overhang_max_deg"]))   # |nz| above this = past the limit
    info = []
    edge_owner = defaultdict(list)
    for i, t in enumerate(tris):
        n, a = normal_area(t)
        info.append((n, a))
        for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edge_owner[tuple(sorted((key(e[0]), key(e[1]))))].append(i)
    on_bed = lambda t: max(p[2] for p in t) - zmin < 0.05
    contact = sum(a for (n, a), t in zip(info, tris) if n[2] < -0.98 and on_bed(t))
    flat = {i for i, ((n, a), t) in enumerate(zip(info, tris)) if n[2] < -0.98 and not on_bed(t) and a > 0}
    # A downward face lying on an upward face at the same height is an internal seam
    # (two solids that touch but weren't merged), not a surface over air: drop it.
    ups = defaultdict(list)
    for i, ((n, a), t) in enumerate(zip(info, tris)):
        if n[2] > 0.98:
            z = round(sum(p[2] for p in t) / 3, 2)
            for bx in range(int(min(p[0] for p in t) // 5), int(max(p[0] for p in t) // 5) + 1):
                for by in range(int(min(p[1] for p in t) // 5), int(max(p[1] for p in t) // 5) + 1):
                    ups[(z, bx, by)].append(t)

    def inside(pt, t):
        (x1, y1, _), (x2, y2, _), (x3, y3, _) = t
        d = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(d) < 1e-12:
            return False
        l1 = ((y2 - y3) * (pt[0] - x3) + (x3 - x2) * (pt[1] - y3)) / d
        l2 = ((y3 - y1) * (pt[0] - x3) + (x1 - x3) * (pt[1] - y3)) / d
        return l1 >= -1e-6 and l2 >= -1e-6 and 1 - l1 - l2 >= -1e-6
    seams = set()
    for i in flat:
        t = tris[i]
        c = (sum(p[0] for p in t) / 3, sum(p[1] for p in t) / 3)
        z = round(sum(p[2] for p in t) / 3, 2)
        if any(inside(c, u) for u in ups.get((z, int(c[0] // 5), int(c[1] // 5)), ())):
            seams.add(i)
    flat -= seams
    steep = {i for i, ((n, a), t) in enumerate(zip(info, tris)) if -0.98 <= n[2] < -cos_lim - 0.01 and not on_bed(t)}

    def clusters(sel):
        seen, out = set(), []
        for s in sel:
            if s in seen:
                continue
            stack, comp = [s], []
            seen.add(s)
            while stack:
                i = stack.pop(); comp.append(i)
                t = tris[i]
                for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                    for j in edge_owner[tuple(sorted((key(e[0]), key(e[1]))))]:
                        if j in sel and j not in seen:
                            seen.add(j); stack.append(j)
            out.append(comp)
        return out
    bridge_max = cfg["bridge_max_mm"].get(material, cfg["bridge_max_mm"].get("*", 10))
    found = []
    for comp in clusters(flat):
        area = sum(info[i][1] for i in comp)
        if area < 0.2:
            continue
        pts = [p for i in comp for p in tris[i]]
        bx0, bx1 = min(p[0] for p in pts), max(p[0] for p in pts)
        by0, by1 = min(p[1] for p in pts), max(p[1] for p in pts)
        z = sum(p[2] for p in pts) / len(pts) - zmin
        # which sides of the region are held: boundary edges shared with a wall that goes down
        sides, held, held_keys = set(), [], []
        free_len = held_len = 0.0
        cs = set(comp)
        for i in comp:
            t = tris[i]
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                owners = [j for j in edge_owner[tuple(sorted((key(e[0]), key(e[1]))))] if j not in cs]
                if not owners:
                    continue
                elen = math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1])
                is_held = False
                for j in owners:
                    n2 = info[j][0]
                    lowest = min(p[2] for p in tris[j])
                    if abs(n2[2]) < 0.95 and lowest < e[0][2] - 0.05:    # a wall (or slope) below this edge
                        is_held = True
                        held.append(((e[0][0], e[0][1]), (e[1][0], e[1][1])))
                        held_keys.append((key(e[0]), key(e[1])))
                        dxn, dyn = n2[0], n2[1]
                        # the wall's outward normal points away from the region: the side is opposite
                        if abs(dxn) > abs(dyn):
                            sides.add("x-" if dxn > 0 else "x+")
                        else:
                            sides.add("y-" if dyn > 0 else "y+")
                if is_held:
                    held_len += elen
                else:
                    free_len += elen
        w, d = bx1 - bx0, by1 - by0
        small = area < cfg["min_area_mm2"]

        def seg_d(p, a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            u = 0 if L2 == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
            return math.hypot(p[0] - a[0] - u * dx, p[1] - a[1] - u * dy)
        samples = [(sum(p[0] for p in tris[i]) / 3, sum(p[1] for p in tris[i]) / 3) for i in comp] + [(p[0], p[1]) for p in pts]
        reach = max(min(seg_d(s, a, b) for a, b in held) for s in samples) if held else None
        # separate places that hold it: held edges joined end to end are one place
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]; a = parent[a]
            return a
        for a, b in held_keys:
            parent[find(a)] = find(b)
        groups = len({find(a) for a, _ in held_keys})
        enclosed = held and free_len < 0.05 * (free_len + held_len)
        if enclosed:
            span = 2 * reach
            kind, size, bad = "bridge", span, span > bridge_max and not small
            why = f"ceiling held all round, about {span:.1f} mm across (limit {bridge_max} mm, {material})"
        elif held and groups >= 2:
            # a point is bridged if its two nearest supports (in different places) are on
            # opposite sides of it; otherwise it hangs off the nearer one (an arm)
            gid = [find(a) for a, _ in held_keys]
            def nearest(s, skip=None):
                best = (1e9, None, None)
                for (a, b), g in zip(held, gid):
                    if g == skip:
                        continue
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    L2 = dx * dx + dy * dy
                    u = 0 if L2 == 0 else max(0, min(1, ((s[0] - a[0]) * dx + (s[1] - a[1]) * dy) / L2))
                    q = (a[0] + u * dx, a[1] + u * dy)
                    dd = math.hypot(s[0] - q[0], s[1] - q[1])
                    if dd < best[0]:
                        best = (dd, g, q)
                return best
            # A printer lays a bridge as straight lines from one support to the other, so a
            # point is bridged only if it lies near the line between its two nearest supports;
            # anything farther off that line hangs (an arm off a bridge, a flange beside it).
            arm, span = 0.0, 0.0
            for s in samples:
                d1, g1, q1 = nearest(s)
                d2, g2, q2 = nearest(s, skip=g1)
                if d1 <= 0.05:
                    continue
                dx, dy = q2[0] - q1[0], q2[1] - q1[1]
                L2 = dx * dx + dy * dy
                u = 0 if L2 == 0 else max(0, min(1, ((s[0] - q1[0]) * dx + (s[1] - q1[1]) * dy) / L2))
                off = math.hypot(s[0] - q1[0] - u * dx, s[1] - q1[1] - u * dy)
                if off <= max(cfg["ledge_max_mm"], 2.0):      # a bridge is several lines wide
                    span = max(span, math.sqrt(L2))
                else:
                    arm = max(arm, min(d1, off))
            if arm > cfg["ledge_max_mm"]:
                kind, size, bad = "ledge", arm, not small
                why = (f"part of a bridge held in {groups} places hangs {arm:.2f} mm past its nearest support "
                       f"(an arm; limit {cfg['ledge_max_mm']} mm)")
            else:
                kind, size, bad = "bridge", span, span > bridge_max and not small
                why = f"held in {groups} places, spanning about {span:.1f} mm (limit {bridge_max} mm, {material})"
        elif held:
            kind, size, bad = "ledge", reach, reach > cfg["ledge_max_mm"] and not small
            why = (f"flat overhang held on {', '.join(sorted(sides))}: its farthest point is {reach:.2f} mm from support "
                   f"(limit {cfg['ledge_max_mm']} mm)")
        else:
            kind, size, bad = "island", min(w, d), True
            why = "held on no side: starts in mid-air"
        found.append(dict(kind=kind, z=z, area=area, bbox=(bx0, by0, bx1, by1), size=size, bad=bad, why=why, tris=comp))
    for comp in clusters(steep):
        area = sum(info[i][1] for i in comp)
        if area < 1.0:
            continue
        worst = max(90 - math.degrees(math.acos(min(1.0, -info[i][0][2]))) for i in comp)   # from vertical
        pts = [p for i in comp for p in tris[i]]
        z = sum(p[2] for p in pts) / len(pts) - zmin
        bb = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        found.append(dict(kind="steep", z=z, area=area, bbox=bb, size=area, bad=area > 5,
                          why=f"{area:.1f} mm² sloping past {cfg['overhang_max_deg']}° from vertical, up to {worst:.0f}°",
                          tris=comp, worst=worst))
    base_w, base_d = max(xs) - min(xs), max(ys) - min(ys)
    return dict(height=height, contact=contact, bbox=(min(xs), min(ys), max(xs), max(ys)), found=found,
                tall=height > cfg["tall_ratio"] * min(base_w, base_d))


def plot(name, tris, res, path):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    x0, y0, x1, y1 = res["bbox"]
    S = 600 / max(x1 - x0, y1 - y0, 1)
    W, H = int((x1 - x0) * S) + 20, int((y1 - y0) * S) + 40
    img = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(img)
    P = lambda p: (10 + (p[0] - x0) * S, 30 + (y1 - p[1]) * S)
    for t in tris:
        d.polygon([P(p) for p in t], fill=(232, 232, 232))
    col = {"bridge": (42, 120, 214), "ledge": (235, 104, 52), "island": (179, 38, 30), "steep": (27, 175, 122)}
    for f in res["found"]:
        c = col[f["kind"]] if f["bad"] else tuple(int(v * 0.35 + 165) for v in col[f["kind"]])
        for i in f["tris"]:
            d.polygon([P(p) for p in tris[i]], fill=c)
    d.text((10, 8), f"{name}: from above, as printed. Bold = flagged; blue bridge, orange ledge, red island, green steep", fill="black")
    img.save(path)
    return True


def main():
    argv = sys.argv[1:]
    cfg = dict(DEF)
    default_mat = "*"
    for flag in ("--config", "--material"):
        if flag in argv:
            i = argv.index(flag)
            val = argv[i + 1]
            del argv[i:i + 2]
            if flag == "--config":
                cfg.update(json.load(open(val)))
            else:
                default_mat = val
    args = argv
    out, files = args[0], args[1:]
    os.makedirs(out, exist_ok=True)
    o = ["# Print review", "",
         f"`print_review.py`, on the parts as they sit on the slicer's plate. Limits: overhang "
         f"{cfg['overhang_max_deg']}° from vertical, flat ledge {cfg['ledge_max_mm']} mm, bridges "
         f"{', '.join(f'{k} {v} mm' for k, v in cfg['bridge_max_mm'].items() if k != '*')}. "
         "Flagged rows first; the full list is below them.", ""]
    flagged, rest, pics = [], [], []
    for f in files:
        objs = read_3mf(f) if f.endswith(".3mf") else read_stl(f)
        material = cfg["material"].get(os.path.basename(f), default_mat)
        for name, k, tris in objs:
            res = analyse(tris, cfg, material)
            label = f"{os.path.basename(f)} › {name}"
            bx = res["bbox"]
            fits = (bx[2] - bx[0]) <= cfg["bed_mm"][0] and (bx[3] - bx[1]) <= cfg["bed_mm"][1]
            summary = (f"| {label} | {material} | {res['height']:.1f} mm | {res['contact']:.0f} mm² | "
                       f"{'yes' if fits else '**no**'} | {'**yes**' if res['tall'] else 'no'} | "
                       f"{sum(1 for x in res['found'] if x['bad'])} |")
            rest.append(summary)
            for x in sorted(res["found"], key=lambda x: (not x["bad"], -x["size"])):
                row = (f"| {label} | {x['kind']} | z {x['z']:.1f} | x {x['bbox'][0]:.1f}-{x['bbox'][2]:.1f}, "
                       f"y {x['bbox'][1]:.1f}-{x['bbox'][3]:.1f} | {x['area']:.1f} mm² | {x['why'].rstrip('. ')} |")
                (flagged if x["bad"] else []).append(row)
            png = os.path.join(out, f"print-{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')}.png")
            if plot(label, tris, res, png):
                pics.append(f"![{label}]({os.path.basename(png)})")
    o += ["## Flagged", "", "| Part | Kind | Height | Where (plate mm) | Area | Why |", "|---|---|---|---|---|---|"]
    o += flagged or ["| none | | | | | |"]
    o += ["", "## Parts", "", "| Part | Material | Height | First-layer contact | Fits the bed | Tall and thin | Flags |",
          "|---|---|---|---|---|---|---|"] + rest + ["", "## Plots", ""] + pics
    open(os.path.join(out, "print-review.md"), "w").write("\n".join(o) + "\n")
    print(f"{len(flagged)} flagged")


if __name__ == "__main__":
    main()

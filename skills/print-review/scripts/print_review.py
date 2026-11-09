#!/usr/bin/env python3
"""Printability review of FDM parts, from the slicer project itself (3MF) so every part
is checked in the orientation it prints in. Plain Python; PIL for the plots.

    print_review.py <out dir> <project.3mf | part.stl> ... [--material PETG] [--config print-review.json]
        [--service jlc3dp:<sla|wjp|mjf|sls|slm|bj|fdm>[:<material>]]

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
Not checked: internal stresses, support settings, anything the slicer adds (supports,
brims). Run the slicer too.

With --service jlc3dp:<process>[:<material>] (a part ordered from JLC3DP rather than
printed here) it also checks the part against JLC3DP's 3D Printing Design Guideline
(https://jlc3dp.com/help/article/3d-printing-design-guideline, "last updated Nov 04, 2026"):
largest and smallest size the process takes, minimum wall thickness for the part's size
(measured by casting a ray inward from every face), and enclosed voids that need escape
holes; and lists that process's numbers for what it can't measure (details, holes, posts,
clearances, threads, tolerances). The numbers are in JLC3DP below and in
references/jlc3dp.md. A wall check without a service: "wall_min_mm" in the config.

Config (all optional): {"bed_mm": [256, 256], "overhang_max_deg": 45,
"bridge_max_mm": {"PETG": 15, "PLA": 20, "TPU": 5, "*": 10}, "ledge_max_mm": 0.5,
"min_area_mm2": 2,
"tall_ratio": 5, "material": {"<3mf file name>": "PETG", ...}, "wall_min_mm": null,
"wall_min_area_mm2": 1, "thin_rows": 15}
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
       "ledge_max_mm": 0.5, "min_area_mm2": 2, "tall_ratio": 5, "material": {},
       "wall_min_mm": None, "wall_min_area_mm2": 1, "thin_rows": 15}

# JLC3DP 3D Printing Design Guideline, https://jlc3dp.com/help/article/3d-printing-design-guideline
# ("Last updated on Nov 04, 2026"; read 2026-11-09). Section numbers are the guideline's.
# Keep in step with references/jlc3dp.md.
JLC3DP_SOURCE = "JLC3DP 3D Printing Design Guideline (updated 2026-11-04)"
JLC3DP = {
    # 1. build size, L x W x H mm, per material; min size: 5x5x5, or 10x2x2 for a long thin part
    "sla": {"name": "SLA (resin)", "min": [(5, 5, 5), (10, 2, 2)],
            "max": {"Ledo6060": (780, 780, 530), "9600": (780, 780, 530), "Black Resin": (780, 780, 530),
                    "JLC Black": (780, 780, 530), "8001 Resin": (780, 780, 530), "CBY": (780, 780, 530),
                    "Imagine Black": (580, 580, 380), "8228": (580, 580, 380), "Grey Resin": (580, 580, 380),
                    "JLC Temp": (580, 580, 380), "9000HE Resin": (580, 580, 380)},
            # 2. min wall by overall size (5, 10, 50, 100, 200 mm); None = not offered
            "wall": (0.5, 0.8, 1.0, 1.5, 2.0),
            "detail": 0.8,             # 3. embossed / engraved: min depth and width, mm
            "fit": "0.2", "moving": 0.5,   # 5. clearance: assembled parts / moving or connecting parts
            "holes": "Φ1.0 h≤3.0, Φ1.5 h≤4.5, Φ2.0 h≤6.0 (depth up to 3 x diameter)",   # 7.
            "posts": "D1.0 H≤1, D2.0 H≤4, D3.0 H≤6 (height up to 2 x diameter; D1.0 only 1 mm)",  # 8.
            "tol": "±0.2 mm within 100 mm, ±0.3% above", "hole_tol": 0.3,   # 10.
            "creep": "grows 0.15 mm or 0.15% in 1-3 days, 0.2 mm or 0.20% in 3-7 days", "voids": True},
    "wjp": {"name": "WJP (full-colour resin)", "min": [(5, 5, 5), (10, 2, 2)],
            "max": {"Full-color Resin": (380, 330, 230), "Full Color Tough Resin": (380, 330, 230)},
            "voids": True},     # the guideline gives WJP a build size only
    "mjf": {"name": "MJF (nylon)", "min": [(5, 5, 5), (10, 2, 2)],
            "max": {"PA12": (370, 276, 360), "PA12S": (370, 276, 360), "PA11": (370, 276, 360),
                    "PAC": (320, 175, 225)},
            "wall": (1.0, 1.2, 1.5, 2.0, 2.0), "detail": 0.8, "fit": "0.2-0.4", "moving": 0.6,
            "holes": "Φ1.5 h≤4.5, Φ2.0 h≤6.0; no Φ1.0", "posts": "D2.0 H≤4, D3.0 H≤6; no D1.0",
            "tol": "±0.3 mm within 100 mm, ±0.4% above", "hole_tol": 0.3, "voids": True},
    "sls": {"name": "SLS (nylon)", "min": [(5, 5, 5), (10, 2, 2)],
            "max": {"3201PA-F": (350, 350, 400), "3301PA": (350, 350, 400), "1172 Pro": (250, 250, 590),
                    "3401GB": (340, 340, 400)},
            "wall": (1.0, 1.2, 1.5, 2.0, 2.0), "detail": 0.8, "fit": "0.2-0.4", "moving": 0.6,
            "holes": "Φ1.5 h≤4.5, Φ2.0 h≤6.0; no Φ1.0", "posts": "D2.0 H≤4, D3.0 H≤6; no D1.0",
            "tol": "±0.3 mm within 100 mm, ±0.4% above", "hole_tol": 0.3, "voids": True},
    "slm": {"name": "SLM (metal)", "min": [(5, 5, 5), (10, 2, 2)],
            "max": {"316L Stainless Steel": (390, 290, 390), "Titanium TC4": (390, 290, 390)},
            "wall": (1.5, 1.5, 1.5, 2.0, 2.5), "detail": 1.0, "fit": "0.5", "moving": 1.0,
            "holes": "Φ1.5 h≤4.5, Φ2.0 h≤6.0; no Φ1.0", "posts": "D2.0 H≤4, D3.0 H≤6; no D1.0",
            "tol": "±0.3 mm within 100 mm, ±0.4% above", "hole_tol": 0.5,
            "extra": "316L: tap threads after printing; rings, sleeves and other enclosed openings come out "
                     "up to 0.5 mm small, more with thicker walls round the hole", "voids": True},
    "bj": {"name": "BJ (metal)", "min": [(5, 5, 5), (10, 2, 2)], "max": {"BJ-316L": (100, 100, 100)},
           "wall": (1.5, 1.5, 1.5, 2.0, None), "detail": 1.0, "fit": "0.5", "moving": 1.0,
           "holes": "Φ1.5 h≤4.5, Φ2.0 h≤6.0; no Φ1.0", "posts": "D2.0 H≤4, D3.0 H≤6; no D1.0",
           "tol": "±0.3 mm or ±0.4% up to 50 mm, ±1.3% above 50 mm", "hole_tol": 0.5, "voids": True},
    "fdm": {"name": "FDM (plastic)", "min": [(30, 30, 10)],
            "max": {"ABS": (580, 480, 480), "ASA": (580, 480, 480), "PA12-CF": (580, 480, 480),
                    "PEEK": (580, 480, 480), "ABS-ESD": (250, 250, 250), "PLA-P": (250, 250, 300),
                    "TPU": (250, 250, 300), "PEBA": (250, 250, 300)},
            "wall": (None, None, 1.6, 2.0, 2.5), "detail": 1.0, "fit": "0.5", "moving": 0.5,
            "holes": "Φ1.5 h≤4.5, Φ2.0 h≤6.0; no Φ1.0", "posts": "D2.0 H≤4, D3.0 H≤6; no D1.0",
            "tol": "±0.3 mm within 100 mm, ±0.4% above", "hole_tol": 0.4, "voids": False},
}
WALL_SIZES = (5, 10, 50, 100, 200)


def jlc_wall_min(proc, dims):
    """Minimum wall for a part of this size: the guideline's column for the smallest size
    at or above the part's largest dimension (FDM's smallest column is 50 mm)."""
    walls = proc.get("wall")
    if not walls:
        return None
    big = max(dims)
    for size, w in zip(WALL_SIZES, walls):
        if big <= size and w is not None:
            return w
    return next((w for w in reversed(walls) if w is not None), None)


def jlc_size(proc, material, dims):
    """[(ok, text)] for the process's largest and smallest part, in any orientation."""
    d = sorted(dims, reverse=True)
    out = []
    maxes = {material: proc["max"][material]} if material in proc["max"] else proc["max"]
    fits = [m for m, mx in maxes.items() if all(a <= b for a, b in zip(d, sorted(mx, reverse=True)))]
    biggest = max(maxes.values(), key=lambda v: v[0] * v[1] * v[2])
    if material in proc["max"]:
        out.append((bool(fits), f"max {' x '.join(map(str, proc['max'][material]))} mm ({material})"))
    else:
        out.append((bool(fits), f"fits {', '.join(fits) if fits else 'no material'} "
                                f"(largest {' x '.join(map(str, biggest))} mm)"))
    mins = proc["min"]
    ok = any(all(a >= b for a, b in zip(d, m)) for m in mins)
    out.append((ok, "min " + " or ".join(" x ".join(map(str, m)) for m in mins) + " mm"))
    return out


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


def ray_tri(o, d, t):
    """Distance along d from o to triangle t (Moller-Trumbore), or None."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
    e1 = (bx - ax, by - ay, bz - az); e2 = (cx - ax, cy - ay, cz - az)
    p = (d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0])
    det = e1[0] * p[0] + e1[1] * p[1] + e1[2] * p[2]
    if abs(det) < 1e-12:
        return None
    s = (o[0] - ax, o[1] - ay, o[2] - az)
    u = (s[0] * p[0] + s[1] * p[1] + s[2] * p[2]) / det
    if u < -1e-9 or u > 1 + 1e-9:
        return None
    q = (s[1] * e1[2] - s[2] * e1[1], s[2] * e1[0] - s[0] * e1[2], s[0] * e1[1] - s[1] * e1[0])
    v = (d[0] * q[0] + d[1] * q[1] + d[2] * q[2]) / det
    if v < -1e-9 or u + v > 1 + 1e-9:
        return None
    return (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) / det


def thin_walls(tris, info, edge_owner, wall_min, min_area):
    """Regions thinner than wall_min: from points spread over every face (about one per
    0.25 mm²... 4 mm²), a ray goes straight in; the material is as thick as the distance to
    where it comes out. Rays are only followed wall_min mm, through a 1 mm grid."""
    C = 1.0
    grid = defaultdict(list)
    for i, t in enumerate(tris):
        lo = [int(math.floor((min(p[k] for p in t) - 0.05) / C)) for k in range(3)]
        hi = [int(math.floor((max(p[k] for p in t) + 0.05) / C)) for k in range(3)]
        for gx in range(lo[0], hi[0] + 1):
            for gy in range(lo[1], hi[1] + 1):
                for gz in range(lo[2], hi[2] + 1):
                    grid[(gx, gy, gz)].append(i)
    step = max(0.5, min(2.0, wall_min))       # sample spacing on the surface, mm
    thin = {}                                 # tri -> (thin samples, samples, min thickness, points)
    for i, t in enumerate(tris):
        n, a = info[i]
        if a <= 0:
            continue
        k = max(1, min(60, int(math.ceil(math.sqrt(a) / step))))
        d = (-n[0], -n[1], -n[2])
        bad, total, tmin, pts = 0, 0, None, []
        for r in range(k):
            for c in range(k - r):
                u, v = (r + 1 / 3) / k, (c + 1 / 3) / k
                if u + v > 1:
                    continue
                o = tuple(t[0][j] + u * (t[1][j] - t[0][j]) + v * (t[2][j] - t[0][j]) for j in range(3))
                total += 1
                cells = set()
                m = 0.0
                while m <= wall_min + C:
                    q = [o[j] + d[j] * m for j in range(3)]
                    cells.add(tuple(int(math.floor(q[j] / C)) for j in range(3)))
                    m += C / 4
                best = None
                for cell in cells:
                    for j in grid.get(cell, ()):
                        if j == i:
                            continue
                        nj = info[j][0]
                        if nj[0] * d[0] + nj[1] * d[1] + nj[2] * d[2] < 0.2:   # must be where the ray leaves
                            continue
                        h = ray_tri(o, d, tris[j])
                        # under 0.05 mm is a sliver in the mesh (text or a cut meeting a face), not a wall
                        if h is not None and 0.05 < h < wall_min and (best is None or h < best):
                            best = h
                if best is not None:
                    bad += 1
                    tmin = best if tmin is None else min(tmin, best)
                    pts.append(o)
        if bad:
            thin[i] = (bad, total, tmin, pts)
    seen, out = set(), []
    for s0 in thin:
        if s0 in seen:
            continue
        stack, comp = [s0], []
        seen.add(s0)
        while stack:
            i = stack.pop(); comp.append(i)
            t = tris[i]
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                for j in edge_owner[tuple(sorted((key(e[0]), key(e[1]))))]:
                    if j in thin and j not in seen:
                        seen.add(j); stack.append(j)
        area = sum(info[i][1] * thin[i][0] / thin[i][1] for i in comp)
        if area < min_area:
            continue
        pts = [p for i in comp for p in thin[i][3]]
        tmin = min(thin[i][2] for i in comp)
        out.append(dict(area=area, tmin=tmin, tris=comp,
                        bbox=(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)),
                        z=sum(p[2] for p in pts) / len(pts)))
    return out


def voids(tris, edge_owner):
    """Closed shells with their normals pointing in: cavities sealed inside the part.
    Volume (mm³) of each, from the signed volume of every edge-connected shell."""
    seen, out = set(), []
    for s0 in range(len(tris)):
        if s0 in seen:
            continue
        stack, comp = [s0], []
        seen.add(s0)
        while stack:
            i = stack.pop(); comp.append(i)
            t = tris[i]
            for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                for j in edge_owner[tuple(sorted((key(e[0]), key(e[1]))))]:
                    if j not in seen:
                        seen.add(j); stack.append(j)
        vol = 0.0
        for i in comp:
            (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tris[i]
            vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6
        if vol < -1.0:
            pts = [p for i in comp for p in tris[i]]
            out.append(dict(volume=-vol, bbox=(min(p[0] for p in pts), min(p[1] for p in pts),
                                                max(p[0] for p in pts), max(p[1] for p in pts)),
                            z=sum(p[2] for p in pts) / len(pts)))
    return out


def analyse(tris, cfg, material, wall_min=None, find_voids=False, detail_mm=None):
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
    if wall_min:
        for w in thin_walls(tris, info, edge_owner, wall_min, cfg["wall_min_area_mm2"]):
            found.append(dict(kind="thin", z=w["z"] - zmin, area=w["area"], bbox=w["bbox"], size=wall_min - w["tmin"],
                              tmin=w["tmin"], bad=True, tris=w["tris"],
                              why=f"wall {w['tmin']:.2f} mm thick over about {w['area']:.1f} mm² (min {wall_min} mm)"
                                  + (f"; if it's text or a fine detail, JLC3DP 3 wants {detail_mm} mm wide and deep"
                                     if detail_mm and w["area"] < 50 else "")))
    if find_voids:
        for v in voids(tris, edge_owner):
            found.append(dict(kind="void", z=v["z"] - zmin, area=0, bbox=v["bbox"], size=v["volume"], bad=True, tris=[],
                              why=f"sealed cavity of {v['volume']:.0f} mm³: needs escape holes, at least 2.5 mm, "
                                  f"two of them if under 3 mm (JLC3DP 6)"))
    base_w, base_d = max(xs) - min(xs), max(ys) - min(ys)
    zs = [p[2] for t in tris for p in t]
    return dict(height=height, contact=contact, bbox=(min(xs), min(ys), max(xs), max(ys)), found=found,
                tall=height > cfg["tall_ratio"] * min(base_w, base_d),
                dims=(base_w, base_d, max(zs) - min(zs)))


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
    col = {"bridge": (42, 120, 214), "ledge": (235, 104, 52), "island": (179, 38, 30), "steep": (27, 175, 122),
           "thin": (140, 60, 200), "void": (90, 90, 90)}
    for f in res["found"]:
        c = col[f["kind"]] if f["bad"] else tuple(int(v * 0.35 + 165) for v in col[f["kind"]])
        for i in f["tris"]:
            d.polygon([P(p) for p in tris[i]], fill=c)
    d.text((10, 8), f"{name}: from above, as printed. Bold = flagged; blue bridge, orange ledge, red island, green steep, purple thin wall", fill="black")
    img.save(path)
    return True


def main():
    argv = sys.argv[1:]
    cfg = dict(DEF)
    default_mat = "*"
    service = None
    for flag in ("--config", "--material", "--service"):
        if flag in argv:
            i = argv.index(flag)
            val = argv[i + 1]
            del argv[i:i + 2]
            if flag == "--config":
                cfg.update(json.load(open(val)))
            elif flag == "--service":
                service = val
            else:
                default_mat = val
    proc = proc_mat = None
    if service:
        bits = service.split(":", 2)
        if bits[0] != "jlc3dp" or len(bits) < 2 or bits[1].lower() not in JLC3DP:
            sys.exit(f"--service must be jlc3dp:<{'|'.join(JLC3DP)}>[:<material>], not {service}")
        proc = JLC3DP[bits[1].lower()]
        if len(bits) == 3:
            proc_mat = next((m for m in proc["max"] if m.lower() == bits[2].lower()), None)
            if not proc_mat:
                sys.exit(f"{proc['name']} materials are: {', '.join(proc['max'])}")
    args = argv
    out, files = args[0], args[1:]
    os.makedirs(out, exist_ok=True)
    o = ["# Print review", "",
         f"`print_review.py`, on the parts as they sit on the slicer's plate. Limits: overhang "
         f"{cfg['overhang_max_deg']}° from vertical, flat ledge {cfg['ledge_max_mm']} mm, bridges "
         f"{', '.join(f'{k} {v} mm' for k, v in cfg['bridge_max_mm'].items() if k != '*')}. "
         "Flagged rows first; the full list is below them.", ""]
    if proc:
        o += [f"Ordered from JLC3DP, {proc['name']}{', ' + proc_mat if proc_mat else ''}: also checked against the "
              f"[{JLC3DP_SOURCE}](https://jlc3dp.com/help/article/3d-printing-design-guideline) for build size, "
              "minimum wall for the part's size" + (" and sealed cavities" if proc["voids"] else "") +
              ". The overhang rows are for FDM: JLC3DP adds and removes supports for SLA, SLM and FDM, "
              "and MJF and SLS print in powder with none, so for those read them only as a sign of a "
              "rough surface where supports were.", ""]
    flagged, rest, pics, jlc_rows = [], [], [], []
    for f in files:
        objs = read_3mf(f) if f.endswith(".3mf") else read_stl(f)
        material = cfg["material"].get(os.path.basename(f), default_mat)
        for name, k, tris in objs:
            label = f"{os.path.basename(f)} › {name}"
            wall = cfg["wall_min_mm"]
            if proc:
                dims0 = [max(p[j] for t in tris for p in t) - min(p[j] for t in tris for p in t) for j in range(3)]
                wall = jlc_wall_min(proc, dims0) or wall
            res = analyse(tris, cfg, material, wall_min=wall, find_voids=bool(proc and proc["voids"]),
                          detail_mm=proc.get("detail") if proc else None)
            if proc:
                size = jlc_size(proc, proc_mat, res["dims"])
                for ok, why in size:
                    if not ok:
                        flagged.append(f"| {label} | size | | | | {' x '.join(f'{v:.1f}' for v in res['dims'])} mm: "
                                       f"outside JLC3DP {proc['name']} {why} (JLC3DP 1) |")
                jlc_rows.append(f"| {label} | {' x '.join(f'{v:.0f}' for v in res['dims'])} mm | "
                                f"{wall if wall else 'none given'}{' mm' if wall else ''} | "
                                f"{'; '.join(('' if ok else '**no**: ') + why for ok, why in size)} |")
            bx = res["bbox"]
            fits = (bx[2] - bx[0]) <= cfg["bed_mm"][0] and (bx[3] - bx[1]) <= cfg["bed_mm"][1]
            summary = (f"| {label} | {material} | {res['height']:.1f} mm | {res['contact']:.0f} mm² | "
                       f"{'yes' if fits else '**no**'} | {'**yes**' if res['tall'] else 'no'} | "
                       f"{sum(1 for x in res['found'] if x['bad'])} |")
            rest.append(summary)
            thin = sorted((x for x in res["found"] if x["kind"] == "thin"), key=lambda x: -x["area"])
            shown = {id(x) for x in thin[:cfg["thin_rows"]]}
            for x in sorted(res["found"], key=lambda x: (not x["bad"], -x["size"])):
                if x["kind"] == "thin" and id(x) not in shown:
                    continue
                row = (f"| {label} | {x['kind']} | z {x['z']:.1f} | x {x['bbox'][0]:.1f}-{x['bbox'][2]:.1f}, "
                       f"y {x['bbox'][1]:.1f}-{x['bbox'][3]:.1f} | {x['area']:.1f} mm² | {x['why'].rstrip('. ')} |")
                (flagged if x["bad"] else []).append(row)
            if len(thin) > len(shown):
                more = thin[len(shown):]
                flagged.append(f"| {label} | thin | | | {sum(x['area'] for x in more):.1f} mm² | {len(more)} more thin "
                               f"regions, smaller than those above, thinnest {min(x['tmin'] for x in more):.2f} mm "
                               "(usually text strokes and small steps; see the plot) |")
            png = os.path.join(out, f"print-{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')}.png")
            if plot(label, tris, res, png):
                pics.append(f"![{label}]({os.path.basename(png)})")
    o += ["## Flagged", "", "| Part | Kind | Height | Where (plate mm) | Area | Why |", "|---|---|---|---|---|---|"]
    o += flagged or ["| none | | | | | |"]
    if proc:
        o += ["", f"## JLC3DP, {proc['name']}", "",
              "| Part | Size | Min wall for that size (JLC3DP 2) | Build size (JLC3DP 1) |", "|---|---|---|---|"] + jlc_rows
        o += ["", "Not measured; check each against the design (JLC3DP section in brackets):", ""]
        if "detail" in proc:
            d = proc["detail"]
            o += [f"- [ ] Snaps, locating features, bosses and fasteners: walls over 1.5 mm (2)",
                  f"- [ ] Embossed and engraved text and detail: at least {d} mm deep and {d} mm wide (3); "
                  f"stroke width counts, so small text fails first",
                  "- [ ] Printed threads: M6 or larger, with the fit clearance below; smaller ones tapped or "
                  "heat-set inserts (4)",
                  f"- [ ] Clearance between parts that assemble: at least {proc['fit']} mm; between parts that move "
                  f"or connect: at least {proc['moving']} mm, for simple shapes (5)",
                  f"- [ ] Small holes: {proc['holes']} (7); oil-sprayed parts need holes of 2.0 mm or more",
                  f"- [ ] Small posts and locating pins: {proc['posts']} (8)",
                  f"- [ ] Fits that depend on size: part tolerance {proc['tol']}, holes ±{proc['hole_tol']} mm and they "
                  "usually come out small (10); before warping, paint or oil spray"]
            if "creep" in proc:
                o.append(f"- [ ] Resin keeps moving after printing: {proc['creep']} (10)")
            if "extra" in proc:
                o.append(f"- [ ] {proc['extra']} (4, 10)")
        else:
            o += [f"- [ ] The guideline gives {proc['name']} only a build size: ask JLC3DP for its wall, detail "
                  "and clearance limits, or use the SLA numbers as a floor"]
        if proc["voids"]:
            o.append("- [ ] Hollowed parts: escape holes at least 2.5 mm, two if under 3 mm, bigger if supports "
                     "must come out of the cavity (6)")
    o += ["", "## Parts", "", "| Part | Material | Height | First-layer contact | Fits the bed | Tall and thin | Flags |",
          "|---|---|---|---|---|---|---|"] + rest + ["", "## Plots", ""] + pics
    open(os.path.join(out, "print-review.md"), "w").write("\n".join(o) + "\n")
    print(f"{len(flagged)} flagged")


if __name__ == "__main__":
    main()

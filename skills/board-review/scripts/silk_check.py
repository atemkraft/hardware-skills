#!/usr/bin/env python3
"""Board-level front silkscreen (logos, labels, board text) that lands on a part.

DRC doesn't look for this: a logo or a label drawn on the board (not in a footprint)
can sit under a part's body or across its pads, and the fab's preview shows it only if
you look. This reports:
  - text whose box overlaps another footprint's copper pad (padded by 0.1 mm, the text box trimmed to its strokes), and
  - graphic strokes (logos, lines, arrows) inside a front part's courtyard or on a pad.

Run with KiCad's Python (it imports pcbnew):
  .../KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \\
      silk_check.py board.kicad_pcb [--allow REF,REF] [--layer F|B]

Coordinates are in the board's own frame (relative to the edge cuts' top-left corner).
Text boxes are generous, so a label right beside its own pad can show up; every report is
a prompt to look at the render, not a verdict. --allow skips parts you have checked (e.g.
a frame drawn round a group of jumpers on purpose). Exit code 1 if anything is reported.
"""
import argparse
import sys

import pcbnew


def box(bb, margin=0.0):
    mm = pcbnew.ToMM
    return (mm(bb.GetLeft()) - margin, mm(bb.GetTop()) - margin,
            mm(bb.GetRight()) + margin, mm(bb.GetBottom()) + margin)


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("board")
    ap.add_argument("--allow", default="", help="comma-separated references to skip")
    ap.add_argument("--layer", default="F", choices=("F", "B"))
    args = ap.parse_args()
    allow = {r for r in args.allow.split(",") if r}
    front = args.layer == "F"
    silk = pcbnew.F_SilkS if front else pcbnew.B_SilkS
    cu = pcbnew.F_Cu if front else pcbnew.B_Cu
    crt_layer = pcbnew.F_CrtYd if front else pcbnew.B_CrtYd

    b = pcbnew.LoadBoard(args.board)
    edge = b.GetBoardEdgesBoundingBox()
    ox, oy = pcbnew.ToMM(edge.GetLeft()), pcbnew.ToMM(edge.GetTop())

    pads, bodies = [], []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref in allow:
            continue
        for p in fp.Pads():
            if p.IsOnLayer(cu) or p.GetDrillSizeX() > 0:
                pads.append((ref, box(p.GetBoundingBox(), 0.1)))
        if fp.GetLayer() == cu:
            c = fp.GetCourtyard(crt_layer)
            if c.OutlineCount():
                bodies.append((ref, box(c.BBox())))

    found = {}
    for d in b.GetDrawings():
        if d.GetLayer() != silk:
            continue
        bb = box(d.GetBoundingBox())
        if isinstance(d, pcbnew.PCB_TEXT):
            # KiCad's text box runs past the strokes; trim it so a label merely beside
            # a pad isn't reported (half the stroke width, and a little more)
            t = pcbnew.ToMM(d.GetTextThickness()) / 2 + 0.1
            bb = (bb[0] + t, bb[1] + t, bb[2] - t, bb[3] - t)
            key = f"text '{d.GetText()}' at {(bb[0] + bb[2]) / 2 - ox:.1f}, {(bb[1] + bb[3]) / 2 - oy:.1f} mm"
            hits = [r for r, pb in pads if overlap(bb, pb)]
        else:
            key = f"graphic near {bb[0] - ox:.0f}, {bb[1] - oy:.0f} mm"
            hits = [r + " pad" for r, pb in pads if overlap(bb, pb)]
            hits += [r + " body" for r, cb in bodies if overlap(bb, cb)]
        if hits:
            found.setdefault(key, set()).update(hits)

    for k in sorted(found):
        print(f"{k}: {', '.join(sorted(found[k]))}")
    print(f"{len(found)} silkscreen item(s) on a part ({args.layer} side)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

---
name: print-review
description: Printability review of FDM 3D-printed parts before printing. It reads the slicer project (Bambu Studio / PrusaSlicer / OrcaSlicer 3MF) or STLs as they'll sit on the bed, and finds flat ledges and arms that droop, bridges past the material's span, islands that start in mid-air, steep overhangs, and parts too big or too tall-and-thin for the bed, with plots of where. Use it whenever someone is about to print an enclosure, bracket, case or any functional part, asks "will this print", "does this need supports", "why did this sag/droop", or changes a part's design or print orientation, even if they don't say "printability".
---

# Print review

A slicer will happily slice a part that prints badly: a flat ledge 0.8 mm wide sags, a
counterbore printed face-down droops into the screw hole, an arm off a post curls up and
the feature built on it fails. These are geometry problems, visible before printing.
`scripts/print_review.py` finds them from the meshes in the orientation they print in.

It was checked against a real enclosure's history: on the old files it flagged exactly the
two problems that had been found by printing (a 0.8 mm flat pocket roof, later sloped at
45°; counterbore ceilings on a lid printed face down, later printed face up). On the fixed
files those flags are gone.

## Run it

```bash
python3 skills/print-review/scripts/print_review.py <out dir> part.3mf [more.3mf part.stl ...] \
    [--material PETG] [--config print-review.json]
```

- **Use the slicer project (3MF) whenever there is one**: it holds every part with its plate
  transform, so each is checked the way up it prints. A part that is fine as modelled can be
  turned over on the plate, and then its foot becomes a ledge; reading the STL or the CAD
  misses that. An STL is checked as it is in its file, so orient it as it will print first.
- Plain Python 3, no packages. PIL (Pillow), if installed, draws a plot per part.
- Output: `<out dir>/print-review.md` (flagged items first, then every part's summary) and
  `print-<part>.png` plots (from above; flagged regions in strong colour).

Config (all optional), as JSON:
`{"bed_mm": [256, 256], "overhang_max_deg": 45, "bridge_max_mm": {"PETG": 15, "PLA": 20,
"TPU": 5, "*": 10}, "ledge_max_mm": 0.5, "min_area_mm2": 2, "tall_ratio": 5,
"material": {"<file name>": "PETG"}}`. Set the material per file when a project mixes
them (TPU bridges far less well than PETG).

## What it finds, and what to do about each

Every surface the printer lays over air is one of these:

| Kind | What it is | Flagged when | Usual fixes |
|---|---|---|---|
| **ledge** | a flat overhang held on one side, or an arm hanging off a bridge | its farthest point is more than `ledge_max_mm` (0.5) from support | a 45° underside or chamfer; turn the part; supports |
| **bridge** | a flat ceiling held in two or more places (or all round) | span over the material's limit | shorter span; an arch or 45° roof; supports |
| **arm** (a kind of ledge) | part of a bridge that sticks out sideways from the line between its supports | over `ledge_max_mm` past the bridge line | a 45° gusset back to a support; supports |
| **island** | a downward surface held on nothing: starts in mid-air | always | supports, or reorient / redesign so it grows from something below |
| **steep** | a sloped downward face past 45° from vertical | over 5 mm² | 45° or less, or a teardrop shape for horizontal holes |

Not flagged on purpose: an **internal seam**, where a part is made of solids that touch but
weren't merged, so a downward face lies on an upward one at the same height. The slicer fills
it solid. Say so if someone asks why a visible "step" wasn't flagged.

Plus: first-layer contact area (small = poor adhesion; large flat PETG = warping), parts
taller than `tall_ratio` x their narrowest base side (wobble), and bed fit.

**Reading results:** each flag gives the part, height above the bed, where it is in plate
coordinates, area and the measured reason. Check a flag against the plot and the design
before changing anything. A 0.6 mm step on a rim is borderline and worth a look on the first
print. A 6 mm arm is not. Exactly-45° faces pass on purpose (that's the usual rule).

## Limits (say these in a review)

It doesn't check wall thickness against the nozzle, bridging *direction* settings, cooling,
supports the slicer would add, or material shrink. Run the slicer too, and print a test part
where a flag is borderline. It needs closed (manifold) meshes: a part made of separate
overlapping bodies, rather than one union, shows false islands.

## When it's part of a hardware order

Keep the findings with the order's review results, each with a severity (T: check on the
first print; B: fix before printing), and a checklist line saying they were read.

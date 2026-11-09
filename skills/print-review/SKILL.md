---
name: print-review
description: Printability review of FDM 3D-printed parts before printing. It reads the slicer project (Bambu Studio / PrusaSlicer / OrcaSlicer 3MF) or STLs as they'll sit on the bed, and finds flat ledges and arms that droop, bridges past the material's span, islands that start in mid-air, steep overhangs, and parts too big or too tall-and-thin for the bed, with plots of where. For parts ordered from JLC3DP (SLA, MJF, SLS, SLM, BJ, WJP, FDM) it also checks JLC3DP's published design guideline: build size, minimum wall for the part's size (measured), sealed cavities that need escape holes, and a checklist with that process's numbers for detail, holes, posts, clearances, threads and tolerances. Use it whenever someone is about to print an enclosure, bracket, case or any functional part, or order one from JLC3DP or another print service, asks "will this print", "does this need supports", "why did this sag/droop", "is this wall thick enough", or changes a part's design, process or print orientation, even if they don't say "printability".
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
    [--material PETG] [--config print-review.json] [--service jlc3dp:mjf[:PA12]]
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
them (TPU bridges far less well than PETG). `"wall_min_mm": 1.2` adds the wall check (below)
for your own printer too, for example 3 perimeters of a 0.4 mm nozzle; `"thin_rows": 15` is how
many thin regions per part get their own row.

## Ordered from JLC3DP

When the part is printed by JLC3DP rather than on your own printer, add
`--service jlc3dp:<sla|wjp|mjf|sls|slm|bj|fdm>[:<material>]` (material names as JLC3DP
lists them, e.g. `jlc3dp:mjf:PA12`, `jlc3dp:sla:8228`, `jlc3dp:fdm:ASA`). The rules come from
JLC3DP's [3D Printing Design Guideline](https://jlc3dp.com/help/article/3d-printing-design-guideline)
(updated 2026-11-04). Every number, and how each is checked, is in
[references/jlc3dp.md](references/jlc3dp.md): read it before you write up the review. The
report then has:

- **Measured**: build size, largest and smallest, in any orientation (JLC3DP 1). The FDM
  minimum is 30 x 30 x 10 mm, so small parts go to SLA or MJF. **Minimum wall for the part's
  size** (JLC3DP 2): MJF/SLS 2.0 mm and SLA 1.5-2.0 mm for a 100-200 mm enclosure, FDM 2.0-2.5 mm,
  and 1.5 mm for snaps, bosses and fasteners. Plus **sealed cavities** that need escape holes,
  at least 2.5 mm, two if under 3 mm (JLC3DP 6).
- **A checklist with that process's numbers** for what a mesh can't tell you: embossed and engraved
  detail (0.8 mm deep and wide for SLA/MJF/SLS, 1.0 for FDM and metal), threads (M6 and up),
  clearances (assembled 0.2-0.5 mm, moving 0.5-1.0 mm), small holes (depth up to 3 x Φ, no
  Φ1.0 except SLA), small posts (H up to 2 x D), and tolerances (±0.2-0.3 mm to 100 mm; holes
  ±0.3-0.5 mm, and they come out small). Go through each line against the design and say
  pass, fail or not present.

Reading the wall rows: the ray measures straight through the material, so a text stroke, fin or
0.2 mm step shows up as a thin "wall". Rows under 50 mm² carry the detail rule beside the wall
rule. Decide which it is from the plot and the design. Rows of 0.05-0.15 mm on tiny areas are
usually slivers where text or a cut meets a face. Real thin walls are large areas at a
round-number thickness the design will name (a 1.2 mm wall beside a seal groove, a 1.8 mm
floor under counterbores). Each one is thicken it, switch process, or an accepted risk written
down. Don't pass it silently.

The overhang rows still print. MJF and SLS need no supports (powder holds the part), and for SLA,
SLM and FDM JLC3DP adds and removes the supports. So for a JLC3DP order those rows mark rough
support-mark surfaces, not failures, and orientation is JLC3DP's choice unless you state one.

## What it finds, and what to do about each

Every surface the printer lays over air is one of these:

| Kind | What it is | Flagged when | Usual fixes |
|---|---|---|---|
| **ledge** | a flat overhang held on one side, or an arm hanging off a bridge | its farthest point is more than `ledge_max_mm` (0.5) from support | a 45° underside or chamfer; turn the part; supports |
| **bridge** | a flat ceiling held in two or more places (or all round) | span over the material's limit | shorter span; an arch or 45° roof; supports |
| **arm** (a kind of ledge) | part of a bridge that sticks out sideways from the line between its supports | over `ledge_max_mm` past the bridge line | a 45° gusset back to a support; supports |
| **island** | a downward surface held on nothing: starts in mid-air | always | supports, or reorient / redesign so it grows from something below |
| **steep** | a sloped downward face past 45° from vertical | over 5 mm² | 45° or less, or a teardrop shape for horizontal holes |

With a wall minimum (`--service`, or `wall_min_mm`):

| Kind | What it is | Flagged when | Usual fixes |
|---|---|---|---|
| **thin** | material thinner than the minimum, measured straight through from the surface | over `wall_min_area_mm2` (1 mm²) | thicken; for text, bigger or bolder (stroke ≥ the detail rule); another process |
| **void** | a sealed cavity inside the part (not FDM) | always | escape holes, ≥ 2.5 mm, two if < 3 mm; or make it solid |
| **size** | outside the service's largest or smallest part | always | split the part, another material/process, or add a sprue/frame for tiny parts |

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

It doesn't check bridging *direction* settings, cooling, supports the slicer would add, or
material shrink. It checks wall thickness only with `--service` or `wall_min_mm`, and even
then not hole and post sizes, clearances between parts, or text size: those are the checklist,
and someone has to look. Run the slicer too, and print a test part
where a flag is borderline. It needs closed (manifold) meshes: a part made of separate
overlapping bodies, rather than one union, shows false islands, and touching but unmerged
bodies can show false thin walls at the seam.

## When it's part of a hardware order

Keep the findings with the order's review results, each with a severity (T: check on the
first print; B: fix before printing), and a checklist line saying they were read.

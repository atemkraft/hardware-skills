# JLC3DP design rules

Source: JLC3DP, [3D Printing Design Guideline](https://jlc3dp.com/help/article/3d-printing-design-guideline),
"Last updated on Nov 04, 2026", read 2026-11-09. Section numbers below are the guideline's;
the review cites them as "JLC3DP 2" and so on. These are the minimums for a part JLC3DP prints
for you. They aren't the rules for your own FDM printer, which the rest of `print-review`
covers. If the page has changed since that date, update this file and the `JLC3DP` table in
`scripts/print_review.py` together.

`print_review.py --service jlc3dp:<process>[:<material>]` measures the rules marked
**measured**. The others it lists in the report as a checklist, with that process's numbers.

Processes: **SLA** (resin), **WJP** (full-colour resin), **MJF** and **SLS** (nylon powder),
**SLM** and **BJ** (metal), **FDM** (plastic filament).

## 1. Build size (measured)

Largest part, L x W x H mm. The check tries every axis-aligned orientation, since JLC3DP
orients the part itself.

| Process | Material | Max (mm) |
|---|---|---|
| SLA | Ledo6060, 9600, Black Resin, JLC Black, 8001 Resin, CBY | 780 x 780 x 530 |
| SLA | Imagine Black, 8228, Grey Resin, JLC Temp, 9000HE Resin | 580 x 580 x 380 |
| WJP | Full-color Resin, Full Color Tough Resin | 380 x 330 x 230 |
| MJF | PA12, PA12S, PA11 | 370 x 276 x 360 |
| MJF | PAC | 320 x 175 x 225 |
| SLS | 3201PA-F, 3301PA | 350 x 350 x 400 |
| SLS | 1172 Pro | 250 x 250 x 590 |
| SLS | 3401GB | 340 x 340 x 400 |
| SLM | 316L Stainless Steel, Titanium TC4 | 390 x 290 x 390 |
| BJ | BJ-316L | 100 x 100 x 100 |
| FDM | ABS, ASA, PA12-CF, PEEK | 580 x 480 x 480 |
| FDM | ABS-ESD | 250 x 250 x 250 |
| FDM | PLA-P (formerly PLA), TPU, PEBA | 250 x 250 x 300 |

Smallest part: **5 x 5 x 5 mm, or 10 x 2 x 2 mm** for a long thin part (SLA, WJP, MJF, SLS,
SLM, BJ). For **FDM it's 30 x 30 x 10 mm**, so a small clip or light pipe goes to SLA or MJF instead.

## 2. Minimum wall thickness (measured)

It goes up with the part's overall size. The check uses the column for the smallest size at
or above the part's largest dimension (a 147 mm box uses the 200 mm column).

| Process | 5 mm | 10 mm | 50 mm | 100 mm | 200 mm |
|---|---|---|---|---|---|
| SLA (resin) | 0.5 | 0.8 | 1.0 | 1.5 | 2.0 |
| MJF (nylon) | 1.0 | 1.2 | 1.5 | 2.0 | 2.0 |
| SLS (nylon) | 1.0 | 1.2 | 1.5 | 2.0 | 2.0 |
| SLM (metal) | 1.5 | 1.5 | 1.5 | 2.0 | 2.5 |
| BJ (metal) | 1.5 | 1.5 | 1.5 | 2.0 | n/a |
| FDM (plastic) | n/a | n/a | 1.6 | 2.0 | 2.5 |

Protrusions, locating features, snaps and fasteners: **more than 1.5 mm**, whatever the part size.
WJP has no wall rule in the guideline.

How it's measured: from points spread over every face, a ray goes straight into the part, and
the wall is as thick as the distance to where the ray comes out. So a text stroke, a fin or a
step measures its width or height, and those rows usually belong to section 3. Distances under
0.05 mm are mesh slivers and are skipped.

## 3. Embossed and engraved detail (checklist)

Minimum depth x width, mm, the same for raised and cut detail:

| SLA | MJF | SLS | FDM | SLM | BJ |
|---|---|---|---|---|---|
| 0.8 x 0.8 | 0.8 x 0.8 | 0.8 x 0.8 | 1.0 x 1.0 | 1.0 x 1.0 | 1.0 x 1.0 |

For text, the stroke width is what counts. Small sans-serif text (about 3 mm cap height) has
strokes of about 0.4-0.5 mm, so it fails first.

## 4. Threads (checklist)

- Smallest thread worth printing: **M6**. Below that, tap it or use a heat-set insert.
- Mating threads need the fit clearance from section 5, or they won't go together.
- 316L metal: tapping after printing is recommended.

## 5. Clearance (checklist)

| | SLA | MJF | SLS | SLM | BJ | FDM |
|---|---|---|---|---|---|---|
| Parts assembled together | 0.2 | 0.2-0.4 | 0.2-0.4 | 0.5 | 0.5 | 0.5 |
| Moving or connecting parts | 0.5 | 0.6 | 0.6 | 1.0 | 1.0 | 0.5 |

Minimums for simple shapes; the guideline says they don't cover every structure.

## 6. Escape holes (measured: sealed cavities)

A hollow part needs a hole for uncured resin or loose powder to get out (otherwise it can crack
later). **Minimum 2.5 mm across; use two holes if they're under 3 mm.** Make them bigger if
supports have to come out of the cavity. The check flags any sealed cavity (an inner shell)
for every process except FDM, which fills it with infill.

## 7. Small holes (checklist)

Deepest hole for a diameter, mm (depth up to 3 x diameter):

| | Φ1.0 | Φ1.5 | Φ2.0 |
|---|---|---|---|
| SLA | h 1.0-3.0 | h 1.5-4.5 | h 2.0-6.0 |
| MJF, SLS, FDM, SLM, BJ | not offered | h 1.5-4.5 | h 2.0-6.0 |

Oil-sprayed parts: holes at least **2.0 mm**, or the finish blocks them.

## 8. Small posts and pins (checklist)

Tallest post for a diameter, mm:

| | D1.0 | D2.0 | D3.0 |
|---|---|---|---|
| SLA | H 1 | H 2-4 | H 3-6 |
| MJF, SLS, FDM, SLM, BJ | not offered | H 2-4 | H 3-6 |

## 9. Special-shaped models

Large hollow shapes that take up a lot of the build volume can be printed, at an extra charge.

## 10. Tolerances (checklist)

| | Part, within 100 mm | Part, above 100 mm | Holes |
|---|---|---|---|
| SLA | ±0.2 mm | ±0.3% | ±0.3 mm |
| MJF | ±0.3 mm | ±0.4% | ±0.3 mm |
| SLS | ±0.3 mm | ±0.4% | ±0.3 mm |
| FDM | ±0.3 mm | ±0.4% | ±0.4 mm |
| SLM | ±0.3 mm | ±0.4% | ±0.5 mm |
| BJ | ±0.3 mm or ±0.4% up to 50 mm | ±1.3% above 50 mm | ±0.5 mm |

- These are for parts that haven't warped and have no paint or oil spray.
- Holes usually come out **small**, and the thicker the wall round them, the smaller. 316L rings,
  sleeves and other enclosed openings: within -0.5 mm. For close-fitting holes and threads,
  leave material and drill or tap to size.
- SLA keeps moving after printing: 0.15 mm or 0.15% in 1-3 days, 0.2 mm or 0.20% in 3-7 days.
  No figures for the other processes.

## What it means for the review

- A part designed for your own FDM printer usually fails the JLC3DP wall check in places. The
  usual reasons: seal-groove side walls, floors under counterbores and light-pipe sleeves, at
  1.0-1.8 mm where MJF or SLS wants 2.0 mm on a 100-200 mm part. Each flag means one of three
  things: thicken it, pick a process with a lower minimum (SLA), or accept the risk in writing.
- The overhang rows (ledge, bridge, island, steep) don't apply the same way. MJF and SLS print
  in powder with no supports. For SLA, SLM and JLC3DP's FDM, JLC3DP adds the supports and
  removes them, so read those rows as places with support marks, not as failures.

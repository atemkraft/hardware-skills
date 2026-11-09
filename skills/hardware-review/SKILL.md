---
name: hardware-review
description: The end-to-end runbook for reviewing and ordering a KiCad board (and its 3D-printed enclosure) with this repo's skills and tools, in order, with the command for each check and what a pass looks like. Covers part search, routing, the build gates, kicad-happy and the community rules, SPICE, the datasheet check, JLC placement and stock, the cart (never checking out), special nets, power and thermal calculations, and the enclosure print review. Use it whenever someone asks how to review a PCB before ordering, what to check before sending a board to JLCPCB, how to run any of these tools, or wants a full design review of a hardware order, even if they only name one step.
---

# Hardware review and order: the runbook

Each step is its own skill with the details; this page is the order to run them in, the
command for each, and what "done" looks like. Tool links and installs are in
[references/tools.md](references/tools.md). Read that first on a new machine.

**Why the order matters:** the cheap, mechanical checks first (they stop the expensive ones
wasting time), then the human-judgement ones, then the cart, then the package the owner signs.
Every result goes into the package with its source, so nothing rests on memory.

## 0. Before you start

- The design is in git and committed. The board is built from it (a script, or KiCad), and
  the fab files (Gerber zip, JLC BOM and CPL) come from the committed board.
- Note the worst case the board must survive: ambient temperature *inside its enclosure's
  surroundings*, supply range and surge, the order quantity.
- On a shared checkout, commit with explicit paths only.

## 1. Choose parts: `jlc-part-search`

```bash
python3 skills/jlc-part-search/scripts/find_part.py "Chip Resistor" --value 10k --package 0603 --bom fab/bom-jlcpcb.csv
```
Basic parts first (no loading fee); a part already on the board adds no BOM line.

## 2. Route: `freerouting-headless`

```bash
<KiCad python> skills/freerouting-headless/scripts/freeroute.py board.kicad_pcb
```
Always headless: no window on anyone's screen. Exit 0 = fully routed.

## 3. Gates: `board-review` part 1 (must pass)

ERC 0 errors; DRC 0 errors and 0 unconnected **with schematic parity**, against a rule file
holding the fab's limits; the netlist round trip; ratings; then:
```bash
<KiCad python> skills/jlc-placement-check/scripts/check_jlc.py --pcb board.kicad_pcb --bom fab/bom-jlcpcb.csv --cpl fab/cpl-jlcpcb.csv --boards 5
```
0 problems = every part sits on its pads with JLC's own footprint, and every line is in stock.

## 4. Review tools: `board-review` part 2 (read every finding)

```bash
skills/board-review/scripts/review_board.sh board.kicad_pcb review/ 65
```
kicad-happy (schematic, PCB, thermal at your ambient, EMC, cross-checks) and the stricter
labtroll JLCPCB rules. Run SPICE on the power path if you have decks. Triage each finding:
fixed, accepted (why), or a known false positive (kept in a list so the next review reads
only what's new). The vendored kicad-happy skills (`kicad`, `emc`, `spice`, `datasheets`,
`bom`, `jlcpcb`, distributor search) go deeper on any one of these.

## 5. Datasheets: `datasheet-check`

Every part against its maker's datasheet, part groups in parallel: pinout against the
netlist and the pads, package and height, ratings at the worst case, the datasheet's own
requirements. Notes cite pages; issues go in one table. Fix, rebuild, rerun 3-4.

## 6. Human review: `board-review` part 3

The board picture, 3D and the enclosure, connectors against real cables, heat, MLCCs near
edges. Then measure what DRC can't:
- **Special nets, power and heat** (with a source for every number): differential pairs, power paths (drop, track rise), the power
  budget per rail, each hot part's dissipation and temperature, and a thermal model of the
  board **in its sealed enclosure**. A box can add several kelvin per watt.
- **The enclosure as printed**: `print-review` on the slicer project:
  ```bash
  python3 skills/print-review/scripts/print_review.py review/print enclosure.3mf --material PETG
  ```
  No ledges or arms that droop, bridges within the material's span, no islands.
  If JLC3DP prints it, add the process and material (`--service jlc3dp:mjf:PA12`): no thin
  walls for the part's size and no sealed cavities, or each one is a written decision. Then
  every checklist line (detail, holes, posts, clearances, tolerances) answered against the design.

## 7. Cart: `jlcpcb-cart` (never check out)

Upload, set options after JLC detects the board, check every BOM line against your file and
tick them all, check placement and orientation, record the quote, save to cart, swap stale
items only with the owner's OK.

## 8. Hand it to the owner

Every result above with its source, the cart record, the open issues with severities, and
a checklist the owner signs. The owner pays after signing.

## Done means

Gates green; review findings triaged; datasheet issues fixed; special nets, power, heat and
print review written up; the cart item matches the files that were checked; the owner has
the results and has signed. If any input changes, run the checks again and get a new
signature.

---
name: board-review
description: The pre-order review of a KiCad board. Hard gates (ERC, DRC with schematic parity against the fab's rules, a netlist round trip, ratings, fab placement and stock) and advisory tools (kicad-happy's schematic, PCB, thermal and EMC analysis, a stricter community JLCPCB rule file, SPICE). Then the human review that DRC can't do: the board picture, 3D and enclosure, connectors against real cables, heat. Use before ordering or re-ordering a board, after any board change, or when asked to review a PCB.
---

# Board review before ordering

## 1. Gates (must pass; fix the design, never the gate)

Run them from the build so they can't be skipped:

| Gate | How |
|---|---|
| ERC, 0 errors | `kicad-cli sch erc --severity-error` |
| DRC, 0 errors and 0 unconnected, **with schematic parity** | `kicad-cli pcb drc --schematic-parity --severity-error`, against a `.kicad_dru` holding the fab's current limits (track/space, drill, annular ring, hole-to-hole, edge clearance, silkscreen) |
| The netlist is the design | if the design comes from a script or a netlist, read the board back and compare pin by pin |
| Ratings | each part's voltage, current and power against the worst case (a small table per part; `datasheet-check` supplies the numbers) |
| Fab placement and stock | the assembler's footprint orientation and stock for the order quantity (e.g. check every LCSC number's stock for N boards) |
| The fab files are the board | re-plot the Gerbers from the board with `kicad-cli pcb export gerbers` and compare them file by file with the zip |

## 2. Review tools (advisory, read every finding)

`scripts/review_board.sh <board.kicad_pcb> <out dir>` runs:
- **kicad-happy** (pinned; MIT, by Andrew Klofas, included as `vendor/kicad-happy`):
  schematic and PCB analysis, thermal at your ambient temperature, EMC pre-compliance, and
  cross-checks. Run it with the network off; read it before bumping the pin.
- **A stricter community JLCPCB rule file**
  ([labtroll/KiCad-DesignRules](https://github.com/labtroll/KiCad-DesignRules), fetched at
  run time) as a second opinion on your own `.kicad_dru`.
- **SPICE** on the power path if the project has decks (ngspice, with the makers' models
  where they publish them: check a model against its datasheet table before trusting it).

**Triage** every finding: fixed, accepted (why), or a known false positive. Keep the list
of known false positives in the project's process doc, so each review reads only what's
new.

## 3. Human review (DRC can't see these)

- **Board picture:** placement, silkscreen readable and on the right parts, polarity marks.
- **3D and enclosure:** heights under the lid (check that the 3D models' heights are the
  makers' maximums), connector overhang, cable routes, a fit check against the box.
- **Connectors against the real cables:** pinout, polarity, plug direction, crossover vs
  straight.
- **Heat:** regulators, the module, anything near them, at the hottest ambient.
- **Each new part's datasheet** (`datasheet-check`).
- **Edges:** MLCCs near a V-cut or tab edge crack at depaneling; keep them off the edge or
  turn them parallel to it.
- **Special nets, power and heat:** list the differential pairs, power paths and sensitive
  nets and measure them; budget every rail against its limit; work out each hot part's
  dissipation and temperature at the worst ambient, **inside the enclosure** (a sealed box
  can add several kelvin per watt, enough to take a module past its rated ambient). Write
  each down with the source of every number.

## 4. Then

Cart it (`jlcpcb-cart`), and keep every result above with its source file, so the owner
can check them before paying.

# hardware-skills: agent skills for ordering a PCB you can stand behind

Eight skills for an AI coding agent (written for Claude Code; plain Markdown and scripts,
so any agent that reads skills can use them) that take a KiCad board from "DRC passes"
to a checked cart item the owner can pay for, plus the tools on the way there:

| Skill | What the agent does |
|---|---|
| [`hardware-review`](skills/hardware-review/SKILL.md) | **Start here.** The runbook: every check below in order, the command for each, what a pass looks like, and [links and installs for every tool](skills/hardware-review/references/tools.md) |
| [`jlc-part-search`](skills/jlc-part-search/SKILL.md) | Searches JLC's parts library by value, package, tolerance and voltage, basic parts first, and flags the ones already on your board (reusing one adds no BOM line) |
| [`freerouting-headless`](skills/freerouting-headless/SKILL.md) | Autoroutes the board with Freerouting, **never opening its window**: a pinned jar, several runs and the best kept, and a replay cache so the same placement routes the same |
| [`board-review`](skills/board-review/SKILL.md) | Hard gates (ERC, DRC with schematic parity, the netlist round trip, ratings, fab stock), then the advisory tools (kicad-happy's schematic, PCB, thermal and EMC analysis, a stricter community JLCPCB rule file, SPICE) and the human review DRC can't do |
| [`datasheet-check`](skills/datasheet-check/SKILL.md) | Every part against its maker's datasheet, in parallel by part group: pinout against netlist and pads, package and **height**, ratings at the worst case, the datasheet's own requirements. Notes cite pages |
| [`jlc-placement-check`](skills/jlc-placement-check/SKILL.md) | Places every part with JLC's own footprint at your CPL's position and rotation, and checks each pad lands on yours (pin 1 on the wrong side, a part turned 90 degrees); every BOM line in stock for the order; a rough cost |
| [`jlcpcb-cart`](skills/jlcpcb-cart/SKILL.md) | Uploads to the owner's JLCPCB cart, checks JLC's BOM and placement pages line by line against your files, records the quote, swaps stale items. **Never checks out** |
| [`print-review`](skills/print-review/SKILL.md) | Printability of 3D-printed parts **as they sit on the slicer's plate** (reads the 3MF): flat ledges and arms that droop, bridges past the material's span, islands, steep overhangs, bed fit, with plots. Checked against a real enclosure's history: it flags the two problems that were found the hard way, and nothing once they were fixed |

## Also included: kicad-happy

[`vendor/kicad-happy`](vendor/kicad-happy) is Andrew Klofas's
[kicad-happy](https://github.com/aklofas/kicad-happy) v3.0.1, MIT, vendored unmodified (see
`VENDORED.md`). It's the analysis `board-review` runs, and its own skills install as a second
plugin from this marketplace: `kicad` (schematic and PCB analysis, thermal, DFM), `emc`
(pre-compliance), `spice`, `datasheets` (structured specs from PDFs), `bom`, `jlcpcb`,
`pcbway`, and distributor search (`lcsc`, `digikey`, `mouser`, `element14`).

## Why

DRC passing doesn't mean the board is right. On the board these skills were built on, every
gate was green, and the datasheet check still found seven issues:
- a regulator with more than twice its maker's maximum output capacitance;
- a TVS that clamped above the input limit of the converter it protected;
- a polyfuse 18.4 mm tall under a lid with 17.9 mm of room (its 3D model said 11 mm, so the
  enclosure fit check passed against the wrong part);
- bleed resistors with no margin against opto leakage when hot;
- a USB VBUS that floated up and would have back-fed a laptop;
- wrong maker names on the BOM.

Separately, the review found capacitors close enough to the board edge to crack at
depaneling. JLC's own pages, checked line by line, had unticked the three status LEDs.

## The flow

```
jlc-part-search (pick parts)  →  place  →  freerouting-headless (route)
      →  board-review  →  datasheet-check  →  fix, rebuild, gates green
      →  print-review (the enclosure, as printed)
      →  jlc-placement-check (0 problems for the order quantity)
      →  jlcpcb-cart (cart item Y30, never paid)
      →  the owner reviews the results and pays
```

A changed board or a re-carted order means running the checks again.

## Install

As a Claude Code plugin:

```bash
claude plugin marketplace add atemkraft/hardware-skills
```

```bash
claude plugin install pcb-signoff@hardware-skills
```

```bash
claude plugin install kicad-happy@hardware-skills
```

Or copy `skills/*` (and `vendor/kicad-happy/skills/*`) into your project's `.claude/skills/`
(or `~/.claude/skills/`).

**Needs:** KiCad 9 (`kicad-cli`), Python 3, Poppler for datasheet text, ngspice if you
simulate. The placement check
and the router run with KiCad's own Python (for `pcbnew`); the router also needs Java and
the Freerouting jar, which you download. The cart skill needs a
browser the agent can drive with the owner signed in (e.g. Claude in Chrome).

## Safety rails in the skills

- The agent never pays, never checks out, never accepts anything at the fab beyond the
  options listed. Swapping a cart item needs the owner's OK.
- The checks are read-only on the design. A failed gate stops the flow; it doesn't get
  papered over.
- Downloaded datasheets go in their own scratch folder and are never executed.
- Third-party review tools are pinned (kicad-happy vendored at a tag) and run with
  the network off. The Freerouting jar is pinned by its SHA-256.
- Freerouting always runs headless: no window opens on the owner's screen.

## Credits

- [kicad-happy](https://github.com/aklofas/kicad-happy) by Andrew Klofas (MIT), the
  schematic, PCB, thermal and EMC analysis, vendored unmodified in `vendor/kicad-happy`.
- [labtroll/KiCad-DesignRules](https://github.com/labtroll/KiCad-DesignRules): the
  community JLCPCB rule file, fetched at run time (not redistributed).
- [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts) by Jan Mrázek (MIT): the JLC parts
  catalogue the part search reads, fetched at run time.
- JLC's EasyEDA library: the footprints the placement check compares against, fetched per
  part and cached locally, never redistributed (its terms ask that).
- [Freerouting](https://github.com/freerouting/freerouting) (GPL-3): the router, run as a
  separate program from the jar you download; not included here.
- KiCad's `kicad-cli` and `pcbnew` do the heavy lifting.

Other tools the workflow uses, not redistributed here (links and installs in
[`hardware-review/references/tools.md`](skills/hardware-review/references/tools.md)):
[KiCad](https://www.kicad.org), [ngspice](https://ngspice.sourceforge.io) with makers' own
SPICE models, [OpenSCAD](https://openscad.org),
[Bambu Studio](https://bambulab.com/en/download/studio)'s command line (headless slicing),
[Poppler](https://poppler.freedesktop.org) (`pdftotext`, `pdftoppm`),
[Pillow](https://python-pillow.org), and
[Claude in Chrome](https://chromewebstore.google.com/detail/fcoeoabgfenejglbffodgkkbkcdhcgfn)
for the fab's pages.

Built while taking a real product board from prototype to its first assembled order.

## Licence

MIT, see [LICENSE](LICENSE). kicad-happy keeps its own MIT licence.

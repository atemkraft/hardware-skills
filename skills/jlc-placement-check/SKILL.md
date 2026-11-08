---
name: jlc-placement-check
description: Before a JLCPCB assembly order, place every part with JLC's own (EasyEDA) footprint at the CPL's position and rotation and check each of its pads lands on the board's pad with the same number (catching pin 1 on the wrong side, a part turned 90 degrees, or an off-centre footprint), and check every BOM line's LCSC part exists and is in stock for N boards, with a rough basic/extended cost. Use after generating the JLC BOM and CPL, before carting or re-ordering a board, or after any part swap.
---

# Checking the JLC placement and BOM

JLC doesn't place your footprint: it places **its** footprint for the LCSC part, at your
CPL's Mid X/Y and rotation. Rotation conventions differ between libraries, so a CPL that
looks right can still put pin 1 on the wrong side. This check does what JLC will do and
compares pad by pad. It's the scripted version of JLC's placement preview, run on every
part, every build.

## Requirements

- KiCad 9's Python, for `pcbnew`. On macOS:
  `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`.
  On Linux, the system `python3` that KiCad's package installs `pcbnew` for.
- `curl`, and network access to `easyeda.com` and `jlcpcb.com`.
- The board, and the JLC BOM and CPL made from **that** board:
  BOM `Comment, Designator, Footprint, LCSC Part #`;
  CPL `Designator, Mid X, Mid Y, Layer, Rotation`.

## Steps

1. Generate the BOM and CPL from the committed board (your fab script or a KiCad JLC
   plugin).
2. Run it for the number of boards JLC will assemble:

   ```bash
   KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
   $KPY scripts/check_jlc.py --pcb hw/board.kicad_pcb --bom hw/fab/bom-jlcpcb.csv \
     --cpl hw/fab/cpl-jlcpcb.csv --boards 5
   ```

   | Option | Meaning |
   |---|---|
   | `--boards N` | boards assembled, for the stock check (default 10) |
   | `--hand-solder REF,REF` | parts JLC won't place by machine (you fit them, or JLC hand-solders a through-hole part): placement not checked, counted as hand-soldered |
   | `--skip-prefix PFX,PFX` | the same, by footprint library-id prefix (`Connector_Molex:`, `MyLib:Terminal`) |
   | `--shape-only REF,REF` | pads match by shape, not number (a 2xN socket JLC numbers by row and KiCad odd/even) |

   Through-hole parts are checked like any other by default: JLC places those too, with
   the same footprint. Skip only the ones that really aren't placed.
3. Read the output:

   ```
   == placement: cpl-jlcpcb.csv against JLC's (EasyEDA) footprints (CPL origin: board edge, bottom-left, median offset 0.00 mm)
      ok   C2       0  C1206
      FAIL D2     270  LED0805-R-RD: pad 2 misses ours by 1.99 mm; fits at 90 (add 180)
   == BOM: bom-jlcpcb.csv, stock for 5 boards
      ok   C4410      basic     SMT stock  2200011  1206W4F1001T5E  R3 R7 ...
      FAIL C1234567   extended  SMT stock       12  LED-RGB-5050  D3 D4 D5  <- stock 12 < 15 needed
   == cost (5 boards, Standard PCBA, rough): 28 BOM lines, 24 SMT x US$1.53 loading ...
   == 0 problem(s)
   ```

   - **The origin line first.** The CPL's origin is picked automatically (board-edge
     bottom-left, the drill/place origin, the grid origin, or the page origin), whichever
     matches the footprints' positions best. A median offset over about 1 mm means the
     CPL wasn't made from this board: regenerate it before reading anything else.
   - **`FAIL ... fits at N (add D)`**: JLC's footprint lands only when turned by D degrees.
     Fix the rotation in your CPL generator (a per-footprint offset), never by hand in the
     CSV, and re-run. `no rotation fits` means a wrong part or footprint.
   - **`our pad(s) X get no pin`**: JLC's part has fewer pads than your footprint (a
     missing thermal pad or shield stake): a wrong part or footprint.
   - **`?`**: no footprint at EasyEDA, or the lookup failed. Look at the part on JLC's
     site before ordering.
   - **BOM `FAIL`**: not in JLC's library, not enough stock for the order, or the BOM
     names a part that isn't on the board.
   - **cost lines** are rough (late-2026 fees); JLC's quote has the last word. A `bake`
     line means a moisture-sensitive part that JLC bakes first (a fee and about 2 days).

Exit status: 0 with no problems, 1 with any, 2 on bad input (a missing file or column).
Every `FAIL` and `?` is a problem: fix the design or the fab files, never the check.

## Polarity

For two-pad polarised parts the pins are matched by name, not number, since JLC often
numbers an LED's anode 1 and KiCad its cathode 1. Names come from the board's pad pin
functions when the board has them, else from KiCad's standard footprint names
(`Diode_*:D_*`, `LED_*:LED_*`: 1 = K, 2 = A; `CP_*`, `C_Elec*`, tantalum: 1 = +, 2 = -), and
JLC's from its symbol (an SMD electrolytic's from its chamfered outline). A polarised part
on a footprint with another name is matched by number: check its polarity by eye in JLC's
preview.

## Limits

- Bottom-side parts are listed as not checked.
- It checks that JLC's pads land on yours, not that the part is right: its value, rating
  and package height come from the datasheet (`datasheet-check`).
- A few library differences are known and handled (USB-C shell stakes, numbered mounting
  stakes, SOT-223 tab numbered 4, 4-pad switches matched by shape). Another mismatch shows
  as a FAIL to look at; use `--shape-only` only once you've seen that the shapes agree.
- JLC's and EasyEDA's endpoints aren't public APIs and can change. Results are cached
  for a day in `${XDG_CACHE_HOME:-~/.cache}/hardware-skills/jlc-cache`; a footprint
  falls back to an older cached copy if EasyEDA is unreachable (stock never does).

## Credits

Footprints and symbols are JLC's EasyEDA library (JLCEDA/EasyEDA, https://easyeda.com),
fetched per part at run time. Its terms ask that its content not be redistributed: keep
the cache out of your repository and your review results (record the results, not the
footprints). Stock and prices are JLCPCB's.

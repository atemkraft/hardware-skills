---
name: jlc-part-search
description: Parametric search of JLCPCB's assembly parts library (the yaqwsx/jlcparts catalogue) by category, value, package, tolerance, voltage and text, ranked basic > preferred > extended, then stock, then price, with parts already on your board flagged from its JLC BOM. Use when choosing or swapping a part for a JLC-assembled board, replacing an out-of-stock part, or cutting extended-part fees.
---

# Finding a part in JLC's library

JLC charges for every extended part line, and a part already on the board adds no line at
all. So look for a basic part, or one you already use, before reaching for a new one.

## Requirements

- Python 3 (any; no packages needed) and `curl`.
- Network access to `yaqwsx.github.io` (the catalogue). The first search downloads the
  manifest and the category's shards (a few MB to tens of MB); they're cached for a day in
  `${XDG_CACHE_HOME:-~/.cache}/hardware-skills/jlcparts`.

## Steps

1. Pick the category: the first argument is a case-insensitive substring of
   "category / subcategory" (`"Chip Resistor"`, `"Multilayer Ceramic"`, `"TVS"`,
   `"Schottky"`, `"LDO"`).
2. Search, with the board's JLC BOM so reuse shows:

   ```bash
   scripts/find_part.py "Chip Resistor" --value 1k --package 1206 --bom fab/bom-jlcpcb.csv
   scripts/find_part.py "Multilayer Ceramic" --value 100nF --package 0603 --voltage 50 --tolerance 10
   scripts/find_part.py "TVS" --voltage 24 --text SMBJ
   ```

   | Option | Meaning |
   |---|---|
   | `--value` | resistance, capacitance or inductance: `5.6k`, `4k7`, `100nF`, `10uH` (exact match) |
   | `--package` | substring of the package (`0805`, `SOT-23`, `SMB`) |
   | `--tolerance` | at most this, percent |
   | `--voltage` | at least this rated voltage (or TVS stand-off), volts |
   | `--text` | substring of the maker part number or description |
   | `--qty` | boards, for the price column (default 10) |
   | `--bom` | JLC BOM CSV (`LCSC Part #` and `Designator` columns): flag parts on the board |
   | `-n` | rows to show (default 15) |

3. Read the output:

   ```
   88 match(es) in 1 category (catalogue of 2026-11-08; price at 10)
     C4410      Basic       2200011  $0.0085   1206W4F1001T5E  1206  ... 1kΩ ... ±1%  <- on board: R3 R7
     C131398    Extended    2812253  $0.0085   RC1206FR-071KL  1206  ...
   1 of the matches already on the board: C4410
   ```

   Columns: LCSC number, class, JLC stock, unit price at `--qty`, maker part number,
   package, description. `<- on board` means reusing it adds no BOM line. The last line
   lists every match already on the board, even one below the `-n` cut.
4. Before committing to a part, check it: its datasheet (`datasheet-check`), and its
   footprint and stock against the board (`jlc-placement-check`).

Exit status 0 with matches, 1 with none.

## Limits

- The catalogue is a daily snapshot of JLC's library, not JLC itself: stock and the
  basic/extended class can change. `jlc-placement-check` asks JLC directly before ordering.
- `--value` matches the part's resistance, capacitance or inductance exactly; it doesn't
  search ranges. `--voltage` reads attributes whose names look like a rated, maximum or
  stand-off voltage; parts with that figure missing are dropped.
- Attribute names are the catalogue's (from LCSC), so a category may describe the same
  property differently. Widen the search (`--text`, no `--package`) if a part you expect
  is missing.

## Credits

The catalogue is [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts) by Jan Mrázek
(MIT), built from JLCPCB's and LCSC's public data. It's fetched at run time, not
redistributed.

---
name: datasheet-check
description: Check every part on a PCB against its maker's datasheet (pinout against the netlist and footprint pads, package against footprint, ratings at the worst-case temperature, the datasheet's own application requirements, and the design's comments and BOM claims), part group by part group, with notes citing pages. Use before ordering a board, after a part swap, or when asked to "check the datasheets".
---

# Datasheet check

A build's gates (ERC, DRC, schematic parity) can't see a wrong pinout in a custom symbol,
a capacitor outside a regulator's stable range, a fuse taller than the lid, or a TVS that
clamps above the part it protects. This check can. It found seven such issues on one
board that had passed every gate.

## Method

1. **List the parts** from the design's source of truth (netlist script, schematic or BOM):
   reference, value, maker part number, supplier number (e.g. LCSC), footprint, and the nets
   on each pin.
2. **Split them into groups** and run one subagent per group in parallel, e.g. power path
   (fuses, diodes, regulators, current limits, bulk caps, TVS), the MCU/module and
   interfaces (USB, RS-485, connectors, LEDs), passives and the analogue paths. Give each
   subagent the part list, the netlist file, the worst-case conditions (ambient temperature,
   supply range, surge) and the rules below. Each writes one notes file.
3. **For every part, fetch the datasheet**: the supplier's copy (LCSC, DigiKey) or the
   maker's. Put downloads in a scratch folder of their own, extract text with
   `pdftotext -layout`, and never run anything downloaded. Record the URL, the revision and
   the page of every claim.
4. **Check:**
   - **Pinout:** datasheet pin → function against the netlist's pin → net, and against the
     footprint's pad numbering. Watch makers that number pins differently from the
     footprint family (5050 RGB LEDs, SOT-23 variants, connectors).
   - **Package against footprint:** pad size and pitch, body size, and **height** against
     the enclosure (check the 3D model's height too: a short model makes a fit check pass
     against the wrong part).
   - **Ratings at the worst case:** voltage (including surge and clamp voltages), current,
     power, and temperature derating at the hottest ambient. A TVS's clamp voltage must sit
     below the absolute maximum of what it protects.
   - **The datasheet's requirements:** input and output capacitance ranges (too much can be
     as bad as too little), ESR, layout notes, enable and reset timing, pull-ups, bleed
     resistors, leakage at temperature.
   - **The design's claims:** comments, docs and BOM maker names agree with the datasheet.
5. **Verdict per part:** OK, NOTE (no change, but worth knowing) or ISSUE (with a proposed
   fix). Fixes prefer parts already in the BOM, then in-stock parts at the assembler
   (check stock and the maker on the supplier's product page).
6. **Summarize** in the folder's `README.md`: one table of issues (number, board, issue
   with datasheet and page, fix), then notes that change nothing, then what couldn't be
   verified and why (download refused, no drawing, dead link). Unverified stays unverified.

## Output

```
docs/datasheet-check-<date>/
  README.md                 the issues and fixes, notes, not verifiable
  power.md  interfaces.md  passives.md   part by part: URL, revision, pages, checks, verdict
```

When one check covers several boards, mark board-specific headings and table rows with
the board name (`v7 F2`, `| 3 | v8 | …`), so one board's part can be pulled out later.

## After the check

Make the fixes in the design's source, rebuild, rerun every gate, and update the docs.
Then re-cart (`jlcpcb-cart`): a cart item uploaded before the fixes is stale.

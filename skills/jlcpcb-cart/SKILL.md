---
name: jlcpcb-cart
description: Put a KiCad board into the owner's JLCPCB cart (PCB plus Standard or Economic PCBA), check JLC's BOM and placement pages against your own files, record the quote, and swap a stale cart item. Never checks out or pays. Use when asked to quote, upload, cart, re-cart, swap or check a board at JLCPCB.
---

# Putting a board in the JLCPCB cart

The owner enters payment and checks out. **Never click Secure Checkout, never pay, never
accept anything beyond the options below.** A cart item is replaced only with the owner's
OK. Drive the owner's own signed-in browser (e.g. Claude in Chrome). A sandboxed browser
pane often can't attach local files.

## Before the browser

1. The fab files are built from the committed board and the build's gates passed (see
   `board-review`): a Gerber zip, the JLC BOM (`Comment, Designator, Footprint, LCSC Part #`)
   and the CPL (`Designator, Mid X, Mid Y, Layer, Rotation`).
2. Note the quantities (boards made; boards assembled, 2-5 on a 5-board order) and the
   options the project uses (colour, finish, thickness).

## Upload

1. `cart.jlcpcb.com/quote`, file input "Add gerber file": upload the zip with the browser
   tool's file-upload action (don't click the input; a native picker can't be driven).
   Wait about 20 s for "Detected N layer board of W x H mm" and check it against the board.
2. **Set the PCB options only after the "Detected" line shows.** JLC resets choices made
   while it processes, including the finish, which reverts to OSP. Then read the
   selections back (the `.cur` buttons) before going on.
   - Lead-free HASL (or ENIG) if the product must be RoHS. OSP is the current default.
   - Confirm Production file: Yes for a revision's first build (accept the 48 h dialog).
   - Two rows have a "2" button ("Different Design", "PCBA Qty"): pick by label, not text.
3. **PCB Assembly** on. Standard PCBA for modules, fine pitch or anything Economic refuses;
   Economic for simple boards (it greys out while the finish is OSP, and then silently falls
   back to Standard with edge rails). Top side, PCBA qty, edge rails by JLC, Confirm Parts
   Placement: Yes (72 h dialog).
4. Next, Next, then upload the BOM and CPL and click Process.

## BOM page: check every line

- List the rows with JavaScript (designators, matched LCSC number, ticked or not) and diff
  them against your BOM file. Every line must be matched to **your** LCSC number. Look
  hardest at modules and anything changed since the last order.
- **Every line ticked:** `[...document.querySelectorAll('tbody input[type=checkbox]')]`,
  none unchecked, count equal to BOM lines. JLC often unticks addressable RGB LEDs
  (WS2812B/SK6812) with quantity 0: tick them.
- A warning icon: hover and read it. "Processing difficult" may add a fee after review;
  moisture-sensitive parts may bring a baking dialog later.

## Placement page

- Accept JLC's auto-align prompt if your CPL uses the board origin (common).
- In 2D, top side, fit to view, then zoom on: the module's pins on all sides; polarised
  parts' pin-1 dots against the silkscreen; every part changed since the last order.
  Through-hole parts show as outlines with a pin-1 dot: normal, they are hand-soldered.
- **Don't use the viewer's arrow buttons:** they nudge the selected part.
- RGB LEDs and other parts whose maker numbers pins differently from the footprint: get
  the footprint's pad positions and nets from the board file (KiCad's Python:
  `FindFootprintByReference`, `Pads()`), and check that JLC's pin-1 dot sits on the pad
  carrying the maker's pin 1 (often GND, not VDD).

## Quote & Order

- Record the full breakdown: PCB lines, setup, stencil, components, feeder loading, SMT,
  hand-soldering, X-ray, packaging, total.
- Product description: choose the honest customs category (e.g. Circuit Control,
  HS 853890 for a controller board).
- Baking: if the maker's datasheet gives a higher MSL than JLC lists, JLC won't offer
  baking. Ask in the **Assembly Remark** ("Please bake D11-D13 (part, LCSC#) before reflow:
  the maker's datasheet rates them MSL 5a").
- SAVE TO CART. The cart can show empty for a few seconds; reload and read it as text.

## Swapping a stale item

1. Save the new item first, then delete the old one, so the cart is never empty.
2. Delete with the old item's trash icon and confirm in the popover. Check that the ticked
   row is the old one.
3. Read the cart back: item names, quantities, prices.

## Report

The item ID, quantities, the price with its breakdown, the checks made (BOM N/N matched
and ticked, placement, orientation), remarks, anything replaced, and that **nothing was
ordered**. Keep it with the review results as the order's record.

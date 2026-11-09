---
name: freerouting-headless
description: Autoroute a placed KiCad board with Freerouting, always headless (no window, ever): Specctra DSN out of pcbnew, Freerouting from a SHA-256-pinned jar with several runs side by side and the best kept, the session (SES) back into the board, and a replay cache keyed by the DSN's hash so the same placement routes the same. Use when asked to autoroute, re-route after a placement change, or route a scratch copy to see whether a placement is routable.
---

# Routing a board with Freerouting, headless

> **Always headless. Never open a Freerouting window.** Every run passes both
> `-Djava.awt.headless=true` (to Java, before `-jar`) and `--gui.enabled=false` (to
> Freerouting). Without both, Freerouting opens its GUI. Don't run the jar any other
> way, don't drop either flag, and don't start KiCad's Freerouting plugin, which opens it.

## Requirements

- KiCad 9's Python, for `pcbnew`. On macOS:
  `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`.
- Java 17 or later (`JAVA`, else `java` on the PATH, else Homebrew's OpenJDK).
- The Freerouting jar, which **the user downloads** from
  [freerouting/freerouting releases](https://github.com/freerouting/freerouting/releases)
  (GPL-3; this repository doesn't include it). The script refuses a jar whose SHA-256
  isn't the pinned one, so a rebuild routes with the same router.

| Variable | Default |
|---|---|
| `FREEROUTING_JAR` | `${XDG_CACHE_HOME:-~/.cache}/hardware-skills/freerouting-2.5.0.jar` |
| `FREEROUTING_SHA256` | Freerouting 2.5.0's: `f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7` |
| `JAVA` | `java` on the PATH |
| `FREEROUTING_PASSES` | 40 (the GND pass: `FREEROUTING_GND_PASSES`, 30) |
| `FREEROUTING_JOBS` | 4 runs side by side; the best is kept |
| `REROUTE=1` | ignore the replay cache |

## Steps

1. Commit the board first (it's saved over unless you pass `--out`), or route a copy.
2. Check the DSN exports (no Java needed):

   ```bash
   KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
   $KPY scripts/freeroute.py hw/board.kicad_pcb --dsn-only --work /tmp/route
   ```

3. Route:

   ```bash
   $KPY scripts/freeroute.py hw/board.kicad_pcb --out hw/board-routed.kicad_pcb \
     --inner-planes --no-outer-planes --pth-grow-um 110 --timeout 1800
   ```

   | Option | Meaning |
   |---|---|
   | `--out` | save here instead of over the input |
   | `--inner-planes` | 4+ layers: no traces on the inner layers, they're planes reached by vias |
   | `--no-outer-planes` | drop F.Cu/B.Cu zones from the DSN, so every pad gets a track; pour after routing |
   | `--pth-grow-um N` | inflate through-hole pads by N µm in the DSN only, for a fab rule stricter than your clearance (110 for JLC's 0.28 mm PTH-to-track over a 0.18-0.2 mm clearance) |
   | `--gnd-pass` | a second pass: lock what's routed, drop the GND plane, route GND as traces where there's room (`--gnd-net` if it isn't `GND`) |
   | `--keep DIR` | also keep the session in DIR by hash (commit it, and another machine replays it) |
   | `--timeout S` | stop after S seconds and keep the best so far |
   | `--work DIR` | where the DSN, SES and logs go (default: a temporary folder) |

4. Read the output:

   ```
      DSN: /tmp/route/board.dsn (80 KiB, 60 nets)
      freerouting: best of 4 run(s) (unrouted: 0, 2, 0, 1)
      freerouting: 0 unrouted; saved hw/board-routed.kicad_pcb
   ```

   Anything unrouted: the log path is printed; move parts or add room, don't hand the
   board over half-routed. Then refill the zones and run DRC with schematic parity
   (`board-review`): Freerouting's own clearance check isn't KiCad's or the fab's.

Exit status: 0 when fully routed, 1 with connections left (always 0 for `--gnd-pass`,
whose remainder is left to the pour), 2 on a setup error (no jar, wrong hash, no Java, no
board, DSN export or SES import failed).

## Replay

Freerouting is random: two runs route differently. Each routed session is kept in
`${XDG_CACHE_HOME:-~/.cache}/hardware-skills/freerouting/`, named by the SHA-256 of the DSN
it came from (with the jar's hash and the pass count). The same placement, nets and rules
replay that routing instead of routing again, and going back to an earlier placement
replays its routing too. Any change to the board's placement, nets or rules makes a new
hash and a fresh route. The copper comes back the same; KiCad may write the tracks in a
different order in the file.

## Limits

- A session (SES) carries the parts' positions as well as the copper: importing it puts
  every part back where it was when routed. Move a part and import an older session, and
  the part quietly moves back (the board still passes DRC). Only import a session whose
  DSN hash matches the board; to move one part on a finished board, route afresh or
  re-route that corner by hand.
- A board that routed once may not route again from scratch: a later change can leave a
  fresh route well short (one board went from 10 unrouted to 64). Keep the routed session with the
  board (`--keep`), and make small later changes in a way that doesn't need a re-route
  (silkscreen, values, a label moved instead of a part).

- It routes only: Freerouting's optimizer is off (on a dense board it can run far longer
  than the routing, single-threaded).
- The autoroute settings (via cost, F.Cu horizontal, B.Cu vertical) are a reasonable
  default for 2 and 4 layers, not tuned for your board. Hand-route sensitive nets
  (differential pairs, switching nodes, RF) first and lock them; Freerouting leaves
  locked tracks alone.
- With planes in the DSN, Freerouting may report plane-reached pads as unrouted, so a run
  never reaches 0 and goes to the pass cap. That's why `--no-outer-planes` and
  `--inner-planes` exist.

## Credits

[Freerouting](https://github.com/freerouting/freerouting) (GPL-3), run as a separate
program from the jar you download; not redistributed here. KiCad's `pcbnew` does the DSN
export and SES import.

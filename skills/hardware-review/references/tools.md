# Tools: links, installs and what each is for

Versions are the ones these skills were built and tested with; newer usually work. Nothing
here is bundled except kicad-happy (MIT, `vendor/kicad-happy`).

| Tool | Link | Install (macOS; Linux in brackets) | Used by | For |
|---|---|---|---|---|
| KiCad 9 (`kicad-cli`, `pcbnew` Python) | https://www.kicad.org | `brew install --cask kicad` (distro packages / kicad.org) | every board step | ERC, DRC with schematic parity, Gerbers, drills, PDFs, renders, SVG plots; `pcbnew` for the placement check and the router. Its Python: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3` |
| kicad-happy | https://github.com/aklofas/kicad-happy | vendored in `vendor/kicad-happy` (v3.0.1) | `board-review` | Schematic and PCB analysis, thermal, EMC pre-compliance, cross-checks, and its own skills |
| labtroll KiCad-DesignRules (JLCPCB) | https://github.com/labtroll/KiCad-DesignRules | fetched at run time by `review_board.sh` | `board-review` | A stricter community JLCPCB rule file, as a second opinion |
| Freerouting | https://github.com/freerouting/freerouting | download the jar (GPL-3); Java: `brew install openjdk` | `freerouting-headless` | Autorouting; always `-Djava.awt.headless=true --gui.enabled=false` |
| yaqwsx/jlcparts | https://github.com/yaqwsx/jlcparts (data: https://yaqwsx.github.io/jlcparts/) | fetched and cached by `find_part.py` | `jlc-part-search` | JLC's parts library as a searchable catalogue |
| JLCPCB / EasyEDA library | https://jlcpcb.com/parts | fetched per part, cached locally, never redistributed | `jlc-placement-check` | JLC's own footprints, to check your placement against |
| ngspice | https://ngspice.sourceforge.io | `brew install ngspice` (`apt install ngspice`) | `board-review` (SPICE) | Power-path and interface simulation. Use the makers' own models and check each against its datasheet table first |
| Poppler (`pdftotext`, `pdftoppm`, `pdfinfo`) | https://poppler.freedesktop.org | `brew install poppler` (`apt install poppler-utils`) | `datasheet-check` | Datasheet text and page images |
| Pillow | https://python-pillow.org | `pip install pillow` | `print-review` | Print-review plots (optional) |
| OpenSCAD | https://openscad.org | `brew install --cask openscad` | enclosure work | Parametric enclosure; STL export; sections for drawings |
| Bambu Studio (command line) | https://bambulab.com/en/download/studio | the app; run its binary with `--slice 0 --export-3mf` | enclosure work | Headless slicing for print time and filament; its 3MF projects feed `print-review` |
| Claude in Chrome | https://chromewebstore.google.com/detail/fcoeoabgfenejglbffodgkkbkcdhcgfn | the browser extension, signed in | `jlcpcb-cart` | Driving the owner's signed-in browser to upload and check the cart (a sandboxed pane often can't attach local files) |

## Quick check of a new machine

```bash
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli version
```

```bash
ngspice --version | head -1; pdftotext -v 2>&1 | head -1; java -version 2>&1 | head -1
```

```bash
python3 -c "import PIL; print('Pillow', PIL.__version__)"
```

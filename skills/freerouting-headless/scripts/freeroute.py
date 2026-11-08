#!/usr/bin/env python3
"""Routes a placed KiCad board with Freerouting, headless: Specctra DSN out,
Freerouting with no window, the session (SES) back in.

Run with KiCad's Python (it needs pcbnew):

    freeroute.py board.kicad_pcb                        route, save over the board
    freeroute.py board.kicad_pcb --out routed.kicad_pcb route, save elsewhere
    freeroute.py board.kicad_pcb --gnd-pass             then GND alone, as traces
    freeroute.py board.kicad_pcb --dsn-only             write the DSN and stop

It ALWAYS runs headless: -Djava.awt.headless=true and --gui.enabled=false
(without both, Freerouting opens its window). It routes only; the optimizer is
off. Exit status 1 if any connection is left unrouted (not for --gnd-pass,
whose remainder is left to the pour), 2 on a setup error.

Environment:
    FREEROUTING_JAR      the jar (default ${XDG_CACHE_HOME:-~/.cache}/hardware-skills/
                         freerouting-2.5.0.jar)
    FREEROUTING_SHA256   the jar's expected SHA-256 (default: Freerouting 2.5.0's),
                         so a rebuild routes with the same router
    JAVA                 java binary (default: java on PATH, else Homebrew's OpenJDK)
    FREEROUTING_PASSES   max passes (default 40; the GND pass 30)
    FREEROUTING_JOBS     runs side by side, the best kept (default 4)
    REROUTE=1            ignore the replay cache and route afresh

Replay: Freerouting is random. Every routed session is kept in
${XDG_CACHE_HOME:-~/.cache}/hardware-skills/freerouting/ under the SHA-256 of the
DSN it was routed from (plus the jar and pass count), so the same placement,
nets and rules replay the same routing instead of routing again. --keep DIR
also keeps a copy there (commit it for byte-identical rebuilds elsewhere).
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

XDG = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hardware-skills"
JAR = Path(os.environ.get("FREEROUTING_JAR") or XDG / "freerouting-2.5.0.jar")
JAR_SHA256 = os.environ.get("FREEROUTING_SHA256",
                            "f6f51bb02245e8e717f9359bd260cc9c5c0b1bc0acc8b7cb2cd5b8ffeb5de3c7")
JAVA = os.environ.get("JAVA") or shutil.which("java") or "/opt/homebrew/opt/openjdk/bin/java"
PASSES = int(os.environ.get("FREEROUTING_PASSES", "40"))
GND_PASSES = int(os.environ.get("FREEROUTING_GND_PASSES", "30"))
JOBS = int(os.environ.get("FREEROUTING_JOBS", "4"))
ROUTES = XDG / "freerouting"
HEADLESS = ["-Djava.awt.headless=true"]          # JVM flag, before -jar
NO_GUI = ["--gui.enabled=false"]                 # Freerouting flag, after the jar


def grow_pth(dsn_text, grow_um):
    """Inflate every through-hole padstack ([A]: all layers; not vias) by grow_um
    in the DSN only, so Freerouting keeps a larger PTH-to-track clearance than
    its single clearance rule would (e.g. JLC's 0.28 mm PTH-to-track). The
    board's pads are untouched: the session brings back only tracks and vias."""
    g = grow_um

    def grow(block):
        block = re.sub(r"\(circle (\S+) ([\d.]+)", lambda m: f"(circle {m.group(1)} {float(m.group(2)) + 2 * g:g}", block)
        block = re.sub(r"\(path (\S+) ([\d.]+)", lambda m: f"(path {m.group(1)} {float(m.group(2)) + 2 * g:g}", block)
        block = re.sub(r"\(rect (\S+) ([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)\)",
                       lambda m: "(rect {} {:g} {:g} {:g} {:g})".format(
                           m.group(1), float(m.group(2)) - g, float(m.group(3)) - g,
                           float(m.group(4)) + g, float(m.group(5)) + g), block)

        def poly(m):
            v = list(map(float, m.group(3).split()))
            out = []
            for x, y in zip(v[::2], v[1::2]):
                r = (x * x + y * y) ** 0.5 or 1.0
                out += [x * (1 + g / r), y * (1 + g / r)]
            return f"(polygon {m.group(1)} {m.group(2)} " + " ".join(f"{c:.3f}" for c in out) + ")"
        return re.sub(r"\(polygon (\S+) ([\d.]+)\s+([-\d.\s]+)\)", poly, block)

    out, pos = [], 0
    for m in re.finditer(r"\n(\s*)\(padstack (\S+)\n", dsn_text):
        if "[A]" not in m.group(2) or m.group(2).startswith("Via"):
            continue
        end = dsn_text.index("\n" + m.group(1) + ")", m.end())
        out += [dsn_text[pos:m.end()], grow(dsn_text[m.end():end])]
        pos = end
    return "".join(out) + dsn_text[pos:]


AUTOROUTE = """    (autoroute_settings
      (fanout off)
      (autoroute on)
      (postroute on)
      (vias on)
      (via_costs 50)
      (plane_via_costs 5)
      (start_ripup_costs 100)
      (start_pass_no 1)
      (layer_rule F.Cu (active on) (preferred_direction horizontal)
        (preferred_direction_trace_costs 1.0) (against_preferred_direction_trace_costs 1.6))
      (layer_rule B.Cu (active on) (preferred_direction vertical)
        (preferred_direction_trace_costs 1.2) (against_preferred_direction_trace_costs 2.0))
    )
"""


def freerouting_cmd(dsn, ses, passes):
    return [JAVA, "-Xmx1500m", *HEADLESS, "-jar", str(JAR), *NO_GUI,
            "--router.optimizer.enabled=false", "--router.max_threads=1",
            "-de", str(dsn), "-do", str(ses), "-mp", str(passes), "-mt", "1"]


def best_of(dsn, ses, log, passes, jobs, timeout):
    """`jobs` Freerouting runs side by side (each routes differently), the best
    kept: fewest unrouted connections, then the smallest session (less copper).
    Returns the unrouted count; the session is written to `ses`."""
    runs = []
    for i in range(jobs):
        s_, l_ = ses.with_name(f"{ses.stem}-{i}.ses"), log.with_name(f"{log.stem}-{i}.log")
        s_.unlink(missing_ok=True)
        fh = open(l_, "w")
        runs.append((s_, l_, fh, subprocess.Popen(freerouting_cmd(dsn, s_, passes), stdout=fh,
                                                  stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)))
    start = time.time()
    # the first run to route everything wins: the others are stopped, not waited for
    while any(r[3].poll() is None for r in runs):
        won = [r for r in runs if r[3].poll() == 0 and r[0].exists()
               and re.findall(r"\((\d+) unrouted", r[1].read_text(errors="replace"))[-1:] == ["0"]]
        if won or (timeout and time.time() - start > timeout):
            if not won:
                print(f"   freerouting: stopped after {timeout} s", file=sys.stderr)
            for r in runs:
                if r[3].poll() is None:
                    r[3].kill()
            break
        time.sleep(2)
    scored = []
    for i, (s_, l_, fh, proc) in enumerate(runs):
        proc.wait()
        fh.close()
        done = re.findall(r"\((\d+) unrouted and (\d+) violations\)", l_.read_text(errors="replace"))
        if s_.exists() and done:
            scored.append((int(done[-1][0]), s_.stat().st_size, i, s_, l_))
    if not scored:
        sys.exit(f"Freerouting wrote no session; see {log.parent}/{log.stem}-*.log")
    scored.sort()
    unrouted, _, i, s_, l_ = scored[0]
    print(f"   freerouting: best of {len(scored)} run(s) (unrouted: "
          f"{', '.join(str(t[0]) for t in sorted(scored, key=lambda t: t[2]))})")
    ses.write_bytes(s_.read_bytes())
    log.write_text(l_.read_text(errors="replace"))
    return unrouted


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", help="the placed .kicad_pcb")
    ap.add_argument("--out", help="save the routed board here (default: over the input)")
    ap.add_argument("--gnd-pass", action="store_true",
                    help="second pass: lock the existing tracks, drop the GND plane, route GND as traces")
    ap.add_argument("--gnd-net", default="GND", help="the ground net's name for --gnd-pass (default GND)")
    ap.add_argument("--inner-planes", action="store_true",
                    help="no traces on In1.Cu/In2.Cu: they are planes, reached by vias (4 layers)")
    ap.add_argument("--no-outer-planes", action="store_true",
                    help="drop F.Cu/B.Cu zones from the DSN (pour them after routing instead)")
    ap.add_argument("--pth-grow-um", type=float, default=0,
                    help="inflate through-hole pads by this much in the DSN only (e.g. 110 for JLC)")
    ap.add_argument("--work", help="folder for the DSN, SES and logs (default: a temporary folder)")
    ap.add_argument("--keep", help="also keep the routed session here, by DSN hash (to commit)")
    ap.add_argument("--timeout", type=int, default=0, help="stop routing after this many seconds (0: none)")
    ap.add_argument("--dsn-only", action="store_true", help="write the DSN and stop (no Java needed)")
    a = ap.parse_args()

    pcb = Path(a.board).resolve()
    if not pcb.is_file():
        print(f"no such board: {pcb}", file=sys.stderr)
        return 2
    if not a.dsn_only:
        if not JAR.exists():
            print(f"Freerouting jar not found: {JAR} (download it, set FREEROUTING_JAR)", file=sys.stderr)
            return 2
        sha = hashlib.sha256(JAR.read_bytes()).hexdigest()
        if JAR_SHA256 and sha != JAR_SHA256:
            print(f"{JAR}: SHA-256 {sha} is not the pinned {JAR_SHA256} (set FREEROUTING_SHA256)",
                  file=sys.stderr)
            return 2
        if not (Path(JAVA).exists() or shutil.which(JAVA)):
            print(f"java not found: {JAVA} (set JAVA)", file=sys.stderr)
            return 2

    import pcbnew
    work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="freeroute-"))
    work.mkdir(parents=True, exist_ok=True)
    tag = "-gnd" if a.gnd_pass else ""
    dsn, ses, log = work / f"{pcb.stem}{tag}.dsn", work / f"{pcb.stem}{tag}.ses", work / f"freerouting{tag}.log"

    board = pcbnew.LoadBoard(str(pcb))
    if a.gnd_pass:
        for t in board.GetTracks():
            t.SetLocked(True)
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        print("DSN export failed", file=sys.stderr)
        return 2
    text = dsn.read_text()
    if a.pth_grow_um:
        text = grow_pth(text, a.pth_grow_um)
    if a.gnd_pass:
        text = re.sub(r"\n\s*\(plane /?" + re.escape(a.gnd_net) + r" \(polygon [^)]*\)\)", "", text)
    elif a.no_outer_planes:
        text = re.sub(r"\n\s*\(plane \S+ \(polygon [FB]\.Cu [^)]*\)\)", "", text)
    rules = AUTOROUTE
    if a.inner_planes and "(layer In1.Cu" in text:
        inner = "".join(f"      (layer_rule {n} (active off))\n" for n in re.findall(r"\(layer (In\d+\.Cu)", text))
        rules = rules.replace("      (layer_rule B.Cu", inner + "      (layer_rule B.Cu", 1)
    if "    (boundary\n" in text:
        text = text.replace("    (boundary\n", rules + "    (boundary\n", 1)      # after the layers
    dsn.write_text(text)
    nets = len(re.findall(r"\n\s*\(net ", text))
    print(f"   DSN: {dsn} ({len(text) // 1024} KiB, {nets} nets)")
    if a.dsn_only:
        return 0

    passes = GND_PASSES if a.gnd_pass else PASSES
    body = text.split("\n", 1)[1]                    # minus the line with this checkout's path
    key = hashlib.sha256((body + f"\n;jar {JAR_SHA256} passes {passes}").encode()).hexdigest()[:16]
    cached = ROUTES / f"{pcb.stem}{tag}-{key}.ses"
    kept = Path(a.keep) / cached.name if a.keep else None
    if os.environ.get("REROUTE") != "1" and (cached.exists() or (kept and kept.exists())):
        src = cached if cached.exists() else kept
        ses.write_bytes(src.read_bytes())
        unrouted = int(src.with_suffix(".unrouted").read_text()) if src.with_suffix(".unrouted").exists() else 0
        print(f"   freerouting: replaying {src}")
    else:
        unrouted = best_of(dsn, ses, log, passes, max(1, JOBS), a.timeout)
        ROUTES.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(ses.read_bytes())
        cached.with_suffix(".unrouted").write_text(f"{unrouted}\n")
    if kept:
        kept.parent.mkdir(parents=True, exist_ok=True)
        kept.write_bytes(ses.read_bytes())
        kept.with_suffix(".unrouted").write_text(f"{unrouted}\n")
    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        print("SES import failed", file=sys.stderr)
        return 2
    if a.gnd_pass:
        for t in board.GetTracks():
            t.SetLocked(False)
    out = Path(a.out) if a.out else pcb
    board.Save(str(out))
    if a.gnd_pass:
        print(f"   freerouting GND pass: {unrouted} left (to the pour); saved {out}")
        return 0
    print(f"   freerouting: {unrouted} unrouted; saved {out}" + (f" (log: {log})" if unrouted else ""))
    return 0 if unrouted == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Advisory pre-order review of a KiCad board: kicad-happy (schematic, PCB, thermal, EMC,
# cross-checks) and a stricter community JLCPCB rule file as a second opinion. Prints a
# summary; read every report in <out dir>.
#
#   review_board.sh <board.kicad_pcb> <out dir> [ambient C, default 50]
#
# kicad-happy: vendor/kicad-happy in this repo (vendored, pinned v3.0.1), or KICAD_HAPPY=path.
set -euo pipefail
PCB="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; OUT="$2"; AMB="${3:-50}"
N="$(basename "$PCB" .kicad_pcb)"; DIR="$(dirname "$PCB")"
HERE="$(cd "$(dirname "$0")" && pwd)"
KH="${KICAD_HAPPY:-$HERE/../../../vendor/kicad-happy}"
case "$(uname)" in Darwin) K="${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}";; *) K="${KICAD_CLI:-kicad-cli}";; esac
[ -d "$KH/skills/kicad/scripts" ] || { echo "kicad-happy not found in vendor/kicad-happy (or set KICAD_HAPPY)"; exit 1; }
mkdir -p "$OUT/proj"; OUT="$(cd "$OUT" && pwd)"
cp "$DIR/$N.kicad_sch" "$DIR/$N.kicad_pcb" "$OUT/proj/"; cp "$DIR/$N"-*.kicad_sch "$OUT/proj/" 2>/dev/null || true   # sub-sheets of a multi-page schematic; [ -f "$DIR/$N.kicad_pro" ] && cp "$DIR/$N.kicad_pro" "$OUT/proj/"
S="$KH/skills/kicad/scripts"; PY=(python3 -s -E)
echo "== kicad-happy ($(grep -o "v[0-9][0-9.]*" "$KH/VENDORED.md" 2>/dev/null | head -1 || echo unpinned)), ambient $AMB C"
(
  cd "$OUT"
  "${PY[@]}" "$S/analyze_schematic.py" proj/$N.kicad_sch -o sch.json 2>/dev/null
  "${PY[@]}" "$S/analyze_pcb.py" proj/$N.kicad_pcb --schematic sch.json --proximity -o pcb.json 2>/dev/null
  "${PY[@]}" "$S/analyze_schematic.py" proj/$N.kicad_sch --text > schematic.txt 2>&1
  "${PY[@]}" "$S/analyze_pcb.py" proj/$N.kicad_pcb --schematic sch.json --text > pcb.txt 2>&1
  "${PY[@]}" "$S/analyze_thermal.py" -s sch.json -p pcb.json --ambient "$AMB" --text > thermal.txt 2>&1 || true
  "${PY[@]}" "$KH/skills/emc/scripts/analyze_emc.py" -s sch.json -p pcb.json --standard fcc-class-b --text > emc.txt 2>&1 || true
  "${PY[@]}" "$S/cross_analysis.py" -s sch.json -p pcb.json --text > cross.txt 2>&1 || true
)
for f in schematic pcb thermal emc cross; do
  printf "   %-10s %s\n" "$f" "$(grep -E "^Total|score:" "$OUT/$f.txt" 2>/dev/null | head -2 | tr '\n' ' ')"
done
echo "== community JLCPCB rules (labtroll/KiCad-DesignRules), a second opinion"
LT="${XDG_CACHE_HOME:-$HOME/.cache}/pcb-signoff/labtroll-JLCPCB.kicad_dru"; mkdir -p "$(dirname "$LT")"
[ -f "$LT" ] || curl -sfL -o "$LT" https://raw.githubusercontent.com/labtroll/KiCad-DesignRules/main/JLCPCB/JLCPCB.kicad_dru
mkdir -p "$OUT/lt"; cp "$DIR/$N.kicad_pcb" "$OUT/lt/"; [ -f "$DIR/$N.kicad_pro" ] && cp "$DIR/$N.kicad_pro" "$OUT/lt/"; cp "$LT" "$OUT/lt/$N.kicad_dru"
"$K" pcb drc -o "$OUT/labtroll-drc.rpt" "$OUT/lt/$N.kicad_pcb" >/dev/null 2>&1 || true
grep "^\[" "$OUT/labtroll-drc.rpt" | sed 's/ (.*//' | sort | uniq -c | grep -v "silk\|text_height\|lib_footprint\|unconnected" || true
echo "== reports in $OUT (triage every finding: fixed, accepted, or known false positive)"

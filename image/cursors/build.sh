#!/bin/sh
# Das Akari-Cursor-Set als Xcursor-Thema für die Linux-Apps (Firefox, xterm …).
# Quelle sind dieselben SVGs wie im Browser (akari/static/assets/cursors) samt
# hotspots.txt; jede Form wird in 24, 32 und 48 Pixeln gerastert, der Hotspot
# mitskaliert. Danach bekommen die Namen, die X und GTK erwarten, Verweise.
#   build.sh <svg-ordner> <thema-ordner>
set -eu
src=$1 out=$2
mkdir -p "$out/cursors" /tmp/xc
while read -r name x y; do
  : > "/tmp/xc/$name.cfg"
  for s in 24 32 48; do
    rsvg-convert -w "$s" -h "$s" "$src/$name.svg" -o "/tmp/xc/$name-$s.png"
    echo "$s $((x * s / 32)) $((y * s / 32)) /tmp/xc/$name-$s.png" >> "/tmp/xc/$name.cfg"
  done
  xcursorgen "/tmp/xc/$name.cfg" "$out/cursors/$name"
done < "$src/hotspots.txt"

# Namen aus X-Cursorschrift, freedesktop und CSS → eine unserer Formen
link() { t=$1; shift; for n in "$@"; do ln -sf "$t" "$out/cursors/$n"; done; }
cd "$out/cursors"
link default     left_ptr arrow top_left_arrow x-cursor X_cursor
link pointer     hand1 hand2 pointing_hand
link text        xterm ibeam vertical-text
link move        fleur all-scroll size_all
link grab        openhand
link grabbing    closedhand dnd-move dnd-none
link ew-resize   sb_h_double_arrow h_double_arrow col-resize e-resize w-resize left_side right_side size_hor split_h
link ns-resize   sb_v_double_arrow v_double_arrow row-resize n-resize s-resize top_side bottom_side size_ver split_v
link nwse-resize bd_double_arrow nw-resize se-resize top_left_corner bottom_right_corner size_fdiag
link nesw-resize fd_double_arrow ne-resize sw-resize top_right_corner bottom_left_corner size_bdiag
link wait        watch
link progress    left_ptr_watch half-busy
link not-allowed crossed_circle forbidden no-drop circle dnd-no-drop
link help        question_arrow whats_this left_ptr_help
link crosshair   cross tcross cross_reverse diamond_cross
printf '[Icon Theme]\nName=Akari\nComment=Akari OS\n' > "$out/index.theme"
rm -rf /tmp/xc

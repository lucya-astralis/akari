#!/usr/bin/env bash
# What akari-shell brings that Debian does not have, on fixed versions, into
# vendor/ (not checked in; the source package carries it, so the build itself
# never goes online):
#
#   oh-my-zsh       a fixed commit (it has no releases)             MIT
#   powerlevel10k   a release                                        MIT
#   gitstatusd      the binary p10k's release names, per architecture  GPL-3
#   MesloLGS NF     p10k's font, from powerlevel10k-media at a commit  Apache-2.0
#
# Every download is checked against vendor.lock (sha256). A new pin: change it
# below, delete its line in vendor.lock, run this; the new sum is written
# there and goes into the commit. VENDOR_STRICT=1 (CI) takes nothing that is not in it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
V="$ROOT/vendor"; LOCK="$ROOT/vendor.lock"
OMZ=1eebae3a3f2071b1502211547791e23495bbfb42
P10K=v1.20.0
GITSTATUS=v1.5.4
MEDIA=145eb9fbc2f42ee408dacd9b22d8e6e0e553f83d

say() { printf '\033[36m▸\033[0m %s\n' "$*"; }
sum() {  # sha256 of a file, on macOS and on Debian
  if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi
}

fetch() {  # fetch NAME URL → $V/dl/NAME, checked against vendor.lock
  local name=$1 url=$2 f="$V/dl/$1" want got
  mkdir -p "$V/dl"
  # "<sha256>  <name>", and names may have spaces (the fonts)
  want=$(awk -v n="$name" 'substr($0, index($0, "  ") + 2) == n { print $1 }' "$LOCK" 2>/dev/null || true)
  if [[ ! -s "$f" || ( -n "$want" && "$(sum "$f")" != "$want" ) ]]; then
    say "$name"
    curl -4 -fsSL --retry 5 -C - -o "$f.part" "$url" || curl -4 -fsSL --retry 5 -o "$f.part" "$url"
    mv "$f.part" "$f"
  fi
  got=$(sum "$f")
  if [[ -z "$want" && -n "${VENDOR_STRICT:-}" ]]; then
    echo "✗ $name steht nicht in vendor.lock (VENDOR_STRICT: nichts Ungeprüftes)" >&2; exit 1
  elif [[ -z "$want" ]]; then
    echo "$got  $name" >> "$LOCK"; say "neu in vendor.lock: $name"
  elif [[ "$got" != "$want" ]]; then
    echo "✗ $name: sha256 $got, erwartet $want" >&2; exit 1
  fi
}

fetch "oh-my-zsh-$OMZ.tar.gz"        "https://github.com/ohmyzsh/ohmyzsh/archive/$OMZ.tar.gz"
fetch "powerlevel10k-$P10K.tar.gz"   "https://github.com/romkatv/powerlevel10k/archive/refs/tags/$P10K.tar.gz"
for arch in x86_64 aarch64; do
  fetch "gitstatusd-linux-$arch-$GITSTATUS.tar.gz" "https://github.com/romkatv/gitstatus/releases/download/$GITSTATUS/gitstatusd-linux-$arch.tar.gz"
done
for s in Regular Bold Italic "Bold Italic"; do
  fetch "MesloLGS NF $s.ttf" "https://github.com/romkatv/powerlevel10k-media/raw/$MEDIA/MesloLGS%20NF%20${s// /%20}.ttf"
done

say "auspacken"
rm -rf "$V/oh-my-zsh" "$V/powerlevel10k" "$V/gitstatusd" "$V/meslo"
mkdir -p "$V/oh-my-zsh" "$V/powerlevel10k" "$V/gitstatusd" "$V/meslo"
tar -xzf "$V/dl/oh-my-zsh-$OMZ.tar.gz" -C "$V/oh-my-zsh" --strip-components 1
echo "$OMZ" > "$V/oh-my-zsh/.akari-ref"
tar -xzf "$V/dl/powerlevel10k-$P10K.tar.gz" -C "$V/powerlevel10k" --strip-components 1
for arch in x86_64 aarch64; do
  tar -xzf "$V/dl/gitstatusd-linux-$arch-$GITSTATUS.tar.gz" -C "$V/gitstatusd"
done
cp "$V"/dl/MesloLGS*.ttf "$V/meslo/"
say "fertig: $(du -sh "$V" | cut -f1) in vendor/"

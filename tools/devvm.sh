#!/usr/bin/env bash
# The development VM for Akari OS: a plain Debian 13 in QEMU, without a
# window. Everything goes over SSH (and the serial console into a log).
#
#   tools/devvm.sh init      key, a working disk over the Debian image, cloud-init
#   tools/devvm.sh start     boot it (headless, in the background)
#   tools/devvm.sh wait      until SSH answers
#   tools/devvm.sh ssh [cmd] a shell, or one command, in the VM
#   tools/devvm.sh build     the .debs from this checkout, built in the VM, into .devvm/debs
#   tools/devvm.sh install   those .debs into the VM, with apt
#   tools/devvm.sh archive   a signed test archive from them and akari-distro, into .devvm/apt
#   tools/devvm.sh fromarchive  Akari from that archive, as a user installs it (keyring, source, apt)
#   tools/devvm.sh deploy    this checkout over the installed package (/opt/akari/src), akarid restarts
#   tools/devvm.sh sync      only the files (static changes need no restart; after deploy)
#   tools/devvm.sh undeploy  back to the installed package
#   tools/devvm.sh stop      shut it down
#   tools/devvm.sh reset     back to a fresh Debian (the working disk goes)
#   tools/devvm.sh status
#   tools/devvm.sh screen [png] what its screen shows (QEMU screendump)
#   tools/devvm.sh keys WORD… type at its console ("ret" for Enter)
#
# Ports on this machine (127.0.0.1 only):
#   2223 → 22 (SSH)   8443 → 443 (Caddy)   8131 → 8130 (akarid)
#
# Needs: qemu (MacPorts: sudo port install qemu; Linux: apt install qemu-system-x86), and in .devvm/ the image
# debian-13-genericcloud-amd64.qcow2 from cloud.debian.org. .devvm/ is not
# checked in. On a Mac with an Intel CPU it runs with HVF, on Linux with KVM.
set -euo pipefail

# QEMU from MacPorts lives in /opt/local/bin, which not every shell has on PATH
[[ -d /opt/local/bin ]] && PATH="/opt/local/bin:$PATH"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/.devvm"
BASE="$DIR/debian-13-genericcloud-amd64.qcow2"
DISK="$DIR/akari.qcow2"
SEED="$DIR/seed.iso"
KEY="$DIR/id_ed25519"
PID="$DIR/qemu.pid"
LOG="$DIR/serial.log"
SSH_PORT=2223
USER_NAME=dev
MEM=${AKARI_VM_MEM:-4096}
CPUS=${AKARI_VM_CPUS:-2}
SIZE=${AKARI_VM_DISK:-20G}

say() { printf '\033[36m▸\033[0m %s\n' "$*"; }
die() { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

running() { [[ -f "$PID" ]] && kill -0 "$(cat "$PID")" 2>/dev/null; }

ssh_vm() {
  ssh -i "$KEY" -p "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile="$DIR/known_hosts" \
      -o LogLevel=ERROR -o ConnectTimeout=5 "$USER_NAME@127.0.0.1" "$@"
}

accel() {
  case "$(uname -s)" in
    Darwin) echo "-accel hvf -cpu host" ;;
    Linux)  [[ -w /dev/kvm ]] && echo "-accel kvm -cpu host" || echo "-accel tcg" ;;
    *)      echo "-accel tcg" ;;
  esac
}

seed_iso() {
  # cloud-init NoCloud: a volume named "cidata" with user-data and meta-data
  local tmp; tmp="$(mktemp -d)"
  cat > "$tmp/meta-data" <<EOF
instance-id: akari-dev-$(date +%s)
local-hostname: akari
EOF
  cat > "$tmp/user-data" <<EOF
#cloud-config
hostname: akari
users:
  - name: $USER_NAME
    groups: [sudo]
    shell: /bin/bash
    sudo: "ALL=(ALL) NOPASSWD:ALL"
    lock_passwd: true
    ssh_authorized_keys:
      - $(cat "$KEY.pub")
package_update: true
packages: [rsync]
growpart: {mode: auto}
EOF
  rm -f "$SEED"
  if command -v hdiutil >/dev/null; then
    hdiutil makehybrid -quiet -iso -joliet -default-volume-name cidata -o "$SEED" "$tmp"
  elif command -v genisoimage >/dev/null; then
    genisoimage -quiet -output "$SEED" -volid cidata -joliet -rock "$tmp/user-data" "$tmp/meta-data"
  else
    die "hdiutil or genisoimage is needed for the cloud-init volume"
  fi
  rm -rf "$tmp"
}

cmd_init() {
  command -v qemu-img >/dev/null || die "qemu is missing (sudo port install qemu)"
  [[ -f "$BASE" ]] || die "missing $BASE (from cloud.debian.org/images/cloud/trixie/latest/)"
  mkdir -p "$DIR"
  [[ -f "$KEY" ]] || { say "a key of its own for the VM"; ssh-keygen -q -t ed25519 -N "" -C "akari-devvm" -f "$KEY"; }
  if [[ ! -f "$DISK" ]]; then
    say "working disk ($SIZE) over the Debian image, which stays untouched"
    qemu-img create -q -f qcow2 -b "$BASE" -F qcow2 "$DISK" "$SIZE"
  fi
  seed_iso
  say "ready: tools/devvm.sh start"
}

cmd_start() {
  running && { say "already running (pid $(cat "$PID"))"; return; }
  [[ -f "$DISK" && -f "$SEED" ]] || cmd_init
  : > "$LOG"
  # shellcheck disable=SC2046
  qemu-system-x86_64 $(accel) -smp "$CPUS" -m "$MEM" -name akari-dev \
    -drive file="$DISK",if=virtio,cache=writeback,discard=unmap \
    -drive file="$SEED",media=cdrom,readonly=on \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22,hostfwd=tcp:127.0.0.1:8443-:443,hostfwd=tcp:127.0.0.1:8131-:8130 \
    -device virtio-rng-pci \
    -vga std -display none -serial file:"$LOG" -monitor unix:"$DIR/monitor.sock",server,nowait \
    -daemonize -pidfile "$PID"
  say "started (pid $(cat "$PID")); console: $LOG"
}

monitor() { printf '%s\n' "$@" | nc -U "$DIR/monitor.sock" >/dev/null; }

cmd_screen() {
  # what the VM's screen shows now (QEMU's screendump), as a PNG
  local out="${1:-$DIR/screen.png}"
  rm -f "$DIR/screen.ppm"; monitor "screendump $DIR/screen.ppm"
  for _ in $(seq 1 20); do [[ -s "$DIR/screen.ppm" ]] && break; sleep 0.2; done
  sips -s format png "$DIR/screen.ppm" --out "$out" >/dev/null 2>&1 || python3 -c "import sys; sys.exit('no sips')"
  say "screen: $out"
}

cmd_keys() {
  # type into the VM's console: letters, digits, space; "ret" alone is Enter
  local cmds=() ch
  for word in "$@"; do
    if [[ "$word" == ret ]]; then cmds+=("sendkey ret"); continue; fi
    for ((i = 0; i < ${#word}; i++)); do
      ch="${word:i:1}"
      case "$ch" in
        [a-z0-9]) cmds+=("sendkey $ch") ;; [A-Z]) cmds+=("sendkey shift-$(tr A-Z a-z <<<"$ch")") ;;
        -) cmds+=("sendkey minus") ;; .) cmds+=("sendkey dot") ;; /) cmds+=("sendkey slash") ;; ' ') cmds+=("sendkey spc") ;;
      esac
    done
  done
  monitor "${cmds[@]}"
}

cmd_wait() {
  say "waiting for SSH …"
  for _ in $(seq 1 120); do
    if ssh_vm true 2>/dev/null; then
      ssh_vm "cloud-init status --wait >/dev/null 2>&1 || true"     # its first apt run holds the dpkg lock
      say "up: tools/devvm.sh ssh"; return
    fi
    running || die "QEMU stopped; see $LOG"
    sleep 2
  done
  die "no SSH after 4 minutes; see $LOG"
}

cmd_ssh() { ssh_vm "$@"; }

_sync() {
  say "this checkout → /opt/akari/src"
  ssh_vm "sudo mkdir -p /opt/akari/src && sudo chown $USER_NAME: /opt/akari/src"
  rsync -a --delete -e "ssh -i $KEY -p $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=$DIR/known_hosts -o LogLevel=ERROR" \
    --exclude .git --exclude .venv --exclude .devvm --exclude __pycache__ --exclude .pytest_cache --exclude .env \
    --exclude design/showcase/export --exclude vendor/dl --exclude debian/build \
    "$ROOT/" "$USER_NAME@127.0.0.1:/opt/akari/src/"
  ssh_vm "sudo chmod -R a+rX /opt/akari/src"
}

cmd_deploy() {
  # over the installed package: akarid and the sessions run this checkout
  # (a drop-in sets PYTHONPATH); tools/devvm.sh undeploy goes back to the package
  _sync
  ssh_vm 'set -e; dpkg -s akari >/dev/null 2>&1 || { echo "akari is not installed: tools/devvm.sh build && tools/devvm.sh install" >&2; exit 1; }
          for u in akarid.service akari-session@.service; do
            sudo mkdir -p /etc/systemd/system/$u.d
            printf "[Service]\nEnvironment=PYTHONPATH=/opt/akari/src\n" | sudo tee /etc/systemd/system/$u.d/dev.conf >/dev/null
          done
          sudo systemctl daemon-reload && sudo systemctl restart akarid'
  say "deployed (akarid restarted; open sessions keep their code until they end)"
}

cmd_sync() { _sync; say "synced (no restart)"; }

cmd_undeploy() {
  ssh_vm 'sudo rm -f /etc/systemd/system/akarid.service.d/dev.conf /etc/systemd/system/akari-session@.service.d/dev.conf
          sudo systemctl daemon-reload && sudo systemctl restart akarid'
  say "the installed package again"
}

cmd_build() {
  # the packages from this checkout (vendor/ from tools/vendor.sh), built in the VM;
  # the .debs, the source package and lintian's report land in .devvm/debs
  [[ -d "$ROOT/vendor/oh-my-zsh" ]] || "$ROOT/tools/vendor.sh"
  _sync
  ssh_vm 'set -e; dpkg -s build-essential >/dev/null 2>&1 || sudo apt-get install -y -qq --no-install-recommends build-essential debhelper dpkg-dev lintian fakeroot librsvg2-bin x11-apps >/dev/null
          rm -rf ~/build && mkdir -p ~/build && cp -a /opt/akari/src ~/build/akari && cd ~/build/akari
          dpkg-buildpackage -us -uc -sa >../build.log 2>&1 || { tail -30 ../build.log; exit 1; }
          cd .. && lintian --profile debian --info --display-info *.changes > lintian.txt 2>&1 || true
          grep -E "^[EW]:" lintian.txt | sort | uniq -c | sort -rn | head -40'
  mkdir -p "$DIR/debs" && rm -f "$DIR/debs"/*
  scp -q -i "$KEY" -P "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile="$DIR/known_hosts" -o LogLevel=ERROR \
    "$USER_NAME@127.0.0.1:build/*.deb" "$USER_NAME@127.0.0.1:build/*.dsc" "$USER_NAME@127.0.0.1:build/*.tar.xz" \
    "$USER_NAME@127.0.0.1:build/*.changes" "$USER_NAME@127.0.0.1:build/lintian.txt" "$DIR/debs/"
  say "built: $(cd "$DIR/debs" && ls *.deb | tr '\n' ' ')"
}

cmd_archive() {
  # a signed test archive like apt.lucya.systems: the .debs of tools/devvm.sh build
  # plus akari-base and akari-archive-keyring from akari-distro (next to this repo,
  # or AKARI_DISTRO), signed with a development key that never leaves .devvm/
  local distro="${AKARI_DISTRO:-$ROOT/../akari-distro}" rs="ssh -i $KEY -p $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=$DIR/known_hosts -o LogLevel=ERROR"
  [[ -d "$distro/packages" ]] || die "akari-distro not found at $distro"
  ls "$DIR"/debs/*.deb >/dev/null 2>&1 || die "no packages yet: tools/devvm.sh build"
  rsync -a --delete -e "$rs" --exclude .git --exclude build "$distro/" "$USER_NAME@127.0.0.1:akari-distro/"
  ssh_vm "rm -rf ~/debs && mkdir ~/debs"
  rsync -a -e "$rs" "$DIR"/debs/*.deb "$USER_NAME@127.0.0.1:debs/"
  [[ -d "$DIR/apt-gnupg" ]] && rsync -a --delete -e "$rs" "$DIR/apt-gnupg/" "$USER_NAME@127.0.0.1:akari-apt-gnupg/"
  ssh_vm 'set -e; export GNUPGHOME=~/akari-apt-gnupg; mkdir -p -m 700 $GNUPGHOME
    dpkg -s reprepro gnupg build-essential debhelper lintian >/dev/null 2>&1 || sudo apt-get install -y -qq --no-install-recommends reprepro gnupg build-essential debhelper lintian fakeroot >/dev/null 2>&1
    gpg -k "Akari OS Archive (dev)" >/dev/null 2>&1 || gpg --batch -q --passphrase "" --quick-gen-key "Akari OS Archive (dev) <dev@akari.invalid>" ed25519 sign 1y
    FPR=$(gpg --with-colons -k "Akari OS Archive (dev)" | awk -F: "/^fpr/{print \$10; exit}")
    gpg --armor --export $FPR > ~/akari-archive-dev.asc
    AKARI_ARCHIVE_KEY=~/akari-archive-dev.asc ~/akari-distro/tools/build.sh ~/distro-build | grep -E "^[EW]:" || true
    rm -rf ~/apt && ~/akari-distro/tools/archive.sh ~/apt $FPR stable ~/debs/*.deb ~/distro-build/*.deb >/dev/null
    echo "signed with $FPR"'
  rsync -a --delete -e "$rs" "$USER_NAME@127.0.0.1:akari-apt-gnupg/" "$DIR/apt-gnupg/"
  rsync -a --delete -e "$rs" "$USER_NAME@127.0.0.1:apt/" "$DIR/apt/"
  say "archive in .devvm/apt (stable: $(ls "$DIR"/apt/pool/main/a | tr '\n' ' '))"
}

cmd_fromarchive() {
  # Akari OS the way a user gets it: the keyring, the source, apt install akari-desktop akari-base.
  # .devvm/apt-cache (if there) fills apt's cache first, to spare a slow network.
  local rs="ssh -i $KEY -p $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=$DIR/known_hosts -o LogLevel=ERROR"
  [[ -d "$DIR/apt/dists" ]] || die "no archive yet: tools/devvm.sh archive"
  ssh_vm "dpkg -s rsync >/dev/null 2>&1 || sudo apt-get install -y -qq rsync >/dev/null"
  [[ -d "$DIR/apt-cache" ]] && rsync -a -e "$rs" --rsync-path="sudo rsync" "$DIR/apt-cache/" "$USER_NAME@127.0.0.1:/var/cache/apt/archives/"
  rsync -a --delete -e "$rs" --rsync-path="sudo rsync" "$DIR/apt/" "$USER_NAME@127.0.0.1:/srv/akari-apt/"
  ssh_vm 'set -e
    sudo dpkg -i /srv/akari-apt/pool/main/a/akari-archive-keyring/*.deb >/dev/null
    printf "Types: deb\nURIs: file:/srv/akari-apt\nSuites: stable\nComponents: main\nSigned-By: /usr/share/keyrings/akari-archive-keyring.gpg\n" \
      | sudo tee /etc/apt/sources.list.d/akari.sources >/dev/null
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq akari-desktop akari-base </dev/null >/tmp/akari-install.log 2>&1 \
      || { tail -25 /tmp/akari-install.log; exit 1; }
    . /etc/os-release; echo "$PRETTY_NAME; akarid $(systemctl is-active akarid), caddy $(systemctl is-active caddy)"'
}

cmd_install() {
  # the .debs from tools/devvm.sh build, installed with apt (it pulls what they depend on)
  ls "$DIR"/debs/*.deb >/dev/null 2>&1 || die "no packages yet: tools/devvm.sh build"
  ssh_vm "rm -rf ~/debs && mkdir ~/debs"
  scp -q -i "$KEY" -P "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile="$DIR/known_hosts" -o LogLevel=ERROR \
    "$DIR"/debs/*.deb "$USER_NAME@127.0.0.1:debs/"
  ssh_vm 'sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --reinstall ~/debs/*.deb >/tmp/akari-install.log 2>&1 || { tail -20 /tmp/akari-install.log; exit 1; }'
  say "installed: $(ssh_vm "dpkg-query -W -f='\${Package} \${Version}  ' akari akari-desktop akari-shell")"
}

cmd_stop() {
  running || { say "not running"; return; }
  ssh_vm "sudo systemctl poweroff" 2>/dev/null || true
  for _ in $(seq 1 30); do running || { say "stopped"; return; }; sleep 1; done
  kill "$(cat "$PID")" 2>/dev/null || true
  say "stopped (hard)"
}

cmd_reset() {
  cmd_stop
  rm -f "$DISK" "$SEED" "$DIR/known_hosts" "$PID"
  cmd_init
}

cmd_status() {
  if running; then
    say "running (pid $(cat "$PID"))"
    ssh_vm 'echo "  $(. /etc/os-release; echo $PRETTY_NAME), $(uname -r), up $(uptime -p)"' 2>/dev/null || say "SSH not up yet"
  else
    say "not running"
  fi
}

case "${1:-}" in
  init|start|wait|ssh|deploy|sync|undeploy|build|archive|fromarchive|install|stop|reset|status|screen|keys) c="$1"; shift; "cmd_$c" "$@" ;;
  *) sed -n '2,25p' "$0"; exit 1 ;;
esac

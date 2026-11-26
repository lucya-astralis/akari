#!/usr/bin/env bash
# The development VM for Akari OS: a plain Debian 13 in QEMU, without a
# window. Everything goes over SSH (and the serial console into a log).
#
#   tools/devvm.sh init      key, a working disk over the Debian image, cloud-init
#   tools/devvm.sh start     boot it (headless, in the background)
#   tools/devvm.sh wait      until SSH answers
#   tools/devvm.sh ssh [cmd] a shell, or one command, in the VM
#   tools/devvm.sh deploy    this checkout to /opt/akari/src in the VM (rsync), akarid restarts
#   tools/devvm.sh install   deploy, then tools/install-system.sh in the VM (packages, units, PAM, Caddy)
#   tools/devvm.sh stop      shut it down
#   tools/devvm.sh reset     back to a fresh Debian (the working disk goes)
#   tools/devvm.sh status
#
# Ports on this machine (127.0.0.1 only):
#   2223 → 22 (SSH)   8443 → 443 (Caddy, from phase 1)   8131 → 8130 (akarid)
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
    -display none -serial file:"$LOG" -monitor none \
    -daemonize -pidfile "$PID"
  say "started (pid $(cat "$PID")); console: $LOG"
}

cmd_wait() {
  say "waiting for SSH …"
  for _ in $(seq 1 120); do
    if ssh_vm true 2>/dev/null; then say "up: tools/devvm.sh ssh"; return; fi
    running || die "QEMU stopped; see $LOG"
    sleep 2
  done
  die "no SSH after 4 minutes; see $LOG"
}

cmd_ssh() { ssh_vm "$@"; }

cmd_deploy() {
  say "this checkout → /opt/akari/src"
  ssh_vm "sudo mkdir -p /opt/akari/src && sudo chown $USER_NAME: /opt/akari/src"
  rsync -a --delete -e "ssh -i $KEY -p $SSH_PORT -o StrictHostKeyChecking=no -o UserKnownHostsFile=$DIR/known_hosts -o LogLevel=ERROR" \
    --exclude .git --exclude .venv --exclude .devvm --exclude __pycache__ --exclude .pytest_cache --exclude .env \
    --exclude design/showcase/export \
    "$ROOT/" "$USER_NAME@127.0.0.1:/opt/akari/src/"
  ssh_vm "sudo chmod -R a+rX /opt/akari/src; systemctl is-enabled -q akarid 2>/dev/null && sudo systemctl restart akarid || true"
  say "deployed"
}

cmd_install() {
  cmd_deploy
  ssh_vm "sudo /opt/akari/src/tools/install-system.sh"
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
  init|start|wait|ssh|deploy|install|stop|reset|status) c="$1"; shift; "cmd_$c" "$@" ;;
  *) sed -n '2,21p' "$0"; exit 1 ;;
esac

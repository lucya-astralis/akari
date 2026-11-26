#!/usr/bin/env bash
# Akari OS on a Debian 13 (trixie): what the packages will do in phase 2,
# as one script for now. Run as root on the machine itself, from a checkout:
#
#   sudo tools/install-system.sh            (tools/devvm.sh install does it in the dev VM)
#
# Idempotent: run it again after a change to system/ or the package list.
# The code stays where it is; /usr/lib/akari points to the checkout.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
[[ $(id -u) -eq 0 ]] || { echo "als root, bitte (sudo $0)" >&2; exit 1; }
export DEBIAN_FRONTEND=noninteractive
say() { printf '\033[36m▸\033[0m %s\n' "$*"; }

PACKAGES=(
  # akarid and the agent, from Debian
  python3 python3-fastapi python3-uvicorn python3-websockets python3-httpx python3-multipart python3-pil python3-pampy
  libpam-systemd dbus-user-session sudo openssh-server caddy qrencode locales ca-certificates
  # the display stack for GUI apps: one Xvnc per app, a window manager, X cookies
  tigervnc-standalone-server matchbox-window-manager x11-xserver-utils x11-utils xauth dbus-x11 wmctrl
  dbus-daemon playerctl
  # the apps, and the front ends Debian ships
  firefox-esr firefox-esr-l10n-de xterm libjs-xterm novnc
  fonts-noto-core fonts-dejavu-core fonts-noto-color-emoji fonts-jetbrains-mono fonts-noto-cjk
  # the shell
  zsh zsh-autosuggestions zsh-syntax-highlighting fastfetch
  bash-completion less nano vim-tiny git curl procps htop tree unzip file
  iputils-ping iputils-tracepath bind9-dnsutils wget netcat-openbsd iproute2 traceroute mtr-tiny whois
  # to build the cursor theme
  librsvg2-bin x11-apps
)

say "Pakete"
apt-get update -qq
apt-get install -y -qq --no-install-recommends "${PACKAGES[@]}" >/dev/null

say "Sprachen: de_DE, en_US, ja_JP (UTF-8)"
sed -i -e 's/^# *\(de_DE.UTF-8\)/\1/' -e 's/^# *\(en_US.UTF-8\)/\1/' -e 's/^# *\(ja_JP.UTF-8\)/\1/' /etc/locale.gen
locale-gen >/dev/null
# the installer asks for the language; a cloud image says C.UTF-8, and then Akari's own is German
grep -qE '^LANG=.+' /etc/default/locale 2>/dev/null && ! grep -qx 'LANG=C.UTF-8' /etc/default/locale || update-locale LANG=de_DE.UTF-8

say "zsh als Shell für neue Konten"
sed -i 's|^#\?SHELL=.*|SHELL=/bin/zsh|' /etc/default/useradd
[[ -f /etc/adduser.conf ]] && sed -i 's|^#\?DSHELL=.*|DSHELL=/bin/zsh|' /etc/adduser.conf

say "oh-my-zsh, powerlevel10k, MesloLGS NF"
P10K_REF=v1.20.0
if [[ ! -d /usr/share/powerlevel10k ]]; then
  git -c advice.detachedHead=false clone -q --depth 1 --branch "$P10K_REF" https://github.com/romkatv/powerlevel10k.git /usr/share/powerlevel10k
  rm -rf /usr/share/powerlevel10k/.git
  GITSTATUS_CACHE_DIR=/usr/share/powerlevel10k/gitstatus/usrbin /usr/share/powerlevel10k/gitstatus/install -f
fi
if [[ ! -d /usr/share/oh-my-zsh ]]; then
  git clone -q --depth 1 https://github.com/ohmyzsh/ohmyzsh.git /usr/share/oh-my-zsh
  git -C /usr/share/oh-my-zsh rev-parse HEAD > /usr/share/oh-my-zsh/.akari-ref
  rm -rf /usr/share/oh-my-zsh/.git
fi
mkdir -p /usr/share/oh-my-zsh/custom/themes /usr/share/oh-my-zsh/custom/plugins/zsh-autosuggestions /usr/share/oh-my-zsh/custom/plugins/zsh-syntax-highlighting
ln -sfn /usr/share/powerlevel10k /usr/share/oh-my-zsh/custom/themes/powerlevel10k
echo 'source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh' > /usr/share/oh-my-zsh/custom/plugins/zsh-autosuggestions/zsh-autosuggestions.plugin.zsh
echo 'source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh' > /usr/share/oh-my-zsh/custom/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.plugin.zsh
MESLO=https://github.com/romkatv/powerlevel10k-media/raw/master
mkdir -p /usr/share/fonts/truetype/meslo-nf
for s in Regular Bold Italic "Bold Italic"; do
  f="/usr/share/fonts/truetype/meslo-nf/MesloLGS NF $s.ttf"
  [[ -s "$f" ]] || curl -4 -fsSL --retry 5 -o "$f" "$MESLO/MesloLGS%20NF%20${s// /%20}.ttf"
done

say "Akari-Dateien im System (skel, zsh, fastfetch, Schrift)"
R="$SRC/image/rootfs"
install -d /usr/share/akari
cp -a "$R/usr/share/akari/." /usr/share/akari/
cp -a "$R/usr/share/fonts/truetype/akari" /usr/share/fonts/truetype/
install -D -m 644 "$R/etc/xdg/fastfetch/config.jsonc" /etc/xdg/fastfetch/config.jsonc
install -m 644 "$R/etc/skel/.zshrc" /etc/skel/.zshrc
install -m 644 "$R/etc/skel/.bashrc" /etc/skel/.bashrc
fc-cache -f >/dev/null

say "Zeiger (Xcursor-Thema Akari)"
if [[ ! -f /usr/share/icons/Akari/index.theme || "$SRC/akari/static/assets/cursors" -nt /usr/share/icons/Akari/index.theme ]]; then
  tmp="$(mktemp -d)"
  sh "$SRC/image/cursors/build.sh" "$SRC/akari/static/assets/cursors" "$tmp/Akari" >/dev/null
  rm -rf /usr/share/icons/Akari && mv "$tmp/Akari" /usr/share/icons/Akari && chmod -R a+rX /usr/share/icons/Akari
  rm -rf "$tmp"
fi
printf '[Icon Theme]\nInherits=Akari\n' > /usr/share/icons/Akari/cursor.theme
update-alternatives --quiet --install /usr/share/icons/default/index.theme x-cursor-theme /usr/share/icons/Akari/cursor.theme 90
update-alternatives --quiet --set x-cursor-theme /usr/share/icons/Akari/cursor.theme

say "akarid, Sitzungen, PAM, sudo, Caddy"
ln -sfn "$SRC" /usr/lib/akari
install -m 644 "$SRC/system/systemd/akarid.service" "$SRC/system/systemd/akari-session@.service" /etc/systemd/system/
install -m 644 "$SRC/system/pam.d/akari" /etc/pam.d/akari
install -m 440 "$SRC/system/sudoers.d/akari" /etc/sudoers.d/akari && visudo -cq
install -m 644 "$SRC/system/caddy/Caddyfile" /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable -q akarid.service caddy.service
systemctl restart caddy.service akarid.service

say "fertig: $(systemctl is-active akarid) / caddy $(systemctl is-active caddy)"

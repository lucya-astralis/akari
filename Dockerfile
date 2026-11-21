# Akari OS: a desktop in the browser with a real Linux under it, on Debian trixie.
#
# akarid runs as root in the container, with only the capabilities it needs
# to be a login manager (see compose.yaml); every account is a real Linux user
# and its session runs as that user. The root filesystem is read-only;
# everything that changes lives in the one volume, /data.
FROM debian:trixie-slim

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv ca-certificates locales \
      # the display stack for GUI apps: one Xvnc per app, a window manager, X cookies
      tigervnc-standalone-server matchbox-window-manager x11-xserver-utils xauth dbus-x11 \
      # the apps
      firefox-esr firefox-esr-l10n-de xterm \
      fonts-noto-core fonts-dejavu-core fonts-noto-color-emoji fonts-jetbrains-mono \
      # the front ends, served as Debian ships them
      libjs-xterm novnc \
      # the shell: zsh by default
      zsh zsh-autosuggestions zsh-syntax-highlighting fastfetch \
      bash-completion less nano vim-tiny git curl procps htop tree unzip file \
      # ssh into the box (akarid starts sshd when an admin turns it on)
      openssh-server openssl \
 && sed -i 's/^# *de_DE.UTF-8/de_DE.UTF-8/' /etc/locale.gen && locale-gen \
 && rm -f /etc/ssh/ssh_host_* \
 && rm -rf /var/lib/apt/lists/*

# the default display: xprop watches which windows are open, wmctrl raises one
RUN apt-get update && apt-get install -y --no-install-recommends x11-utils wmctrl \
 && rm -rf /var/lib/apt/lists/*

# media in the taskbar: a session bus per desktop, playerctl follows the MPRIS players on it
RUN apt-get update && apt-get install -y --no-install-recommends dbus-daemon playerctl \
 && rm -rf /var/lib/apt/lists/*

# oh-my-zsh and powerlevel10k, system-wide and read-only. p10k has releases;
# oh-my-zsh does not, so its commit is pinned here (OMZ_REF) and written to
# /usr/share/oh-my-zsh/.akari-ref. gitstatusd comes into the image too, so
# nothing downloads at the first prompt.
ARG P10K_REF=v1.20.0
ARG OMZ_REF=master
RUN git clone --depth 1 --branch "$P10K_REF" https://github.com/romkatv/powerlevel10k.git /usr/share/powerlevel10k \
 && git clone https://github.com/ohmyzsh/ohmyzsh.git /usr/share/oh-my-zsh \
 && git -C /usr/share/oh-my-zsh checkout -q "$OMZ_REF" \
 && git -C /usr/share/oh-my-zsh rev-parse HEAD > /usr/share/oh-my-zsh/.akari-ref \
 && rm -rf /usr/share/powerlevel10k/.git /usr/share/oh-my-zsh/.git \
 && GITSTATUS_CACHE_DIR=/usr/share/powerlevel10k/gitstatus/usrbin /usr/share/powerlevel10k/gitstatus/install -f \
 && mkdir -p /usr/share/oh-my-zsh/custom/themes /usr/share/oh-my-zsh/custom/plugins/zsh-autosuggestions /usr/share/oh-my-zsh/custom/plugins/zsh-syntax-highlighting \
 && ln -s /usr/share/powerlevel10k /usr/share/oh-my-zsh/custom/themes/powerlevel10k \
 && echo 'source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh' > /usr/share/oh-my-zsh/custom/plugins/zsh-autosuggestions/zsh-autosuggestions.plugin.zsh \
 && echo 'source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh' > /usr/share/oh-my-zsh/custom/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.plugin.zsh

# MesloLGS NF: the font p10k is made for (Apache 2.0, from powerlevel10k-media).
# Installed for Linux apps and served to the web terminal under /vendor/meslo.
# Not pinned yet: replace master with a commit of powerlevel10k-media.
ARG MESLO=https://github.com/romkatv/powerlevel10k-media/raw/master
RUN mkdir -p /usr/share/fonts/truetype/meslo-nf && cd /usr/share/fonts/truetype/meslo-nf \
 && for s in Regular Bold Italic "Bold Italic"; do curl -fsSL --retry 5 -o "MesloLGS NF $s.ttf" "$MESLO/MesloLGS%20NF%20$(echo $s | sed 's/ /%20/').ttf"; done \
 && ls -la

COPY requirements.txt /opt/akari/requirements.txt
RUN python3 -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --retries 10 --timeout 60 -r /opt/akari/requirements.txt

# sudo for accounts that manage (group akari-admin, see /etc/sudoers.d/akari)
RUN apt-get update && apt-get install -y --no-install-recommends sudo \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 990 akari-admin

# Akari OS: os-release, fastfetch, zsh defaults, skeleton home, sudoers, the apt hook
COPY image/rootfs/ /
RUN chsh -s /bin/zsh root && sed -i 's|^SHELL=.*|SHELL=/bin/zsh|' /etc/default/useradd \
 && chmod 440 /etc/sudoers.d/akari && visudo -cq \
 && fc-cache -f >/dev/null \
 && mkdir -p /usr/share/akari/apt && apt-mark showmanual | sort -u > /usr/share/akari/apt/baseline.list

COPY akari /opt/akari/akari

# Accounts change at runtime, the root filesystem does not: passwd and friends
# live in the volume. The image's own system users are the seed akarid starts from.
RUN mkdir -p /usr/share/akari/etc \
 && cp /etc/passwd /etc/group /etc/shadow /etc/gshadow /usr/share/akari/etc/ \
 && chmod 640 /usr/share/akari/etc/shadow /usr/share/akari/etc/gshadow \
 && for f in passwd group shadow gshadow; do ln -sf /data/system/$f /etc/$f; done \
 && mkdir -p /data && chmod 755 /data

ENV PYTHONPATH=/opt/akari PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LANG=de_DE.UTF-8
WORKDIR /data
VOLUME /data
EXPOSE 8130
CMD ["/opt/venv/bin/python", "-m", "akari"]

# Akari OS als echte Distribution

Ziel: Akari OS ist eine eigene Distribution auf Debian-Basis. Man installiert
es von einem ISO; der Rechner bootet in die Konsole, ohne grafische Oberfläche
vor Ort, und der Desktop ist die Seite im Browser, wie heute. Hauptziel sind
**virtuelle Maschinen** (Proxmox/KVM, VirtualBox, VMware, Hyper-V, UTM), in
die man das ISO installiert; echte Hardware geht mit demselben ISO. Fertige
VM-Images kommen erst später.

Der Docker-Container ist zweitrangig: Er bleibt auf dem Stand 0.10 stehen
(auch im Store von Lucent) und wird nicht weiterentwickelt, bis entschieden
ist, ob und wie er aus den Paketen der Distro wiederkommt.

Stand der Planung: 25.11.2026, Akari 0.10. Ziel: Akari OS 1.0.

## Leitlinien

1. **Eine echte Distribution, aber Debian darunter.** Eigener Name, eigene
   Systemidentität, eigener Installer im Akari-Look, eigene Paketquelle.
   Kernel, Bootloader und Sicherheitsupdates kommen von Debian trixie; nur so
   bleibt Secure Boot mit Debians signiertem shim, grub und Kernel ohne eigene
   Schlüssel erhalten. Kein eigener Kernel.
2. **Ein Weg zur Installation: das ISO.** Getestet wird es, indem CI genau
   dieses ISO unbeaufsichtigt in QEMU installiert und das Ergebnis prüft.
   Kommen später fertige VM-Images dazu, entstehen sie auf demselben Weg.
3. **Ein Code-Weg.** Akari 1.0 läuft als echtes System mit systemd, PAM und
   logind. Keine zweite Variante für Container im Code; die Sonderwege von
   heute (eigene passwd, eigener sshd, Pakete nach Updates wieder einspielen)
   fallen weg.
4. **Standardwerkzeuge.** systemd, PAM, logind, useradd, sshd_config.d, apt,
   debian-cd: Was ein Debian-Admin kennt, funktioniert in Akari OS genauso.
   Konsole, SSH und Browser zeigen dieselben Konten und Dateien.
5. **Pakete statt Kopien.** Alles, was Akari auf ein System bringt, ist ein
   `.deb` aus der eigenen Paketquelle; Updates laufen über apt.

## Was Debian trixie mitbringt

Akaris Python-Abhängigkeiten sind in trixie paketiert, das venv entfällt:

| heute (PyPI) | trixie |
|---|---|
| fastapi 0.115.0 | python3-fastapi 0.115.11 |
| uvicorn 0.32.0 | python3-uvicorn 0.32.0 |
| websockets 13.1 | python3-websockets 15.0.1 (prüfen: `close_code`, `unix_connect`) |
| httpx 0.27.2 | python3-httpx 0.28.1 (prüfen: entfernte Parameter) |
| python-multipart 0.0.12 | python3-multipart 1.2.1 |
| Pillow 12.0 | python3-pil 11.1 |
| – | python3-pam 0.4.2, python3-systemd 235, python3-sdbus 0.14 |

Dazu noVNC 1.6, TigerVNC 1.15, fastfetch 2.40, Caddy 2.6, qemu-guest-agent,
open-vm-tools, hyperv-daemons; für den Bau debian-cd, mmdebstrap 1.5.7,
reprepro, aptly. Nicht in Debian: oh-my-zsh, powerlevel10k in aktueller
Version, MesloLGS NF. Die packen wir selbst.

## Entscheidungen

**Installer: debian-installer, grafisch, im Akari-Look, gebaut mit
debian-cd.** Debians eigener Installer, wie ihn Debian und Ableger wie Kali
nutzen. Gebrandet wird:
- das Banner in jedem Schritt (Paket `rootskel-gtk`, in trixie
  `logo_debian_ceratopsian.svg` und `_dark.svg`): eine eigene Fassung des
  Pakets mit dem Akari-Banner;
- das Bootmenü des ISOs (GRUB für UEFI, isolinux für BIOS): Hintergrund,
  Farben, Einträge „Akari OS installieren“, „… im Textmodus“, „… Experte“;
- was angeboten wird: eine Auswahl „Akari OS“ statt der Debian-Desktops
  (tasksel), Akaris Paketquelle mit Schlüssel, und eine Vorbelegung, die nur
  fragt, was offen ist (Sprache, Tastatur, Platte, Netz, Rechnername, erstes
  Konto).
Einzelne Texte sagen weiter „Debian“ (etwa beim Spiegelserver); die ersetzen
wir später über eigene Übersetzungen. debian-cd statt simple-cdd, weil es
eigene Installer-Pakete (udebs) aufnimmt.

**Systemidentität.** Paket `akari-base`: `os-release` mit `ID=akari`,
`ID_LIKE=debian`, `NAME="Akari OS"`, `VERSION_ID`; `issue`, `motd`,
GRUB-Theme und `GRUB_DISTRIBUTOR`, Herkunft für dpkg
(`/etc/dpkg/origins/akari`). Paket `akari-archive-keyring` mit dem Schlüssel
der Paketquelle. Programme erkennen Akari OS und wissen über `ID_LIKE`, dass
es Debian-kompatibel ist.

**Konten: echte Systemkonten, Anmeldung über PAM.** Akari legt Konten mit
`useradd`/`usermod`/`userdel` an und prüft Passwörter über PAM (Dienst
`akari`). Verwalten heißt Gruppe `sudo`. `accounts.json` (unter
`/var/lib/akari`) behält nur, was Linux nicht kennt: Kontobild,
Lucent-Verknüpfung, SSH-Passwort-Freigabe. Das Konto aus dem Installer ist
sofort ein Akari-Konto, ohne Setup-Token; Konten, die an der Konsole mit
`adduser` entstehen, übernimmt Akari von selbst.

**Sitzungen: systemd und logind.** Der Agent eines Kontos läuft als
`akari-session@<konto>.service` mit `User=` und `PAMName=akari`. Das gibt eine
echte Anmeldesitzung: `/run/user/<uid>`, den Session-Bus des Kontos (ersetzt
den eigenen dbus-daemon pro Desktop), Ressourcengrenzen per Slice;
`loginctl` zeigt, wer im Browser angemeldet ist.

**akarid als Systemdienst.** `akarid.service` als root mit
`CapabilityBoundingSet` auf die bekannten zehn Capabilities, `ProtectSystem`,
`ProtectHome=read-only` für sich selbst, eigene Schreibpfade unter
`/var/lib/akari` und `/run/akari`.

**HTTPS von Anfang an.** Caddy vor akarid, akarid nur auf 127.0.0.1. Beim
ersten Start ein selbst signiertes Zertifikat für Rechnername und IPs;
Let's Encrypt, wenn der Rechner einen öffentlichen Namen hat. Ohne HTTPS
fehlen im LAN Zwischenablage, Medientasten und mehr.

**Erster Start: die Konsole sagt, wohin.** Die Anmeldemaske an der Konsole
zeigt `https://<ip>` und einen QR-Code, aktualisiert, wenn sich die IP ändert.

**SSH: der Dienst des Systems.** Akari schaltet `ssh.service` an und aus und
schreibt seine Regeln nach `/etc/ssh/sshd_config.d/akari.conf`. Port 22.

**VMs: Gast-Werkzeuge an Bord.** qemu-guest-agent, open-vm-tools und
hyperv-daemons sind installiert und starten nur auf ihrem Hypervisor
(`ConditionVirtualization=`). Dazu serielle Konsole, damit Proxmox und
virsh die Konsole zeigen.

**Software: apt, wie es ist.** Updates von System und Akari in Einstellungen
→ Software und als Wartungsaktion in Lucent. Das Wiedereinspielen nach einem
Image-Update braucht ein echtes System nicht.

**Architekturen.** amd64 zuerst. arm64 danach (UTM auf Apple Silicon,
Raspberry Pi); die Akari-Pakete selbst sind architekturunabhängig.

**Container.** Eingefroren auf 0.10: Der Image-Workflow baut `:stable` nur
noch von einem Zweig `container-0.10`, der Store bietet weiter diesen Stand
an. Später entscheiden: wiederbeleben (aus den Paketen, mit eigener
Container-Anpassung) oder aus dem Store nehmen.

## Was im Code wegfällt, was neu kommt

| heute (Container) | Akari OS 1.0 |
|---|---|
| eigene passwd/shadow im Volume, Symlinks in /etc | useradd/usermod/userdel, PAM |
| scrypt-Hashes in accounts.json | PAM; accounts.json nur noch Zusatzdaten |
| Gruppe `akari-admin` | Gruppe `sudo` |
| setpriv startet den Agenten | `akari-session@.service`, logind |
| eigener sshd auf 2222, eigene Hostschlüssel | `ssh.service`, sshd_config.d |
| packages.list, apt-Hook, Wiedereinspielen | entfällt |
| dbus-daemon pro Desktop | Session-Bus von logind (Desktops trennen über Namen) |
| `/data/system`, `/data/homes`, `/tmp/akari` | `/var/lib/akari`, `/home`, `/run/user/<uid>/akari` |
| akarid auf 0.0.0.0:8130 | akarid auf 127.0.0.1, Caddy auf 443 |
| Setup-Token im Log | erstes Konto im Installer, sonst Token an der Konsole |
| venv mit PyPI-Paketen | python3-Pakete von Debian |

Betroffen sind vor allem accounts, agents, ssh, software (fällt weg),
config, media, files und lucent (Pfade, Konten).

## Phasen

### Phase 0: Grundlage
- **Tests einführen.** Akari hat noch keine. Zuerst für das, was den Umbau
  übersteht und ihn absichert: Zugriffsschutz in files, Audio (Range, ID3),
  Lucent-Connector (Token, Seiten), Namen und Passwortregeln der Konten.
- **Entwicklungs-VM.** Ein frisches Debian trixie in QEMU (oder UTM), in das
  ein Skript den Checkout spielt und akarid neu startet. Das ersetzt
  compose.dev.yaml als Arbeitsumgebung.
- Container einfrieren: Zweig `container-0.10`, Image-Workflow darauf
  umstellen.

*Fertig, wenn:* pytest läuft in CI; die Entwicklungs-VM steht und startet
den heutigen Stand von Hand.

### Phase 1: Akari als echtes System
- Konten über useradd und PAM, Sitzungen als systemd-Units, SSH über den
  Systemdienst, Pfade nach FHS, akarid als Dienst.
- Abhängigkeiten auf die Debian-Pakete (websockets 15, httpx 0.28, Pillow 11).
- Caddy mit selbst signiertem Zertifikat; Konsole mit Adresse und QR-Code.

*Fertig, wenn:* In der Entwicklungs-VM läuft Akari als Dienst; Konsole, SSH
und Browser zeigen dieselben Konten; Neustart der VM übersteht alles.

*Stand (26.11.2026): erledigt.* `tools/install-system.sh` richtet ein Debian
13 ein (bis zu den Paketen in Phase 2 der Ersatz für deren postinst),
`tools/e2e-system.sh` prüft es von außen: Einrichten über den Link der
Konsole, Anmelden über PAM, Sitzung als Unit mit logind-Sitzung, Konten
mit sudo, SSH-Passwort pro Konto (`sshd -T`), Abmelden räumt Apps und
logind-Sitzung ab, Löschen samt Home, akarid-Neustart lässt Sitzungen
leben, VM-Neustart. Offen für später: der dbus-daemon pro Desktop (media)
bleibt vorerst; `ProtectSystem` für akarid.

Gelernt dabei:
- `PAMName=` legt die Prozesse in den Scope der logind-Sitzung, nicht in
  den Cgroup der Unit. Abmelden beendet deshalb zusätzlich die Sitzung mit
  Dienst `akari` (`loginctl terminate-session`); ssh-Sitzungen bleiben.
- Caddy mit `tls internal` und `on_demand` bedient auch Aufrufe über die
  IP-Adresse ohne SNI.
- sshd: ein `Match` in `sshd_config.d/akari.conf` gilt bis zum Ende dieser
  Datei, nicht bis in sshd_config hinein; darum steht er dort zuletzt.
- PAM-Modul ist `python3-pampy` (`import pam`), nicht `python3-pam`.

### Phase 2: Pakete, Paketquelle, Identität
- `debian/` im Akari-Repo, gebaut mit dpkg-buildpackage, geprüft mit lintian:
  - `akari` (akarid, Agent, Weboberfläche, systemd-Units, PAM-Datei),
  - `akari-desktop` (Metapaket: akari, TigerVNC, matchbox, noVNC, Firefox ESR,
    Schriften, zsh, fastfetch, openssh-server, sudo, playerctl,
    Netzwerk-Werkzeuge, Caddy, Gast-Werkzeuge),
  - `akari-shell` (zsh-Einstellungen, oh-my-zsh und powerlevel10k auf festen
    Ständen, MesloLGS NF, Akari Symbols, fastfetch-Logo).
- Im neuen Repo `akari-distro`: `akari-base`, `akari-archive-keyring`, das
  Installer-Banner (eigene Fassung von rootskel-gtk), GRUB-Theme.
- Paketquelle `apt.lucya.systems` (reprepro oder aptly), signiert;
  Kanäle `stable` und `testing`. CI baut und lädt hoch.

*Fertig, wenn:* Auf einem frischen trixie macht `apt install akari-desktop`
nach Einbinden der Quelle daraus ein Akari OS mit Namen, Logo und Diensten.

### Phase 3: Das ISO
- Installer-ISO mit debian-cd: grafisch und im Akari-Look, Bootmenü,
  Auswahl „Akari OS“, Vorbelegung, Paketquelle.
- Rauchtest bei jedem Bau: CI installiert das ISO unbeaufsichtigt in QEMU,
  bootet, wartet bis `https://…/api/login/state` antwortet, meldet sich an,
  öffnet ein Fenster.
- Von Hand einmal in Proxmox, VirtualBox und Hyper-V installieren.
- Veröffentlichung: das ISO mit Prüfsumme und Signatur als Release.

*Fertig, wenn:* Das ISO installiert sich in einer VM ohne Hilfe, bootet in
die Konsole, und der Desktop ist im Browser erreichbar.

### Phase 4: Akari verwaltet den Rechner
Über akarid und die Dienste des Systems (hostnamed, timedated,
NetworkManager, logind):
- Netzwerk (DHCP, feste IP, später WLAN), Rechnername, Zeitzone,
- Updates von System und Akari, Neustart und Herunterfahren,
- Speicher (Platten, Belegung, Vergrößern einer VM-Platte),
- Lucent: dieselben Aktionen als Wartung, Updates als Ereignis.

*Fertig, wenn:* Eine VM lässt sich nach dem Start vollständig im Browser
betreiben, ohne Konsole.

### Phase 5: Danach
- fertige VM-Images aus dem ISO (qcow2 für Proxmox/KVM und UTM, OVA für
  VirtualBox und VMware, VHDX für Hyper-V), optional mit cloud-init,
- arm64 (UTM auf Apple Silicon, Raspberry Pi 4/5),
- Ton aus Linux-Apps (PipeWire je Sitzung, in den Browser gestreamt),
- eigene Texte im Installer statt „Debian“,
- reproduzierbare Builds,
- Entscheidung über den Container.

## Repos

| Repo | Inhalt |
|---|---|
| `akari` | Code, `debian/`, systemd-Units, PAM-Datei, Tests, Entwicklungs-VM |
| `akari-distro` (neu) | debian-cd-Konfiguration, Vorbelegung, tasksel-Auswahl, Installer-Banner, `akari-base`, `akari-archive-keyring`, GRUB-Theme, CI für das ISO, Paketquelle |

## Risiken

- **websockets 15 und httpx 0.28** ändern APIs, die akarid nutzt (Relay,
  Proxy, Lucent). In Phase 1 geprüft: Proxy und Terminal-Relay laufen mit
  Debians Paketen durch Caddy; Lucent gegen ein echtes Lucent steht aus.
- **Konten von außerhalb:** Wer an der Konsole mit `adduser` oder über SSH
  arbeitet, ändert Konten an Akari vorbei. Akari liest den Zustand deshalb
  immer vom System und hält selbst nur Zusatzdaten.
- **Xvnc pro App** braucht Speicher; Empfehlung für eine VM: 4 GB, 2 Kerne.
- **Selbst signiertes Zertifikat** zeigt im Browser eine Warnung. Klar
  erklären; Let's Encrypt anbieten, wo möglich.
- **Secure Boot** nur mit Debians Kernel und Bootloader.
- **Lucent und der Container:** Lucents Store bietet weiter Akari 0.10 im
  Container an. Bis zur Entscheidung kein neues Store-Image.

## Nächster Schritt

Phase 2: die Pakete `akari`, `akari-desktop`, `akari-shell` und das Repo
`akari-distro` mit `akari-base`; `tools/install-system.sh` wird dabei zu
deren postinst.

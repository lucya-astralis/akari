# Akari OS

Ein Desktop im Browser mit einem echten Linux darunter, auf Debian trixie,
gebaut in [Facet 1.8](../facet). Gedacht als Tool für Lucent: Lucent verwaltet
es (installieren, koppeln, Zustand), Akari OS hat seine eigene Oberfläche.

**Stand 0.8:** Musik, ein kleiner Audio-Player: die eigene Musik aus ~/Musik
(dazu lose Dateien in Downloads und Schreibtisch, Titel, Künstler und Cover aus
ID3 oder dem Albumordner) und, auf Wunsch, ein Subsonic-Server (Navidrome,
Airsonic, Gonic) über den Agenten, ohne gespeichertes Passwort. Springen per
Range, Zufall, Wiederholen, Lautstärke; was spielt, steht in der Leiste und im
Kontrollzentrum und hört auf die Medientasten.

**Stand 0.6:** an Lucent angebunden (Connector-Vertrag 1, siehe
[lucent/CONNECTOR.md](../lucent/CONNECTOR.md)). Lucent zeigt Akari mit Zustand und
Kennzahlen und zeichnet drei Seiten: Übersicht (Last, Speicher, wer angemeldet ist),
Konten (anlegen, verwalten erlauben, Passwort, abmelden, löschen) und System (SSH,
nachinstallierte Software). Wartung: alle abmelden, Software wieder einspielen.
„Mit Lucent anmelden“ am Anmeldebildschirm für Konten, die unter Einstellungen →
Lucent verknüpft sind. Außerdem: Pakete, die Systembenutzer anlegen, nehmen Akari
nicht mehr `/etc/passwd` weg.

**0.5.6:** Anmeldebildschirm nach macOS-Art: Datum und große Uhr oben,
die Konten unten als kurze Liste, ein gewähltes Konto wächst und bekommt eine
Pille fürs Passwort; Sprache und Farbschema oben rechts. Japanisch vorinstalliert
(Noto CJK, Locale ja_JP.UTF-8).

**0.5.5:** die Leiste nach macOS-Art: aktive Apps nur noch als Symbol mit
Strich darunter (kein Fenstername mehr), minimierte Fenster in einem eigenen Bereich
rechts der Apps, ein Medienbereich in der Status-Pille (Cover, Titel, Künstler,
Zurück, Pause, Weiter). Jeder Desktop hat dafür einen eigenen D-Bus, playerctl
folgt den MPRIS-Playern darauf (Firefox, mpv, VLC, Spotify). Der Ton selbst kommt
noch nicht im Browser an.

**0.5:** neues Startmenü (Suche über Apps, Einstellungen und zuletzt
geöffnete Dateien), Kontobilder (von Pillow neu gerendert, nie die hochgeladene
Datei), Raster auf dem Schreibtisch (Symbole rasten ein und tauschen den Platz),
Leiste zum Anheften, Umsortieren per Ziehen und Größe per Rechtsklick, Animationen
(Vergrößerung beim Zeigen, Symbole gleiten ein und aus, die Pille gleitet zur neuen
Breite, Klappfenster gehen animiert zu, minimierte Fenster kommen aus dem Dock zurück).

**Bis 0.4:** eigenes Zeichen („Schein“), Leiste aus zwei Glas-Pillen (unten oder
oben), Widgets und verschiebbare Symbole, eigenes Hintergrundbild, Rechtsklick-Menüs,
Aktivität (Task-Manager) und Auslastung, Deutsch und Englisch, sudo und apt ohne
Datenverlust, Programme aus dem Terminal erscheinen in Akari. Dazu aus 0.3: echte
Linux-Benutzer, getrennte Desktops, SSH, oh-my-zsh mit powerlevel10k. Noch ohne Lucent.

## Starten

```bash
docker compose pull && docker compose up -d     # das fertige Image von ghcr.io
docker compose logs akari                       # beim ersten Start: der Einrichtungslink
```

Selbst bauen statt ziehen: `docker compose up -d --build`. Zum Entwickeln
mit eingehängtem Code: `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`
(oder `COMPOSE_FILE=compose.yaml:compose.dev.yaml` in `.env`, unter Windows mit `;`).

Der Link `http://127.0.0.1:8130/?token=…` führt zur Einrichtung des ersten
Kontos. Danach meldet man sich am Login-Bildschirm an; weitere Konten legt
ein Konto, das verwalten darf, unter **Einstellungen → Konten** an.

## Aufbau

```
Browser ──► akarid (root im Container, 6 Capabilities)
              Login, Konten, Sitzungen, Oberfläche
              │  Unix-Socket /tmp/akari/<uid>/agent.sock (0700)
              ▼
            Session-Agent, einer pro angemeldetem Konto, läuft als dieser Benutzer
              Terminal (zsh) · Dateien · Editor · Einstellungen
              Linux-Apps: Xvnc + matchbox + App, VNC nur über Unix-Socket (0600)
```

| Datei | |
|---|---|
| `akari/gateway.py` | akarid: Tür, Login, Konten-API, Weiterleitung an den Agenten (HTTP und WebSocket) |
| `akari/accounts.py` | Konten → `/etc/passwd`, `group`, `shadow` (liegen im Volume, `/etc` verweist dorthin) |
| `akari/agents.py` | startet und beendet Session-Agenten als der jeweilige Benutzer |
| `akari/agent.py` | der Agent: `term.py`, `files.py`, `display.py`, `system.py` |
| `akari/static/` | `login.html` (Login), `index.html` (Desktop), `apps/*.js` |
| `image/rootfs/` | was Akari OS zur Distro macht: `os-release`, zsh, fastfetch, `/etc/skel` |
| `tools/logo.py` | rechnet den Adler aus dem SVG in Blockzeichen für fastfetch um |

## Konten und Trennung

- Jedes Konto ist ein Linux-Benutzer (UID ab 1000) mit Home `/data/homes/<name>` (0700).
- Alles, was ein Konto startet, läuft unter seiner UID: Shell, Firefox, Dateioperationen.
- Ein Display einer Linux-App ist nur für seinen Besitzer erreichbar: VNC über einen
  Unix-Socket mit 0600, X nur mit MIT-Cookie.
- **Benutzer wechseln** beendet nur die Sitzung im Browser, die Apps laufen weiter.
  **Abmelden** beendet alles, was unter dieser UID läuft.
- Passwörter prüft akarid (scrypt). `su` und `sudo` gehen nicht, `no-new-privileges`
  verbietet Setuid-Programme.

## Desktops

Ein Konto kann mehrere Desktops haben ("Arbeit", "Spielwiese"). Nach dem
Passwort fragt der Login-Bildschirm, welcher; mit nur einem geht es direkt
hinein. Jeder Desktop hat eigene laufende Apps, ein eigenes Firefox-Profil und
ein eigenes Aussehen (`~/.config/akari/desktops/<id>/`). Oben rechts steht der
Name; ein Klick darauf wechselt, die Apps laufen weiter. **Desktop beenden**
beendet nur seine Apps.

## SSH

Ein Konto, das verwaltet, schaltet SSH unter **Einstellungen → SSH** ein
(Port 2222, in `compose.yaml` an `127.0.0.1` gebunden). Jedes Konto legt dort
seine öffentlichen Schlüssel ab (`~/.ssh/authorized_keys`) und entscheidet
selbst, ob sein Passwort über SSH gilt. Ohne diese Wahl steht im `shadow` `*`:
Schlüssel gehen, Passwörter nicht. sshd läuft ohne PAM, ohne Weiterleitungen,
root darf nicht. Die Host-Schlüssel liegen in `/data/system/ssh/`.

## Akari OS als Distro

- `/etc/os-release`: `NAME="Akari OS"`, `ID=akari`, `ID_LIKE=debian`.
- zsh ist die Shell jedes Kontos: oh-my-zsh mit powerlevel10k (Stil "lean" in
  Facets Farben), Autosuggestions, Syntax-Hervorhebung, git, z. Beides liegt nur
  lesbar in `/usr/share`, systemweit eingerichtet in `/usr/share/akari/zsh/`;
  eigene Zeilen in `~/.zshrc`, eigener Prompt mit `p10k configure`.
  Das Web-Terminal nutzt MesloLGS NF, die Schrift, für die p10k gemacht ist.
- fastfetch begrüßt jedes neue Terminal mit dem Adler (`/etc/xdg/fastfetch/config.jsonc`).
  `AKARI_QUIET=1` in `~/.zshrc` schaltet das ab.

## Grenzen gegenüber lucya-aio

Die anderen Tools laufen unter aio ohne Capabilities. Akari OS braucht als
Login-Manager sieben (`compose.yaml`): SETUID, SETGID, CHOWN, FOWNER, DAC_OVERRIDE,
KILL und SYS_CHROOT (für sshd). Dazu `shm_size: 512m` für Firefox und ein tmpfs auf
`/run` für sshd. Das muss die aio-Vorlage für Akari bekommen.

Weiterhin: Root-Dateisystem nur lesbar, kein `apt install` zur Laufzeit,
Programme kommen ins Image.

## sudo und Software

Konten, die verwalten, sind in der Gruppe `akari-admin` und dürfen `sudo`, mit
ihrem Akari-Passwort. Dafür ist das Root-Dateisystem beschreibbar und
Setuid-Programme gehen. Ein apt-Hook (`/usr/local/sbin/akari-apt-record`) schreibt
nach jedem dpkg-Lauf die zusätzlich installierten Pakete nach
`/data/system/apt/packages.list`; nach einem Image-Update spielt akarid sie beim
Start wieder ein (`akari/software.py`, Log in `/data/system/logs/apt-restore.log`).
Was von Hand unter `/etc`, `/usr` oder `/opt` geändert wird, überlebt ein Update
nicht. Ohne sudo: `docker compose -f compose.yaml -f compose.locked.yaml up -d`.

## Sprache

Deutsch ist die Quelle, `akari/static/i18n/en.js` die englische Fassung
(genaue Texte und Muster für Texte mit Werten). Gewählt wird unter Einstellungen →
Darstellung → Sprache, sonst gilt die Sprache des Browsers.

## Aus Lucents Store

Akari OS steht im Store von lucya.systems. Lucent installiert es über den
Helfer lucya-aio aus `ghcr.io/lucya-astralis/akari:stable` (gebaut von
`.github/workflows/image.yml` bei jedem Push auf main) und fragt nach den
Rechten:

- **Gesperrt** (Vorgabe): nur lesbares System, `no-new-privileges`. Konten,
  Desktops, Apps und SSH gehen, sudo und apt nicht.
- **Mit sudo und apt**: beschreibbares System, setuid erlaubt; was Admins
  installieren, kommt nach einem Update von selbst wieder.

Beide behalten genau die zehn Capabilities aus `compose.yaml` und sonst nichts.
Das erste Konto legt Lucent an (Akari OS → Konten → Erstes Konto anlegen): Es
darf verwalten und ist gleich mit der Lucent-Person verknüpft.

## Lucent

Koppeln: in Lucent unter **Tools** einen Code erzeugen, dann in Akari unter
**Einstellungen → Lucent** (Konten, die verwalten) Lucents Adresse, den Code und
Akaris Adresse eintragen. Oder im Container:

```bash
docker compose exec akari /opt/venv/bin/python -m akari --lucent-join https://lucent.example ABCD-EFGH-JKLM --ui-url https://akari.example
```

Läuft Lucent auf demselben Rechner außerhalb von Docker, ist es aus dem Container
`http://host.docker.internal:8060`. Die Kopplung liegt in `/data/system/lucent.json`
(nur root): das OIDC-Client-Geheimnis und ein Hash des Connector-Geheimnisses.

Wer ist wer: Akari-Konten sind Linux-Benutzer, deshalb legt eine Anmeldung über
Lucent nie ein Konto an. Man verknüpft sein Konto einmal, angemeldet, unter
Einstellungen → Lucent. Was Lucent auf Akaris Seiten ändert (Konten, SSH), führt
Akari nur aus, wenn die Lucent-Person mit einem Akari-Konto verknüpft ist, das
verwalten darf, egal was Lucent selbst erlaubt.

## Roadmap

1. **Echtes ISO-Image.** Akari OS als installierbares System: Debian-Basis mit
   eigenem Installer, nach der Installation bootet es in die Konsole (kein
   grafischer Desktop auf dem Rechner selbst), akarid startet als Dienst, bedient
   wird es über den Browser wie heute. Bausteine: `live-build` oder `mmdebstrap`
   für das Image, systemd-Units für akarid und die Agenten statt Docker, die
   Paketliste dieses Images als `akari-desktop`-Metapaket, später eine eigene
   apt-Quelle für Akari-Pakete.
2. Ton aus Linux-Apps (der Medien-Teil der Leiste steht schon), HiDPI.
3. Eigene Fenster pro Linux-Programm auch aus dem Terminal (Xpra „seamless“).

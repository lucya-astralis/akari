"""Akari OS showcase: two bento grids in Facet, as one page.

  python3 design/showcase/build.py     → design/showcase/index.html

Stage 1 shows desktops in different looks, each a small live rendering built
from the same tokens Akari uses (accent hue, light or dark, Nova's side, logo,
bar). Stage 2 shows design and features. The page links facet.css and the
fonts next to it; publishing maps them in from akari/static/."""

from __future__ import annotations

import html
import re
import pathlib

HERE = pathlib.Path(__file__).parent
SPRITE = (HERE / "_sprite.svg").read_text()
LOGO = """         $1███
        $1▄██  $2▄▄▄▄▄▄
       $1▄██▀ $2▄█████▀
       $1██▀  $2█████▀
      $1███  $2██████  ▄▄▄▄▄▄
     $1███  $2██████  ██████
    $1▄██  $2▄█████  ▄█████▀
   $1▄██▀ $2▄█████▀ ▄█████▀
   $1██▀  $2█████▀  █████▀
  $1███  $2██████  ██████
 $1███  $2██████  ██████
$1▄██  $2██████  ▄█████"""


def fastfetch_logo() -> str:
    out = []
    for line in LOGO.splitlines():
        parts = line.split("$")
        row = html.escape(parts[0])
        for p in parts[1:]:
            cls = "ff1" if p[0] == "1" else "ff2"
            row += f'<span class="{cls}">{html.escape(p[1:])}</span>'
        out.append(row)
    return "\n".join(out)


FF = fastfetch_logo()


def app(i: str) -> str:
    return f'<svg class="ic"><use href="#app-{i}"/></svg>'


def line(i: str) -> str:
    return f'<svg class="li"><use href="#{i}"/></svg>'


DOCK = "".join(app(a) for a in ("files", "terminal", "editor", "web", "settings"))


def bar(look: dict) -> str:
    media = ""
    if look.get("media"):
        media = ('<span class="mb__media"><i class="mb__cover"></i><span><b>Magic</b><small>Geo22</small></span>'
                 f'{line("i-prev")}{line("i-pause")}{line("i-next")}</span><i class="mb__sep"></i>')
    shelf = '<i class="mb__sep"></i><i class="mb__min"></i>' if look.get("min") else ""
    return (f'<div class="mini__bar" data-align="{look.get("align", "center")}">'
            f'<div class="mb"><svg class="mb__mark am" viewBox="0 0 95.64 100"><use href="#am"/></svg><i class="mb__sep"></i>{DOCK}{shelf}</div>'
            f'<div class="mb">{media}<span class="mb__desk">{line("i-window")}{html.escape(look["name"])}</span><i class="mb__sep"></i>'
            f'{line("i-net")}{line("i-battery")}<i class="mb__sep"></i>{line("i-sliders")}{line("i-bell")}'
            f'<span class="mb__clock"><b>{look.get("time", "10:53")}</b><small>21.11.2026</small></span></div></div>')


def window(kind: str) -> str:
    dots = '<span class="mw__dots"><i></i><i></i><i></i></span>'
    if kind == "term":
        return (f'<div class="mwin mwin--term">{dots}<span class="mwin__title">Terminal · ada@akari</span>'
                f'<div class="mwin__body"><pre class="ff">{FF}</pre><div class="ffi"><b>ada<span>@</span>akari</b><i></i>'
                '<p><span>System</span>Akari OS 0.7</p><p><span>Kernel</span>7.0.12</p><p><span>Desktop</span>Akari · Facet 1.8</p>'
                '<p><span>Shell</span>zsh 5.9</p><p><span>Pakete</span>600 (dpkg)</p><p><span>Speicher</span>1,2 / 7,7 GiB</p></div></div></div>')
    if kind == "files":
        cells = "".join(f'<span class="fcell"><svg><use href="#app-files"/></svg><small>{n}</small></span>'
                        for n in ("Dokumente", "Bilder", "Downloads", "Musik", "Projekte", "akari"))
        side = "".join(f"<p>{n}</p>" for n in ("Home", "Schreibtisch", "Dokumente", "Papierkorb"))
        return (f'<div class="mwin mwin--files">{dots}<span class="mwin__title">Dateien · Home</span>'
                f'<div class="mwin__body"><aside>{side}</aside><div class="fgrid">{cells}</div></div></div>')
    if kind == "settings":
        side = "".join(f"<p{' class=on' if n == 'Darstellung' else ''}>{n}</p>" for n in ("Darstellung", "Schreibtisch", "Konto", "Lucent", "SSH"))
        sw = "".join(f'<i style="--h:{h}"></i>' for h in (277, 250, 215, 150, 70, 25, 350))
        return (f'<div class="mwin mwin--set">{dots}<span class="mwin__title">Einstellungen</span>'
                f'<div class="mwin__body"><aside>{side}</aside><div class="sbody"><b>Darstellung</b>'
                f'<div class="srow"><span>Akzent</span><span class="sw">{sw}<i class="sw--rb"></i></span></div>'
                '<div class="srow"><span>Licht von</span><span class="seg"><i>Links</i><i class="on">Rechts</i><i>Beide</i></span></div>'
                '<div class="srow"><span>Logo</span><span class="seg"><i>Keins</i><i class="on">Akari</i><i>lucya</i></span></div></div></div></div>')
    if kind == "web":
        return (f'<div class="mwin mwin--web">{dots}<span class="mwin__title">Firefox</span>'
                '<div class="mwin__body"><div class="wtabs"><i class="on">lucya.systems</i><i>Neuer Tab</i></div>'
                '<div class="wurl">lucya.systems</div><div class="wpage"><i class="wh"></i><i class="wl"></i><i class="wl s"></i>'
                '<span class="wcards"><i></i><i></i><i></i></span></div></div></div>')
    if kind == "cc":
        sw = "".join(f'<i style="--h:{h}"></i>' for h in (277, 250, 215, 150, 70, 25, 350, 300))
        return ('<div class="mcc"><div class="mcc__row"><span class="mcc__mod"><small>Darstellung</small>'
                f'<span class="mcc__orbs"><i></i><i class="on"></i><i></i></span></span><span class="mcc__mod mcc__mod--on">{line("i-bell")}<small>Nicht stören</small></span></div>'
                f'<span class="mcc__mod mcc__mod--wide"><small>Akzent</small><span class="sw">{sw}<i class="sw--rb"></i><i class="sw--sp"></i></span></span>'
                '<span class="mcc__mod mcc__mod--wide"><small>Nova</small><span class="seg"><i>Links</i><i class="on">Beide</i><i>Rechts</i></span></span>'
                f'<div class="mcc__toggles"><i class="on">{line("i-folder")}</i><i class="on">{line("i-pulse")}</i><i class="on">{line("i-pointer")}</i><i>{line("i-motion")}</i></div></div>')
    return ""


def mini(look: dict, cls: str = "") -> str:
    mode = look.get("mode", "")
    style = f'--tint-h:{look.get("h", 277)}'
    logo = ""
    if look.get("logo") == "akari":
        logo = '<svg class="mini__logo am" viewBox="0 0 95.64 100"><use href="#am"/></svg>'
    elif look.get("logo") == "lucya":
        logo = '<svg class="mini__logo mini__logo--lucya" viewBox="0 0 964 543"><use href="#lm"/></svg>'
    widgets = ""
    if look.get("widgets", True):
        widgets = (f'<div class="mini__widgets"><div class="mwg mwg--clock"><b>{look.get("time", "10:53")}</b><small>Samstag, 21. November</small></div>'
                   '<div class="mwg mwg--perf"><small>CPU</small><span class="spark"></span><small>Speicher</small><i style="--v:.42"></i></div>'
                   '<div class="mwg mwg--note"><small>Notiz …</small></div></div>')
    icons = ""
    if look.get("icons", True):
        icons = '<div class="mini__icons">' + "".join(f'<span>{app(a)}<small>{n}</small></span>' for a, n in
                                                       (("web", "Firefox"), ("terminal", "Terminal"), ("files", "Dateien"), ("settings", "Einstellungen"))) + "</div>"
    return (f'<div class="mini f-nova look look--{look["scheme"]} {mode and "look--" + mode} {"look--plain" if look.get("plain") else ""} {cls}" '
            f'style="{style}" data-side="{look.get("side", "left")}" data-logo="{look.get("logo", "none")}" data-top="{1 if look.get("top") else 0}">'
            f'{logo}{widgets}{icons}{window(look.get("win", ""))}{bar(look)}</div>')


LOOKS = [
    dict(area="a", name="Arbeit", h=277, scheme="light", side="left", win="files",
         tags=["Facet-Violett", "Hell", "Licht von links"]),
    dict(area="b", name="Abends", h=70, scheme="dark", side="right", win="term", time="21:40",
         tags=["Bernstein", "Dunkel", "Licht von rechts"]),
    dict(area="c", name="Studio", mode="spectrum", h=300, scheme="light", side="both", logo="lucya", align="split", media=True, win="",
         tags=["Farbverlauf", "Hell", "Beide Seiten", "Leiste geteilt", "lucya.systems-Logo"]),
    dict(area="d", name="Fokus", h=250, scheme="dark", side="left", widgets=False, icons=False, top=True, win="web",
         tags=["Blau", "Dunkel", "Leiste oben", "Ohne Widgets"]),
    dict(area="e", name="Garten", h=150, scheme="light", side="right", logo="lucya", win="", min=True,
         tags=["Grün", "Hell", "Licht von rechts", "Minimiert"]),
    dict(area="f", name="Nacht", h=-10, scheme="dark", side="both", logo="akari", win="", time="23:12",
         tags=["Pink", "Dunkel", "Beide Seiten", "Akari-Logo"]),
    dict(area="g", name="Schlicht", h=215, scheme="dark", plain=True, win="settings", icons=False,
         tags=["Cyan", "Dunkel", "Ohne Nova"]),
    dict(area="h", name="Party", mode="rainbow", h=0, scheme="dark", side="both", logo="akari", win="cc", align="split", media=True, time="00:30",
         tags=["Regenbogen", "Dunkel", "Kontrollzentrum"]),
    dict(area="i", name="Werkstatt", h=25, scheme="light", side="left", align="left", win="term",
         tags=["Rot", "Hell", "Leiste links"]),
    dict(area="j", name="Eigen", h=320, scheme="dark", side="right", logo="lucya", align="right", win="",
         tags=["Eigene Farbe 320°", "Dunkel", "Leiste rechts"]),
]


def look_tile(look: dict) -> str:
    chips = "".join(f'<span class="chip">{html.escape(t)}</span>' for t in look["tags"])
    wide = " is-wide" if look["area"] in ("c", "h") else ""
    return (f'<figure class="tile tile--look{wide}" data-ga="{look["area"]}">{mini(look)}'
            f'<figcaption><b>{html.escape(look["name"])}</b><span class="chips">{chips}</span></figcaption></figure>')


STAGE1 = "".join(look_tile(l) for l in LOOKS)

# ---------- stage 2: design and features ----------
CURSORS = "".join(f'<span class="cur"><img src="cursors/{n}.svg" alt="" width="32" height="32"><small>{n}</small></span>'
                  for n in ("default", "pointer", "text", "grab", "move", "wait", "nwse-resize", "help"))
SWATCHES = "".join(f'<i class="sw" style="--h:{h}"><small>{n}</small></i>' for h, n in
                   ((277, "Facet"), (250, "Blau"), (215, "Cyan"), (150, "Grün"), (70, "Bernstein"), (25, "Rot"), (350, "Pink")))

STAGE2_RAW = f"""
<figure class="tile feat feat--term" style="grid-area:a">
  <div class="feat__head"><span class="eyebrow">Echtes Debian</span><h3>Ein Linux, kein Spielzeug</h3>
  <p>zsh mit powerlevel10k, fastfetch in deiner Akzentfarbe, sudo und apt, Pakete überleben jedes Update.</p></div>
  <div class="term look look--dark" style="--tint-h:150"><pre class="ff">{FF}</pre>
  <div class="ffi"><b>ada<span>@</span>akari</b><i></i><p><span>System</span>Akari OS 0.7 x86_64</p><p><span>Kernel</span>7.0.12</p>
  <p><span>Desktop</span>Akari · Facet 1.8</p><p><span>Shell</span>zsh 5.9</p><p><span>Terminal</span>Akari Terminal</p><p><span>Pakete</span>600 (dpkg)</p></div>
  <code class="prompt"><span class="p1">◆ ada@akari</span> <span class="p2">~</span><br>❯ sudo apt install btop</code></div>
</figure>

<figure class="tile feat feat--cursor" style="grid-area:b">
  <div class="feat__head"><span class="eyebrow">Eigene Cursor</span><h3>15 Zeiger, in jeder Farbe</h3></div>
  <div class="curs look" style="--tint-h:277">{CURSORS}</div>
</figure>

<figure class="tile feat feat--apps" style="grid-area:c">
  <div class="feat__head"><span class="eyebrow">Linux-Apps</span><h3>Firefox, Konsole, GIMP als Fenster</h3>
  <p>Jede App auf einem eigenen Display, gestreamt in ein Akari-Fenster. Zwischenablage in beide Richtungen.</p></div>
  <div class="mini mini--flat f-nova look look--light" style="--tint-h:250" data-side="left">{window("web")}</div>
</figure>

<figure class="tile feat feat--hero look look--dark look--spectrum f-nova" style="grid-area:h;--tint-h:280" data-side="both">
  <svg class="hero__mark am" viewBox="0 0 95.64 100"><use href="#am"/></svg>
  <h2 class="hero__title">Akari OS</h2>
  <p class="hero__lede">Ein Desktop im Browser mit einem echten Debian darunter.</p>
  <span class="hero__ver">0.7 · Facet 1.8</span>
</figure>

<figure class="tile feat feat--media" style="grid-area:d">
  <div class="feat__head"><span class="eyebrow">Medien</span><h3>Was spielt, steht in der Leiste</h3></div>
  <div class="pill look look--light" style="--tint-h:-10"><i class="pill__cover"></i><span><b>Magic</b><small>Geo22</small></span>
  <span class="pill__ctl">{line("i-prev")}{line("i-pause")}{line("i-next")}</span></div>
</figure>

<figure class="tile feat feat--dock" style="grid-area:e">
  <div class="feat__head"><span class="eyebrow">Die Leiste</span><h3>Minimiert wie bei macOS</h3></div>
  <div class="dock look look--light" style="--tint-h:277"><svg class="dock__mark am" viewBox="0 0 95.64 100"><use href="#am"/></svg><i class="dsep"></i>
  {app("files")}{app("terminal")}{app("editor")}<i class="dsep"></i><span class="dmin">{app("web")}</span><span class="dmin">{app("settings")}</span></div>
  <p class="feat__note">Unten, oben, links, rechts oder geteilt.</p>
</figure>

<figure class="tile feat feat--cc" style="grid-area:f">
  <div class="feat__head"><span class="eyebrow">Kontrollzentrum</span><h3>Alles mit einem Klick</h3></div>
  <div class="ccw look look--light" style="--tint-h:150">{window("cc")}</div>
</figure>

<figure class="tile feat feat--lucent" style="grid-area:g">
  <div class="feat__head"><span class="eyebrow">Lucent</span><h3>Verwaltet von Lucent, bedient wie immer</h3>
  <p>Zustand, Konten, SSH und Wartung auf Lucents Seiten. Anmelden mit dem Lucent-Konto.</p></div>
  <div class="lu">
    <div class="lu__card"><span class="lu__state"><i></i>erreichbar</span><b>Akari OS</b><small>3 Konten, 1 angemeldet</small></div>
    <div class="lu__stats"><span><small>CPU</small><b>4 %</b></span><span><small>Speicher</small><b>1,3 GB</b></span><span><small>Platz</small><b>3 %</b></span></div>
    <span class="lu__btn">Mit Lucent anmelden</span>
  </div>
</figure>

<figure class="tile feat feat--ssh" style="grid-area:i">
  <div class="feat__head"><span class="eyebrow">Fernzugriff</span><h3>SSH mit Schlüssel</h3></div>
  <code class="cmd">ssh -p 2222 ada@akari</code>
  <p class="feat__note">Passwort pro Konto wählbar.</p>
</figure>

<figure class="tile feat feat--desks" style="grid-area:j">
  <div class="feat__head"><span class="eyebrow">Getrennte Desktops</span><h3>Arbeit hier, Spiel dort</h3></div>
  <div class="desks"><span class="on"><b>Arbeit</b><small>Firefox läuft</small></span><span><b>Abends</b><small>zuletzt heute 21:40</small></span><span><b>Studio</b><small>zuletzt 18. Nov.</small></span></div>
</figure>

<figure class="tile feat feat--accent" style="grid-area:k">
  <div class="feat__head"><span class="eyebrow">Zehn Akzente</span><h3>Eine Farbe färbt alles: Nova, Cursor, Terminal</h3></div>
  <div class="accents">{SWATCHES}<i class="sw sw--custom"><small>Eigene</small></i><i class="sw sw--rb"><small>Regenbogen</small></i><i class="sw sw--sp"><small>Farbverlauf</small></i></div>
</figure>

<figure class="tile feat feat--lang" style="grid-area:l">
  <div class="feat__head"><span class="eyebrow">Sprachen</span><h3>Deutsch, English, 日本語</h3></div>
  <p class="lang"><span>Schreibtisch</span><span>Desktop</span><span lang="ja">デスクトップ</span></p>
</figure>
"""

# grid areas as data attributes; the wide ones marked for the smaller layouts
STAGE2 = re.sub(r'style="grid-area:(\w)(;?)', lambda m: f'data-ga="{m.group(1)}" style="' if m.group(2) else f'data-ga="{m.group(1)}"', STAGE2_RAW)
for k in ("c", "g", "k"):
    STAGE2 = STAGE2.replace(f'class="tile feat feat--', f'class="tile feat feat--', 1)
STAGE2 = re.sub(r'class="tile feat (feat--(?:apps|lucent|accent))"', r'class="tile feat is-wide \1"', STAGE2)

CSS = (HERE / "showcase.css").read_text()

PAGE = f"""<title>Akari Showcase</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="facet.css">
<style>
{CSS}
</style>
<svg width="0" height="0" class="sprite" aria-hidden="true" style="position:absolute">{SPRITE}</svg>
<main class="show">
  <header class="stage__head">
    <span class="eyebrow">Akari OS 0.7</span>
    <h1>Jeder Desktop ein eigener Look</h1>
    <p>Mehrere Desktops pro Konto, jeder mit Farbe, Licht, Logo und Leiste nach Wahl. Alles echte Akari-Einstellungen.</p>
  </header>
  <section class="stage stage--looks" aria-label="Desktops">{STAGE1}
    <figure class="tile tile--title look look--light look--spectrum f-nova" data-ga="t" style="--tint-h:250" data-side="both">
      <span class="eyebrow">Ein System</span>
      <h2>Zehn Desktops,<br>zehn Looks</h2>
      <p>Hell oder dunkel, Licht von links, rechts oder beiden Seiten, zehn Akzente, Logo auf Nova.</p>
    </figure>
  </section>

  <header class="stage__head">
    <span class="eyebrow">Design und Funktionen</span>
    <h1>Gebaut in Facet 1.8</h1>
    <p>Ein echtes Linux unter einer ruhigen, gläsernen Oberfläche.</p>
  </header>
  <section class="stage stage--feats" aria-label="Design und Funktionen">{STAGE2}</section>
  <footer class="show__foot"><svg class="am" viewBox="0 0 95.64 100"><use href="#am"/></svg> Akari OS · lucya.systems</footer>
</main>
"""

(HERE / "index.html").write_text(PAGE)
print("design/showcase/index.html", len(PAGE))

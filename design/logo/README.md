# Akari OS: Zeichen-Entwürfe

Fünf Konzepte für ein eigenes Zeichen von Akari OS, statt des lucya.systems-Adlers.
Akari heißt Licht, Schein. Jedes Zeichen hat darum eine Facette, die das Licht ist;
sie ist violett (`#5865f2` auf dunkel, `#404ee7` auf hell), die übrigen sind Silber
bzw. Ink wie bei Lucent. Alle Schnitte laufen im Nova-Winkel (22° gegen die
Senkrechte), die Fuge ist 5 Einheiten breit.

Ansehen: `index.html` (lädt `../../akari/static/facet.css`).

## Empfehlung: Schein

Eine schmale, violette Lichtkante und zwei Splitter, die von ihr wegfallen und kürzer
werden. Das ist Nova auf drei Flächen: Licht von einer Kante, Splitter im 22°-Winkel.
Es hält sich bei 16 px und als Halbblock-Text, und es ist kein A (Arch), kein Fenster,
kein Stern und keine Lampe.

Fila (drei kürzer werdende Balken) und Strata (drei Platten) sprechen heute eine
ähnliche Strich-Sprache. Damit Schein allein steht, bekommen beide ein neues Zeichen
(lucya will das ohnehin).

Wortmarke: „Akari“ in Space Grotesk Medium, „OS“ in Regular mit 55 % Deckkraft, als
Umrisse. Im Lockup ist das Zeichen 1,5 Versalhöhen hoch und steht mittig zu den Versalien.

## Die Konzepte

| Konzept | Idee | In klein |
|---|---|---|
| **Lichtfenster** | Fenster mit Titelleiste, ein Lichtstreifen fällt im Nova-Winkel hindurch. Sagt am direktesten „Schreibtisch“. | Hält bei 16 px; als volles Viereck etwas schwer neben anderen Symbolen. |
| **A-Splitter** | Das A aus zwei 22°-Splittern, der Funke als Querstrich. | Gut lesbar, aber ein A/Dreieck liest sich als Arch Linux. Verworfen. |
| **Laterne** | Papierlaterne (Akari ist auch die Papierlampe), Körper in Licht und Schatten geteilt. | Groß am meisten Charakter; bei 16 px wird es ein Achteck mit Strich, als Favicon am schwächsten. |
| **Schein** ★ | Lichtkante plus zwei fallende Splitter. Nova im Kleinen. | Drei schräge Flächen bleiben bis 16 px getrennt. Nah an Fila und Strata, siehe oben. |
| **Funke** | Vierstrahliger Funke aus vier Facetten wie Lucent, um 22° geneigt. | Gut lesbar; wird aber leicht für ein KI-Symbol gehalten. |

## Dateien

- `svg/<konzept>/<konzept>-mono.svg`: `currentColor`
- `…-silver.svg`: für dunklen Grund · `…-ink.svg`: für hellen Grund
- `…-favicon.svg`: breitere Fuge (9), folgt `prefers-color-scheme`
- `…-lockup-{mono,silver,ink}.svg`: Zeichen und Wortmarke
- `svg/wordmark-{mono,silver,ink}.svg`: nur die Wortmarke
- `fastfetch/<konzept>.txt`: Halbblöcke, 12 Zeilen hoch (der Adler hatte 11). `$1` ist
  das Licht, `$2` der Rest; passt zur heutigen `config.jsonc` (`"1": "38;5;141"`,
  `"2": "97"`), es muss nur `logo.txt` getauscht werden.

Für die Facetten im Markup (wie `.f-mark`) tragen die Pfade die Töne `a` bis `d` und `l`
(das Licht); `index.html` zeigt, wie sie über Tokens mit dem Modus wechseln.

## Bauen

```bash
python3 build.py
```

Alles kommt aus der Geometrie in `build.py`. Die Halbblöcke rechnet eine angepasste
Kopie von `akari/tools/logo.py` (feste Zeilenhöhe, das Licht gewinnt bei Mischzellen);
das Original ist unverändert. Für die Wortmarke braucht es `fonttools`; ohne bleibt
`wordmark.json` als Vorlage. `python3 build.py --standalone <datei>` schreibt die
Vorschau mit eingebettetem CSS und Schriften in eine einzelne Datei.

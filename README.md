# Miniflux OPML Import

Importiert ausschließlich neue Feed-Abonnements aus einer lokalen OPML-Datei
oder einer OPML-URL in eine frei wählbare Miniflux-Kategorie.

Bereits in Miniflux vorhandene Feed-URLs und Duplikate innerhalb der OPML-Datei
werden übersprungen. Bestehende Abonnements werden weder verschoben noch
verändert.

## Voraussetzungen

- Python 3.9 oder neuer
- Eine erreichbare Miniflux-Instanz
- Ein Miniflux-API-Token

Das Skript verwendet nur die Python-Standardbibliothek.

## Verwendung

Miniflux-Adresse und API-Token können als Umgebungsvariablen gesetzt werden:

```bash
export MINIFLUX_URL="https://miniflux.example.org"
export MINIFLUX_API_TOKEN="dein-api-token"
```

Alternativ können die Werte in einer `.env`-Datei liegen:

```dotenv
MINIFLUX_URL=https://miniflux.example.org
MINIFLUX_API_TOKEN=dein-api-token
```

Diese Datei wird explizit mit `--env-file` geladen:

```bash
./miniflux_opml_import.py abonnements.opml "Meine Blogs" --env-file .env
```

Die Priorität bei mehrfach gesetzten Werten lautet: direkte Befehlsparameter,
bereits vorhandene Umgebungsvariablen, Werte aus der `.env`-Datei.

OPML von einer URL importieren:

```bash
./miniflux_opml_import.py \
  "https://wirres.net/articles/blockroll?opml" \
  "Wirres Blogrolle"
```

Lokale OPML-Datei importieren:

```bash
./miniflux_opml_import.py abonnements.opml "Meine Blogs"
```

Änderungen zunächst nur anzeigen:

```bash
./miniflux_opml_import.py abonnements.opml "Meine Blogs" --dry-run
```

Alternativ können Miniflux-Adresse und Token direkt übergeben werden:

```bash
./miniflux_opml_import.py abonnements.opml "Meine Blogs" \
  --miniflux-url "https://miniflux.example.org" \
  --api-token "dein-api-token"
```

Alle Optionen:

```bash
./miniflux_opml_import.py --help
```

## Verhalten

1. Das Skript liest alle `xmlUrl`-Einträge aus der OPML-Datei.
2. Duplikate innerhalb der OPML-Datei werden entfernt.
3. Kategorien und Abonnements werden über die Miniflux-API abgefragt.
4. Die angegebene Zielkategorie wird angelegt, sofern neue Feeds vorhanden sind
   und die Kategorie noch nicht existiert.
5. Nur Feed-URLs, die noch nicht in Miniflux vorhanden sind, werden hinzugefügt.

Ein Fehler bei einem einzelnen Feed stoppt die übrigen Importe nicht. Das
Skript beendet sich in diesem Fall mit Statuscode `2`.

## Sicherheit

Der API-Token sollte bevorzugt über `MINIFLUX_API_TOKEN` gesetzt werden. So
erscheint er nicht in der Kommandohistorie oder Prozessliste. Token und andere
Zugangsdaten gehören nicht in OPML-Dateien oder Git-Commits.

Die mitgelieferte `.env.example` kann als Vorlage kopiert werden. Die echte
`.env`-Datei wird von Git ignoriert.

## Lizenz

MIT

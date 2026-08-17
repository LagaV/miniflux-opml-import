#!/usr/bin/env python3
"""Importiert neue Feeds aus einer OPML-Datei in eine Miniflux-Kategorie.

Das Skript verwendet ausschließlich die Python-Standardbibliothek. Bereits in
Miniflux vorhandene Feed-URLs und Duplikate innerhalb der OPML-Datei werden
übersprungen. Vorhandene Feeds werden weder verschoben noch verändert.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


class ImportErrorWithContext(RuntimeError):
    """Fehler mit einer verständlichen Meldung für die Kommandozeile."""


ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_env_file(filename: str) -> None:
    """Lädt eine einfache dotenv-Datei, ohne bestehende Variablen zu ersetzen."""
    path = Path(filename).expanduser()
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ImportErrorWithContext(
            f"Umgebungsdatei konnte nicht gelesen werden: {exc}"
        ) from exc

    for line_number, original_line in enumerate(lines, start=1):
        line = original_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ImportErrorWithContext(
                f"Ungültige Zeile {line_number} in {path}: '=' fehlt."
            )

        name, raw_value = line.split("=", 1)
        name = name.strip()
        raw_value = raw_value.strip()
        if not ENV_NAME_PATTERN.fullmatch(name):
            raise ImportErrorWithContext(
                f"Ungültiger Variablenname in Zeile {line_number} von {path}."
            )

        if raw_value.startswith('"'):
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ImportErrorWithContext(
                    f"Ungültiger Anführungswert in Zeile {line_number} von {path}."
                ) from exc
            if not isinstance(value, str):
                raise ImportErrorWithContext(
                    f"Ungültiger Wert in Zeile {line_number} von {path}."
                )
        elif raw_value.startswith("'"):
            if len(raw_value) < 2 or not raw_value.endswith("'"):
                raise ImportErrorWithContext(
                    f"Nicht geschlossenes Anführungszeichen in Zeile {line_number} von {path}."
                )
            value = raw_value[1:-1]
        else:
            value = re.split(r"\s+#", raw_value, maxsplit=1)[0].rstrip()

        os.environ.setdefault(name, value)


def read_opml(source: str, timeout: float) -> bytes:
    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in {"http", "https"}:
        request = urllib.request.Request(
            source,
            headers={"User-Agent": "miniflux-opml-import/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ImportErrorWithContext(
                f"OPML-URL konnte nicht geladen werden: {exc}"
            ) from exc

    path = Path(source).expanduser()
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ImportErrorWithContext(
            f"OPML-Datei konnte nicht gelesen werden: {exc}"
        ) from exc


def parse_feed_urls(data: bytes) -> list[str]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportErrorWithContext(f"Ungültiges OPML/XML: {exc}") from exc

    if root.tag.rsplit("}", 1)[-1].lower() != "opml":
        raise ImportErrorWithContext("Das XML-Wurzelelement ist kein <opml>.")

    body = next(
        (child for child in root if child.tag.rsplit("}", 1)[-1].lower() == "body"),
        None,
    )
    if body is None:
        raise ImportErrorWithContext("Die OPML-Datei enthält kein <body>.")

    urls: list[str] = []
    seen: set[str] = set()
    for outline in body.iter():
        if outline.tag.rsplit("}", 1)[-1].lower() != "outline":
            continue
        # XML-Attributnamen sind grundsätzlich case-sensitive. In der Praxis
        # kommen in OPML-Exporten jedoch xmlUrl und xmlurl vor.
        feed_url = next(
            (value.strip() for key, value in outline.attrib.items()
             if key.lower() == "xmlurl" and value.strip()),
            "",
        )
        if feed_url and feed_url not in seen:
            seen.add(feed_url)
            urls.append(feed_url)
    return urls


class MinifluxClient:
    def __init__(self, base_url: str, token: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        data = None
        headers = {
            "Accept": "application/json",
            "X-Auth-Token": self.token,
            "User-Agent": "miniflux-opml-import/1.0",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content = response.read()
                return json.loads(content) if content else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            try:
                detail = json.loads(detail).get("error_message", detail)
            except (json.JSONDecodeError, AttributeError):
                pass
            raise ImportErrorWithContext(
                f"Miniflux-API {method} {path}: HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ImportErrorWithContext(
                f"Miniflux-API ist nicht erreichbar: {exc}"
            ) from exc

    def categories(self) -> list[dict[str, Any]]:
        return self.request("GET", "/v1/categories")

    def feeds(self) -> list[dict[str, Any]]:
        return self.request("GET", "/v1/feeds")

    def create_category(self, title: str) -> int:
        result = self.request("POST", "/v1/categories", {"title": title})
        return int(result["id"])

    def create_feed(self, feed_url: str, category_id: int) -> int:
        result = self.request(
            "POST", "/v1/feeds", {"feed_url": feed_url, "category_id": category_id}
        )
        return int(result["feed_id"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fügt neue Feeds aus einer OPML-Datei oder -URL einer "
            "Miniflux-Kategorie hinzu."
        )
    )
    parser.add_argument("source", help="Lokale OPML-Datei oder HTTP(S)-URL")
    parser.add_argument("category", help="Zielkategorie für neue Feeds")
    parser.add_argument(
        "--env-file",
        metavar="DATEI",
        help="Zugangsdaten aus einer dotenv-Datei laden, z. B. .env",
    )
    parser.add_argument(
        "--miniflux-url",
        default=os.environ.get("MINIFLUX_URL"),
        help="Miniflux-Basis-URL (oder Umgebungsvariable MINIFLUX_URL)",
    )
    parser.add_argument(
        "--api-token",
        default=os.environ.get("MINIFLUX_API_TOKEN"),
        help="Miniflux-API-Token (oder MINIFLUX_API_TOKEN)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, was angelegt würde",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="HTTP-Zeitlimit in Sekunden (30)"
    )
    return parser


def run(args: argparse.Namespace) -> int:
    if not args.miniflux_url:
        raise ImportErrorWithContext(
            "Miniflux-URL fehlt (--miniflux-url oder MINIFLUX_URL)."
        )
    if not args.api_token:
        raise ImportErrorWithContext(
            "API-Token fehlt (--api-token oder MINIFLUX_API_TOKEN)."
        )
    if not args.category.strip():
        raise ImportErrorWithContext("Der Kategoriename darf nicht leer sein.")

    opml_urls = parse_feed_urls(read_opml(args.source, args.timeout))
    client = MinifluxClient(args.miniflux_url, args.api_token, args.timeout)
    categories = client.categories()
    feeds = client.feeds()

    existing_urls = {
        str(feed.get("feed_url", "")).strip()
        for feed in feeds
        if feed.get("feed_url")
    }
    new_urls = [url for url in opml_urls if url not in existing_urls]
    skipped = len(opml_urls) - len(new_urls)

    category_title = args.category.strip()
    category = next(
        (item for item in categories if item.get("title") == category_title), None
    )

    print(f"OPML: {len(opml_urls)} eindeutige Feed-URL(s)")
    print(f"Bereits in Miniflux: {skipped}")
    print(f"Neu: {len(new_urls)}")

    if not new_urls:
        print("Keine Änderungen erforderlich.")
        return 0

    if category is None:
        if args.dry_run:
            category_id = -1
            print(f"[Testlauf] Kategorie anlegen: {category_title}")
        else:
            category_id = client.create_category(category_title)
            print(f"Kategorie angelegt: {category_title} (ID {category_id})")
    else:
        category_id = int(category["id"])
        print(f"Kategorie verwenden: {category_title} (ID {category_id})")

    failures = 0
    for feed_url in new_urls:
        if args.dry_run:
            print(f"[Testlauf] Hinzufügen: {feed_url}")
            continue
        try:
            feed_id = client.create_feed(feed_url, category_id)
            print(f"Hinzugefügt: {feed_url} (ID {feed_id})")
        except ImportErrorWithContext as exc:
            failures += 1
            print(f"Fehler: {feed_url}: {exc}", file=sys.stderr)

    if failures:
        print(
            f"Abgeschlossen mit {failures} fehlgeschlagenem Feed/Feeds.",
            file=sys.stderr,
        )
        return 2
    return 0


def main() -> int:
    try:
        env_parser = argparse.ArgumentParser(add_help=False)
        env_parser.add_argument("--env-file")
        env_args, _ = env_parser.parse_known_args()
        if env_args.env_file:
            load_env_file(env_args.env_file)

        parser = build_parser()
        args = parser.parse_args()
        return run(args)
    except ImportErrorWithContext as exc:
        raise SystemExit(f"Fehler: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())

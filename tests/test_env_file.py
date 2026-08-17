import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import miniflux_opml_import as importer


class LoadEnvFileTests(unittest.TestCase):
    def make_env_file(self, content: str) -> str:
        temporary = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".env", delete=False
        )
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        with temporary:
            temporary.write(content)
        return temporary.name

    def test_loads_supported_values(self) -> None:
        filename = self.make_env_file(
            "# Kommentar\n"
            "MINIFLUX_URL=https://example.org # Instanz\n"
            'MINIFLUX_API_TOKEN="token mit leerzeichen"\n'
            "export EXTRA_VALUE='unverändert # behalten'\n"
        )
        with patch.dict(os.environ, {}, clear=True):
            importer.load_env_file(filename)
            self.assertEqual(os.environ["MINIFLUX_URL"], "https://example.org")
            self.assertEqual(os.environ["MINIFLUX_API_TOKEN"], "token mit leerzeichen")
            self.assertEqual(os.environ["EXTRA_VALUE"], "unverändert # behalten")

    def test_does_not_replace_existing_environment(self) -> None:
        filename = self.make_env_file("MINIFLUX_API_TOKEN=aus-datei\n")
        with patch.dict(
            os.environ, {"MINIFLUX_API_TOKEN": "aus-umgebung"}, clear=True
        ):
            importer.load_env_file(filename)
            self.assertEqual(os.environ["MINIFLUX_API_TOKEN"], "aus-umgebung")

    def test_rejects_invalid_line(self) -> None:
        filename = self.make_env_file("KEIN_GLEICHHEITSZEICHEN\n")
        with self.assertRaises(importer.ImportErrorWithContext):
            importer.load_env_file(filename)


if __name__ == "__main__":
    unittest.main()

import csv
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bs4 import BeautifulSoup

import scraper


class NameNormalizationTests(unittest.TestCase):
    def test_explicit_castroseiros_aliases_use_canonical_name(self):
        names = [
            "CASTROSEIROS Mª Eugenia",
            "CASTROSEIROS BRIONGO Mº Eugenia",
            "CASTROSEIROS BRIONGOS Mª Eugenia",
        ]
        mapped, _ = scraper.agrupar_nombres(Counter(names))
        canonical = "CASTROSEIROS BRIONGOS Mª Eugenia"
        self.assertEqual({mapped[name] for name in names}, {canonical})

    def test_distinct_complete_surnames_are_not_merged(self):
        names = ["CASTROSEIROS BRIONGOS Mª Eugenia", "CASTROSEIROS GARCIA Mª Eugenia"]
        mapped, _ = scraper.agrupar_nombres(Counter(names))
        self.assertNotEqual(mapped[names[0]], mapped[names[1]])


class ResultSourceTests(unittest.TestCase):
    def test_pdf_only_page_is_reported_without_inventing_php_url(self):
        soup = BeautifulSoup(
            '<a href="/Tournament/20436/IC.pdf?time=1">Clasificación</a>', "lxml"
        )
        pages = scraper.paginas_resultados("20436", soup, scraper.BASE, False)
        self.assertEqual(pages, [("IC", "Clasificación", None, True)])

    def test_html_link_is_preferred_when_pdf_and_php_are_available(self):
        soup = BeautifulSoup(
            '<a href="/Tournament/20436/IC.pdf?time=1"><img src="pdf.png"></a>'
            '<a href="/Tournament/20436/IC.php">Clasificación</a>',
            "lxml",
        )
        pages = scraper.paginas_resultados("20436", soup, scraper.BASE, False)
        self.assertEqual(
            pages, [("IC", "Clasificación", "https://www.ianseo.net/Tournament/20436/IC.php", False)]
        )

    def test_pdf_only_competition_is_incomplete_and_not_fetched_as_php(self):
        details = '<a href="/Tournament/20436/IC.pdf?time=1">Clasificación</a>'
        with patch.object(scraper, "get", return_value=details) as get:
            fingerprint, rows, complete = scraper.procesar("20436", "Prueba", None, False)
        self.assertIsNone(fingerprint)
        self.assertEqual(rows, [])
        self.assertFalse(complete)
        get.assert_called_once_with("https://www.ianseo.net/Details.php?toId=20436")

    def test_missing_html_result_page_marks_competition_incomplete(self):
        details = '<a href="/Tournament/20436/IFRM.php">Recurve</a>'
        responses = [
            SimpleNamespace(status_code=200, text=details),
            SimpleNamespace(status_code=404, text=""),
        ]
        with patch.object(scraper.S, "get", side_effect=responses) as request, patch.object(
            scraper.time, "sleep"
        ):
            fingerprint, rows, complete = scraper.procesar("20436", "Prueba", None, False)
        self.assertIsNone(fingerprint)
        self.assertEqual(rows, [])
        self.assertFalse(complete)
        self.assertEqual(request.call_count, 2)

    def test_get_does_not_retry_not_found(self):
        response = type("Response", (), {"status_code": 404, "text": ""})()
        with patch.object(scraper.S, "get", return_value=response) as request:
            self.assertIsNone(scraper.get("https://example.invalid/missing.php"))
        request.assert_called_once()

    def test_get_keeps_retries_for_other_http_errors(self):
        response = SimpleNamespace(status_code=503, text="")
        with patch.object(scraper.S, "get", return_value=response) as request, patch.object(
            scraper.time, "sleep"
        ):
            self.assertIsNone(scraper.get("https://example.invalid/unavailable.php"))
        self.assertEqual(request.call_count, 3)


class IncompleteStateTests(unittest.TestCase):
    def test_incomplete_competition_preserves_rows_and_invalidates_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            comp_csv = data / "competiciones.csv"
            nac_csv = data / "resultados_nacionales.csv"
            reg_csv = data / "resultados_regionales.csv"
            state_file = data / "state.json"

            old_row = {column: "" for column in scraper.COLS_NAC}
            old_row.update(toId="20436", tipo="Individual", atleta="Atleta anterior", posicion_final="1")
            scraper.escribir_csv(nac_csv, [old_row], scraper.COLS_NAC)
            scraper.escribir_csv(reg_csv, [], scraper.COLS_REG)
            scraper.escribir_csv(comp_csv, [], scraper.COLS_COMP)
            state_file.write_text(
                json.dumps({"20436": {"h": "old", "a": "", "v": scraper.VERSION_DATOS}}),
                encoding="utf-8",
            )
            competition = {column: "" for column in scraper.COLS_COMP}
            competition.update(toId="20436", competicion="Prueba", fecha_fin="")

            with (
                patch.object(scraper, "DATA", data),
                patch.object(scraper, "COMP_CSV", comp_csv),
                patch.object(scraper, "NAC_CSV", nac_csv),
                patch.object(scraper, "REG_CSV", reg_csv),
                patch.object(scraper, "STATE", state_file),
                patch.object(scraper, "listar_competiciones", return_value={"20436": competition}),
                patch.object(scraper, "procesar", return_value=(None, [], False)),
                patch("sys.argv", ["scraper.py"]),
            ):
                with self.assertRaises(SystemExit) as error:
                    scraper.main()

            self.assertEqual(error.exception.code, 1)
            with nac_csv.open(encoding="utf-8", newline="") as stream:
                saved_rows = list(csv.DictReader(stream))
            self.assertEqual([row["atleta"] for row in saved_rows], ["Atleta anterior"])
            self.assertNotIn("20436", json.loads(state_file.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()

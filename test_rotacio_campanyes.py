import datetime
import sys
import types
import unittest
from unittest import mock


# El Mac pot executar les proves sense tenir instal·lat el client nou de Google;
# aquestes proves només necessiten les funcions pures de rotació.
google_fals = sys.modules.get("google") or types.ModuleType("google")
genai_fals = types.ModuleType("google.genai")
genai_fals.types = types.SimpleNamespace()
google_fals.genai = genai_fals
sys.modules["google"] = google_fals
sys.modules["google.genai"] = genai_fals

import generador


class RotacioCampanyesTest(unittest.TestCase):
    def setUp(self):
        self.dia = datetime.date(2026, 8, 24)

    def test_despres_arrel_toca_llibre(self):
        historial = {
            "2026-08-23": {"campanya": "arrel", "tema": "Rigidesa"},
        }
        self.assertFalse(generador._es_dia_arrel(self.dia, historial))

    def test_despres_llibre_toca_arrel(self):
        historial = {
            "2026-08-23": {
                "campanya": "cita",
                "tema": "Una frase de «Nara»",
            },
        }
        self.assertTrue(generador._es_dia_arrel(self.dia, historial))

    def test_ignora_entrades_futures_i_fitxers_desordenats(self):
        historial = {
            "2026-08-25": {"campanya": "cita"},
            "2026-08-22": {"campanya": "cita"},
            "2026-08-23": {"campanya": "arrel"},
        }
        self.assertFalse(generador._es_dia_arrel(self.dia, historial))

    def test_no_repeteix_el_mateix_llibre_en_dues_cites_seguides(self):
        ordre = generador._ordre_llibres()
        preferit = ordre[self.dia.toordinal() % len(ordre)]
        alternatiu = next(titol for titol in ordre if titol != preferit)
        historial = {
            "2026-08-22": {
                "campanya": "cita",
                "tema": "Una frase de «{}»".format(preferit),
            },
            "2026-08-23": {"campanya": "arrel", "tema": "Arrel"},
        }
        cites = {
            preferit: ["Frase encara no usada del llibre preferit."],
            alternatiu: ["Frase encara no usada del llibre alternatiu."],
        }
        with mock.patch.object(generador, "_carrega_cites", return_value=cites), \
             mock.patch.object(generador, "_frase_ja_usada", return_value=False):
            _, titol = generador._cita_del_dia(self.dia, historial)
        self.assertEqual(titol, alternatiu)


if __name__ == "__main__":
    unittest.main()

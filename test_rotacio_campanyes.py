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

    def test_despres_arrel_toca_sutsumu(self):
        historial = {
            "2026-08-23": {"campanya": "arrel", "tema": "Rigidesa"},
        }
        self.assertEqual(
            generador._tria_campanya(self.dia, historial), "sutsumu"
        )

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

    def test_rotacio_inclou_tots_els_projectes_sense_repeticions(self):
        ordre = ("cita", "arrel", "sutsumu", "bondiari")
        for actual, seguent in zip(ordre, ordre[1:] + ordre[:1]):
            with self.subTest(actual=actual):
                historial = {"2026-08-23": {"campanya": actual}}
                triada = generador._tria_campanya(self.dia, historial)
                self.assertEqual(triada, seguent)
                self.assertNotEqual(triada, actual)

    def test_salta_genikids_mentre_no_te_cap_pagina_publica(self):
        historial = {"2026-08-24": {"campanya": "sutsumu"}}
        self.assertEqual(
            generador._tria_campanya(
                datetime.date(2026, 8, 25), historial
            ),
            "bondiari",
        )
        self.assertNotIn("genikids", generador._campanyes_actives())

    def test_despres_un_genikids_ja_programat_continua_amb_bondiari(self):
        historial = {"2026-08-25": {"campanya": "genikids"}}
        self.assertEqual(
            generador._tria_campanya(
                datetime.date(2026, 8, 26), historial
            ),
            "bondiari",
        )

    def test_cataleg_te_els_tres_projectes_addicionals(self):
        self.assertEqual(
            set(generador.PROJECTES_PROMOCIO),
            {"sutsumu", "genikids", "bondiari"},
        )

    def test_prompts_usen_nomes_enllacos_verificats(self):
        sutsumu = generador._construir_prompt_projecte(
            self.dia, "sutsumu", {}
        )
        bondiari = generador._construir_prompt_projecte(
            self.dia, "bondiari", {}
        )
        self.assertIn("https://apps.apple.com/app/sutsumu/id6776719183", sutsumu)
        self.assertIn("https://bondiari.com", bondiari)

    def test_no_permet_generar_genikids_sense_enllac_public(self):
        self.assertIsNone(generador.PROJECTES_PROMOCIO["genikids"]["url"])
        with self.assertRaisesRegex(ValueError, "pausat"):
            generador._construir_prompt_projecte(
                self.dia, "genikids", {}
            )

    def test_finalitzacio_afegeix_producte_i_web(self):
        posts = {
            "linkedin": {"text": "Un arxiu personal ha de donar calma."},
            "twitter": {"text": "Guardar menys també pot ser conservar millor."},
            "instagram": {"text": "Una biblioteca pròpia per als textos importants."},
        }
        generador._finalitza_projecte(posts, "sutsumu")
        for plataforma in ("linkedin", "twitter"):
            text = posts[plataforma]["text"]
            self.assertIn("https://apps.apple.com/app/sutsumu/id6776719183", text)
            self.assertIn("https://sergicastillo.com", text)
        self.assertIn("Sutsumu · disponible a l'App Store", posts["instagram"]["text"])
        self.assertIn("sergicastillo.com · enllaç a la bio", posts["instagram"]["text"])
        self.assertIn("#Sutsumu", posts["instagram"]["text"])
        self.assertEqual(posts["campanya"], "sutsumu")

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

    def test_una_cita_porta_tres_descripcions_visuals_diferents(self):
        with mock.patch.object(
                generador, "_cita_del_dia",
                return_value=("Una frase literal.", "Nara")):
            posts = generador._genera_posts_cita(self.dia, {})
        descripcions = {
            posts[xarxa]["imatge"]
            for xarxa in ("linkedin", "twitter", "instagram")
        }
        self.assertEqual(len(descripcions), 3)
        self.assertIn("Pla general", posts["linkedin"]["imatge"])
        self.assertIn("Primer pla", posts["twitter"]["imatge"])
        self.assertIn("angle elevat", posts["instagram"]["imatge"])


if __name__ == "__main__":
    unittest.main()

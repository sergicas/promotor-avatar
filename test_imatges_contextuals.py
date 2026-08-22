import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

import illustracions
import imatges_obertes
import publicador


def _png_bytes(mida=(1400, 1000), color=(75, 125, 92)):
    sortida = io.BytesIO()
    Image.new("RGB", mida, color).save(sortida, "PNG")
    return sortida.getvalue()


class ImatgesObertesTest(unittest.TestCase):
    def test_extreu_conceptes_visuals_del_catala(self):
        termes = imatges_obertes.termes_cerca(
            "unes arrels fortes sota un arbre vell al bosc"
        )
        self.assertEqual(termes[:3], ["roots", "tree", "forest"])

    def test_una_branca_no_es_converteix_en_una_cerca_generica_de_llum(self):
        termes = imatges_obertes.termes_cerca(
            "una branca verda que brota d'un tronc vell i molsós amb llum de matí"
        )
        self.assertEqual(termes[:3], ["tree branch", "tree trunk", "moss"])

    def test_cerca_cc0_i_retalla_al_format_de_la_xarxa(self):
        resposta_cerca = Mock()
        resposta_cerca.raise_for_status.return_value = None
        resposta_cerca.json.return_value = {
            "results": [{
                "title": "Old tree roots",
                "creator": "Fotògraf",
                "license": "cc0",
                "mature": False,
                "url": "https://imatges.example/arbre.png",
                "thumbnail": "https://imatges.example/arbre-petit.png",
                "foreign_landing_url": "https://example.com/origen",
                "width": 1400,
                "height": 1000,
            }]
        }
        resposta_imatge = Mock()
        resposta_imatge.raise_for_status.return_value = None
        resposta_imatge.content = _png_bytes()

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(imatges_obertes, "DIR_IMATGES", Path(tmp)), \
             patch("imatges._tradueix_a_prompt", return_value="old tree roots in forest"), \
             patch.object(
                 imatges_obertes.requests, "get",
                 side_effect=[resposta_cerca, resposta_imatge],
             ):
            cami = imatges_obertes.busca_imatge_oberta(
                "arrels d'un arbre al bosc", "2026-08-24", "instagram"
            )
            self.assertIsNotNone(cami)
            with Image.open(cami) as imatge:
                self.assertEqual(imatge.size, (1080, 1080))
            self.assertTrue(cami.with_suffix(".json").exists())

    def test_descarta_imatges_que_exigeixen_atribucio(self):
        resultat = imatges_obertes._tria_resultat(
            [{
                "url": "https://example.com/foto.jpg",
                "license": "by",
                "mature": False,
                "width": 1200,
                "height": 900,
            }],
            "2026-08-24", "linkedin",
        )
        self.assertIsNone(resultat)


class IllustracionsTest(unittest.TestCase):
    def test_genera_formats_sense_targeta_tipografica(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(illustracions, "DIR_IMATGES", Path(tmp)):
            casos = {
                "instagram": (1080, 1080),
                "twitter": (1600, 900),
                "linkedin": (1200, 900),
            }
            descripcions = {
                "instagram": "unes ales de papallona sobre un llibre",
                "twitter": "un fanal en un carrer moll de nit",
                "linkedin": "arrels fortes d'un arbre vell",
            }
            for xarxa, mida in casos.items():
                cami = illustracions.genera_illustracio(
                    descripcions[xarxa], "2026-08-24", xarxa,
                )
                with Image.open(cami) as imatge:
                    self.assertEqual(imatge.size, mida)


class CadenaDeReservaTest(unittest.TestCase):
    def test_si_gemini_falla_usa_fotografia_i_no_targeta(self):
        with tempfile.TemporaryDirectory() as tmp:
            foto = Path(tmp) / "foto.png"
            foto.write_bytes(_png_bytes())
            with patch("imatges.genera_imatge", return_value=None), \
                 patch("imatges_obertes.busca_imatge_oberta", return_value=foto) as cerca, \
                 patch.object(publicador, "_puja_imatge", return_value="https://example.com/foto.png"):
                url, error = publicador._imatge_publica(
                    "arrels sota un arbre", "text del post",
                    "2026-08-24", "instagram",
                )
        self.assertIsNone(error)
        self.assertEqual(url, "https://example.com/foto.png")
        cerca.assert_called_once()

    def test_si_tambe_falla_la_cerca_usa_illustracio(self):
        with tempfile.TemporaryDirectory() as tmp:
            dibuix = Path(tmp) / "dibuix.png"
            dibuix.write_bytes(_png_bytes())
            with patch("imatges.genera_imatge", return_value=None), \
                 patch("imatges_obertes.busca_imatge_oberta", return_value=None), \
                 patch("illustracions.genera_illustracio", return_value=dibuix) as genera, \
                 patch.object(publicador, "_puja_imatge", return_value="https://example.com/dibuix.png"):
                url, error = publicador._imatge_publica(
                    "un rellotge antic", "text del post",
                    "2026-08-24", "linkedin",
                )
        self.assertIsNone(error)
        self.assertEqual(url, "https://example.com/dibuix.png")
        genera.assert_called_once()


if __name__ == "__main__":
    unittest.main()

import datetime
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import bondiari_xarxes as bx


def story_editorial():
    return {
        "title": "Una escola de motocròs combina tècnica esportiva i formació personal",
        "summary": "El projecte acompanya els participants en la pràctica esportiva.",
        "impact": "La iniciativa reforça la formació.",
        "language": "ca",
        "imageUrl": "/api/story-image/feed-editorial?s=prova",
    }


class Resposta:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        return None


class BondiariTests(unittest.TestCase):
    def test_calcula_id_des_de_url_quan_la_imatge_real_es_externa(self):
        story = {
            "title": "Les exploracions de càlcic del cor poden orientar l'ús d'estatines",
            "url": (
                "https://www.statnews.com/2026/08/26/"
                "cac-scans-statin-use-prevent-calculator-heart-disease-risk/"
                "?utm_campaign=rss"
            ),
            "imageUrl": (
                "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/"
                "Coronary_CT_Angiography_Scan.jpg/1280px-Coronary_CT_Angiography_Scan.jpg"
            ),
        }

        self.assertEqual(
            bx.selecciona_capcalera([story])["canonical_url"],
            "https://bondiari.com/noticia/feed-7ox3gq",
        )

    def test_prioritza_id_explicit_valid_encara_que_la_imatge_sigui_externa(self):
        story = {
            "id": "feed-explicit",
            "title": "Una notícia amb foto real",
            "url": "https://example.com/noticia",
            "imageUrl": "https://example.com/foto.jpg",
        }
        self.assertEqual(bx._id_noticia(story), "feed-explicit")

    def test_descarta_anunci_kia_i_tria_noticia_editorial(self):
        anunci = {
            "title": (
                "El nuevo SUV eléctrico de Kia combina una gran autonomía y "
                "soluciones prácticas para el día a día"
            ),
            "summary": "Facilita la transició mostrant un model pràctic i accessible.",
            "source": "elDiario.es",
            "imageUrl": "/api/story-image/feed-anunci?s=prova",
        }
        self.assertTrue(bx.es_contingut_publicitari(anunci))
        self.assertEqual(
            bx.selecciona_capcalera([anunci, story_editorial()])["canonical_url"],
            "https://bondiari.com/noticia/feed-editorial",
        )

    def test_no_publica_si_la_portada_nomes_conte_anuncis(self):
        anunci = {
            "title": "El nuevo SUV de Kia presenta soluciones prácticas y gran autonomía",
            "imageUrl": "/api/story-image/feed-anunci?s=prova",
        }
        with self.assertRaisesRegex(ValueError, "només conté anuncis"):
            bx.selecciona_capcalera([anunci])

    def test_verifica_titular_canonical_i_tres_dades(self):
        story = bx.selecciona_capcalera([story_editorial()])
        article = """
        <html><head><link rel="canonical" href="https://bondiari.com/noticia/feed-editorial"></head>
        <body><article>
          <h1>Una escola de motocròs combina tècnica esportiva i formació personal</h1>
          <p>La iniciativa s'ha posat en marxa aquest estiu.</p>
          <p>El projecte treballa la tècnica esportiva. També acompanya la formació personal.</p>
          <p>Font: Mitjà de prova</p>
        </article></body></html>
        """
        with mock.patch.object(bx.requests, "get", return_value=Resposta(article)):
            verificat = bx.verifica_article(story)
        self.assertEqual(len(verificat["facts"]), 3)
        self.assertTrue(verificat["facts"][0].startswith("La iniciativa"))

    def test_tres_textos_comparteixen_url_i_x_no_supera_280(self):
        story = bx.selecciona_capcalera([story_editorial()])
        story["facts"] = [
            "La iniciativa s'ha posat en marxa aquest estiu.",
            "El projecte treballa la tècnica esportiva.",
            "També acompanya la formació personal.",
        ]
        textos = {x: bx.munta_text(x, story, datetime.date(2026, 8, 3)) for x in bx.XARXES}
        self.assertLessEqual(len(textos["twitter"]), 280)
        for text in textos.values():
            self.assertIn(story["canonical_url"], text)

    def test_registre_es_per_url_i_plataforma(self):
        story = bx.selecciona_capcalera([story_editorial()])
        registre = {"version": 1, "urls": {}}
        ara = datetime.datetime(2026, 8, 3, tzinfo=datetime.timezone.utc)
        bx.registra_publicacio(registre, story, "twitter", {"id": "buffer-1"}, ara=ara)
        self.assertTrue(bx.ja_publicat(registre, story["canonical_url"], "twitter"))
        self.assertFalse(bx.ja_publicat(registre, story["canonical_url"], "instagram"))
        with tempfile.TemporaryDirectory() as carpeta:
            cami = Path(carpeta) / "registre.json"
            bx.desa_registre(registre, cami)
            self.assertEqual(bx.carrega_registre(cami), registre)

    def test_imatge_real_de_noticia_es_retalla_per_instagram(self):
        story = story_editorial()
        buffer = io.BytesIO()
        Image.new("RGB", (1600, 900), (30, 90, 140)).save(buffer, "JPEG")
        resposta = mock.Mock()
        resposta.content = buffer.getvalue()
        resposta.raise_for_status.return_value = None
        with tempfile.TemporaryDirectory() as carpeta, mock.patch.object(
            bx, "DIR_CARDS", Path(carpeta)
        ), mock.patch.object(bx.requests, "get", return_value=resposta):
            cami = bx.prepara_imatge_noticia(
                story, datetime.date(2026, 8, 3), "instagram"
            )
            with Image.open(cami) as imatge:
                self.assertEqual(imatge.format, "PNG")
                self.assertEqual(imatge.size, (1080, 1080))


if __name__ == "__main__":
    unittest.main()

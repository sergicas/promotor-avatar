import datetime
import sys
import types
import unittest
from unittest.mock import patch

promotor_stub = types.ModuleType("promotor")
promotor_stub.PLATAFORMES = ("twitter", "linkedin", "instagram")
promotor_stub._ja_publicat = lambda *args: False
promotor_stub._marcar_publicat = lambda *args: None
promotor_stub._obtenir_posts_dia = lambda *args: {}
publicador_stub = types.ModuleType("publicador")
publicador_stub.publica_post = lambda *args, **kwargs: {"ok": True}
tiktok_stub = types.ModuleType("tiktok")
tiktok_stub.publica_tiktok = lambda *args, **kwargs: {"ok": True}
sys.modules.setdefault("promotor", promotor_stub)
sys.modules.setdefault("publicador", publicador_stub)
sys.modules.setdefault("tiktok", tiktok_stub)

import mati

REAL_DATE = datetime.date


class CadenciaTests(unittest.TestCase):
    def test_proper_dia_es_el_mateix_si_ja_toca(self):
        dia = datetime.date(2026, 7, 24)
        self.assertEqual(mati.proper_dia_publicacio(dia), dia)

    def test_proper_dia_avanca_fins_al_seguent_multiple(self):
        dia = datetime.date(2026, 7, 22)
        self.assertEqual(
            mati.proper_dia_publicacio(dia),
            datetime.date(2026, 7, 24),
        )

    @patch("correu.envia_estat_cadencia")
    @patch("mati.datetime.date")
    def test_dia_sense_posts_envia_heartbeat(self, mock_date, mock_email):
        mock_date.today.return_value = REAL_DATE(2026, 7, 21)
        mock_date.side_effect = lambda *args, **kwargs: REAL_DATE(*args, **kwargs)

        self.assertEqual(mati.executa_amb_reintents(), 0)
        mock_email.assert_called_once_with("2026-07-22", "2026-07-24")


if __name__ == "__main__":
    unittest.main()

import unittest

import bondiari_xarxes as bx


class BondiariTests(unittest.TestCase):
    def test_reparteix_sense_repetir_histories(self):
        stories = [
            {
                "title": "Un projecte català de recerca avança amb un acord històric {}".format(i),
                "language": "ca",
            }
            for i in range(9)
        ]
        lots = bx.reparteix(stories)
        titols = [story["title"] for xarxa in bx.XARXES for story in lots[xarxa]]
        self.assertEqual(len(titols), 9)
        self.assertEqual(len(set(titols)), 9)

    def test_filtre_rebutja_noticies_negatives(self):
        story = {
            "title": "Un acord històric arriba després d'una guerra molt llarga",
            "language": "ca",
        }
        self.assertFalse(bx.es_bona(story))


if __name__ == "__main__":
    unittest.main()

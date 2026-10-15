"""Asignación tolerante de etiquetas del HUD (sin OCR real)."""
import unittest

from vision_engine.hud_locator import _matches, _norm


class LabelMatchingTest(unittest.TestCase):
    def test_exact_labels(self):
        self.assertTrue(_matches('balance', 'CRÉDITO'))
        self.assertTrue(_matches('wager', 'Apuesta'))
        self.assertTrue(_matches('payout', 'GANANCIA'))

    def test_ocr_noise_goes_to_the_closest_field(self):
        self.assertTrue(_matches('wager', 'BPUESTA'))
        self.assertTrue(_matches('balance', 'REDITO'))
        self.assertFalse(_matches('payout', 'REDITO'))

    def test_unrelated_words_and_short_noise_are_ignored(self):
        for word in ('Mame', 'TIR.', 'AUTO.', 'i', '1,60€'):
            for name in ('balance', 'wager', 'payout'):
                self.assertFalse(_matches(name, word), (word, name))

    def test_normalisation_drops_accents_and_symbols(self):
        self.assertEqual(_norm('Crédito:'), 'CREDITO')


if __name__ == '__main__':
    unittest.main()

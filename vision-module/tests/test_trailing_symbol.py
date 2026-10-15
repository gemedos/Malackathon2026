"""El símbolo de moneda leído como dígito («112,25 €» → «112,256») se descarta antes de la segunda lectura."""
import unittest

import numpy as np

from vision_engine.imaging import strip_trailing_symbol


def _line(glyph_widths, gaps, height=20):
    width = sum(glyph_widths) + sum(gaps) + 10
    image = np.full((height + 10, width), 255, np.uint8)
    x = 5
    for i, w in enumerate(glyph_widths):
        image[5:5 + height, x:x + w] = 0
        x += w + (gaps[i] if i < len(gaps) else 0)
    return image


class StripTrailingSymbolTest(unittest.TestCase):
    def test_symbol_after_a_space_is_removed(self):
        image = _line([10, 10, 10, 4, 10, 10, 18], [3, 3, 3, 3, 3, 9])      # «112,25 €»
        out = strip_trailing_symbol(image)
        self.assertIsNotNone(out)
        self.assertTrue((out[:, -20:] == 255).all())
        self.assertLess((out < 128).any(axis=0).sum(), (image < 128).any(axis=0).sum())

    def test_last_digit_without_space_is_kept(self):
        image = _line([10, 10, 10, 4, 10, 10], [3, 3, 3, 3, 3])
        self.assertIsNone(strip_trailing_symbol(image))

    def test_blank_image(self):
        self.assertIsNone(strip_trailing_symbol(np.full((30, 80), 255, np.uint8)))


if __name__ == '__main__':
    unittest.main()

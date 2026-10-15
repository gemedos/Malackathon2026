import tempfile
import unittest

import numpy as np

from support import frame_with, noise_template, synthetic_profile
from vision_engine.engine import VisionEngine
from vision_engine.errors import CalibrationError, ImageError
from vision_engine.geometry import ROI, page_point
from vision_engine.imaging import decode_png
from vision_engine.ready import ReadyDetector


class GeometryTests(unittest.TestCase):
    def test_css_transform_with_offset_and_scale(self):
        self.assertEqual(page_point((100, 50), (400, 200), dict(x=20, y=30, width=200, height=100)), (70, 55))

    def test_mismatched_aspect_ratio_rejected(self):
        with self.assertRaises(CalibrationError):
            page_point((10, 10), (400, 200), dict(x=0, y=0, width=200, height=200))

    def test_point_outside_image_rejected(self):
        with self.assertRaises(CalibrationError):
            page_point((400, 10), (400, 200), dict(x=0, y=0, width=400, height=200))

    def test_invalid_roi(self):
        with self.assertRaises(ValueError):
            ROI(9, 0, 5, 5).crop(np.zeros((10, 10, 3), np.uint8))

    def test_invalid_png(self):
        with self.assertRaises(ImageError):
            decode_png(b'no es una imagen')


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.template = noise_template()
        self.engine = VisionEngine(synthetic_profile(), self.tmp.name, ocr_backend=lambda *_: 'EUR 10.00')

    def test_locate_spin(self):
        hit = self.engine.locate_spin(frame_with(self.template, at=(150, 60)), self.template)
        self.assertIsNotNone(hit)
        self.assertEqual(hit.point, (160.0, 70.0))
        self.assertGreater(hit.confidence, 0.99)

    def test_missing_button_returns_none(self):
        self.assertIsNone(self.engine.locate_spin(frame_with(None), self.template))
        other = noise_template(seed=1)
        self.assertIsNone(self.engine.locate_spin(frame_with(other), self.template))

    def test_different_resolution_rejected(self):
        with self.assertRaises(CalibrationError):
            self.engine.locate_spin(frame_with(self.template, size=(300, 100)), self.template)

    def test_ocr_keeps_text_and_crops(self):
        result = self.engine.read_field(frame_with(None), 'balance', 's1', 0.0)
        self.assertEqual((result.raw_text, result.value, result.error), ('EUR 10.00', '10.00', None))
        self.assertTrue(result.crop_path.endswith('s1-balance.png'))
        self.assertTrue(result.processed_path.endswith('s1-balance-ocr.png'))

    def test_ocr_failure_is_explicit_not_zero(self):
        engine = VisionEngine(synthetic_profile(), self.tmp.name, ocr_backend=lambda *_: '1O.0')
        result = engine.read_field(frame_with(None), 'payout', 's1', 0.0)
        self.assertIsNone(result.value)
        self.assertIn('ilegible', result.error)

    def test_insufficient_message_requires_specific_phrase(self):
        self.assertTrue(self.engine.is_insufficient_message('INSUFFICIENT  Balance!'))
        self.assertFalse(self.engine.is_insufficient_message('Balance'))
        self.assertFalse(self.engine.is_insufficient_message('insufficient'))


class ReadyTests(unittest.TestCase):
    def test_ready_and_busy(self):
        profile = synthetic_profile()
        ready, busy = noise_template(seed=0), noise_template(seed=1)
        detector = ReadyDetector(profile, ready, busy)
        self.assertTrue(detector.observe(frame_with(ready)).ready)
        self.assertFalse(detector.observe(frame_with(busy)).ready)
        self.assertFalse(detector.observe(frame_with(None)).ready)


class WideMessageTests(unittest.TestCase):
    """Respaldo: el mensaje de saldo insuficiente fuera de la región calibrada (otro juego)."""

    def test_wide_read_finds_text_outside_the_calibrated_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = VisionEngine(synthetic_profile(), tmp, ocr_backend=lambda *args: 'Insufficient funds to place this bet')
            frame = np.zeros((100, 200, 3), np.uint8)
            reading = engine.read_wide_message(frame, 'wide')
            self.assertTrue(engine.is_insufficient_message(reading.raw_text))

import copy
import unittest

from support import ROOT, SYNTHETIC_PROFILE
from vision_engine.errors import ProfileError
from vision_engine.profile import GameProfile


def variant(**changes):
    data = copy.deepcopy(SYNTHETIC_PROFILE)
    data.update(changes)
    return data


class ProfileTests(unittest.TestCase):
    def test_examples_load_but_are_not_calibrated(self):
        for name, currency in (('com.example.json', 'EUR'), ('pe.example.json', 'PEN')):
            profile = GameProfile.load(ROOT / 'config' / 'profiles' / name)
            self.assertFalse(profile.calibrated)
            self.assertEqual(profile.expected_currency, currency)
            self.assertIsNotNone(profile.betsson_page)

    def test_missing_region(self):
        data = variant()
        del data['regions']['payout']
        with self.assertRaises(ProfileError):
            GameProfile.from_dict(data)

    def test_region_outside_image(self):
        data = variant()
        data['regions']['reels'] = [150, 0, 100, 50]
        with self.assertRaises(ProfileError):
            GameProfile.from_dict(data)

    def test_generic_pattern_rejected(self):
        for pattern in (r'\bsaldo\b', 'balance', 'insufficient'):
            with self.assertRaises(ProfileError):
                GameProfile.from_dict(variant(insufficient_patterns=[pattern]))

    def test_market_currency_mismatch(self):
        with self.assertRaises(ProfileError):
            GameProfile.from_dict(variant(market='betsson.pe', expected_currency='EUR'))

    def test_motion_thresholds_must_be_separated(self):
        with self.assertRaises(ProfileError):
            GameProfile.from_dict(variant(motion={'start_threshold': 2.0, 'quiet_threshold': 2.0}))

    def test_infinite_timeout_rejected(self):
        with self.assertRaises(ProfileError):
            GameProfile.from_dict(variant(motion={'timeout_seconds': float('inf')}))

    def test_consensus_needs_three_readings(self):
        with self.assertRaises(ProfileError):
            GameProfile.from_dict(variant(consensus={'min_readings': 2}))

    def test_market_defaults_come_from_config(self):
        com = GameProfile.from_dict(variant())
        pe = GameProfile.from_dict(variant(market='betsson.pe', expected_currency='PEN',
                                           insufficient_patterns=None))
        self.assertEqual((com.language, com.language_name), ('en', 'English'))
        self.assertEqual((pe.language, pe.ocr_language), ('es', 'spa+eng'))

    def test_betsson_region_outside_page(self):
        with self.assertRaises(ProfileError):
            GameProfile.from_dict(variant(betsson_page={'image_size': [100, 50], 'balance': [90, 0, 20, 20]}))

    def test_unknown_setting_rejected(self):
        with self.assertRaises(ProfileError):
            GameProfile.from_dict(variant(motion={'typo': 1}))

import tempfile
import unittest
from decimal import Decimal

import numpy as np

from support import after, before_frames, reading, scenario_record, synthetic_profile, W
from vision_engine.engine import VisionEngine
from vision_engine.errors import CalibrationError, ProfileError
from vision_engine.evaluation import BetssonBalance, evaluate_insufficient, evaluate_spin
from vision_engine.language import detect_language
from vision_engine.profile import ConsensusSettings, load_markets
from vision_engine.report import NOT_RUN, TestResult, empty_matrix, overall_status, render_matrix
from vision_engine.verdict import Verdict

PAGE = {'image_size': [300, 100], 'balance': [200, 10, 90, 30]}


def verdicts(report):
    return {a.name: a.verdict for a in report.assertions}


class LanguageTests(unittest.TestCase):
    def test_detection(self):
        self.assertEqual(detect_language('Insufficient balance. Please deposit'), 'en')
        self.assertEqual(detect_language('No tienes saldo suficiente'), 'es')
        self.assertIsNone(detect_language('Balance'))       # una palabra no basta
        self.assertIsNone(detect_language('x7#k ~~ 0.00'))

    def test_wrong_language_fails(self):
        frames = before_frames() + [after(3 + i, t, W, message='Saldo insuficiente para jugar', insufficient=False)
                                    for i, t in enumerate((1.4, 1.8, 2.2, 3.4))]
        report = evaluate_insufficient(scenario_record(frames))   # perfil betsson.com => inglés
        self.assertEqual(verdicts(report)['message_language'], Verdict.FAIL)


class BetssonBalanceTests(unittest.TestCase):
    def test_from_readings_requires_consensus(self):
        settings = ConsensusSettings()
        before = [reading('betsson_balance', '10.00', f'b{i}', t) for i, t in enumerate((0, .5, 1))]
        after = [reading('betsson_balance', '9.00', f'a{i}', t) for i, t in enumerate((5, 5.5))]
        balance = BetssonBalance.from_readings(before, after, settings)
        self.assertEqual(balance.before, Decimal('10.00'))
        self.assertIsNone(balance.after)   # solo dos lecturas: desconocido, nunca cero

    def test_betsson_mismatch_fails_spin(self):
        frames = before_frames()
        report = evaluate_spin(scenario_record(frames),
                               BetssonBalance.from_values(Decimal('10.00'), Decimal('10.00')))
        # Sin apuesta/premio confirmados tras el giro no se puede reconciliar => INCONCLUSIVE, no PASS.
        self.assertEqual(verdicts(report)['betsson_balance'], Verdict.INCONCLUSIVE)

    def test_betsson_changed_after_rejection_fails(self):
        frames = before_frames() + [after(3, 1.4, W)]
        report = evaluate_insufficient(scenario_record(frames),
                                       BetssonBalance.from_values(Decimal('10.00'), Decimal('9.00')))
        self.assertEqual(verdicts(report)['betsson_balance_unchanged'], Verdict.FAIL)
        self.assertIs(report.verdict, Verdict.FAIL)

    def test_page_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = VisionEngine(synthetic_profile(betsson_page=PAGE), tmp, ocr_backend=lambda *_: 'EUR 1,234.50')
            result = engine.read_betsson_balance(np.zeros((100, 300, 3), np.uint8), 'p0', 0.0)
            self.assertEqual(result.value, '1234.50')
            with self.assertRaises(CalibrationError):
                engine.read_betsson_balance(np.zeros((100, 200, 3), np.uint8), 'p1', 0.0)

    def test_page_ocr_needs_profile_region(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = VisionEngine(synthetic_profile(), tmp, ocr_backend=lambda *_: '')
            with self.assertRaises(ProfileError):
                engine.read_betsson_balance(np.zeros((100, 300, 3), np.uint8), 'p0', 0.0)


class ReportTests(unittest.TestCase):
    def test_matrix_keeps_all_four_combinations(self):
        rows = empty_matrix(load_markets())
        self.assertEqual(sorted(rows), ['T01', 'T02', 'T03', 'T04'])
        self.assertEqual(overall_status(list(rows.values())), NOT_RUN)
        text = render_matrix([rows[t] for t in sorted(rows)])
        self.assertIn('T04  betsson.pe', text)
        self.assertIn('FINAL RESULT: NOT RUN', text)

    def test_overall_requires_all_pass(self):
        markets = load_markets()
        rows = empty_matrix(markets)
        passed = [TestResult(r.test_id, r.market, r.scenario, 'PASS') for r in rows.values()]
        self.assertEqual(overall_status(passed), 'PASS')
        self.assertEqual(overall_status(passed[:3] + [TestResult('T04', markets['betsson.pe'],
                                                                 passed[3].scenario, 'ERROR')]), 'ERROR')

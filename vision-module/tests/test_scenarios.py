import tempfile
import unittest
from decimal import Decimal

from support import (M, Q, T, W, after, before_frames, frame_with, noise_template, scenario_record,
                     synthetic_profile)
from vision_engine.engine import VisionEngine
from vision_engine.errors import SequenceError, SpinNotFoundError
from vision_engine.evaluation import ExternalBalance, evaluate_insufficient, evaluate_spin
from vision_engine.motion import MotionSummary
from vision_engine.scenario import SpinAttemptRecorder
from vision_engine.verdict import Verdict

SETTLED = MotionSummary(started_at=1.4, quiet_at=3.0)


def verdicts(report):
    return {a.name: a.verdict for a in report.assertions}


def spin_record(*, final='14.00', payout='5.00', summary=SETTLED, settled_kwargs=None, **kwargs):
    settled_kwargs = settled_kwargs or {}
    frames = before_frames() + [
        after(3, 1.4, M), after(4, 1.6, M),
        after(5, 3.0, Q, balance=final, payout=payout, **settled_kwargs),
        after(6, 3.5, Q, balance=final, payout=payout, **settled_kwargs),
        after(7, 4.0, Q, balance=final, payout=payout, **settled_kwargs),
    ]
    return scenario_record(frames, summary=summary, **kwargs)


class SpinScenarioTests(unittest.TestCase):
    def test_win_reconciles_but_needs_external_balance(self):
        report = evaluate_spin(spin_record())
        self.assertEqual(verdicts(report)['reconciliation'], Verdict.PASS)
        self.assertEqual(verdicts(report)['external_balance'], Verdict.INCONCLUSIVE)
        self.assertIs(report.verdict, Verdict.INCONCLUSIVE)

    def test_win_with_external_balance_passes(self):
        report = evaluate_spin(spin_record(), ExternalBalance(Decimal('10.00'), Decimal('14.00')))
        self.assertIs(report.verdict, Verdict.PASS, report.to_dict())

    def test_loss(self):
        report = evaluate_spin(spin_record(final='9.00', payout='0.00'),
                               ExternalBalance(Decimal('10.00'), Decimal('9.00')))
        self.assertIs(report.verdict, Verdict.PASS)

    def test_wrong_balance_fails(self):
        report = evaluate_spin(spin_record(final='15.00'))
        self.assertEqual(verdicts(report)['reconciliation'], Verdict.FAIL)
        self.assertIs(report.verdict, Verdict.FAIL)

    def test_unreadable_payout_is_unknown_not_zero(self):
        report = evaluate_spin(spin_record(final='9.00', payout='0,0'))
        self.assertEqual(verdicts(report)['payout'], Verdict.INCONCLUSIVE)
        self.assertEqual(verdicts(report)['reconciliation'], Verdict.INCONCLUSIVE)
        self.assertIsNone(report.observed['payout'])

    def test_wrong_currency_fails_and_illegible_is_inconclusive(self):
        wrong = evaluate_spin(scenario_record(before_frames(currency='USD'), summary=SETTLED))
        self.assertEqual(verdicts(wrong)['currency'], Verdict.FAIL)
        illegible = evaluate_spin(scenario_record(before_frames(currency='E?R'), summary=SETTLED))
        self.assertEqual(verdicts(illegible)['currency'], Verdict.INCONCLUSIVE)

    def test_timeout_without_motion(self):
        frames = before_frames() + [after(3, 1.4, T)]
        report = evaluate_spin(scenario_record(frames, summary=MotionSummary(timed_out=True)))
        self.assertEqual(verdicts(report)['reels_started'], Verdict.INCONCLUSIVE)
        self.assertEqual(verdicts(report)['reels_settled'], Verdict.INCONCLUSIVE)

    def test_quiet_without_ready_control_is_not_settlement(self):
        report = evaluate_spin(spin_record(settled_kwargs={'ready': False}))
        self.assertEqual(verdicts(report)['ready_after_settle'], Verdict.INCONCLUSIVE)
        self.assertEqual(verdicts(report)['final_balance'], Verdict.INCONCLUSIVE)

    def test_bonus_or_cascade(self):
        summary = MotionSummary(started_at=1.4, quiet_at=3.0, resumed_after_quiet=True)
        report = evaluate_spin(spin_record(summary=summary))
        self.assertEqual(verdicts(report)['no_cascade_or_bonus'], Verdict.INCONCLUSIVE)

    def test_uncalibrated_profile_never_passes(self):
        report = evaluate_spin(spin_record(profile=synthetic_profile(calibrated=False)),
                               ExternalBalance(Decimal('10.00'), Decimal('14.00')))
        self.assertIs(report.verdict, Verdict.INCONCLUSIVE)


def insufficient_record(*, message_frames=3, balance='10.00', last=3.4, summary=MotionSummary()):
    times = [1.4, 1.8, 2.2, last]
    frames = before_frames() + [
        after(3 + i, t, M if summary.started_at is not None else W, balance=balance,
              message='Insufficient balance', insufficient=i < message_frames)
        for i, t in enumerate(times)]
    return scenario_record(frames, summary=summary)


class InsufficientScenarioTests(unittest.TestCase):
    def test_rejection(self):
        report = evaluate_insufficient(insufficient_record(), ExternalBalance(Decimal('10.00'), Decimal('10.00')))
        self.assertIs(report.verdict, Verdict.PASS, report.to_dict())

    def test_message_in_too_few_frames(self):
        report = evaluate_insufficient(insufficient_record(message_frames=1))
        self.assertEqual(verdicts(report)['rejection_message'], Verdict.INCONCLUSIVE)

    def test_window_not_covered(self):
        report = evaluate_insufficient(insufficient_record(last=3.0))
        self.assertEqual(verdicts(report)['balance_unchanged_in_window'], Verdict.INCONCLUSIVE)

    def test_paid_spin_completed_fails(self):
        report = evaluate_insufficient(insufficient_record(balance='9.00', summary=MotionSummary(started_at=1.4)))
        self.assertEqual(verdicts(report)['no_paid_spin_completed'], Verdict.FAIL)
        self.assertEqual(verdicts(report)['balance_unchanged_in_window'], Verdict.FAIL)
        self.assertIs(report.verdict, Verdict.FAIL)


class RecorderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.template = noise_template()
        engine = VisionEngine(synthetic_profile(), tmp.name, ocr_backend=lambda *_: 'EUR 10.00')
        self.recorder = SpinAttemptRecorder(engine, self.template)

    def test_single_click_only(self):
        self.recorder.observe_before(frame_with(self.template), 0.0)
        hit = self.recorder.register_click(0.1)
        self.assertEqual(hit.point, (160.0, 70.0))
        with self.assertRaises(SequenceError):
            self.recorder.register_click(0.2)
        with self.assertRaises(SequenceError):
            self.recorder.observe_before(frame_with(self.template), 0.3)
        record = self.recorder.observe_after(frame_with(self.template), 0.4)
        self.assertEqual(record.readings['balance'].value, '10.00')

    def test_frame_before_click_is_required(self):
        with self.assertRaises(SequenceError):
            self.recorder.register_click(0.0)
        with self.assertRaises(SequenceError):
            self.recorder.observe_after(frame_with(self.template), 0.1)

    def test_no_click_without_spin_evidence(self):
        self.recorder.observe_before(frame_with(None), 0.0)
        with self.assertRaises(SpinNotFoundError):
            self.recorder.register_click(0.1)
        self.assertFalse(self.recorder.clicked)

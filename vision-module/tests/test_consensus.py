import unittest

from support import reading
from vision_engine.consensus import ConsensusStatus, consensus
from vision_engine.errors import SequenceError
from vision_engine.profile import ConsensusSettings

SETTINGS = ConsensusSettings(min_readings=3, min_separation_seconds=0.3)


def readings(texts, times):
    return [reading('balance', text, f's{i}', t) for i, (text, t) in enumerate(zip(texts, times))]


class ConsensusTests(unittest.TestCase):
    def test_three_spaced_agreeing_readings(self):
        result = consensus('balance', readings(['10.00'] * 3, [0, .5, 1]), SETTINGS)
        self.assertIs(result.status, ConsensusStatus.AGREED)
        self.assertEqual(result.value, '10.00')

    def test_too_close_in_time(self):
        result = consensus('balance', readings(['10.00'] * 3, [0, .1, .2]), SETTINGS)
        self.assertIs(result.status, ConsensusStatus.INSUFFICIENT)

    def test_failed_reading_is_not_counted(self):
        result = consensus('balance', readings(['10.00', '', '10.00'], [0, .5, 1]), SETTINGS)
        self.assertIs(result.status, ConsensusStatus.INSUFFICIENT)
        self.assertIsNone(result.value)

    def test_disagreement(self):
        result = consensus('balance', readings(['10.00', '10.00', '18.00', '10.00'], [0, .5, 1, 1.5]), SETTINGS)
        self.assertIs(result.status, ConsensusStatus.DISAGREEMENT)

    def test_same_frame_counts_once(self):
        same = [reading('balance', '10.00', 's0', t) for t in (0, .5, 1)]
        self.assertIs(consensus('balance', same, SETTINGS).status, ConsensusStatus.INSUFFICIENT)

    def test_mixed_fields_rejected(self):
        with self.assertRaises(SequenceError):
            consensus('balance', [reading('wager', '1.00', 's0', 0)], SETTINGS)

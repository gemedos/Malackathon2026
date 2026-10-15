import unittest

import numpy as np

from vision_engine.errors import SequenceError
from vision_engine.geometry import ROI
from vision_engine.motion import MotionState, MotionTracker
from vision_engine.profile import MotionSettings

BLACK = np.zeros((10, 10, 3), np.uint8)
WHITE = np.full((10, 10, 3), 255, np.uint8)


class MotionTests(unittest.TestCase):
    def tracker(self, **settings):
        return MotionTracker(ROI(0, 0, 10, 10), MotionSettings(**settings))

    def test_no_motion_is_not_settlement(self):
        tracker = self.tracker()
        tracker.observe(BLACK, 0)
        self.assertIs(tracker.observe(BLACK, 2).state, MotionState.WAITING)
        self.assertIsNone(tracker.summary.quiet_at)

    def test_motion_then_quiet(self):
        tracker = self.tracker()
        tracker.observe(BLACK, 0)
        self.assertIs(tracker.observe(WHITE, .2).state, MotionState.MOTION)
        self.assertIs(tracker.observe(WHITE, .4).state, MotionState.MOTION)
        self.assertIs(tracker.observe(WHITE, 1.5).state, MotionState.QUIET_AFTER_MOTION)
        self.assertEqual((tracker.summary.started_at, tracker.summary.quiet_at), (.2, 1.5))

    def test_small_noise_counts_as_quiet(self):
        tracker = self.tracker()
        tracker.observe(BLACK, 0)
        tracker.observe(WHITE, .2)
        almost_white = np.full((10, 10, 3), 254, np.uint8)
        tracker.observe(almost_white, .4)
        self.assertIs(tracker.observe(WHITE, 1.5).state, MotionState.QUIET_AFTER_MOTION)

    def test_motion_resumed_after_quiet_is_flagged(self):
        tracker = self.tracker()
        for frame, t in ((BLACK, 0), (WHITE, .2), (WHITE, .4), (WHITE, 1.5), (BLACK, 1.7)):
            last = tracker.observe(frame, t)
        self.assertIs(last.state, MotionState.MOTION)
        self.assertTrue(tracker.summary.resumed_after_quiet)

    def test_timeout(self):
        tracker = self.tracker(timeout_seconds=1.0)
        tracker.observe(BLACK, 0)
        self.assertIs(tracker.observe(BLACK, 1.5).state, MotionState.TIMEOUT)
        self.assertTrue(tracker.summary.timed_out)

    def test_timestamps_must_increase(self):
        tracker = self.tracker()
        tracker.observe(BLACK, 1.0)
        with self.assertRaises(SequenceError):
            tracker.observe(BLACK, 1.0)

import unittest
from core import SpamDetector, target_allowed


class SafetyTests(unittest.TestCase):
    def test_hierarchy(self):
        self.assertTrue(target_allowed(1, 9, 5, 2, 3, 8, 6))
        self.assertFalse(target_allowed(1, 9, 3, 2, 3, 8, 6))
        self.assertFalse(target_allowed(1, 9, 5, 2, 3, 8, 3))
        self.assertFalse(target_allowed(1, 9, 5, 9, 1, 8, 6))
        self.assertFalse(target_allowed(1, 9, 5, 1, 1, 8, 6))
        self.assertFalse(target_allowed(1, 9, 5, 8, 1, 8, 6))
        self.assertTrue(target_allowed(9, 9, 1, 2, 3, 8, 6))

    def test_spam_threshold_and_reset(self):
        detector = SpamDetector()
        for n in range(5):
            self.assertFalse(detector.hit((1, 2), n))
        self.assertTrue(detector.hit((1, 2), 5))
        self.assertFalse(detector.hit((1, 2), 6))

    def test_window_and_isolation(self):
        detector = SpamDetector()
        for n in range(5):
            self.assertFalse(detector.hit((1, 2), n))
        self.assertFalse(detector.hit((2, 2), 5))
        self.assertFalse(detector.hit((1, 3), 5))
        self.assertFalse(detector.hit((1, 2), 8))


if __name__ == '__main__':
    unittest.main()

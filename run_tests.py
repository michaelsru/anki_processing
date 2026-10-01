#!/usr/bin/env python3
"""Run every test under tests/. Same as `python -m unittest discover tests`."""
import os
import sys
import unittest

if __name__ == '__main__':
    tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests')
    suite = unittest.defaultTestLoader.discover(tests_dir)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

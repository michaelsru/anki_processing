#!/usr/bin/env python3
import unittest
import sys
import os

# Add current directory to path so tests can import scripts
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import tests
from tests.test_anki_scripts import *

if __name__ == '__main__':
    unittest.main(module='tests.test_anki_scripts')

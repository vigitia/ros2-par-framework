# Written by Claude Code
"""Lets the tests import the backend's modules, which live one folder up and are no package."""

import os
import sys

BACKEND_FOLDER_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_FOLDER_PATH)

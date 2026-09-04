"""Test package. Puts this directory on sys.path so `python3 -m unittest` from the repo root
finds `_util` the same way `python3 -m unittest discover -s tests` does."""
import os, sys
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

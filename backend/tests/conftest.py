"""Pytest bootstrap: put project root on sys.path so tests can use absolute
`from backend import ...` imports regardless of where pytest is invoked from."""
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Tests should never reach the real model client.
os.environ.setdefault("CASE_PROVIDER", "stub")
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

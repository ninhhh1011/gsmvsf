"""Run audit tests or exported unit tests with explicit boundary fixtures."""
import sys
from pathlib import Path
import audit_support
import pytest
h=Path(__file__).parent
args=sys.argv[1:] or [str(h/'test_correctness.py'), '-q', '--tb=short']
raise SystemExit(pytest.main(['--noconftest','--asyncio-mode=auto','-p','no:cacheprovider',*args]))

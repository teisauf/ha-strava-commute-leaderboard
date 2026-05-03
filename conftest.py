"""Pytest configuration — make custom_components/ importable from tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

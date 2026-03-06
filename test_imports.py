#!/usr/bin/env python3
"""
Test script to verify core module imports work correctly
Run this locally before deploying to Render
"""
import sys
from pathlib import Path

# Add project root to path (mimics what main.py does)
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print("Testing imports...")
print(f"Python path includes: {project_root}")

try:
    # Test 1: Import from core package
    from core import init_db, close_db, get_settings
    print("✓ Test 1 PASSED: from core import init_db, close_db, get_settings")
except ImportError as e:
    print(f"✗ Test 1 FAILED: {e}")
    sys.exit(1)

try:
    # Test 2: Import specific modules
    from core.config import Settings
    from core.database import Database
    from core.security import verify_password
    print("✓ Test 2 PASSED: Direct module imports work")
except ImportError as e:
    print(f"✗ Test 2 FAILED: {e}")
    sys.exit(1)

try:
    # Test 3: Check that functions are callable
    settings = get_settings()
    print(f"✓ Test 3 PASSED: get_settings() works, ENV={settings.ENV}")
except Exception as e:
    print(f"✗ Test 3 FAILED: {e}")
    sys.exit(1)

print("\n" + "="*50)
print("ALL TESTS PASSED - Ready to deploy to Render")
print("="*50)

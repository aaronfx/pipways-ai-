"""
Core module initialization
"""
import sys
from pathlib import Path

# Add parent directory to path for absolute imports
if __name__ != "__main__":
    current_file = Path(__file__).resolve()
    parent_dir = current_file.parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

# Now import with try/except for flexibility
try:
    from core.config import get_settings, Settings
    from core.database import db, init_db, close_db
    from core.security import (
        verify_password, 
        get_password_hash, 
        create_access_token, 
        decode_token,
        get_current_user,
        get_current_admin
    )
except ImportError as e:
    # Fallback for when core is not in path
    import importlib.util
    import os

    # Find the core directory
    current_dir = Path(__file__).parent

    def load_module_from_file(module_name, file_path):
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    # Load modules directly
    config_module = load_module_from_file("core_config", current_dir / "config.py")
    database_module = load_module_from_file("core_database", current_dir / "database.py")
    security_module = load_module_from_file("core_security", current_dir / "security.py")

    get_settings = config_module.get_settings
    Settings = config_module.Settings
    db = database_module.db
    init_db = database_module.init_db
    close_db = database_module.close_db
    verify_password = security_module.verify_password
    get_password_hash = security_module.get_password_hash
    create_access_token = security_module.create_access_token
    decode_token = security_module.decode_token
    get_current_user = security_module.get_current_user
    get_current_admin = security_module.get_current_admin

__all__ = [
    "get_settings",
    "Settings", 
    "db",
    "init_db",
    "close_db",
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "decode_token",
    "get_current_user",
    "get_current_admin"
]

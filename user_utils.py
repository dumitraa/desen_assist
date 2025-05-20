# user_utils.py ----------------------------------------------------------
from qgis.PyQt.QtWidgets import QInputDialog  # type: ignore
from qgis.core import QgsSettings  # type: ignore
import configparser
from pathlib import Path

_SETTINGS_KEY = "/DesenAssist/UserName"

def get_current_user(parent=None) -> str:
    """Return stored user name; prompt once if not set."""
    s = QgsSettings()
    user = s.value(_SETTINGS_KEY, "", type=str)

    if not user:                                            # first run
        user, ok = QInputDialog.getText(
            parent, "Who is working?", "Enter your name:")
        if ok and user.strip():
            s.setValue(_SETTINGS_KEY, user.strip())
        else:
            user = "unknown"

    return user


def get_plugin_version() -> str:
    """Return plugin version string from metadata.txt"""
    meta_path = Path(__file__).with_name("metadata.txt")
    parser = configparser.ConfigParser()
    parser.read(meta_path, encoding="utf-8")
    return parser.get("general", "version", fallback="0")

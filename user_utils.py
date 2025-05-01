# user_utils.py ----------------------------------------------------------
from qgis.PyQt.QtWidgets import QInputDialog # type: ignore
from qgis.core import QgsSettings # type: ignore

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

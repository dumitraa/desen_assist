# config.py  (what you have now)
NULL_VALUES = ["NULL", "None", None, "nan", ""]

from pathlib import Path
import configparser, logging

_cfg = configparser.ConfigParser()
ini_path = Path(__file__).with_name("config.ini")
_cfg.read(ini_path, encoding="utf-8")

def _get(section, key, default=None):
    return _cfg.get(section, key, fallback=default)

BACKEND_URL = _get("backend", "url", "http://localhost:8000").rstrip("/")
TIMEOUT     = float(_get("backend", "timeout", 1))

LAYERS      = [
    n.strip() for n in _get("layers", "watch", "").split(",") if n.strip()
]

AUTH_TOKEN  = _get("auth", "token", None)
VALIDATION  = _cfg["validation"] if "validation" in _cfg else {}

logging.info("Config loaded – BACKEND_URL=%s LAYERS=%s", BACKEND_URL, LAYERS)

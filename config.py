"""
config.py — Carrega les claus API des de dades/keys.json (o variables d'entorn)
Prioritat: variables d'entorn > keys.json
Compatible amb Python 3.9+
"""

import os
import json
from pathlib import Path
from typing import Optional

FITXER_KEYS = Path(__file__).parent / "dades" / "keys.json"


def get_key(nom):
    # type: (str) -> Optional[str]
    """
    Retorna el valor d'una clau API.
    Prioritat: variable d'entorn > dades/keys.json
    """
    # 1. Variable d'entorn té prioritat
    valor = os.environ.get(nom)
    if valor:
        return valor

    # 2. Llegir del fitxer keys.json
    try:
        if FITXER_KEYS.exists():
            with open(FITXER_KEYS, "r", encoding="utf-8") as f:
                keys = json.load(f)
            valor = keys.get(nom, "").strip()
            if valor:
                return valor
    except (json.JSONDecodeError, IOError):
        pass

    return None


def guardar_key(nom, valor):
    # type: (str, str) -> bool
    """Guarda o actualitza una clau al fitxer keys.json."""
    try:
        keys = {}
        if FITXER_KEYS.exists():
            with open(FITXER_KEYS, "r", encoding="utf-8") as f:
                keys = json.load(f)
        keys[nom] = valor.strip()
        FITXER_KEYS.parent.mkdir(parents=True, exist_ok=True)
        with open(FITXER_KEYS, "w", encoding="utf-8") as f:
            json.dump(keys, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def keys_configurades():
    # type: () -> dict
    """Retorna quines claus estan configurades (sense revelar els valors)."""
    return {
        "GEMINI_API_KEY": bool(get_key("GEMINI_API_KEY")),
        "BUFFER_ACCESS_TOKEN": bool(get_key("BUFFER_ACCESS_TOKEN")),
    }

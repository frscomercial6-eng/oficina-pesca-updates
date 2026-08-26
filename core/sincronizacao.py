# -*- coding: utf-8 -*-
"""Helpers de backup e sincronização isolados para reduzir acoplamento do menu."""

from __future__ import annotations

import requests

from config import obter_firebase_web_config


def checar_status_firebase() -> bool:
    """Verifica rapidamente se o Firebase Web está disponível."""
    try:
        cfg = obter_firebase_web_config() if callable(obter_firebase_web_config) else {}
        db_url = str((cfg or {}).get("databaseURL") or "").strip()
        if not db_url:
            return False
        resp = requests.get(f"{db_url.rstrip('/')}/.json", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False

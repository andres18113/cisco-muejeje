"""Serializacion segura de la llamada IOS oficial de Packet Tracer."""

from __future__ import annotations

import json


def build_configure_ios_call(device: str, ios_payload: str) -> str:
    """Devuelve una llamada de una sola linea compatible con ``executeCode``."""
    return "configureIosDevice(" + json.dumps(device) + "," + json.dumps(ios_payload) + ");"

"""Descubrimiento de las áreas de Vendedores.

Recorre `vendedores/agentes/*/` y lee su contrato público. El orquestador de este
multiagente solo puede delegar en estas áreas: las de `clientes` no existen para él,
porque están en otro paquete y este registro nunca las mira.
"""
import importlib
import logging
import pkgutil
from pathlib import Path

_PAQUETE = "vendedores.agentes"
_DIR = Path(__file__).parent / "agentes"
_REQUERIDO = ("MODELO", "TOOLS")


def _descubrir() -> dict:
    areas = {}
    for info in pkgutil.iter_modules([str(_DIR)]):
        if not info.ispkg:
            continue
        try:
            mod = importlib.import_module(f"{_PAQUETE}.{info.name}")
        except Exception as e:
            logging.error(f"[vendedores] área {info.name!r} no importa: {e}")
            continue
        if any(not hasattr(mod, c) for c in _REQUERIDO):
            logging.warning(f"[vendedores] área {info.name!r} sin contrato, ignorada.")
            continue
        areas[info.name] = mod
    return areas


_AREAS = _descubrir()


def nodos() -> dict:
    return {n: m.NODO for n, m in _AREAS.items() if getattr(m, "NODO", None) is not None}


def tools_de_delegacion() -> list:
    """Una tool por área para que el orquestador delegue.

    TODO: Command(goto=<area>, graph=Command.PARENT). La descripción es la
    pregunta que contesta el área, no sus tools internas.
    """
    raise NotImplementedError


def mapa() -> dict:
    return {n: (m.MODELO, [t.name for t in m.TOOLS]) for n, m in _AREAS.items()}

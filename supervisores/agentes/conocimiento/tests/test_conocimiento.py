"""Tests de `conocimiento` (supervisores)."""


def test_consulta_va_sin_modificar():
    """Lo que entra a la búsqueda debe ser la consulta del usuario, tal cual.

    Es la regla que se rompe primero cuando alguien agregue reformulación sin
    medirla.
    """


def test_no_devuelve_documentos_de_otro_multiagente():
    """El filtro por multiagente va antes de la similitud."""

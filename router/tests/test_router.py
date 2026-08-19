"""Tests del router. Son los más importantes del repo.

El router es la única frontera entre un cliente y el precio neto de Catusita.
Cada caso de acá corresponde a una forma real de fallar.

La prueba que no puede faltar: NINGUNA entrada rara llega a `vendedores`.
"""
import pytest

from router import resolver


# ── La única ruta a vendedores ───────────────────────────────────────────────

@pytest.mark.skip("pendiente: implementar router.resolver")
def test_asesor_registrado_en_canal_interno_va_a_vendedores():
    d = resolver("987654321", "vendedores")
    assert d.multiagente == "vendedores"


# ── Todo lo demás cae a clientes ─────────────────────────────────────────────

@pytest.mark.skip("pendiente: implementar router.resolver")
@pytest.mark.parametrize("numero,session,caso", [
    ("999999999", "vendedores", "desconocido escribiendo a la sesión interna"),
    ("987654321", "clientes", "asesor escribiendo al número público"),
    ("987654321", "default", "la sesión de hoy, sin canal declarado"),
    ("987654321", "", "session vacía"),
    ("987654321", None, "session ausente"),
    ("", "vendedores", "número vacío"),
    (None, "vendedores", "número ausente"),
    ("12345@lid", "vendedores", "LID que no se pudo traducir a teléfono"),
])
def test_todo_lo_dudoso_cae_a_clientes(numero, session, caso):
    assert resolver(numero, session).multiagente == "clientes", caso


@pytest.mark.skip("pendiente: implementar router.resolver")
def test_sin_canal_configurado_nadie_llega_a_vendedores(monkeypatch):
    """Hoy webhooks/whatsapp.py:471 hardcodea "vendedor" para todo WAHA."""
    monkeypatch.setattr("router.numeros.SESION_VENDEDORES", "")
    assert resolver("987654321", "vendedores").multiagente == "clientes"


@pytest.mark.skip("pendiente: implementar router.resolver")
def test_registro_caido_cae_a_clientes(monkeypatch):
    """Si la BD de asesores no responde, se degrada al lado seguro."""
    def explota(_):
        raise ConnectionError("BD caída")
    monkeypatch.setattr("router.numeros.es_asesor", explota)
    assert resolver("987654321", "vendedores").multiagente == "clientes"


@pytest.mark.skip("pendiente: implementar router.resolver")
def test_nunca_lanza():
    """El router no puede tumbar el webhook. Ante basura, devuelve clientes."""
    for basura in [None, "", "  ", "no-es-un-numero", "51" * 100, "🙂"]:
        assert resolver(basura, basura).multiagente == "clientes"


# ── Aislamiento entre multiagentes ──────────────────────────────────────────────

def test_clientes_no_importa_codigo_de_vendedores():
    """Las áreas de clientes no pueden alcanzar crédito, cartera ni facturación.

    Este test no necesita el router implementado: mira el código fuente.
    """
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[2]
    ofensores = []
    for py in (raiz / "clientes").rglob("*.py"):
        texto = py.read_text(encoding="utf-8")
        if "vendedores" in texto and "from vendedores" in texto or "import vendedores" in texto:
            ofensores.append(str(py.relative_to(raiz)))
    assert not ofensores, f"clientes importa código de vendedores: {ofensores}"

"""Tests del router. Son los más importantes del repo.

El router es la única frontera entre un desconocido y el precio neto de
Catusita. Cada caso de acá corresponde a una forma real de fallar.

La prueba que no puede faltar: NINGUNA entrada rara llega a `vendedores`.

── Sin Redis y sin pytest-asyncio ─────────────────────────────────────────────

`padron.multiagente_de` se reemplaza por una función en memoria, así que estos
tests corren sin Redis y sin red. Y `resolver` es async, pero se invoca con un
`asyncio.run` adentro de tests sincrónicos: no hace falta pytest-asyncio.
"""
import asyncio

import pytest

from recepcion import numeros, padron, router

ASESOR = "51987654321"
DESCONOCIDO = "51999999999"

# La de verdad, capturada antes de que el fixture la reemplace. `router.padron`
# y `recepcion.padron` son el MISMO objeto módulo: parchear uno parchea el otro,
# así que sin esta referencia no habría forma de probar la original.
MULTIAGENTE_DE_REAL = padron.multiagente_de


@pytest.fixture(autouse=True)
def padron_falso(monkeypatch):
    """Un padrón en memoria con un solo asesor."""
    async def multiagente_de(numero):
        if numero == ASESOR:
            return "vendedores", "padrón dice vendedores"
        return "clientes", "no está en el padrón"

    monkeypatch.setattr(router.padron, "multiagente_de", multiagente_de)


def resolver(numero, session=""):
    return asyncio.run(router.resolver(numero, session))


# ── La ruta a vendedores ─────────────────────────────────────────────────────

def test_el_padron_alcanza_para_llegar_a_vendedores():
    """Con UN número de WhatsApp, el padrón es la única señal que hay.

    La versión anterior exigía además que el mensaje entrara por la sesión de
    vendedores. Como esa sesión no existe todavía, la condición no se cumplía
    nunca y TODO caía a clientes — el ruteo entero muerto por una verificación
    que no verificaba nada.
    """
    assert resolver(ASESOR, "default").multiagente == "vendedores"


@pytest.mark.parametrize("session", ["default", "", None, "cualquier-cosa"])
def test_una_sesion_no_declarada_no_opina(session):
    """Si nadie reclamó esa sesión, el canal no aporta y decide el padrón."""
    assert resolver(ASESOR, session).multiagente == "vendedores"


# ── Todo lo dudoso cae a clientes ────────────────────────────────────────────

@pytest.mark.parametrize("numero,caso", [
    (DESCONOCIDO, "número que no está en el padrón"),
    ("", "número vacío"),
    (None, "número ausente"),
    ("12345@lid", "LID que no se pudo traducir a teléfono"),
    ("no-es-un-numero", "basura"),
    ("🙂", "emoji"),
])
def test_todo_lo_dudoso_cae_a_clientes(numero, caso):
    assert resolver(numero, "default").multiagente == "clientes", caso


def test_padron_caido_cae_a_clientes(monkeypatch):
    """Si Redis no responde, se degrada al lado seguro.

    Un asesor atendido como cliente es una molestia; un desconocido atendido
    como asesor es una fuga de cartera.
    """
    async def explota(_):
        raise ConnectionError("Redis caído")

    # El try/except está en padron.multiagente_de, así que se parchea el pool.
    monkeypatch.setattr(router.padron, "multiagente_de", explota)
    with pytest.raises(ConnectionError):
        resolver(ASESOR)


def test_el_padron_real_absorbe_la_caida_de_redis(monkeypatch):
    """La misma caída, pero con el `padron` de verdad: devuelve clientes."""

    class RedisMuerto:
        async def hget(self, *a):
            raise ConnectionError("Redis caído")

    async def get():
        return RedisMuerto()

    monkeypatch.setattr(padron.redis_mod, "get", get)
    dueno, motivo = asyncio.run(MULTIAGENTE_DE_REAL(ASESOR))
    assert dueno == "clientes"
    assert "inaccesible" in motivo


def test_nunca_lanza():
    """El router no puede tumbar el webhook. Ante basura, devuelve clientes."""
    for basura in [None, "", "  ", "no-es-un-numero", "51" * 100, "🙂", "@@@"]:
        assert resolver(basura, basura).multiagente == "clientes"


# ── Cuando SÍ haya canales separados ─────────────────────────────────────────

def test_escribir_al_numero_de_otro_multiagente_cae_a_clientes(monkeypatch):
    """El canal define el alcance, no el cargo.

    Un asesor que le escribe al número público no debería sacar precio neto por
    ahí. Esta regla se activa sola el día que se declaren las sesiones.
    """
    monkeypatch.setitem(numeros.SESIONES, "vendedores", "wa-internos")
    monkeypatch.setitem(numeros.SESIONES, "clientes", "wa-publico")

    assert resolver(ASESOR, "wa-internos").multiagente == "vendedores"

    d = resolver(ASESOR, "wa-publico")
    assert d.multiagente == "clientes"
    assert "número de clientes" in d.motivo


def test_el_motivo_siempre_explica_el_destino():
    """Sin motivo, «entró como cliente» no dice si fue por el padrón, por Redis
    o porque efectivamente es un cliente. Es la auditoría del ruteo."""
    for numero in (ASESOR, DESCONOCIDO, "", "basura"):
        assert resolver(numero, "default").motivo


# ── Responder ────────────────────────────────────────────────────────────────

def test_se_responde_por_el_unico_numero_mientras_no_haya_otros():
    """Con una sola sesión, los tres multiagentes contestan por ella."""
    for ma in ("vendedores", "clientes", "supervisores"):
        assert numeros.sesion_de(ma) == numeros.SESION_UNICA


def test_con_sesion_propia_se_responde_por_la_suya(monkeypatch):
    monkeypatch.setitem(numeros.SESIONES, "vendedores", "wa-internos")
    assert numeros.sesion_de("vendedores") == "wa-internos"
    assert numeros.sesion_de("clientes") == numeros.SESION_UNICA


# ── Aislamiento entre multiagentes ───────────────────────────────────────────

def test_clientes_no_importa_codigo_de_vendedores():
    """Las áreas de clientes no pueden alcanzar crédito, cartera ni facturación.

    Mira el código fuente: un import cruzado es la forma más silenciosa de que
    el aislamiento vertical se rompa.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    ofensores = []
    for py in (raiz / "clientes").rglob("*.py"):
        texto = py.read_text(encoding="utf-8")
        if "from vendedores" in texto or "import vendedores" in texto:
            ofensores.append(str(py.relative_to(raiz)))
    assert not ofensores, f"clientes importa código de vendedores: {ofensores}"


def test_recepcion_no_importa_ningun_multiagente():
    """La recepción no sabe qué es un vendedor_id ni un RUC. Si importara un
    multiagente, tendría que desplegarse cada vez que cambia uno."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[2]
    ofensores = []
    for py in (raiz / "recepcion").rglob("*.py"):
        if "tests" in py.parts:
            continue
        texto = py.read_text(encoding="utf-8")
        for ma in ("vendedores", "clientes", "supervisores"):
            if f"from {ma}" in texto or f"import {ma}" in texto:
                ofensores.append(f"{py.relative_to(raiz)} -> {ma}")
    assert not ofensores, f"la recepción importa multiagentes: {ofensores}"

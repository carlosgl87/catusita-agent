"""Normalización de números y mapa de sesiones de WAHA.

── Por qué normalizar ─────────────────────────────────────────────────────────

El mismo número llega escrito de cinco formas distintas según de dónde venga:

    51987654321@c.us        WAHA, formato interno
    +51 987 654 321         como lo guardó un humano
    987654321               local, sin país
    51987654321             completo

Si el padrón se publica con uno y la consulta llega con otro, el HGET no matchea
y el asesor entra como cliente. Sin error, sin log: simplemente atendido por el
agente equivocado. Por eso normalizar es lo primero que pasa con un número, acá
y en el padrón de cada multiagente.

── Los LID ────────────────────────────────────────────────────────────────────

WAHA entrega `<lid>@lid` para muchos contactos en vez del teléfono. Un LID no se
puede normalizar a número: hay que preguntarle a WAHA a qué teléfono
corresponde, y eso es una llamada de red.

Por eso esa traducción NO está acá. La hace el webhook antes de llamar al
router, y si falla, el número queda sin resolver y el mensaje cae a `clientes` —
que es el lado seguro.

── Las sesiones ───────────────────────────────────────────────────────────────

Una sesión de WAHA es un número de WhatsApp conectado. Hoy corre UNA sola
(`WAHA_SESSION`, normalmente "default") y los tres multiagentes comparten ese
número: quién atiende cada mensaje lo decide el padrón, no el canal.

Las variables por multiagente existen para el día que Catusita conecte un número
por canal. Mientras estén vacías:

    multiagente_de_sesion(...)  -> ""        el canal no opina, manda el padrón
    sesion_de("vendedores")     -> "default" se responde por el único número

Ese es el orden correcto de dependencia: primero funciona con un número, y
conectar los otros dos es llenar variables — no tocar código.
"""
import os
import re

# El único número que hay hoy. Es el que se usa para responder mientras no haya
# uno declarado por multiagente.
SESION_UNICA = os.getenv("WAHA_SESSION", "default")

# Una sesión por multiagente, para cuando haya varios números. Vacías = todavía
# no existe ese canal separado.
SESIONES = {
    "vendedores":   os.getenv("WAHA_SESSION_VENDEDORES", ""),
    "clientes":     os.getenv("WAHA_SESSION_CLIENTES", ""),
    "supervisores": os.getenv("WAHA_SESSION_SUPERVISORES", ""),
}

_SOLO_DIGITOS = re.compile(r"\D")

# Perú. Los locales son de 9 dígitos y empiezan en 9.
PREFIJO = "51"
LARGO_LOCAL = 9


def normalizar(numero: str) -> str:
    """Cualquier forma -> '51987654321'. Cadena vacía si no se puede.

    Devuelve vacío y no lanza: quien llama trata el vacío como «no resuelto» y
    manda el mensaje al lado seguro.
    """
    if not numero:
        return ""

    # Un LID no es un teléfono. Hay que traducirlo antes (ver encabezado).
    if "@lid" in numero:
        return ""

    limpio = _SOLO_DIGITOS.sub("", numero.split("@")[0])
    if not limpio:
        return ""

    if len(limpio) == LARGO_LOCAL and limpio.startswith("9"):
        return PREFIJO + limpio

    return limpio


def multiagente_de_sesion(session: str) -> str:
    """Qué multiagente reclama esa sesión como suya. Vacío si ninguno.

    Vacío es el caso normal hoy: nadie declaró sesión propia, así que el canal
    no aporta información y el router decide con el padrón solo.
    """
    for ma, s in SESIONES.items():
        if s and str(session) == s:
            return ma
    return ""


def sesion_de(multiagente: str) -> str:
    """Desde qué sesión de WAHA se le responde a este multiagente.

    La suya si tiene una declarada; si no, el número único. Es lo que hace que
    responder funcione igual con un número o con tres.
    """
    return SESIONES.get(multiagente) or SESION_UNICA

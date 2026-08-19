"""Un asesor solo ve clientes de SU cartera.

── Por qué está acá y no en un área ───────────────────────────────────────────

Lo usan tres: `pedidos`, `facturacion` y `clientes`. No es de ninguna — es una
regla del multiagente vendedores entero, igual que las reglas de privacidad de
`validar`. Ponerla en un área y que las otras la importen sería exactamente el
cruce que el diseño prohíbe.

Y no existe en `clientes/` ni en `supervisores/`: un cliente no tiene cartera, y
qué ve un supervisor está sin definir. Por eso vive en `plataforma_vendedores/` y
no en una plataforma compartida.

── Por qué en código y no en el prompt ────────────────────────────────────────

Un prompt que dice «no consultes clientes ajenos» se cumple casi siempre. Casi.
Acá la consulta ni se ejecuta: se valida antes de tocar el backend.

── Lo que también hace, y no es obvio ─────────────────────────────────────────

Resuelve nombres a RUC. El asesor escribe «los pedidos de Repuestos Lima» y esto
lo convierte al RUC — buscando SOLO dentro de su cartera, así que la resolución
por nombre es al mismo tiempo el control de acceso. No hay forma de nombrar a un
cliente ajeno y que resuelva.

Tres salidas cuando no resuelve a uno solo:

    MULTIPLE_COINCIDENCIAS   varios de su cartera coinciden -> que elija
    ACCESO_DENEGADO          escribió un RUC bien formado que no es suyo
    CLIENTE_NO_ENCONTRADO    escribió un nombre que no coincide con nada suyo

La distinción entre los dos últimos importa: a un RUC ajeno se le dice que no es
de su cartera; a un nombre que no existe, que verifique cómo lo escribió. Decir
«no es tuyo» ante un tipeo manda al asesor a pelear con su supervisor por un
permiso que ya tiene.
"""
import logging

from vendedores.plataforma_vendedores import backend_cartera

LONGITUD_RUC = 11


async def _cartera(perfil: dict) -> list[dict]:
    """Clientes del asesor. Cacheado en el perfil para no repetir la llamada
    dentro del mismo turno: `pedidos` y `facturacion` la piden por separado."""
    if (cache := perfil.get("_cartera")) is not None:
        return cache
    datos = await backend_cartera.cartera(perfil.get("vendedor_id", ""))
    clientes = datos.get("clientes", []) if isinstance(datos, dict) else []
    perfil["_cartera"] = clientes
    return clientes


async def resolver(termino: str, perfil: dict) -> dict:
    """RUC o nombre parcial -> {ok|multiple|ninguno}. Solo dentro de su cartera."""
    termino = (termino or "").strip()
    if not termino:
        return {"estado": "ninguno"}

    try:
        clientes = await _cartera(perfil)
    except Exception as e:
        # Falla cerrada: sin cartera no se autoriza nada. Un asesor sin servicio
        # es un incidente menor; un desconocido con acceso a una cartera ajena
        # es uno grave.
        logging.error(f"[acceso] no se pudo leer la cartera: {e}")
        return {"estado": "ninguno"}

    for c in clientes:
        if c.get("ruc") == termino:
            return {"estado": "ok", "ruc": termino}

    buscado = termino.lower()
    exactos, parciales = [], []
    for c in clientes:
        if not c.get("ruc"):
            continue
        razon = (c.get("razon_social") or "").lower()
        if buscado == razon:
            exactos.append(c)
        elif buscado in razon or (razon and razon in buscado):
            parciales.append(c)

    for grupo in (exactos, parciales):
        if len(grupo) == 1:
            return {"estado": "ok", "ruc": grupo[0]["ruc"]}
        if len(grupo) > 1:
            return {"estado": "multiple", "clientes": grupo}

    return {"estado": "ninguno"}


async def verificar(termino: str, perfil: dict) -> tuple[str | None, dict | None]:
    """(ruc_resuelto, None) si puede pasar. (None, error) si no.

    Las tools llaman a esto ANTES de tocar el backend y devuelven el error tal
    cual si viene. Nunca al revés: consultar primero y filtrar después significa
    que el dato ajeno ya salió del backend.
    """
    if perfil.get("tipo") != "asesor":
        return None, {
            "error": "ACCESO_DENEGADO",
            "mensaje": "Esta consulta es solo para asesores.",
        }

    r = await resolver(termino, perfil)

    if r["estado"] == "ok":
        return r["ruc"], None

    if r["estado"] == "multiple":
        return None, {
            "error": "MULTIPLE_COINCIDENCIAS",
            "mensaje": (
                f"Hay varios clientes que coinciden con '{termino}' en tu cartera. "
                "Preguntale al usuario a cuál se refiere."
            ),
            "clientes": [
                {"ruc": c["ruc"], "razon_social": c.get("razon_social", "")}
                for c in r["clientes"]
            ],
        }

    if termino.isdigit() and len(termino) == LONGITUD_RUC:
        return None, {
            "error": "ACCESO_DENEGADO",
            "mensaje": (
                "Ese cliente no está en tu cartera asignada. Solo puedo darte "
                "información de tus propios clientes."
            ),
        }

    return None, {
        "error": "CLIENTE_NO_ENCONTRADO",
        "mensaje": (
            f"No hay ningún cliente que coincida con '{termino}' en tu cartera. "
            "Pedile al usuario que verifique el nombre o te dé el RUC."
        ),
    }
